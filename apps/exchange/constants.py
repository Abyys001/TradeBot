"""Shared exchange constants and utility functions.

Extracted from hl_constants.py — provides normalize_coin, normalize_interval,
BAR_MAP, and other utilities used across the codebase.
"""
from __future__ import annotations

# Interval string → milliseconds mapping
INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

# Bar interval aliases → canonical interval strings
BAR_MAP: dict[str, str] = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    # Aliases
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1s": "1m",  # Sub-minute not supported, map to 1m
}

# Hyperliquid fee constants
HL_MAKER_FEE = 0.0002
HL_TAKER_FEE = 0.0005


def normalize_coin(coin: str) -> str:
    """Normalize coin symbol to uppercase with underscore separator."""
    return coin.strip().upper().replace("-", "_").replace("/", "_")


def normalize_interval(interval: str) -> str:
    """Normalize interval string to canonical form."""
    interval = interval.strip()
    return BAR_MAP.get(interval, interval)


def candle_channel(network: str, coin: str, interval: str) -> str:
    """Generate Redis Pub/Sub channel name for closed candles."""
    return f"hl:candles:{network}:{coin}:{interval}"


def network_url(network: str = "mainnet") -> str:
    """Return API URL for the given network."""
    if network == "testnet":
        return "https://api.hyperliquid-testnet.xyz"
    return "https://api.hyperliquid.xyz"
