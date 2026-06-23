"""Rate limiting, retry, and nonce locking for Hyperliquid signed actions."""
from __future__ import annotations

import logging
import time
from collections import deque
from contextlib import contextmanager
from functools import wraps
from typing import Callable, TypeVar

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_IP_WEIGHT_LIMIT = 1200
_IP_WINDOW_SEC = 60


class _TokenBucket:
    def __init__(self, capacity: int, window_sec: float):
        self.capacity = capacity
        self.window_sec = window_sec
        self.events: deque[float] = deque()

    def acquire(self, weight: int = 1) -> bool:
        now = time.monotonic()
        while self.events and now - self.events[0] > self.window_sec:
            self.events.popleft()
        if len(self.events) + weight > self.capacity:
            return False
        for _ in range(weight):
            self.events.append(now)
        return True

    def wait(self, weight: int = 1) -> None:
        while not self.acquire(weight):
            time.sleep(0.05)


_ip_bucket = _TokenBucket(_IP_WEIGHT_LIMIT, _IP_WINDOW_SEC)


def _redis():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


@contextmanager
def nonce_lock(credential_id: int, ttl: int = 10):
    """Redis lock around signed exchange actions for one credential."""
    key = f"hl:nonce:{credential_id}"
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


def with_rate_limit(weight: int = 1, max_retries: int = 3):
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
                    msg = str(exc).lower()
                    if "429" in msg or "rate" in msg or "limit" in msg:
                        last_exc = exc
                        time.sleep(min(2**attempt, 8))
                        continue
                    raise
            if last_exc:
                raise last_exc
            raise RuntimeError("rate limit retries exhausted")

        return wrapper

    return decorator


def signed_action(credential, fn: Callable[[], T], *, weight: int = 1) -> T:
    """Run a signed HL action under nonce lock + rate limit."""

    @with_rate_limit(weight=weight)
    def _run():
        return fn()

    with nonce_lock(credential.pk):
        return _run()
