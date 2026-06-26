"""Data integrity checks for stored market data."""
from __future__ import annotations

from apps.exchange.candle_store import load_candles, load_candles_from_db
from apps.exchange.candles import _INTERVAL_MS
from apps.exchange.hl_constants import normalize_coin, normalize_interval


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
    bar_ms = _INTERVAL_MS.get(interval, 60_000)

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
    bar_ms = _INTERVAL_MS.get(interval, 60_000)
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
