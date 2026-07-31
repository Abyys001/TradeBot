"""Readiness — "can this strategy go live yet?" (Master Plan §P3, candle design §5).

Because Tabdeal has no candle backfill, history accrues from the moment the recorder
starts (candle design §1.3). Readiness makes that a first-class, honest signal instead
of an error state: how many clean warmup bars exist *now*, and — if not enough yet —
how long until there are.

A bar is usable for warmup iff its ``[t0, t0+tf)`` window is fully covered by the union
of ingest nodes (CLEAN or FLAT; SUSPECT/MISSING are not). We report the length of the
contiguous run of usable bars ending at the most recently sealed bar — that is exactly
the window a strategy would be warmed from.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import coverage
from .ledger import union_coverage
from .timeframes import is_fixed, tf_to_ms

# Full coverage is fractional (float rounding across interval merges); treat ~1.0 as full.
_FULL = 0.999


def _iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def readiness(symbol: str, tf: str, required_bars: int) -> dict:
    """Readiness report for ``(symbol, tf)`` against a warmup requirement.

    Returns the shape consumed by the frontend Go-Live gate: clean_bars,
    required_bars, ready, eta_seconds, recording_since, coverage_pct, suspect_bars_24h.
    """
    tf = str(tf)
    required_bars = max(int(required_bars), 0)
    if not is_fixed(tf):
        return _empty(symbol, tf, required_bars, error=f"{tf!r} is not a fixed timeframe")

    tf_ms = tf_to_ms(tf)
    cov = union_coverage(symbol)
    if not cov:
        return _empty(symbol, tf, required_bars)  # recorder has never covered this symbol

    recording_since_ms = cov[0][0]
    latest_ms = cov[-1][1]

    # Most recent fully-sealed bucket (its right edge <= latest covered ms).
    last_bucket = ((latest_ms // tf_ms) * tf_ms) - tf_ms
    if last_bucket < recording_since_ms:
        clean_bars = 0
    else:
        clean_bars = _contiguous_clean(symbol, last_bucket, tf_ms, cap=max(required_bars, 1))

    # Recorded trades are not enough: the strategy seeds its warmup window from the
    # *candle store*, so a symbol can be fully recorded and still unable to start.
    stored_bars = stored_bar_count(symbol, tf)

    recording_ready = required_bars > 0 and clean_bars >= required_bars
    ready = recording_ready and stored_bars >= required_bars
    eta_seconds = 0 if recording_ready else int((required_bars - clean_bars) * (tf_ms / 1000))

    out = {
        "symbol": symbol.upper(),
        "timeframe": tf,
        "clean_bars": clean_bars,
        "stored_bars": stored_bars,
        "recording_ready": recording_ready,
        "required_bars": required_bars,
        "ready": ready,
        "eta_seconds": eta_seconds,
        "recording_since": _iso(recording_since_ms),
        "coverage_pct": round(coverage.coverage_pct(symbol, recording_since_ms, latest_ms) * 100, 2),
        "suspect_bars_24h": _suspect_bars_24h(symbol, tf_ms, latest_ms),
    }
    if recording_ready and not ready:
        out["needs_backfill"] = True
        out["hint"] = (
            f"{clean_bars} bars recorded but only {stored_bars} stored — run "
            f"`manage.py backfill_candles --symbols {symbol.upper()} --timeframes {tf}`"
        )
    return out


def stored_bar_count(symbol: str, tf: str) -> int:
    """Candles actually materialized for ``(symbol, tf)`` — what warmup reads."""
    from .candle_store import Candle
    from .resampler import ledger_symbol_to_coin

    return Candle.objects.filter(
        asset=ledger_symbol_to_coin(symbol), timeframe=tf
    ).count()


def strategy_readiness(strategy, required_bars: int | None = None) -> dict:
    """Readiness for a strategy across its chart timeframe *and* every HTF it requests.

    A `request.security` strategy is only ready when the higher timeframe is warm
    too; reporting the chart timeframe alone is the same false green light as
    reporting recorded trades without stored candles.
    """
    from apps.transpiler.engine import compile as pine_compile
    from apps.transpiler.runtime.tabdeal_broker import to_tabdeal_symbol
    from apps.transpiler.runtime.timeframe import minutes_to_interval

    symbol = to_tabdeal_symbol(strategy.symbol)
    required = int(required_bars if required_bars is not None else strategy.warmup_bars)
    report = readiness(symbol, strategy.timeframe, required)

    htf: list[dict] = []
    if (strategy.source or "").strip():
        try:
            program = pine_compile(strategy.source)
            minutes = getattr(program, "security_minutes", ()) or ()
        except Exception:  # noqa: BLE001 — a broken script is the start endpoint's problem
            minutes = ()
        for mins in minutes:
            try:
                tf = minutes_to_interval(mins)
            except Exception:  # noqa: BLE001
                htf.append({"minutes": mins, "error": "timeframe not on the supported ladder",
                            "ready": False})
                report["ready"] = False
                continue
            # An HTF bar spans several chart bars, so proportionally fewer are needed.
            factor = max(mins // max(tf_to_ms(strategy.timeframe) // 60_000, 1), 1)
            sub = readiness(symbol, tf, max(required // factor, 1))
            htf.append(sub)
            if not sub["ready"]:
                report["ready"] = False
    report["htf"] = htf
    return report


def _contiguous_clean(symbol: str, last_bucket: int, tf_ms: int, *, cap: int) -> int:
    """Length of the run of fully-covered buckets ending at ``last_bucket``.

    Scans backward, stopping at the first non-full bucket. Bounded by ``cap`` (we only
    need to know whether the warmup window is satisfied) so a long clean history does
    not turn this into an O(history) walk.
    """
    count = 0
    t0 = last_bucket
    while count < cap and t0 >= 0:
        if coverage.coverage_pct(symbol, t0, t0 + tf_ms) < _FULL:
            break
        count += 1
        t0 -= tf_ms
    return count


def _suspect_bars_24h(symbol: str, tf_ms: int, latest_ms: int) -> int:
    """Buckets in the last 24h that are partially (not fully, not zero) covered."""
    window_start = latest_ms - 24 * 60 * 60 * 1000
    t0 = (max(window_start, 0) // tf_ms) * tf_ms
    suspect = 0
    while t0 + tf_ms <= latest_ms:
        pct = coverage.coverage_pct(symbol, t0, t0 + tf_ms)
        if 0 < pct < _FULL:
            suspect += 1
        t0 += tf_ms
    return suspect


def _empty(symbol: str, tf: str, required_bars: int, *, error: str | None = None) -> dict:
    out = {
        "symbol": symbol.upper(),
        "timeframe": tf,
        "clean_bars": 0,
        "stored_bars": 0,
        "recording_ready": False,
        "required_bars": required_bars,
        "ready": False,
        "eta_seconds": None,
        "recording_since": None,
        "coverage_pct": 0.0,
        "suspect_bars_24h": 0,
    }
    if error:
        out["error"] = error
    return out


def _now_ms() -> int:
    return int(time.time() * 1000)
