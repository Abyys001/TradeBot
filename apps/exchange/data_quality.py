"""Data integrity checks for stored market data.

Includes the per-bar **quality model** (Master Plan §3.2, invariant 1): every sealed bar
carries a ``BarQuality``, and a strategy never consumes a SUSPECT/MISSING bar — it halts.
"""
from __future__ import annotations

from enum import Enum

from apps.exchange.candle_store import load_candles, load_candles_from_db
from apps.exchange.constants import INTERVAL_MS, normalize_coin, normalize_interval


class BarQuality(str, Enum):
    """Quality of a single sealed bar.

    - ``CLEAN``   — fully covered by ingest and contained real trades.
    - ``FLAT``    — fully covered but no trades (quiet bar, price carried forward). Legitimate.
    - ``SUSPECT`` — only partially covered by the union of ingest nodes.
    - ``MISSING`` — not covered by any node; the data is gone (Class-3 unless still recoverable).
    """

    CLEAN = "CLEAN"
    FLAT = "FLAT"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"


# Severity for halt-gating: a strategy halts when its window's worst quality is >= SUSPECT.
_SEVERITY = {BarQuality.CLEAN: 0, BarQuality.FLAT: 1, BarQuality.SUSPECT: 2, BarQuality.MISSING: 3}


def classify_bar(bar: dict, *, covered_ms: int, tf_ms: int) -> BarQuality:
    """Classify a sealed bar from its trade count and how much of it ingest covered.

    ``covered_ms`` is the covered milliseconds within the bar's ``[t0, t0+tf_ms)`` window
    (from ``coverage``); ``bar['trade_count']`` distinguishes CLEAN from FLAT.
    """
    if covered_ms <= 0:
        return BarQuality.MISSING
    if covered_ms < tf_ms:
        return BarQuality.SUSPECT
    return BarQuality.CLEAN if bar.get("trade_count", 0) > 0 else BarQuality.FLAT


def worst(*qualities: BarQuality) -> BarQuality:
    """Most-degraded quality by severity (CLEAN < FLAT < SUSPECT < MISSING)."""
    if not qualities:
        return BarQuality.CLEAN
    return max(qualities, key=lambda q: _SEVERITY[q])


def should_halt(qualities) -> bool:
    """True if any bar in the window is SUSPECT or MISSING (invariant 1)."""
    return any(_SEVERITY[q] >= _SEVERITY[BarQuality.SUSPECT] for q in qualities)


def derive_quality(qualities) -> BarQuality:
    """Quality of a higher-TF bar from its constituents (worst-case, §3.2).

    Unlike ``worst``, a FLAT constituent does not downgrade a bar that also had real trades:
    MISSING if any missing, else SUSPECT if any suspect, else CLEAN if any real trades, else FLAT.
    """
    qs = list(qualities)
    if not qs:
        return BarQuality.MISSING
    if any(q == BarQuality.MISSING for q in qs):
        return BarQuality.MISSING
    if any(q == BarQuality.SUSPECT for q in qs):
        return BarQuality.SUSPECT
    if any(q == BarQuality.CLEAN for q in qs):
        return BarQuality.CLEAN
    return BarQuality.FLAT


def validate_candles(df) -> list[dict]:
    """Return list of integrity issues (empty if healthy)."""
    issues: list[dict] = []
    if df.empty:
        issues.append({"code": "empty", "message": "no rows"})
        return issues

    if df["ts"].duplicated().any():
        issues.append({"code": "duplicate_ts", "message": "duplicate timestamps found"})

    bad_ohlc = df[(df["high"] < df["low"]) | (df["open"] > df["high"]) | (df["open"] < df["low"])]
    if not bad_ohlc.empty:
        issues.append({"code": "ohlc_invalid", "message": f"{len(bad_ohlc)} invalid OHLC rows"})

    if (df["volume"] < 0).any():
        issues.append({"code": "negative_volume", "message": "negative volume values"})

    return issues


def find_gaps(
    coin: str,
    interval: str,
    *,
    network: str = "mainnet",
    source: str = "db",
) -> list[dict]:
    """Detect missing candles based on expected interval spacing."""
    coin = normalize_coin(coin)
    interval = normalize_interval(interval)
    bar_ms = INTERVAL_MS.get(interval, 60_000)

    if source == "parquet":
        df = load_candles(coin, interval, network=network)
    else:
        df = load_candles_from_db(coin, interval, network=network)

    if df.empty or len(df) < 2:
        return []

    gaps: list[dict] = []
    ts_list = sorted(int(t) for t in df["ts"].tolist())
    for i in range(1, len(ts_list)):
        delta = ts_list[i] - ts_list[i - 1]
        if delta > bar_ms * 1.5:
            missing = int(delta // bar_ms) - 1
            if missing > 0:
                gaps.append(
                    {
                        "after_ts": ts_list[i - 1],
                        "before_ts": ts_list[i],
                        "missing_bars": missing,
                        "gap_ms": delta,
                    }
                )
    return gaps


def dataset_quality_light(
    *,
    bars: int,
    start_ts: int,
    end_ts: int,
    interval: str,
) -> dict:
    """Fast gap estimate from metadata (no full candle load)."""
    if bars < 2 or end_ts <= start_ts:
        return {"healthy": True, "gap_count": 0, "missing_bars": 0}

    interval = normalize_interval(interval)
    bar_ms = INTERVAL_MS.get(interval, 60_000)
    expected = int((end_ts - start_ts) / bar_ms) + 1
    missing = max(0, expected - bars)
    return {
        "healthy": missing == 0,
        "gap_count": 1 if missing > 0 else 0,
        "missing_bars": missing,
    }


def dataset_report(
    coin: str,
    interval: str,
    *,
    network: str = "mainnet",
    kind: str = "ohlcv",
) -> dict:
    """Full quality report for a dataset."""
    if kind != "ohlcv":
        return {"healthy": True, "issues": [], "gaps": [], "kind": kind}

    df = load_candles_from_db(coin, interval, network=network)
    if df.empty:
        df = load_candles(coin, interval, network=network)

    issues = validate_candles(df)
    gaps = find_gaps(coin, interval, network=network, source="parquet" if not df.empty else "db")
    return {
        "coin": normalize_coin(coin),
        "interval": normalize_interval(interval),
        "network": network,
        "kind": kind,
        "bars": int(len(df)),
        "healthy": not issues and not gaps,
        "issues": issues,
        "gaps": gaps,
        "gap_count": len(gaps),
        "missing_bars": sum(g["missing_bars"] for g in gaps),
    }
