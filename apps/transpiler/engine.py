"""Public transpiler API: compile, backtest, and live execution.

    program = compile(source)                  # parse + semantic check
    result  = run_backtest(source, df)          # SimBroker over an OHLCV frame
    run_live(source, df_tail, credential, ...)  # LiveBroker -> Hyperliquid
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ast_nodes as ast
from .parser import parse
from .runtime import interpreter
from .runtime.context import ExecutionContext
from .runtime.order_router import LiveBroker, SimBroker
from .semantic import analyze


def compile(source: str) -> ast.ProgramNode:
    """Parse and semantically validate. Raises PineSyntaxError /
    PineSemanticError / UnsupportedFeatureError on invalid input."""
    program = parse(source)
    analyze(program)
    return program


@dataclass
class BacktestResult:
    metrics: dict
    trades: list


def run_backtest(source: str, df, *, default_qty: float = 1.0) -> BacktestResult:
    """Compile then run over an OHLCV DataFrame with a simulated broker."""
    program = compile(source)
    broker = SimBroker(default_qty=default_qty)
    ctx = ExecutionContext(df, broker, header=program.header)
    interpreter.run(program, ctx)
    return BacktestResult(metrics=broker.metrics(), trades=broker.trades())


def run_live(source: str, df, *, credential, strategy, symbol):
    """Compile then run over recent bars with the live Hyperliquid broker.

    `df` should end at the current bar; orders fire on the final bar's logic.
    The LiveBroker enforces the per-user kill-switch before any order.

    For incremental live execution use ``LiveIncrementalRunner`` (Phase 3).
    """
    program = compile(source)
    broker = LiveBroker(credential=credential, strategy=strategy, symbol=symbol)
    ctx = ExecutionContext(df, broker, header=program.header)
    interpreter.run(program, ctx)
    return broker


def start_live(strategy) -> None:
    """Seed, warmup, and register a strategy for live candle processing."""
    from .live.runner import LiveIncrementalRunner

    LiveIncrementalRunner().seed_and_warmup(strategy)


def stop_live(strategy) -> None:
    """Stop live execution and clear session state."""
    from .live.runner import LiveIncrementalRunner

    LiveIncrementalRunner.stop(strategy)
