"""Hyperliquid asset metadata: sizing, pricing, and notional validation."""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass

import redis
from django.conf import settings

from .hl_constants import network_url, normalize_coin

logger = logging.getLogger(__name__)

MIN_NOTIONAL_USD = 10.0


@dataclass
class AssetMeta:
    name: str
    sz_decimals: int
    is_spot: bool


def _redis():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _cache_key(network: str, market: str) -> str:
    return f"hl:meta:{network}:{market}"


def _load_meta(network: str) -> dict:
    ttl = getattr(settings, "HL_META_CACHE_TTL", 300)
    key = _cache_key(network, "perp")
    r = _redis()
    cached = r.get(key)
    if cached:
        return json.loads(cached)

    from hyperliquid.info import Info

    info = Info(network_url(network), skip_ws=True, timeout=5)
    meta = info.meta()
    spot_meta = info.spot_meta()
    payload = {"perp": meta, "spot": spot_meta, "name_to_coin": info.name_to_coin}
    r.setex(key, ttl, json.dumps(payload))
    return payload


def resolve_trading_name(coin: str, *, market_type: str, network: str) -> str:
    """Resolve strategy symbol to HL `name` for perp or spot."""
    base = normalize_coin(coin)
    data = _load_meta(network)
    name_to_coin = data.get("name_to_coin") or {}

    if market_type == "spot":
        for candidate in (f"{base}/USDC", base):
            if candidate in name_to_coin:
                return candidate
        spot = data.get("spot") or {}
        for item in spot.get("universe") or []:
            name = item.get("name", "")
            if name.startswith(base) or base in name:
                return name
        raise ValueError(f"no spot market for {base!r} on {network}")

    if base in name_to_coin:
        return base
    raise ValueError(f"no perp market for {base!r} on {network}")


def get_asset_meta(name: str, *, market_type: str, network: str) -> AssetMeta:
    data = _load_meta(network)
    if market_type == "spot":
        spot = data.get("spot") or {}
        for item in spot.get("universe") or []:
            if item.get("name") == name:
                tokens = item.get("tokens") or []
                base_idx = tokens[0] if tokens else None
                sz = 8
                for tok in spot.get("tokens") or []:
                    if tok.get("index") == base_idx:
                        sz = int(tok.get("szDecimals", 8))
                        break
                return AssetMeta(name=name, sz_decimals=sz, is_spot=True)
        return AssetMeta(name=name, sz_decimals=8, is_spot=True)

    perp = data.get("perp") or {}
    for item in perp.get("universe") or []:
        if item.get("name") == name:
            return AssetMeta(
                name=name,
                sz_decimals=int(item.get("szDecimals", 4)),
                is_spot=False,
            )
    return AssetMeta(name=name, sz_decimals=4, is_spot=False)


def round_size(sz: float, meta: AssetMeta) -> float:
    factor = 10**meta.sz_decimals
    return math.floor(sz * factor) / factor


def round_price(px: float, meta: AssetMeta) -> float:
    decimals = 8 if meta.is_spot else 6
    return round(float(f"{px:.5g}"), decimals - meta.sz_decimals)


def validate_min_notional(sz: float, px: float, *, min_usd: float = MIN_NOTIONAL_USD) -> str | None:
    if sz <= 0:
        return "size must be positive"
    if px <= 0:
        return "price must be positive"
    if sz * px < min_usd:
        return f"notional ${sz * px:.2f} below minimum ${min_usd:.0f}"
    return None


def aggressive_spot_price(
    coin: str,
    *,
    is_buy: bool,
    network: str,
    slippage: float = 0.01,
) -> float:
    """Fetch mid price and apply slippage for IOC spot market semantics."""
    from hyperliquid.info import Info

    info = Info(network_url(network), skip_ws=True, timeout=5)
    name = resolve_trading_name(coin, market_type="spot", network=network)
    mids = info.all_mids() or {}
    mid_key = info.name_to_coin.get(name, name)
    mid = mids.get(mid_key) or mids.get(name)
    if mid is None:
        for k, v in mids.items():
            if normalize_coin(k) == normalize_coin(coin):
                mid = v
                break
    if mid is None:
        raise ValueError(f"no mid price for {coin!r}")
    px = float(mid)
    return px * (1 + slippage) if is_buy else px * (1 - slippage)
