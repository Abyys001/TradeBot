"""Tests for execution mutex — §1 invariant 8 (mocked Redis)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from apps.exchange.execution_mutex import ExecutionMutex


class ExecutionMutexUnitTests(SimpleTestCase):
    def test_owner_generated(self):
        m = ExecutionMutex("BTC_USDT")
        self.assertEqual(m.symbol, "BTC_USDT")
        self.assertIn("pid-", m.owner)

    def test_lock_key_format(self):
        m = ExecutionMutex("ETH_USDT")
        self.assertEqual(m._lock_key, "lock:order:ETH_USDT")

    def test_symbol_uppercased(self):
        m = ExecutionMutex("eth_usdt")
        self.assertEqual(m.symbol, "ETH_USDT")

    @patch("apps.exchange.execution_mutex.aioredis")
    def test_acquire_success(self, mock_redis):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_redis.from_url.return_value = mock_client

        m = ExecutionMutex("BTC_USDT", redis_url="redis://localhost:6379/0")
        result = asyncio.get_event_loop().run_until_complete(m.acquire(retry=False))

        self.assertTrue(result)
        self.assertTrue(m._acquired)
        mock_client.set.assert_awaited_once()

    @patch("apps.exchange.execution_mutex.aioredis")
    def test_acquire_fail(self, mock_redis):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=False)
        mock_redis.from_url.return_value = mock_client

        m = ExecutionMutex("BTC_USDT", redis_url="redis://localhost:6379/0")
        result = asyncio.get_event_loop().run_until_complete(m.acquire(retry=False))

        self.assertFalse(result)
        self.assertFalse(m._acquired)

    @patch("apps.exchange.execution_mutex.aioredis")
    def test_release_cas(self, mock_redis):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.eval = AsyncMock(return_value=1)
        mock_redis.from_url.return_value = mock_client

        m = ExecutionMutex("BTC_USDT", redis_url="redis://localhost:6379/0")
        asyncio.get_event_loop().run_until_complete(m.acquire(retry=False))
        asyncio.get_event_loop().run_until_complete(m.release())

        self.assertFalse(m._acquired)
        mock_client.eval.assert_awaited_once()

    def test_release_not_acquired(self):
        m = ExecutionMutex("BTC_USDT")
        result = asyncio.get_event_loop().run_until_complete(m.release())
        self.assertFalse(result)

    @patch("apps.exchange.execution_mutex.aioredis")
    def test_extend(self, mock_redis):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.eval = AsyncMock(return_value=1)
        mock_redis.from_url.return_value = mock_client

        m = ExecutionMutex("BTC_USDT", redis_url="redis://localhost:6379/0")
        asyncio.get_event_loop().run_until_complete(m.acquire(retry=False))
        result = asyncio.get_event_loop().run_until_complete(m.extend(60))

        self.assertTrue(result)

    @patch("apps.exchange.execution_mutex.aioredis")
    def test_context_manager(self, mock_redis):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.eval = AsyncMock(return_value=1)
        mock_redis.from_url.return_value = mock_client

        m = ExecutionMutex("BTC_USDT", redis_url="redis://localhost:6379/0")

        async def ctx():
            async with m as lock:
                self.assertTrue(lock._acquired)
            self.assertFalse(m._acquired)

        asyncio.get_event_loop().run_until_complete(ctx())

    @patch("apps.exchange.execution_mutex.aioredis")
    def test_context_manager_timeout(self, mock_redis):
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=False)
        mock_redis.from_url.return_value = mock_client

        m = ExecutionMutex("BTC_USDT", redis_url="redis://localhost:6379/0")

        async def ctx():
            with self.assertRaises(TimeoutError):
                async with m:
                    pass

        asyncio.get_event_loop().run_until_complete(ctx())
