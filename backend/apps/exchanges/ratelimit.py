"""Per-account rate limiting.

Spec §2 demands that one account's rate limit never affects another. Every
limiter instance belongs to exactly one adapter instance, which belongs to
exactly one connected account — there is no shared/global bucket anywhere, and
adding one would break the isolation guarantee.
"""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """Simple async token bucket. One per account, never shared."""

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate  # tokens per second
        self._capacity = burst
        self._tokens = float(burst)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1, *, timeout: float | None = None) -> bool:
        """Take tokens, waiting if needed. False when it would exceed ``timeout``.

        Returning False rather than sleeping past the deadline matters: the
        fan-out has a 1-second budget, and a leg that can't be sent in time must
        fail fast so the admin sees a notification, not silently queue.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._updated) * self._rate
                )
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                shortfall = tokens - self._tokens
                wait = shortfall / self._rate if self._rate > 0 else float("inf")

            if deadline is not None and time.monotonic() + wait > deadline:
                return False
            await asyncio.sleep(min(wait, 0.25))
