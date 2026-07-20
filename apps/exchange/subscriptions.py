"""Redis-backed subscription registry for live market data feeds."""
from __future__ import annotations

import redis
from django.conf import settings


def _client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _subs_key(network: str, coin: str, interval: str) -> str:
    return f"market:subs:{network}:{coin}:{interval}"


def _channel_key(network: str, coin: str, interval: str) -> str:
    return f"{network}:{coin}:{interval}"


def register_strategy(strategy_id: int, *, symbol: str, bar: str, network: str) -> None:
    """Register a strategy for candle fan-out on *symbol*/*bar*."""
    from .constants import normalize_coin, normalize_interval

    coin = normalize_coin(symbol)
    interval = normalize_interval(bar)
    r = _client()
    ck = _channel_key(network, coin, interval)
    r.sadd(_subs_key(network, coin, interval), str(strategy_id))
    r.sadd("market:channels", ck)


def unregister_strategy(strategy_id: int, *, symbol: str, bar: str, network: str) -> None:
    """Remove a strategy from the subscription registry."""
    from .constants import normalize_coin, normalize_interval

    coin = normalize_coin(symbol)
    interval = normalize_interval(bar)
    r = _client()
    sk = _subs_key(network, coin, interval)
    r.srem(sk, str(strategy_id))
    if r.scard(sk) == 0:
        r.delete(sk)
        r.srem("market:channels", _channel_key(network, coin, interval))


def list_channels() -> list[tuple[str, str, str]]:
    """Return active (network, coin, interval) triples."""
    r = _client()
    out = []
    for ck in r.smembers("market:channels"):
        parts = ck.split(":", 2)
        if len(parts) == 3:
            out.append((parts[0], parts[1], parts[2]))
    return out


def strategies_for(network: str, coin: str, interval: str) -> list[int]:
    """Return strategy IDs subscribed to a channel."""
    r = _client()
    return [int(x) for x in r.smembers(_subs_key(network, coin, interval))]
