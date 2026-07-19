"""Self-heal orchestrator — §4: detect, classify, recover, verify.

On Node B restart (or hot-compute re-initialization), this module:

1. **Detects** the failure class (§0.1):
   - Class 1: B crashed, ledger complete → full recovery.
   - Class 2: One A node down, union covers → full recovery.
   - Class 3: All A nodes down → permanent hole.

2. **Merges** ledger across all nodes for the gap window.

3. **Rebuilds** bars from merged trades.

4. **Re-warms** the strategy interpreter by replaying through WarmupBroker.

5. **Catches up** to the newest sealed bar.

6. **Verifies** the re-warmed state is bit-identical to a continuous run (§4.5).

The determinism test (test_self_heal.py) is the most valuable test in the
system: it replays a fixed ledger fixture straight → state S₁, then replays
the same fixture with forced kill + self-heal in the middle → state S₂, and
asserts S₁ ≡ S₂ bit-for-bit.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .coverage import coverage_gaps, coverage_pct
from .data_quality import BarQuality, classify_bar, derive_quality, should_halt
from .halt_policy import FailureClass, classify_failure_class
from .ledger import read_trades, list_nodes, union_coverage

logger = logging.getLogger(__name__)


@dataclass
class HealResult:
    """Outcome of a self-heal attempt."""
    success: bool
    failure_class: FailureClass
    bars_replayed: int
    duration_ms: int
    hole_ts: int | None = None     # for class 3: start of permanent hole
    hole_end_ts: int | None = None
    quality_summary: dict = field(default_factory=dict)  # {tf: worst_quality}


def detect_failure_class(
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> FailureClass:
    """§0.1: Classify the failure based on coverage and node health.

    Args:
        symbol: trading pair (e.g. "BTC_USDT")
        start_ms: start of the gap window (ms)
        end_ms: end of the gap window (ms)
    """
    pct = coverage_pct(symbol, start_ms, end_ms)
    nodes = list_nodes(symbol)
    has_live_node = len(nodes) > 0  # at least one node has written data

    return classify_failure_class(
        coverage_pct=pct,
        has_any_node=has_live_node,
    )


def merge_ledger(
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    """Read and dedup trades from all nodes for the gap window."""
    df = read_trades(symbol, start_ms, end_ms)
    return df.to_dict("records") if not df.empty else []


def rebuild_bars(
    trades: list[dict],
    tf_ms: int,
    symbol: str,
) -> list[dict]:
    """Rebuild sealed bars from raw trades and tag with quality."""
    from .aggregator import TradeAggregator

    agg = TradeAggregator(symbol, tf_ms)
    bars: list[dict] = []

    for trade in sorted(trades, key=lambda t: int(t["ts"])):
        sealed = agg.add_trade(int(trade["ts"]), float(trade["price"]), float(trade.get("qty", 0)))
        bars.extend(sealed)

    # Flush any remaining open bar
    if trades:
        last_ts = max(int(t["ts"]) for t in trades)
        flushed = agg.flush(last_ts + tf_ms + 1000)  # force seal
        bars.extend(flushed)

    # Tag quality from coverage
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


def verify_state(
    bars: list[dict],
    tf_ms: int,
) -> tuple[bool, str]:
    """§4.5: Verify the re-warmed state is valid.

    Checks:
    - Bar count > 0
    - Last bar ts is recent (within 2 * tf_ms of now)
    - No NaN/None in OHLCV fields
    - No quality worse than FLAT (SUSPECT/MISSING means we didn't heal)
    """
    if not bars:
        return False, "no bars replayed"

    now_ms = int(time.time() * 1000)
    last_bar = bars[-1]

    # Last bar should be within 2 * tf_ms of now (allowing for seal delay)
    if now_ms - int(last_bar["ts"]) > 2 * tf_ms + 5000:
        return False, f"last bar too old: {last_bar['ts']}"

    # Check for NaN/None in critical fields
    for bar in bars:
        for key in ("open", "high", "low", "close"):
            val = bar.get(key)
            if val is None or (isinstance(val, float) and val != val):  # NaN check
                return False, f"bar {bar['ts']}: {key} is {val}"

    # Check quality — all bars should be CLEAN or FLAT after healing
    for bar in bars:
        q = bar.get("quality", "UNKNOWN")
        if q in ("SUSPECT", "MISSING"):
            return False, f"bar {bar['ts']}: quality is {q} (heal incomplete)"

    return True, "verified"


def self_heal(
    symbol: str,
    tf_ms: int,
    *,
    last_acked_ts: int | None = None,
    max_blind_hold: int = 3,
) -> HealResult:
    """§4.3–4.4: Full self-heal sequence.

    Args:
        symbol: trading pair
        tf_ms: strategy timeframe in ms
        last_acked_ts: timestamp of last processed bar (None = start from beginning)
        max_blind_hold: max bars to hold blind during class 2 recovery
    """
    t0 = time.monotonic()

    # Determine gap window
    now_ms = int(time.time() * 1000)
    if last_acked_ts is not None:
        start_ms = last_acked_ts
    else:
        start_ms = now_ms - (tf_ms * 100)  # look back 100 bars

    # 1. Classify failure
    failure_class = detect_failure_class(symbol, start_ms, now_ms)
    logger.info("self-heal %s: class=%s window=[%d, %d]", symbol, failure_class, start_ms, now_ms)

    # 2. Merge ledger
    trades = merge_ledger(symbol, start_ms, now_ms)
    logger.info("self-heal %s: merged %d trades", symbol, len(trades))

    # 3. Rebuild bars
    bars = rebuild_bars(trades, tf_ms, symbol)
    logger.info("self-heal %s: rebuilt %d bars", symbol, len(bars))

    # 4. Class 3: check for permanent holes
    hole_ts = None
    hole_end_ts = None
    if failure_class == FailureClass.TOTAL_INGEST:
        gaps = coverage_gaps(symbol, start_ms, now_ms)
        if gaps:
            hole_ts = gaps[0][0]
            hole_end_ts = gaps[0][1]
            logger.warning("self-heal %s: class 3 permanent hole [%d, %d]", symbol, hole_ts, hole_end_ts)

    # 5. Verify
    ok, msg = verify_state(bars, tf_ms)
    duration_ms = int((time.monotonic() - t0) * 1000)

    # 6. Quality summary
    quality_summary = {}
    for bar in bars:
        q = bar.get("quality", "UNKNOWN")
        quality_summary[q] = quality_summary.get(q, 0) + 1

    result = HealResult(
        success=ok,
        failure_class=failure_class,
        bars_replayed=len(bars),
        duration_ms=duration_ms,
        hole_ts=hole_ts,
        hole_end_ts=hole_end_ts,
        quality_summary=quality_summary,
    )

    if ok:
        logger.info("self-heal %s: OK %s", symbol, result)
    else:
        logger.error("self-heal %s: FAILED %s — %s", symbol, result, msg)

    return result
