"""The emergency halt (spec §7).

Two independent sources, OR'd together:

  ``STOP_ALL=true`` in the environment
      A deployment-level halt. Pinned on — the API refuses to clear it, because
      a halt someone deployed must not be undoable from a browser session.

  the ``KillSwitch`` row
      The runtime halt the admin flips from the panel. This is the one spec §7
      asks for: "immediately halts new order routing platform-wide".

Reads go through the cache so the routing path costs a cache hit rather than a
query, and so every worker process sees a flip immediately when the cache is
Redis. All of these functions are **synchronous** and must be called from async
code via ``sync_to_async``; doing DB or Redis I/O directly on the event loop is
what the fan-out deadline cannot afford.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_KEY = "trading:stop_all"
CACHE_TTL = 300


def env_pinned() -> bool:
    """True when the environment pins the halt on. Not clearable via the API."""
    return bool(settings.TRADING["STOP_ALL"])


def _row():
    from apps.trading.models import KillSwitch

    row, _ = KillSwitch.objects.get_or_create(singleton=1)
    return row


def runtime_on() -> bool:
    """The DB half, cached.

    A database failure resolves to *halted*, not *running*. When the platform
    cannot tell whether the admin pulled the switch, routing other people's
    capital is the wrong side to fail on.
    """
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return bool(cached)
    try:
        value = _row().stop_all
    except DatabaseError:
        logger.exception("kill switch unreadable — treating routing as halted")
        return True
    cache.set(CACHE_KEY, value, CACHE_TTL)
    return bool(value)


def is_on() -> bool:
    return env_pinned() or runtime_on()


def state() -> dict:
    """What the panel shows: the effective value plus why it is what it is."""
    try:
        row = _row()
        runtime, reason, at, by = row.stop_all, row.reason, row.updated_at, row.updated_by
    except DatabaseError:
        runtime, reason, at, by = True, "kill switch row unreadable", timezone.now(), ""
    pinned = env_pinned()
    return {
        "stop_all": pinned or bool(runtime),
        "runtime": bool(runtime),
        # True means the panel must render the control as locked: the halt came
        # from the environment and no API call will clear it.
        "locked": pinned,
        "source": "env" if pinned else ("panel" if runtime else "off"),
        "reason": reason,
        "updated_at": at,
        "updated_by": by,
    }


def set_stop_all(on: bool, *, actor: str = "", reason: str = "") -> dict:
    """Flip the runtime halt. Returns the new state.

    Raises ``PermissionError`` when the environment has pinned it on, so the
    caller answers 409 instead of silently accepting a change it did not make.
    """
    if env_pinned() and not on:
        raise PermissionError("STOP_ALL is pinned on by the environment")

    row = _row()
    row.stop_all = bool(on)
    row.reason = reason[:200]
    row.updated_by = actor[:150]
    row.save(update_fields=["stop_all", "reason", "updated_by", "updated_at"])
    cache.set(CACHE_KEY, row.stop_all, CACHE_TTL)
    logger.warning("STOP_ALL set to %s by %s (%s)", row.stop_all, actor or "?", reason or "-")

    if row.stop_all:
        # Q22, and the most important line of the eight: **the halt stops every
        # running bot.** A halt that flattens positions while a bot is still
        # evaluating is a halt that re-enters ninety seconds later, which is not
        # a halt. Imported here rather than at module scope because the bot
        # supervisor reads this module back.
        from apps.bots.supervisor import stop_all_sync

        stopped = stop_all_sync(
            reason="halt", detail=f"STOP_ALL set by {actor or '?'}: {reason or 'no reason given'}"
        )
        if stopped:
            logger.warning("STOP_ALL also stopped %d running bot(s)", len(stopped))

    return state()
