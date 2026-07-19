"""P7/P8: Execution mutex + mocked-FAPI order lifecycle tests.

Tests the full order lifecycle path through ExecutionMutex → TabdealFuturesClient
with all external calls mocked. Verifies invariant 7 (DELETE close only) and
invariant 8 (one order per symbol at a time).
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from decimal import Decimal

from django.test import SimpleTestCase

from apps.exchange.execution_mutex import ExecutionMutex


class MutexLifecycleTests(SimpleTestCase):
    """P8: Full order lifecycle through mutex — entry → fill → release."""

    def test_entry_fill_release_cycle(self):
        """Acquire → order placed → release simulates the happy path."""
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.eval = AsyncMock(return_value=1)
        mock_client.get = AsyncMock(return_value=None)

        async def cycle():
            m = ExecutionMutex("BTC_USDT", redis_url="redis://localhost:6379/0")
            with patch("apps.exchange.execution_mutex.aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                acquired = await m.acquire(retry=False)
                self.assertTrue(acquired)

                # Simulate order placement happens here...
                # Then release
                released = await m.release()
                self.assertTrue(released)
                self.assertFalse(m._acquired)

        asyncio.get_event_loop().run_until_complete(cycle())

    def test_mutex_blocks_second_order(self):
        """Second acquire attempt fails while first holds the lock."""
        call_count = [0]

        mock_client = AsyncMock()

        async def set_side_effect(key, val, nx=None, ex=None):
            call_count[0] += 1
            return call_count[0] == 1  # First succeeds, second fails

        mock_client.set = AsyncMock(side_effect=set_side_effect)

        async def cycle():
            m1 = ExecutionMutex("BTC_USDT", owner="owner-1", redis_url="redis://localhost:6379/0")
            m2 = ExecutionMutex("BTC_USDT", owner="owner-2", redis_url="redis://localhost:6379/0")

            with patch("apps.exchange.execution_mutex.aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client

                r1 = await m1.acquire(retry=False)
                self.assertTrue(r1)

                r2 = await m2.acquire(retry=False)
                self.assertFalse(r2)  # Blocked by owner-1

                await m1.release()

        asyncio.get_event_loop().run_until_complete(cycle())

    def test_cas_release_prevents_wrong_owner(self):
        """Release returns False if owner doesn't match (Lua CAS)."""
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        # Lua returns 0 → owner doesn't match
        mock_client.eval = AsyncMock(return_value=0)

        async def cycle():
            m = ExecutionMutex("BTC_USDT", owner="correct-owner", redis_url="redis://localhost:6379/0")
            with patch("apps.exchange.execution_mutex.aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                await m.acquire(retry=False)
                result = await m.release()
                self.assertFalse(result)

        asyncio.get_event_loop().run_until_complete(cycle())


class TabdealClosePositionTests(SimpleTestCase):
    """P7: Verify DELETE close is the only close path (invariant 7)."""

    def test_close_position_uses_delete(self):
        """TabdealFuturesClient.close_position uses DELETE /fapi/v1/position."""
        mock_credential = MagicMock()
        mock_credential.get_api_key.return_value = "test-key"
        mock_credential.get_api_secret.return_value = "test-secret"

        with patch("apps.exchange.tabdeal_futures.base_url", return_value="https://fake.api"):
            from apps.exchange.tabdeal_futures import TabdealFuturesClient
            client = TabdealFuturesClient(mock_credential)

            with patch.object(client, "_signed") as mock_signed:
                mock_signed.return_value = {"symbol": "BTC_USDT", "positionAmt": "0"}
                result = client.close_position("BTC_USDT")

                mock_signed.assert_called_once_with(
                    "DELETE", "/fapi/v1/position", {"symbol": "BTC_USDT"}
                )
                self.assertEqual(result["positionAmt"], "0")

    def test_cancel_order_uses_delete(self):
        """cancel_order uses DELETE (invariant 7)."""
        mock_credential = MagicMock()
        mock_credential.get_api_key.return_value = "test-key"
        mock_credential.get_api_secret.return_value = "test-secret"

        with patch("apps.exchange.tabdeal_futures.base_url", return_value="https://fake.api"):
            from apps.exchange.tabdeal_futures import TabdealFuturesClient
            client = TabdealFuturesClient(mock_credential)

            with patch.object(client, "_signed") as mock_signed:
                mock_signed.return_value = {"orderId": 123, "status": "cancelled"}
                client.cancel_order("BTC_USDT", 123)
                mock_signed.assert_called_once_with(
                    "DELETE", "/fapi/v1/order", {"symbol": "BTC_USDT", "orderId": 123}
                )

    def test_place_market_order_uses_post(self):
        """Market orders use POST (invariant 7: no DELETE to open)."""
        mock_credential = MagicMock()
        mock_credential.get_api_key.return_value = "test-key"
        mock_credential.get_api_secret.return_value = "test-secret"

        with patch("apps.exchange.tabdeal_futures.base_url", return_value="https://fake.api"):
            from apps.exchange.tabdeal_futures import TabdealFuturesClient
            client = TabdealFuturesClient(mock_credential)

            with patch.object(client, "_signed") as mock_signed:
                mock_signed.return_value = {"orderId": 456, "status": "filled"}
                result = client.place_market_order(
                    symbol="BTC_USDT", side="BUY", quantity=0.01,
                )
                mock_signed.assert_called_once()
                args = mock_signed.call_args
                self.assertEqual(args[0][0], "POST")
                self.assertEqual(args[0][1], "/fapi/v1/order")


class FullLifecycleIntegrationTests(SimpleTestCase):
    """P8: End-to-end lifecycle — place → monitor → close, all mocked."""

    def test_full_lifecycle(self):
        """Place market entry → check position → SL attach → close via DELETE."""
        mock_credential = MagicMock()
        mock_credential.get_api_key.return_value = "test-key"
        mock_credential.get_api_secret.return_value = "test-secret"

        with patch("apps.exchange.tabdeal_futures.base_url", return_value="https://fake.api"):
            from apps.exchange.tabdeal_futures import TabdealFuturesClient
            client = TabdealFuturesClient(mock_credential)

            with patch.object(client, "_signed") as mock_signed:
                # 1. Place entry
                mock_signed.return_value = {"orderId": 1, "status": "filled"}
                entry = client.place_market_order(symbol="BTC_USDT", side="BUY", quantity=0.01)
                self.assertEqual(entry["status"], "filled")

                # 2. Check position
                mock_signed.return_value = [{
                    "symbol": "BTC_USDT", "positionAmt": "0.01",
                    "entryPrice": "50000", "unRealizedProfit": "5.0",
                }]
                pos = client.get_position("BTC_USDT")
                self.assertIsNotNone(pos)
                self.assertEqual(float(pos["positionAmt"]), 0.01)

                # 3. Attach SL
                mock_signed.return_value = {"positionId": 1, "slPrice": 49500}
                sl = client.set_position_sl_tp(position_id=1, sl_price=49500, symbol="BTC_USDT")
                self.assertEqual(sl["slPrice"], 49500)

                # 4. Close via DELETE (invariant 7)
                mock_signed.return_value = {"symbol": "BTC_USDT", "positionAmt": "0"}
                close = client.close_position("BTC_USDT")
                self.assertEqual(close["positionAmt"], "0")

                # Verify: close uses DELETE, not POST
                close_call = mock_signed.call_args_list[-1]
                self.assertEqual(close_call[0][0], "DELETE")

    def test_rate_limit_retry(self):
        """Error 1216 triggers exponential backoff retry at the _signed level."""
        from apps.exchange.tabdeal_futures import TabdealFuturesClient
        from apps.exchange.tabdeal_errors import TabdealAPIError, TabdealErrorInfo

        mock_credential = MagicMock()
        mock_credential.get_api_key.return_value = "test-key"
        mock_credential.get_api_secret.return_value = "test-secret"

        with patch("apps.exchange.tabdeal_futures.base_url", return_value="https://fake.api"):
            client = TabdealFuturesClient(mock_credential)

            rate_limit_err = TabdealAPIError(TabdealErrorInfo("1216", "rate limited", "wait"))
            ok_response = {"orderId": 1, "status": "filled"}

            # Mock _signed to simulate: first call rate-limited, second succeeds
            # We mock the inner _parse to raise on first call
            call_count = [0]
            original_parse = client._parse

            def side_effect_parse(resp):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise rate_limit_err
                return ok_response

            with patch.object(client, "_parse", side_effect=side_effect_parse):
                with patch("apps.exchange.tabdeal_futures.time.sleep"):
                    # The retry happens inside _signed, but since _signed
                    # directly calls _parse (not through requests), we need
                    # to mock at the requests level instead.
                    # Let's test the retry logic directly.
                    with patch("apps.exchange.tabdeal_futures.requests") as mock_requests:
                        # First request → rate limit (parsed by _parse), second → ok
                        resp1 = MagicMock()
                        resp1.json.return_value = {"code": "1216", "msg": "rate limited"}
                        resp2 = MagicMock()
                        resp2.json.return_value = ok_response
                        mock_requests.request.side_effect = [resp1, resp2]

                        result = client.place_market_order(
                            symbol="BTC_USDT", side="BUY", quantity=0.01,
                        )
                        self.assertEqual(result["status"], "filled")
                        self.assertEqual(mock_requests.request.call_count, 2)
