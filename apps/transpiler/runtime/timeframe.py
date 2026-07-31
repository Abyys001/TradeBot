"""Chart timeframe helpers for Pine `timeframe.*` and `request.security`.

Semantics follow the Pine v5 spec, not this repo's internal interval strings:

- ``timeframe.period`` is the TradingView resolution string: minutes as a bare
  number (``"60"`` for 1h), seconds suffixed ``S``, and ``D``/``W``/``M`` for the
  calendar family.
- ``timeframe.multiplier`` is the leading number of that string (``60`` for 1h,
  ``1`` for ``"D"``, ``3`` for ``"3D"``).
- A ``request.security`` resolution of ``"180"`` means **180 minutes**, never
  "180 chart bars".

The timeframe ladder comes from ``apps.exchange.timeframes`` (the Master Plan
§3.2 ladder), not the legacy ``INTERVAL_MS`` map, so 2h/6h/12h/3d and the
sub-minute tiers all resolve.
"""
from __future__ import annotations

from apps.exchange.constants import normalize_interval
from apps.exchange.timeframes import FIXED_MS

from ..exceptions import PineSemanticError

_MIN_MS = 60_000

# Canonical interval -> Pine resolution string. Anything absent is derived from
# its millisecond length.
_PERIOD_MAP = {
    "1s": "1S", "5s": "5S", "15s": "15S", "30s": "30S",
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "3h": "180", "4h": "240",
    "6h": "360", "8h": "480", "12h": "720",
    "1d": "D", "3d": "3D",
    "1w": "W", "1M": "M", "3M": "3M", "6M": "6M", "1y": "12M",
}


def chart_bar_ms(interval: str) -> int:
    """Milliseconds per bar for the chart interval."""
    iv = normalize_interval(interval)
    ms = FIXED_MS.get(iv)
    if ms is None:
        ms = FIXED_MS.get(str(interval).strip())
    return int(ms) if ms else _MIN_MS


def chart_bar_minutes(interval: str) -> int:
    """Minutes per bar for the chart interval (floor 1 for sub-minute charts)."""
    return max(chart_bar_ms(interval) // _MIN_MS, 1)


def pine_period(interval: str) -> str:
    """`timeframe.period` — the TradingView resolution string."""
    iv = normalize_interval(interval)
    period = _PERIOD_MAP.get(iv) or _PERIOD_MAP.get(str(interval).strip())
    if period is not None:
        return period
    ms = chart_bar_ms(iv)
    if ms % (24 * 60 * _MIN_MS) == 0:
        days = ms // (24 * 60 * _MIN_MS)
        return "D" if days == 1 else f"{days}D"
    if ms < _MIN_MS:
        return f"{max(ms // 1000, 1)}S"
    return str(ms // _MIN_MS)


def pine_multiplier(interval: str) -> int:
    """`timeframe.multiplier` — the leading number of `timeframe.period`.

    1h -> 60 (period "60"), 5m -> 5, 1d -> 1 (period "D"), 3d -> 3 (period "3D").
    """
    lead = ""
    for ch in pine_period(interval):
        if not ch.isdigit():
            break
        lead += ch
    return int(lead) if lead else 1


def resolve_security_minutes(chart_interval: str, tf_str: str) -> int:
    """Resolve a `request.security` resolution string to minutes (Pine semantics).

    Raises ``PineSemanticError`` when the string cannot be resolved — a silent
    fallback to the chart timeframe would turn a broken multi-timeframe strategy
    into a plausible-looking single-timeframe one.
    """
    s = str(tf_str).strip().upper()
    if not s or s == "NAN":
        raise PineSemanticError(
            f"request.security resolution is not a resolvable timeframe: {tf_str!r}"
        )
    # Empty string means "chart timeframe" in Pine.
    if s in ("", '""'):
        return chart_bar_minutes(chart_interval)
    if s.isdigit():  # bare number == minutes
        return int(s)
    if s.endswith("S") and s[:-1].isdigit():  # seconds -> floor to 1 minute
        return max(int(s[:-1]) // 60, 1)
    if s.endswith("D") and (s[:-1].isdigit() or s[:-1] == ""):
        return (int(s[:-1]) if s[:-1] else 1) * 24 * 60
    if s.endswith("W") and (s[:-1].isdigit() or s[:-1] == ""):
        return (int(s[:-1]) if s[:-1] else 1) * 7 * 24 * 60
    if s.endswith("M") and (s[:-1].isdigit() or s[:-1] == ""):
        # Calendar months are variable-length; the resampler has a separate path
        # for them (§0.3) and the security evaluator only handles fixed TFs.
        raise PineSemanticError(
            f"calendar timeframes are not supported by request.security: {tf_str!r}"
        )
    lowered = str(tf_str).strip()
    if normalize_interval(lowered) in FIXED_MS or lowered in FIXED_MS:
        return max(chart_bar_ms(lowered) // _MIN_MS, 1)
    raise PineSemanticError(
        f"request.security resolution is not a resolvable timeframe: {tf_str!r}"
    )


def minutes_to_interval(minutes: int) -> str:
    """Nearest canonical interval string for a minute count (for HTF lookups)."""
    target_ms = int(minutes) * _MIN_MS
    for name, ms in FIXED_MS.items():
        if ms == target_ms:
            return name
    raise PineSemanticError(f"no canonical timeframe for {minutes} minutes")
