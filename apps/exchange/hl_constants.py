"""Hyperliquid network URLs, intervals, and symbol helpers."""
from __future__ import annotations

from django.conf import settings

# User-facing bar labels -> Hyperliquid candle interval strings.
BAR_MAP: dict[str, str] = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1H": "1h",
    "2h": "2h",
    "4h": "4h",
    "4H": "4h",
    "6h": "6h",
    "12h": "12h",
    "1d": "1d",
    "1D": "1d",
    "1w": "1w",
    "1W": "1w",
}

NETWORK_CHOICES = ("mainnet", "testnet")

# Hyperliquid perpetuals fee schedule (decimal fractions).
HL_MAKER_FEE: float = 0.0002   # 0.02% maker rebate
HL_TAKER_FEE: float = 0.0005   # 0.05% taker fee (default for backtest fills)


def normalize_interval(bar: str) -> str:
    """Map user bar label to HL interval."""
    key = BAR_MAP.get(bar) or BAR_MAP.get(bar.lower()) or bar.lower()
    if key not in set(BAR_MAP.values()):
        raise ValueError(f"unsupported timeframe: {bar!r}")
    return key


def normalize_coin(symbol: str) -> str:
    """Normalize strategy symbol to HL coin (strip legacy OKX pair suffix)."""
    s = symbol.strip().upper()
    if "-" in s:
        s = s.split("-")[0]
    if "/" in s:
        s = s.split("/")[0]
    return s


def network_url(network: str) -> str:
    """Return HL API URL for *network*."""
    override = getattr(settings, "HL_API_URL", "") or ""
    if override:
        return override
    from hyperliquid.utils import constants

    if network == "testnet":
        return constants.TESTNET_API_URL
    return constants.MAINNET_API_URL


def candle_channel(network: str, coin: str, interval: str) -> str:
    prefix = getattr(settings, "HL_CANDLE_CHANNEL_PREFIX", "hl:candles")
    return f"{prefix}:{network}:{normalize_coin(coin)}:{normalize_interval(interval)}"
