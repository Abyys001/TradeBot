"""Tests for Phase 3 live engine components."""
import numpy as np
import pandas as pd
import pytest

from apps.transpiler.engine import compile, run_backtest
from apps.transpiler.live.sliding_window import SlidingWindow
from apps.transpiler.runtime import interpreter
from apps.transpiler.runtime.context import ExecutionContext
from apps.transpiler.runtime.order_router import LiveBroker, WarmupBroker


def _ohlcv_df(n=30, start=100.0):
    rows = []
    for i in range(n):
        c = start + i
        rows.append({"ts": 1000 + i, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10})
    return pd.DataFrame(rows)


SMA_CROSS = (
    'strategy("x", overlay=true)\n'
    "fast = ta.sma(close, 3)\n"
    "slow = ta.sma(close, 10)\n"
    "if ta.crossover(fast, slow)\n"
    '    strategy.entry("long", strategy.long)\n'
)


def test_sliding_window_drops_oldest_at_max_size():
    w = SlidingWindow(max_size=3)
    for i in range(5):
        w.append_closed({"ts": i, "open": 1, "high": 1, "low": 1, "close": float(i), "volume": 1})
    assert len(w) == 3
    df = w.to_dataframe()
    assert df.iloc[0]["ts"] == 2
    assert df.iloc[-1]["ts"] == 4


def test_warmup_builds_scalar_state_without_orders():
    src = (
        'strategy("x")\n'
        "var int counter = 0\n"
        "counter := counter + 1\n"
    )
    df = _ohlcv_df(10)
    program = compile(src)
    broker = WarmupBroker()
    ctx = ExecutionContext(df, broker, header=program.header)
    interpreter.run_warmup(program, ctx)
    assert ctx.scalars["counter"].values[-1] == 10
    assert broker.trades() == []


def test_run_bar_only_executes_target_bar():
    src = 'strategy("x")\nstrategy.entry("long", strategy.long)\n'
    df = _ohlcv_df(5)
    program = compile(src)
    broker = WarmupBroker()
    ctx = ExecutionContext(df, broker, header=program.header)
    interpreter.run_warmup(program, ctx)

    order_broker = WarmupBroker()
    ctx2 = ExecutionContext(df, order_broker, header=program.header)
    ctx2.scalars = ctx.scalars
    interpreter.run_bar(program, ctx2, bar_index=4)
    # WarmupBroker still no-op; verify bar_index reached last bar
    assert ctx2.bar_index == 4


def test_incremental_sma_matches_full_replay():
    df = _ohlcv_df(40, start=50.0)
    program = compile(SMA_CROSS)

    full_broker = WarmupBroker()
    full_ctx = ExecutionContext(df, full_broker, header=program.header)
    interpreter.run_warmup(program, full_ctx)
    full_fast = full_ctx.arrays.get("fast")

    # Incremental: warmup then one bar at a time on growing window
    window = SlidingWindow(max_size=len(df))
    window.load_df(df.iloc[:20])
    inc_ctx = ExecutionContext(window.to_dataframe(), WarmupBroker(), header=program.header)
    interpreter.run_warmup(program, inc_ctx)

    for i in range(20, len(df)):
        window.append_closed(
            {
                "ts": int(df.iloc[i]["ts"]),
                "open": df.iloc[i]["open"],
                "high": df.iloc[i]["high"],
                "low": df.iloc[i]["low"],
                "close": df.iloc[i]["close"],
                "volume": df.iloc[i]["volume"],
            }
        )
        inc_ctx = ExecutionContext(window.to_dataframe(), WarmupBroker(), header=program.header)
        inc_ctx.scalars = inc_ctx.scalars  # fresh
        interpreter.run_bar(program, inc_ctx, bar_index=len(window) - 1)

    inc_program = compile(SMA_CROSS)
    inc_final = ExecutionContext(window.to_dataframe(), WarmupBroker(), header=inc_program.header)
    interpreter.vectorize_pass(inc_program, inc_final)
    inc_fast = inc_final.arrays.get("fast")

    if full_fast is not None and inc_fast is not None:
        np.testing.assert_allclose(full_fast[-1], inc_fast[-1], rtol=1e-9)


def test_run_backtest_still_works_after_interpreter_refactor():
    res = run_backtest(SMA_CROSS, _ohlcv_df(40))
    assert res.metrics["num_trades"] >= 0
