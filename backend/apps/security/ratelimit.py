"""Counting failures in the cache, and nowhere near the money path.

Two counters, both optional, both cache-only:

* the sign-in limiter, which turns a run of wrong passwords into a wait;
* the admin-write limiter, which caps how fast the settings, ledger and
  account endpoints can be written.

The order-routing endpoints are **deliberately excluded** from the second one.
A limiter in front of "close this position" is a control that can cost money
during exactly the minute it matters most, and the thing it would defend
against — an attacker who already holds a staff session — is not stopped by
being asked to wait.

Cache-only because the counters are worthless the moment they are slow: a
window that survives a restart is not worth a table.
"""

from __future__ import annotations

from django.core.cache import cache

_PREFIX = "security:rl"


def _keys(bucket: str) -> tuple[str, str]:
    return f"{_PREFIX}:n:{bucket}", f"{_PREFIX}:lock:{bucket}"


def locked_for(bucket: str) -> int:
    """Seconds left on this bucket's cooling-off period, or 0."""
    _, lock_key = _keys(bucket)
    remaining = cache.get(lock_key)
    return int(remaining) if remaining else 0


def register_failure(bucket: str, *, limit: int, window: int, lockout: int) -> int:
    """Count one failure. Returns the lock-out in seconds if this one tripped it."""
    count_key, lock_key = _keys(bucket)
    # ``add`` then ``incr``: ``incr`` on a missing key raises, and ``add`` is
    # the atomic way to create it with the window's TTL attached.
    if not cache.add(count_key, 1, window):
        try:
            count = cache.incr(count_key)
        except ValueError:  # expired between the add and the incr
            cache.set(count_key, 1, window)
            count = 1
    else:
        count = 1

    if count >= limit:
        cache.set(lock_key, lockout, lockout)
        cache.delete(count_key)
        return lockout
    return 0


def clear(bucket: str) -> None:
    """Forget a bucket — called on a successful sign-in."""
    for key in _keys(bucket):
        cache.delete(key)


def over_rate(bucket: str, *, per_minute: int) -> bool:
    """Fixed one-minute window. True when this request is one too many."""
    key = f"{_PREFIX}:m:{bucket}"
    if not cache.add(key, 1, 60):
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, 60)
            count = 1
    else:
        count = 1
    return count > per_minute
