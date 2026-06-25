"""Public transpiler API: compile, backtest, and live execution."""
from __future__ import annotations

from dataclasses import dataclass

from apps.risk.config import parse_risk_config
from apps.risk.manager import RiskManager

from . import ast_nodes as ast
from .parser import parse
from .runtime import interpreter
from .runtime.context import ExecutionContext
from .runtime.order_router import LiveBroker, SimBroker
from .semantic import analyze


def compile(source: str) -> ast.ProgramNode:
    program = parse(source)
    analyze(program)
    return program


@dataclass
class BacktestResult:
    metrics: dict
    trades: list


def _header_kwargs(program: ast.ProgramNode) -> dict:
    out: dict = {}
    if program.header is not None:
        for a in program.header.args:
            if a.name is not None and isinstance(a.value, ast.LiteralNode):
                out[a.name] = a.value.value
    return out


def _coerce_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _build_funding_map(funding_df) -> dict[int, float]:
    if funding_df is None or funding_df.empty:
        return {}
    return {int(row.ts): float(row.funding_rate) for row in funding_df.itertuples()}


def run_backtest_pine(
    source: str,
    df,
    *,
    default_qty: float | None = None,
    commission: float | None = None,
    slippage: float | None = None,
    leverage: float | None = None,
    initial_balance: float = 10_000.0,
    funding_df=None,
    live_config: dict | None = None,
    allow_pyramiding: bool = False,
) -> BacktestResult:
    program = compile(source)
    hk = _header_kwargs(program)
    qty = default_qty if default_qty is not None else _coerce_float(
        hk.get("default_qty_value", hk.get("qty")), 1.0
    )
    comm = commission if commission is not None else _coerce_float(hk.get("commission_value"), 0.0)
    slip = slippage if slippage is not None else _coerce_float(hk.get("slippage"), 0.0)
    lev = leverage if leverage is not None else _coerce_float(
        (live_config or {}).get("leverage", 1), 1.0
    )

    risk_cfg = parse_risk_config(live_config)
    risk_mgr = RiskManager(risk_cfg, initial_balance=initial_balance)
    funding_rates = _build_funding_map(funding_df)

    broker = SimBroker(
        default_qty=qty,
        commission=comm,
        slippage=slip,
        leverage=lev,
        initial_balance=initial_balance,
        funding_rates=funding_rates,
        allow_pyramiding=allow_pyramiding or bool((live_config or {}).get("pyramiding")),
        risk_manager=risk_mgr,
    )
    ctx = ExecutionContext(df, broker, header=program.header)
    interpreter.run(program, ctx)
    return BacktestResult(metrics=broker.metrics(), trades=broker.trades())


def run_backtest(
    source: str,
    df,
    *,
    default_qty: float | None = None,
    commission: float | None = None,
    slippage: float | None = None,
    leverage: float | None = None,
    initial_balance: float = 10_000.0,
    funding_df=None,
    live_config: dict | None = None,
    allow_pyramiding: bool = False,
    engine: str = "pine",
    params: dict | None = None,
) -> BacktestResult:
    """Run backtest via the strategy plugin registry (default: Pine)."""
    from apps.strategies.plugins.registry import get_engine

    plugin = get_engine(engine)
    compiled = plugin.compile(source, params=params)
    kwargs = {
        "default_qty": default_qty,
        "commission": commission,
        "slippage": slippage,
        "leverage": leverage,
        "initial_balance": initial_balance,
        "funding_df": funding_df,
        "live_config": live_config,
        "allow_pyramiding": allow_pyramiding,
        "source": source,
        "params": params,
    }
    return plugin.run_backtest(compiled, df, **{k: v for k, v in kwargs.items() if v is not None})


def run_live(source: str, df, *, credential, strategy, symbol):
    program = compile(source)
    broker = LiveBroker(credential=credential, strategy=strategy, symbol=symbol)
    ctx = ExecutionContext(df, broker, header=program.header)
    interpreter.run(program, ctx)
    return broker


def start_live(strategy) -> None:
    from .live.runner import LiveIncrementalRunner

    LiveIncrementalRunner().seed_and_warmup(strategy)


def stop_live(strategy) -> None:
    from .live.runner import LiveIncrementalRunner

    LiveIncrementalRunner.stop(strategy)
