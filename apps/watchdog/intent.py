"""Write-ahead entry intent — §7.3.

Publishes an intent key to Redis *before* order placement so the watchdog
can detect orphaned/partial entries. TTL 60s prevents stale keys.
"""
from __future__ import annotations

import json
import logging

import redis

from django.conf import settings

logger = logging.getLogger(__name__)

_INTENT_TTL = 60  # seconds


def _redis():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(strategy_id: int, symbol: str) -> str:
    return f"intent:entry:{strategy_id}:{symbol}"


def publish_entry_intent(
    strategy_id: int,
    symbol: str,
    side: str,
    qty: float,
    expected_sl_price: float,
) -> None:
    """Write an intent dict to Redis with a 60s TTL."""
    r = _redis()
    data = json.dumps({
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "expected_sl_price": expected_sl_price,
    })
    r.set(_key(strategy_id, symbol), data, ex=_INTENT_TTL)
    logger.info("intent published: strategy=%s symbol=%s side=%s", strategy_id, symbol, side)


def confirm_intent(strategy_id: int, symbol: str) -> None:
    """Delete the intent key (order placed + SL confirmed, or intent consumed on failure)."""
    r = _redis()
    deleted = r.delete(_key(strategy_id, symbol))
    if deleted:
        logger.info("intent confirmed: strategy=%s symbol=%s", strategy_id, symbol)


def read_intent(strategy_id: int, symbol: str) -> dict | None:
    """Read the intent dict, or None if absent/expired."""
    r = _redis()
    raw = r.get(_key(strategy_id, symbol))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
