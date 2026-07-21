"""Per-symbol execution mutex — §1 invariant 8.

One in-flight order per symbol. Uses Redis lock with TTL to prevent deadlocks.
Acquire before order, release on fill/cancel/timeout.

Usage::

    async with ExecutionMutex(symbol="BTC_USDT") as lock:
        await lock.place_order(...)
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from django.conf import settings

logger = logging.getLogger(__name__)

# Default TTL: 30 seconds. If an order takes longer than this, something is wrong.
_DEFAULT_LOCK_TTL = 30
# Default retry delay: 100ms between acquisition attempts.
_DEFAULT_RETRY_DELAY = 0.1
# Max retry attempts: 50 (5 seconds total at 100ms delay).
_DEFAULT_MAX_RETRIES = 50


class ExecutionMutex:
    """Per-symbol mutex for order execution.

    Uses Redis SET NX EX for distributed locking. The lock key is
    ``lock:order:{symbol}`` and includes the owner ID to prevent
    one process from releasing another's lock.
    """

    def __init__(
        self,
        symbol: str,
        *,
        owner: str | None = None,
        ttl: int = _DEFAULT_LOCK_TTL,
        redis_url: str | None = None,
    ):
        self.symbol = symbol.upper()
        self.owner = owner or f"pid-{__import__('os').getpid()}-{int(time.time())}"
        self.ttl = ttl
        self._redis_url = redis_url or settings.REDIS_URL
        self._client: aioredis.Redis | None = None
        self._lock_key = f"lock:order:{self.symbol}"
        self._acquired = False

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def acquire(self, *, retry: bool = True, max_retries: int = _DEFAULT_MAX_RETRIES) -> bool:
        """Acquire the mutex. Returns True if acquired, False if timeout."""
        client = await self._get_client()
        attempt = 0
        while attempt <= max_retries:
            acquired = await client.set(
                self._lock_key,
                self.owner,
                nx=True,
                ex=self.ttl,
            )
            if acquired:
                self._acquired = True
                return True
            if not retry:
                return False
            attempt += 1
            await __import__("asyncio").sleep(_DEFAULT_RETRY_DELAY)
        logger.warning("mutex acquire timeout: %s after %d attempts", self.symbol, attempt)
        return False

    async def release(self) -> bool:
        """Release the mutex. Only releases if we own it (Lua CAS)."""
        if not self._acquired:
            return False
        client = await self._get_client()
        # Lua script: compare-and-swap release (only release if owner matches)
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await client.eval(script, 1, self._lock_key, self.owner)
        self._acquired = False
        return bool(result)

    async def extend(self, additional_ttl: int | None = None) -> bool:
        """Extend the lock TTL (useful for long-running orders)."""
        if not self._acquired:
            return False
        client = await self._get_client()
        ttl = additional_ttl or self.ttl
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await client.eval(script, 1, self._lock_key, self.owner, str(ttl))
        return bool(result)

    async def is_locked(self) -> tuple[bool, str | None]:
        """Check if the mutex is locked. Returns (is_locked, owner)."""
        client = await self._get_client()
        owner = await client.get(self._lock_key)
        return owner is not None, owner

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        acquired = await self.acquire()
        if not acquired:
            raise TimeoutError(f"could not acquire mutex for {self.symbol} within timeout")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()
        await self.close()
        return False


def sync_mutex(symbol: str, **kwargs) -> ExecutionMutex:
    """Create a mutex for synchronous usage (e.g., in Celery tasks)."""
    return ExecutionMutex(symbol, **kwargs)


class SyncMutexContext:
    """Synchronous context-manager wrapper around ExecutionMutex."""

    def __init__(self, symbol: str, ttl: int = _DEFAULT_LOCK_TTL):
        self.symbol = symbol
        self.ttl = ttl
        self._mutex: ExecutionMutex | None = None

    def __enter__(self):
        self._mutex = ExecutionMutex(self.symbol, ttl=self.ttl)
        result = [False]

        def _acquire():
            loop = asyncio.new_event_loop()
            try:
                result[0] = loop.run_until_complete(self._mutex.acquire(retry=False))
            finally:
                loop.close()

        t = threading.Thread(target=_acquire, daemon=True)
        t.start()
        t.join(timeout=5)
        if not result[0]:
            raise TimeoutError(f"mutex timeout for {self.symbol}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._mutex and self._mutex._acquired:

            def _release():
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._mutex.release())
                finally:
                    loop.close()

            t = threading.Thread(target=_release, daemon=True)
            t.start()
            t.join(timeout=3)
        return False


def sync_lock_order(symbol: str, ttl: int = _DEFAULT_LOCK_TTL) -> SyncMutexContext:
    """Return a synchronous context-manager that acquires/releases the mutex."""
    return SyncMutexContext(symbol, ttl=ttl)
