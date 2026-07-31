"""Public transpiler API: compile, backtest, and live execution."""
from __future__ import annotations

from dataclasses import dataclass

from apps.risk.config import parse_risk_config, read_risk
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
    program.security_minutes = security_minutes(program)
    return program


def security_minutes(program: ast.ProgramNode, chart_interval: str = "1h") -> tuple[int, ...]:
    """Higher timeframes (in minutes) the program requests via `request.security`.

    Higher-timeframe bars are folded out of the chart window rather than stored
    separately, so this is what decides how many chart bars a live session needs
    before its HTF indicators are warm. Resolutions that depend on the chart
    timeframe are resolved against *chart_interval*.
    """
    from .runtime.context import ExecutionContext
    from .runtime.order_router import WarmupBroker
    from .runtime.security import _is_security_expr  # noqa: PLC2701 — same package
    from .runtime.timeframe import resolve_security_minutes

    import pandas as pd

    # A one-row frame is enough: only bar-invariant expressions are evaluated.
    stub = pd.DataFrame({c: [1.0] for c in ("open", "high", "low", "close", "volume")})
    ctx = ExecutionContext(stub, WarmupBroker(), header=program.header,
                           chart_interval=chart_interval, program=program)
    interpreter.const_eval_pass(program, ctx)

    found: set[int] = set()
    for node in _walk(program.body):
        if not _is_security_expr(node) or len(node.args) < 2:
            continue
        try:
            tf_str = str(interpreter.eval_scalar(node.args[1].value, ctx))
            found.add(resolve_security_minutes(chart_interval, tf_str))
        except Exception:  # noqa: BLE001 — unresolvable here surfaces at run time
            continue
    return tuple(sorted(found))


def _walk(nodes):
    """Depth-first walk over every node reachable from a statement list."""
    from .semantic import _children  # noqa: PLC2701 — same package

    for node in nodes:
        if node is None:
            continue
        yield node
        yield from _walk(_children(node))


@dataclass
class BacktestResult:
    metrics: dict
    trades: list


def _header_kwargs(program: ast.ProgramNode) -> dict:
    out: dict = {}
    if program.header is not None:
        for a in program.header.args:
            if a.name is None:
                continue
            if isinstance(a.value, ast.LiteralNode):
                out[a.name] = a.value.value
            elif isinstance(a.value, ast.BuiltinFunctionNode) and a.value.namespace == "strategy":
                out[a.name] = a.value.name
    return out


def _header_qty_mode(hk: dict) -> bool:
    qty_type = hk.get("default_qty_type", "")
    return str(qty_type) == "percent_of_equity"


def header_sizing(program: ast.ProgramNode) -> dict:
    """`default_qty_type` / `default_qty_value` as live-broker kwargs.

    The backtest broker has always honoured these; the live Tabdeal brokers did
    not, so a script declaring `percent_of_equity=90` was backtested at 90% and
    traded at whatever the dashboard risk config said. Passing the same values
    both ways is what makes a backtest predictive of live.
    """
    hk = _header_kwargs(program)
    if "default_qty_value" not in hk and "qty" not in hk:
        return {}
    return {
        "default_qty": _coerce_float(hk.get("default_qty_value", hk.get("qty")), 1.0),
        "qty_is_percent_of_equity": _header_qty_mode(hk),
    }


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
    initial_balance: float | None = None,
    funding_df=None,
    live_config: dict | None = None,
    allow_pyramiding: bool = False,
    chart_interval: str = "1h",
    symbol: str = "",
) -> BacktestResult:
    program = compile(source)
    hk = _header_kwargs(program)
    qty = default_qty if default_qty is not None else _coerce_float(
        hk.get("default_qty_value", hk.get("qty")), 1.0
    )
    init_bal = initial_balance if initial_balance is not None else _coerce_float(
        hk.get("initial_capital"), 10_000.0
    )
    comm = commission if commission is not None else _coerce_float(hk.get("commission_value"), 0.0)
    slip = slippage if slippage is not None else _coerce_float(hk.get("slippage"), 0.0)
    lev = leverage if leverage is not None else _coerce_float(
        read_risk(live_config).get("leverage", 1), 1.0
    )

    risk_cfg = parse_risk_config(live_config)
    risk_mgr = RiskManager(risk_cfg, initial_balance=init_bal)
    funding_rates = _build_funding_map(funding_df)

    broker = SimBroker(
        default_qty=qty,
        commission=comm,
        slippage=slip,
        leverage=lev,
        initial_balance=init_bal,
        funding_rates=funding_rates,
        allow_pyramiding=allow_pyramiding or bool((live_config or {}).get("pyramiding")),
        risk_manager=risk_mgr,
        qty_is_percent_of_equity=_header_qty_mode(hk),
    )
    ctx = ExecutionContext(
        df,
        broker,
        header=program.header,
        chart_interval=chart_interval,
        symbol=symbol,
        program=program,
    )
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
    initial_balance: float | None = None,
    funding_df=None,
    live_config: dict | None = None,
    allow_pyramiding: bool = False,
    chart_interval: str = "1h",
    symbol: str = "",
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
        "chart_interval": chart_interval,
        "symbol": symbol,
        "source": source,
        "params": params,
    }
    return plugin.run_backtest(compiled, df, **{k: v for k, v in kwargs.items() if v is not None})


def run_live(source: str, df, *, credential, strategy, symbol):
    from apps.credentials.models import Exchange

    program = compile(source)
    if credential and credential.exchange == Exchange.TABDEAL:
        from .runtime.tabdeal_live_broker import TabdealLiveBroker

        broker = TabdealLiveBroker(
            credential=credential, strategy=strategy, symbol=symbol,
            **header_sizing(program),
        )
    else:
        broker = LiveBroker(credential=credential, strategy=strategy, symbol=symbol)
    ctx = ExecutionContext(
        df,
        broker,
        header=program.header,
        chart_interval=strategy.timeframe,
        symbol=symbol,
        program=program,
    )
    interpreter.run(program, ctx)
    return broker


def start_live(strategy) -> None:
    from .live.runner import LiveIncrementalRunner

    LiveIncrementalRunner().seed_and_warmup(strategy)


def stop_live(strategy) -> None:
    from .live.runner import LiveIncrementalRunner

    LiveIncrementalRunner.stop(strategy)
