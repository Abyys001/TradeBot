"""`request.security` — higher-timeframe series without repainting."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import ast_nodes as ast
from .context import NA, ExecutionContext
from .order_router import WarmupBroker
from .timeframe import chart_bar_minutes, resolve_security_minutes


def resample_ohlcv(df: pd.DataFrame, target_minutes: int, chart_minutes: int) -> pd.DataFrame:
    """Aggregate chart OHLCV to a higher timeframe (integer multiple of chart bars)."""
    if target_minutes <= chart_minutes:
        return df.reset_index(drop=True)
    factor = max(int(round(target_minutes / chart_minutes)), 1)
    if factor <= 1:
        return df.reset_index(drop=True)

    out_rows = []
    n = len(df)
    for start in range(0, n, factor):
        chunk = df.iloc[start : start + factor]
        if chunk.empty:
            continue
        out_rows.append(
            {
                "ts": int(chunk["ts"].iloc[-1]),
                "open": float(chunk["open"].iloc[0]),
                "high": float(chunk["high"].max()),
                "low": float(chunk["low"].min()),
                "close": float(chunk["close"].iloc[-1]),
                "volume": float(chunk["volume"].sum()) if "volume" in chunk else 0.0,
            }
        )
    return pd.DataFrame(out_rows)


def align_htf_to_ltf(
    htf_values: np.ndarray,
    chart_len: int,
    factor: int,
) -> np.ndarray:
    """Forward-fill HTF values onto the chart timeframe (one value per HTF bar)."""
    out = np.full(chart_len, NA, dtype="float64")
    if factor < 1 or len(htf_values) == 0:
        return out
    for i in range(chart_len):
        htf_idx = min(i // factor, len(htf_values) - 1)
        out[i] = float(htf_values[htf_idx])
    return out


def _is_security_expr(node) -> bool:
    return (
        isinstance(node, ast.BuiltinFunctionNode)
        and node.namespace == "request"
        and node.name == "security"
    )


def _strip_security_assigns(program: ast.ProgramNode) -> ast.ProgramNode:
    """Program body without `x = request.security(...)` (for HTF replay)."""
    body = [
        s
        for s in program.body
        if not (isinstance(s, ast.AssignNode) and _is_security_expr(s.value))
    ]
    return ast.ProgramNode(header=program.header, body=body, functions=list(program.functions))


def _unwrap_arg(expr):
    if isinstance(expr, ast.ArgNode):
        return expr.value
    return expr


def _history_offset(expr) -> int:
    expr = _unwrap_arg(expr)
    if isinstance(expr, ast.HistoryAccessNode):
        if isinstance(expr.offset, ast.LiteralNode) and expr.offset.type == "int":
            return int(expr.offset.value)
    return 0


def _inner_series(expr):
    expr = _unwrap_arg(expr)
    if isinstance(expr, ast.HistoryAccessNode):
        return expr.series
    return expr


def _series_from_ctx(ctx: ExecutionContext, series_node) -> np.ndarray:
    """Materialize a Pine series on *ctx* after warmup (arrays or scalar buffers)."""
    if isinstance(series_node, ast.IdentifierNode):
        name = series_node.name
        if name in ctx.arrays:
            return np.asarray(ctx.arrays[name], dtype="float64")
        buf = ctx.scalars.get(name)
        if buf is not None and buf.values:
            vals = list(buf.values)
            if len(vals) < ctx.n:
                vals.append(buf.current)
            arr = np.full(ctx.n, NA, dtype="float64")
            for i, v in enumerate(vals[: ctx.n]):
                try:
                    arr[i] = float(v)
                except (TypeError, ValueError):
                    arr[i] = NA
            return arr
    from . import interpreter

    try:
        return interpreter.as_array(series_node, ctx).astype("float64")
    except interpreter.NotVectorizable:
        return np.full(ctx.n, NA, dtype="float64")


def evaluate_security(
    program: ast.ProgramNode,
    parent_ctx: ExecutionContext,
    *,
    expr,
    tf_str: str,
) -> np.ndarray:
    """Evaluate `request.security(..., tf, expr, ...)` on resampled HTF data."""
    from . import interpreter

    chart_iv = parent_ctx.chart_interval or "1h"
    chart_min = chart_bar_minutes(chart_iv)
    target_min = resolve_security_minutes(chart_iv, tf_str)
    factor = max(int(round(target_min / chart_min)), 1)

    htf_df = resample_ohlcv(parent_ctx.df, target_min, chart_min)
    if htf_df.empty:
        return np.full(parent_ctx.n, NA, dtype="float64")

    stripped = _strip_security_assigns(program)
    broker = WarmupBroker()
    htf_ctx = ExecutionContext(
        htf_df,
        broker,
        header=parent_ctx.header,
        chart_interval=chart_iv,
        symbol=parent_ctx.symbol,
        program=stripped,
    )
    htf_ctx.functions = dict(parent_ctx.functions)
    interpreter.run_warmup(stripped, htf_ctx)

    inner = _inner_series(expr)
    hist = _history_offset(expr)
    htf_arr = _series_from_ctx(htf_ctx, inner)

    if hist > 0:
        htf_arr = pd.Series(htf_arr).shift(hist).to_numpy()

    return align_htf_to_ltf(htf_arr, parent_ctx.n, factor)
