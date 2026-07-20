"""Tests for position guardian — §6.6."""
from django.test import SimpleTestCase
from unittest.mock import MagicMock

from apps.watchdog.guardian import check_position, GuardianCheck


class GuardianCheckTests(SimpleTestCase):
    def _mock_client(self, position=None, error=None):
        client = MagicMock()
        if error:
            client.get_position.side_effect = error
        else:
            client.get_position.return_value = position
        return client

    def test_no_position_no_expected(self):
        client = self._mock_client(position=None)
        result = check_position(
            exchange_client=client, symbol="BTC_USDT",
            expected_has_sl=False, sl_confirmed=False,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.position.side, "NONE")

    def test_position_gone_but_sl_expected(self):
        client = self._mock_client(position=None)
        result = check_position(
            exchange_client=client, symbol="BTC_USDT",
            expected_has_sl=True, sl_confirmed=True,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.action_needed, "reconcile")

    def test_api_error(self):
        client = self._mock_client(error=ConnectionError("timeout"))
        result = check_position(
            exchange_client=client, symbol="BTC_USDT",
            expected_has_sl=False, sl_confirmed=False,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.action_needed, "retry")

    def test_position_with_sl(self):
        pos = {
            "positionAmt": "0.1",
            "entryPrice": "50000",
            "stopLossPrice": "49000",
            "unRealizedProfit": "10.5",
        }
        client = self._mock_client(position=pos)
        result = check_position(
            exchange_client=client, symbol="BTC_USDT",
            expected_has_sl=True, sl_confirmed=True,
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.position.has_sl)
        self.assertEqual(result.position.side, "LONG")

    def test_position_missing_sl(self):
        pos = {
            "positionAmt": "0.05",
            "entryPrice": "3000",
            "stopLossPrice": None,
            "unRealizedProfit": "-2.0",
        }
        client = self._mock_client(position=pos)
        result = check_position(
            exchange_client=client, symbol="ETH_USDT",
            expected_has_sl=True, sl_confirmed=False,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.action_needed, "attach_sl")
        self.assertEqual(result.position.side, "LONG")

    def test_short_position(self):
        pos = {
            "positionAmt": "-0.5",
            "entryPrice": "2000",
            "stopLossPrice": "2100",
            "unRealizedProfit": "50",
        }
        client = self._mock_client(position=pos)
        result = check_position(
            exchange_client=client, symbol="ETH_USDT",
            expected_has_sl=True, sl_confirmed=True,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.position.side, "SHORT")
        self.assertEqual(result.position.size, 0.5)
