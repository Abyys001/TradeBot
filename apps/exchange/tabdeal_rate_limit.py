"""Rate limiting, retry, and nonce locking for Tabdeal signed actions.

Mirrors apps/exchange/hl_rate_limit.py's pattern; uses its own Redis key
namespace (tabdeal:nonce:) and IP token bucket so Tabdeal traffic never
shares state with the Hyperliquid client.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from contextlib import contextmanager
from functools import wraps
from typing import Callable, TypeVar

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# UNVERIFIED: placeholder weight/window until Tabdeal's real rate limits are known.
_IP_WEIGHT_LIMIT = 1200
_IP_WINDOW_SEC = 60


class _TokenBucket:
    def __init__(self, capacity: int, window_sec: float):
        self.capacity = capacity
        self.window_sec = window_sec
        self.events: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, weight: int = 1) -> bool:
        now = time.monotonic()
        with self._lock:
            while self.events and now - self.events[0] > self.window_sec:
                self.events.popleft()
            if len(self.events) + weight > self.capacity:
                return False
            for _ in range(weight):
                self.events.append(now)
        return True

    def wait(self, weight: int = 1) -> None:
        while not self.acquire(weight):
            time.sleep(0.1)


_ip_bucket = _TokenBucket(_IP_WEIGHT_LIMIT, _IP_WINDOW_SEC)


def is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many requests" in msg or "rate limit" in msg


def is_transient_error(exc: BaseException) -> bool:
    """True for errors worth retrying: rate limits, timeouts, and connection resets."""
    if is_rate_limit_error(exc):
        return True
    msg = str(exc).lower()
    return any(
        kw in msg
        for kw in (
            "timed out",
            "timeout",
            "connection reset",
            "connection refused",
            "connection aborted",
            "remotedisconnected",
            "broken pipe",
            "eof occurred",
            "ssl",
            "temporarily unavailable",
        )
    )


def sanitize_tabdeal_error(exc: BaseException) -> str:
    """Short, user-facing message for Tabdeal API failures."""
    if is_rate_limit_error(exc):
        return "Tabdeal rate limit (HTTP 429) — too many requests. Wait a minute and retry."
    msg = str(exc).strip()
    if len(msg) > 240:
        return msg[:240] + "…"
    return msg


def _redis():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


@contextmanager
def nonce_lock(credential_id: int, ttl: int = 10):
    """Redis lock around signed Tabdeal actions for one credential."""
    key = f"tabdeal:nonce:{credential_id}"
    r = _redis()
    acquired = r.set(key, "1", nx=True, ex=ttl)
    if not acquired:
        deadline = time.monotonic() + ttl
        while time.monotonic() < deadline:
            if r.set(key, "1", nx=True, ex=ttl):
                acquired = True
                break
            time.sleep(0.02)
    if not acquired:
        raise RuntimeError(f"nonce lock timeout for credential {credential_id}")
    try:
        yield
    finally:
        r.delete(key)


def with_rate_limit(
    weight: int = 1,
    max_retries: int = 3,
    *,
    max_backoff: float = 8.0,
):
    """Decorator: IP token bucket + exponential backoff on rate-limit errors."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(max_retries):
                _ip_bucket.wait(weight)
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    if is_transient_error(exc):
                        last_exc = exc
                        delay = min(2**attempt + random.uniform(0.25, 1.0), max_backoff)
                        kind = "rate-limit" if is_rate_limit_error(exc) else "transient"
                        logger.warning(
                            "Tabdeal %s on %s (attempt %s/%s), sleeping %.1fs: %s",
                            kind,
                            fn.__name__,
                            attempt + 1,
                            max_retries,
                            delay,
                            exc,
                        )
                        time.sleep(delay)
                        continue
                    raise
            if last_exc:
                raise last_exc
            raise RuntimeError("rate limit retries exhausted")

        return wrapper

    return decorator


def signed_action(credential, fn: Callable[[], T], *, weight: int = 1) -> T:
    """Run a signed Tabdeal action under nonce lock + rate limit."""

    @with_rate_limit(weight=weight)
    def _run():
        return fn()

    with nonce_lock(credential.pk):
        return _run()
