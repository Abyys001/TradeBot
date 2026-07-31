"""Materialization policy — §3.2: what to persist vs derive on read.

Three tiers:
- **HOT**: in-memory only, on Node B (1s, 5s, 15s, 30s — transient).
- **BASE**: materialized Parquet (1m, 1h, 1d — authoritative cache).
- **DERIVED**: computed on read from nearest dividing base, LRU-cached.
- **OPT_IN**: materialized only if a strategy with this TF is live (1s at sub-minute).

This module is the source of truth for which TFs get written to disk and which
are computed on-the-fly. The resampler (Node C) and candle_store consult this
to decide their write path.
"""
from __future__ import annotations

from enum import Enum

from .timeframes import FIXED_MS, CALENDAR


class MaterializationTier(Enum):
    """§3.2: Materialization strategy for a timeframe."""
    HOT = "hot"            # in-memory only, on Node B — never persisted
    BASE = "base"          # materialized Parquet — the authoritative cache
    DERIVED = "derived"    # computed on read, LRU-cached
    OPT_IN = "opt_in"      # materialized only if a live strategy uses this TF


# Fixed TFs: base tiers (1m, 1h, 1d) are materialized; everything else derives.
# Calendar TFs: always derived from 1d (§0.3 — separate resampler path).
_TIER_MAP: dict[str, MaterializationTier] = {}

# Fixed TFs
_FIXED_TIERS: dict[str, MaterializationTier] = {
    "1s": MaterializationTier.OPT_IN,
    "5s": MaterializationTier.HOT,
    "15s": MaterializationTier.HOT,
    "30s": MaterializationTier.HOT,
    "1m": MaterializationTier.BASE,
    "3m": MaterializationTier.DERIVED,
    "5m": MaterializationTier.DERIVED,
    "15m": MaterializationTier.DERIVED,
    "30m": MaterializationTier.DERIVED,
    "1h": MaterializationTier.BASE,
    "2h": MaterializationTier.DERIVED,
    "3h": MaterializationTier.DERIVED,
    "4h": MaterializationTier.DERIVED,
    "8h": MaterializationTier.DERIVED,
    "6h": MaterializationTier.DERIVED,
    "12h": MaterializationTier.DERIVED,
    "1d": MaterializationTier.BASE,
    "3d": MaterializationTier.DERIVED,
}

# Calendar TFs
_CALENDAR_TIERS: dict[str, MaterializationTier] = {
    "1w": MaterializationTier.DERIVED,
    "1M": MaterializationTier.DERIVED,
    "3M": MaterializationTier.DERIVED,
    "6M": MaterializationTier.DERIVED,
    "1y": MaterializationTier.DERIVED,
}

_TIER_MAP.update(_FIXED_TIERS)
_TIER_MAP.update(_CALENDAR_TIERS)


def tier_for(tf: str) -> MaterializationTier:
    """Return the materialization tier for a timeframe."""
    return _TIER_MAP.get(tf, MaterializationTier.DERIVED)


def is_materialized(tf: str) -> bool:
    """True if this TF is written to Parquet (BASE or OPT_IN)."""
    t = tier_for(tf)
    return t in (MaterializationTier.BASE, MaterializationTier.OPT_IN)


def is_derived(tf: str) -> bool:
    """True if this TF is computed on read from a base TF."""
    return tier_for(tf) == MaterializationTier.DERIVED


def is_hot(tf: str) -> bool:
    """True if this TF lives only in memory on Node B."""
    return tier_for(tf) == MaterializationTier.HOT


def needs_persistence(tf: str) -> bool:
    """True if the resampler should write this TF to Parquet + PG."""
    t = tier_for(tf)
    return t in (MaterializationTier.BASE, MaterializationTier.OPT_IN)


def derivation_chain(tf: str) -> list[str]:
    """Return the chain of base TFs needed to derive this TF.

    For example, ``derivation_chain("4h")`` returns ``["1h"]`` because 4h is
    derived from 1h bars. Calendar TFs derive from 1d.
    """
    from .timeframes import divides, BASE_TIMEFRAMES, FIXED_MS

    if tf in CALENDAR:
        return ["1d"]

    # Fixed TF: find the largest base that divides it.
    candidates = [b for b in BASE_TIMEFRAMES if divides(b, tf)]
    if candidates:
        return [max(candidates, key=lambda b: FIXED_MS[b])]
    return ["1m"]  # fallback
