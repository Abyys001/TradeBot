"""Chart timeframe helpers for Pine `timeframe.*` and `request.security`."""
from __future__ import annotations

from apps.exchange.constants import INTERVAL_MS, normalize_interval

# Pine-style period string for common HL intervals.
_PERIOD_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
}


def chart_bar_minutes(interval: str) -> int:
    """Minutes per bar for the chart interval."""
    iv = normalize_interval(interval)
    ms = INTERVAL_MS.get(iv, 60_000)
    return max(int(ms // 60_000), 1)


def pine_multiplier(interval: str) -> int:
    """`timeframe.multiplier` — multiplier of the chart's timeframe unit."""
    iv = normalize_interval(interval)
    if iv.endswith("h"):
        return int(iv[:-1]) if iv[:-1].isdigit() else 1
    if iv.endswith("d"):
        return int(iv[:-1]) if iv[:-1].isdigit() else 1
    if iv.endswith("w"):
        return int(iv[:-1]) if iv[:-1].isdigit() else 1
    if iv.endswith("m"):
        return int(iv[:-1]) if iv[:-1].isdigit() else 1
    return 1


def pine_period(interval: str) -> str:
    """`timeframe.period` string."""
    iv = normalize_interval(interval)
    return _PERIOD_MAP.get(iv, str(chart_bar_minutes(iv)))


def resolve_security_minutes(chart_interval: str, tf_str: str) -> int:
    """Resolve `request.security` timeframe string relative to the chart."""
    s = str(tf_str).strip().upper()
    base = chart_bar_minutes(chart_interval)
    if s.isdigit():
        return base * int(s)
    if s.endswith("H") and s[:-1].isdigit():
        return int(s[:-1]) * 60
    if s.endswith("D") and s[:-1].isdigit():
        return int(s[:-1]) * 24 * 60
    if s.endswith("M") and s[:-1].isdigit():
        return int(s[:-1])
    if s in INTERVAL_MS:
        return chart_bar_minutes(s)
    try:
        return int(s)
    except ValueError:
        return base
