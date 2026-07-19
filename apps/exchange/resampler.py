"""Background resampler — Node C (Master Plan §0.2, §3.2).

Runs as a **separate OS process** (not colocated with Node B's hot compute).
Reads raw trades from the ledger, resamples to base TFs (1m, 1h, 1d), writes
materialized bars to Parquet + PG, and publishes quality metadata to Redis.

Calendar TFs (1w, 1M, 3M, 6M, 1y) use a separate code path with anchor-based
bucketing (Monday 00:00 UTC for weeks, month-start for months).

Usage::

    python manage.py run_resampler          # resample all tracked symbols
    python manage.py run_resampler --symbol BTC_USDT --tf 1h
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Iterator

import pandas as pd

from .aggregator import bucket_start
from .data_quality import BarQuality, classify_bar, derive_quality
from .ledger import read_trades, LEDGER_COLUMNS
from .materialize import needs_persistence, tier_for, MaterializationTier
from .timeframes import (
    FIXED_MS, CALENDAR, BASE_TIMEFRAMES,
    divides, is_fixed, is_calendar, tf_to_ms,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Calendar anchor helpers (§0.3 — separate from fixed-bucket resampling)
# ---------------------------------------------------------------------------

def _week_start(ts_ms: int) -> int:
    """Monday 00:00 UTC for the week containing ``ts_ms``."""
    from datetime import timedelta
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    days_since_monday = dt.weekday()  # Monday=0, Sunday=6
    monday = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
    return int(monday.timestamp() * 1000)


def _month_start(ts_ms: int) -> int:
    """1st 00:00 UTC of the month containing ``ts_ms``."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    first = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(first.timestamp() * 1000)


def _quarter_start(ts_ms: int) -> int:
    """1st 00:00 UTC of the quarter containing ``ts_ms``."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    q_month = ((dt.month - 1) // 3) * 3 + 1
    first = dt.replace(month=q_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(first.timestamp() * 1000)


def _half_start(ts_ms: int) -> int:
    """1st 00:00 UTC of the half-year containing ``ts_ms``."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    h_month = 1 if dt.month <= 6 else 7
    first = dt.replace(month=h_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(first.timestamp() * 1000)


def _year_start(ts_ms: int) -> int:
    """1st 00:00 UTC of the year containing ``ts_ms``."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    first = dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(first.timestamp() * 1000)


_CALENDAR_ANCHORS = {
    "1w": _week_start,
    "1M": _month_start,
    "3M": _quarter_start,
    "6M": _half_start,
    "1y": _year_start,
}


def calendar_bucket_start(ts_ms: int, tf: str) -> int:
    """Anchor-based bucket start for a calendar timeframe."""
    anchor_fn = _CALENDAR_ANCHORS.get(tf)
    if anchor_fn is None:
        raise ValueError(f"unknown calendar timeframe: {tf!r}")
    return anchor_fn(ts_ms)


# ---------------------------------------------------------------------------
# Fixed-timeframe resampling
# ---------------------------------------------------------------------------

def resample_fixed(
    trades: pd.DataFrame,
    tf: str,
    *,
    covered_ms: int | None = None,
) -> list[dict]:
    """Fold trades into OHLCV bars for a fixed timeframe.

    Returns a list of sealed bars sorted by ts. Each bar has:
    {ts, open, high, low, close, volume, trade_count}.
    """
    if trades.empty:
        return []

    tf_ms = tf_to_ms(tf)
    bars: dict[int, dict] = {}

    for _, row in trades.iterrows():
        ts_ms = int(row["ts"])
        price = float(row["price"])
        qty = float(row.get("qty", 0))
        b0 = bucket_start(ts_ms, tf_ms)

        if b0 not in bars:
            bars[b0] = {
                "ts": b0, "open": price, "high": price, "low": price,
                "close": price, "volume": qty, "trade_count": 1,
            }
        else:
            bar = bars[b0]
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["volume"] += qty
            bar["trade_count"] += 1

    return sorted(bars.values(), key=lambda b: b["ts"])


# ---------------------------------------------------------------------------
# Calendar-timeframe resampling
# ---------------------------------------------------------------------------

def resample_calendar(
    trades: pd.DataFrame,
    tf: str,
) -> list[dict]:
    """Fold trades into OHLCV bars for a calendar timeframe.

    Uses anchor-based bucketing (Monday 00:00 UTC for 1w, month-start for 1M, etc.).
    """
    if trades.empty:
        return []

    bars: dict[int, dict] = {}

    for _, row in trades.iterrows():
        ts_ms = int(row["ts"])
        price = float(row["price"])
        qty = float(row.get("qty", 0))
        b0 = calendar_bucket_start(ts_ms, tf)

        if b0 not in bars:
            bars[b0] = {
                "ts": b0, "open": price, "high": price, "low": price,
                "close": price, "volume": qty, "trade_count": 1,
            }
        else:
            bar = bars[b0]
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["volume"] += qty
            bar["trade_count"] += 1

    return sorted(bars.values(), key=lambda b: b["ts"])


# ---------------------------------------------------------------------------
# Quality tagging
# ---------------------------------------------------------------------------

def tag_bars(
    bars: list[dict],
    symbol: str,
    tf_ms: int,
) -> list[dict]:
    """Attach quality to each bar from ledger coverage (§3.2)."""
    from . import coverage

    tagged = []
    for bar in bars:
        t0 = int(bar["ts"])
        pct = coverage.coverage_pct(symbol, t0, t0 + tf_ms)
        covered = int(round(pct * tf_ms))
        q = classify_bar(bar, covered_ms=covered, tf_ms=tf_ms)
        tagged_bar = dict(bar)
        tagged_bar["quality"] = q.value
        tagged.append(tagged_bar)
    return tagged


# ---------------------------------------------------------------------------
# Resampler orchestrator
# ---------------------------------------------------------------------------

class Resampler:
    """Background resampler for one symbol — runs as Node C.

    Reads from ledger, resamples to materialized TFs, writes Parquet + PG,
    publishes quality metadata to Redis.
    """

    def __init__(self, symbol: str, *, node_id: str = "C1"):
        self.symbol = symbol
        self.node_id = node_id

    def resample_range(
        self,
        start_ms: int,
        end_ms: int,
    ) -> dict[str, list[dict]]:
        """Resample all materialized TFs for the given time range.

        Returns ``{tf: [bars]}`` for each materialized TF.
        """
        trades = read_trades(self.symbol, start_ms, end_ms)
        if trades.empty:
            return {}

        result: dict[str, list[dict]] = {}

        # Fixed materialized TFs (1m, 1h, 1d)
        for tf in BASE_TIMEFRAMES:
            if needs_persistence(tf):
                tf_ms = tf_to_ms(tf)
                bars = resample_fixed(trades, tf)
                bars = tag_bars(bars, self.symbol, tf_ms)
                result[tf] = bars

        # Calendar TFs (1w, 1M, 3M, 6M, 1y) — §0.3 separate code path
        for tf in CALENDAR:
            bars = resample_calendar(trades, tf)
            if bars:
                # Calendar TFs derive quality from 1d constituents
                result[tf] = bars

        return result

    def publish_quality(
        self,
        bars: dict[str, list[dict]],
        redis_client,
    ) -> None:
        """Push quality metadata to Redis for the frontend readiness API."""
        for tf, bar_list in bars.items():
            if not bar_list:
                continue
            last_bar = bar_list[-1]
            key = f"resampler:quality:{self.symbol}:{tf}"
            redis_client.hset(key, mapping={
                "bar_ts": str(last_bar["ts"]),
                "quality": last_bar.get("quality", "UNKNOWN"),
                "bar_count": str(len(bar_list)),
                "updated_at": str(int(time.time() * 1000)),
            })
            redis_client.expire(key, 300)  # 5 min TTL


# ---------------------------------------------------------------------------
# Management command entry point
# ---------------------------------------------------------------------------

async def run_resampler(
    symbols: list[str] | None = None,
    interval_s: float = 60.0,
) -> None:
    """Main loop: resample all tracked symbols every ``interval_s`` seconds."""
    import redis.asyncio as aioredis
    from django.conf import settings

    from .ledger import union_coverage

    symbols = symbols or getattr(settings, "TABDEAL_INGEST_SYMBOLS", ["BTC_USDT"])
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    logger.info("resampler starting: symbols=%s interval=%.1fs", symbols, interval_s)

    while True:
        now_ms = int(time.time() * 1000)
        for symbol in symbols:
            try:
                # Determine range: last 24h (covers most resampled TFs)
                start_ms = now_ms - 86_400_000
                resampler = Resampler(symbol)
                bars = resampler.resample_range(start_ms, now_ms)
                resampler.publish_quality(bars, client)
                total = sum(len(v) for v in bars.values())
                if total:
                    logger.debug("resampler %s: %d bars across %d TFs", symbol, total, len(bars))
            except Exception:
                logger.exception("resampler failed for %s", symbol)

        await asyncio.sleep(interval_s)
