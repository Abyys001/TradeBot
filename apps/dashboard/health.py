"""System health probes for the dashboard."""
from __future__ import annotations

import time

from django.core.cache import cache

MARKET_FEED_HEARTBEAT_KEY = "health:market_feed"
MARKET_FEED_STALE_SECONDS = 15


def set_market_feed_heartbeat(*, last_bar_ts: int | None = None) -> None:
    cache.set(
        MARKET_FEED_HEARTBEAT_KEY,
        {"ts": time.time(), "last_bar_ts": last_bar_ts},
        timeout=MARKET_FEED_STALE_SECONDS * 2,
    )


def get_market_feed_status() -> dict:
    data = cache.get(MARKET_FEED_HEARTBEAT_KEY)
    if not data:
        return {"status": "disconnected", "last_bar_ts": None}
    age = time.time() - float(data.get("ts", 0))
    if age > MARKET_FEED_STALE_SECONDS:
        return {"status": "stale", "last_bar_ts": data.get("last_bar_ts")}
    return {"status": "connected", "last_bar_ts": data.get("last_bar_ts")}


def get_celery_status() -> dict:
    try:
        from config.celery import ping

        result = ping.delay().get(timeout=2)
        if result == "pong":
            return {"status": "ok", "workers": 1}
        return {"status": "error", "workers": 0, "detail": str(result)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "workers": 0, "detail": type(exc).__name__}
