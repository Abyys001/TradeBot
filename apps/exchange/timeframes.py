"""Timeframe ladder + anchor rules (Master Plan §3.2, §0.3).

Two families, deliberately separate code paths (§0.3 — don't let one resampler fake both):

- **Fixed** intervals (1s..3d): a constant number of seconds, UTC/epoch-aligned, so they
  bucket and resample exactly.
- **Calendar** intervals (1w, 1M, 3M, 6M, 1y): variable length, need an anchor convention
  (week = Monday 00:00 UTC; month/quarter/half/year = 1st 00:00 UTC). Handled by the
  calendar resampler (P3), not by millisecond bucketing.

``divides`` + ``anchor_of`` enforce the exactness rule: a TF may only be derived from a base
that divides it and shares its anchor.
"""
from __future__ import annotations

_SEC = 1000
_MIN = 60 * _SEC
_HOUR = 60 * _MIN
_DAY = 24 * _HOUR

# Fixed timeframes → milliseconds.
FIXED_MS: dict[str, int] = {
    "1s": 1 * _SEC, "5s": 5 * _SEC, "15s": 15 * _SEC, "30s": 30 * _SEC,
    "1m": 1 * _MIN, "3m": 3 * _MIN, "5m": 5 * _MIN, "15m": 15 * _MIN, "30m": 30 * _MIN,
    "1h": 1 * _HOUR, "2h": 2 * _HOUR, "4h": 4 * _HOUR, "6h": 6 * _HOUR, "12h": 12 * _HOUR,
    "1d": 1 * _DAY, "3d": 3 * _DAY,
}

# Calendar timeframes (variable length — no fixed ms).
CALENDAR = ("1w", "1M", "3M", "6M", "1y")

ALL_TIMEFRAMES = tuple(FIXED_MS.keys()) + CALENDAR

# Materialized base tiers (§3.2): everything else derives from the nearest dividing base.
BASE_TIMEFRAMES = ("1m", "1h", "1d")


def is_fixed(tf: str) -> bool:
    return tf in FIXED_MS


def is_calendar(tf: str) -> bool:
    return tf in CALENDAR


def tf_to_ms(tf: str) -> int:
    """Milliseconds for a fixed timeframe. Raises for calendar TFs (variable length)."""
    try:
        return FIXED_MS[tf]
    except KeyError:
        raise ValueError(f"{tf!r} is not a fixed timeframe (calendar TFs have no fixed ms)")


def divides(base: str, target: str) -> bool:
    """True if ``base`` bars can compose ``target`` bars exactly (fixed family only)."""
    if base not in FIXED_MS or target not in FIXED_MS:
        return False
    return FIXED_MS[target] % FIXED_MS[base] == 0 and FIXED_MS[target] >= FIXED_MS[base]


def nearest_base(target: str) -> str:
    """Largest materialized base that exactly divides ``target`` (fixed family)."""
    candidates = [b for b in BASE_TIMEFRAMES if divides(b, target)]
    if not candidates:
        return "1m"
    return max(candidates, key=lambda b: FIXED_MS[b])
