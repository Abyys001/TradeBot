"""`request.security` — higher-timeframe series without repainting."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import ast_nodes as ast
from .context import NA, ExecutionContext
from .order_router import WarmupBroker
from .timeframe import chart_bar_minutes, resolve_security_minutes


_MIN_MS = 60_000


def resample_ohlcv(
    df: pd.DataFrame,
    target_minutes: int,
    chart_minutes: int,
) -> pd.DataFrame:
    """Aggregate chart OHLCV to a higher timeframe.

    Buckets are cut on **absolute UTC time** (``ts // target_ms``), never on the
    dataframe's own index. Live execution slides a window over the candles, so
    index-relative bucketing would move the HTF boundaries every bar and give the
    same chart bar a different HTF value depending on where the window started.

    The returned frame carries ``ts`` = bucket **start**, so callers can tell
    exactly when each HTF bar closes.
    """
    if target_minutes <= chart_minutes or df.empty:
        return df.reset_index(drop=True)
    if "ts" not in df.columns:
        # No timestamps (synthetic frames in tests) — fall back to index chunks.
        return _resample_by_index(df, max(int(round(target_minutes / chart_minutes)), 1))

    target_ms = int(target_minutes) * _MIN_MS
    buckets = (df["ts"].to_numpy(dtype="int64") // target_ms) * target_ms
    grouped = df.groupby(buckets, sort=True)
    out = pd.DataFrame(
        {
            "ts": grouped["ts"].first().index.to_numpy(dtype="int64"),
            "open": grouped["open"].first().to_numpy(dtype="float64"),
            "high": grouped["high"].max().to_numpy(dtype="float64"),
            "low": grouped["low"].min().to_numpy(dtype="float64"),
            "close": grouped["close"].last().to_numpy(dtype="float64"),
            "volume": (
                grouped["volume"].sum().to_numpy(dtype="float64")
                if "volume" in df.columns
                else np.zeros(grouped.ngroups, dtype="float64")
            ),
        }
    )
    return out.reset_index(drop=True)


def _resample_by_index(df: pd.DataFrame, factor: int) -> pd.DataFrame:
    if factor <= 1:
        return df.reset_index(drop=True)
    rows = []
    for start in range(0, len(df), factor):
        chunk = df.iloc[start : start + factor]
        if chunk.empty:
            continue
        row = {
            "open": float(chunk["open"].iloc[0]),
            "high": float(chunk["high"].max()),
            "low": float(chunk["low"].min()),
            "close": float(chunk["close"].iloc[-1]),
            "volume": float(chunk["volume"].sum()) if "volume" in chunk else 0.0,
        }
        if "ts" in chunk:
            row["ts"] = int(chunk["ts"].iloc[0])
        rows.append(row)
    return pd.DataFrame(rows)


def align_htf_to_ltf(
    htf_values: np.ndarray,
    chart_len: int,
    factor: int,
    *,
    chart_ts: np.ndarray | None = None,
    htf_ts: np.ndarray | None = None,
    target_ms: int | None = None,
    lookahead: bool = False,
) -> np.ndarray:
    """Project HTF values onto chart bars.

    With ``lookahead=False`` (Pine's ``barmerge.lookahead_off``, the default) a
    chart bar may only see HTF bars that have already **closed** — the bar the
    chart is currently inside is still forming. Using it would repaint: the
    backtest would trade on information that did not exist yet in live.
    """
    out = np.full(chart_len, NA, dtype="float64")
    if len(htf_values) == 0:
        return out

    if chart_ts is None or htf_ts is None or target_ms is None:
        if factor < 1:
            return out
        for i in range(chart_len):
            idx = i // factor - (1 if lookahead is False else 0)
            if 0 <= idx < len(htf_values):
                out[i] = float(htf_values[idx])
        return out

    # Absolute-time mapping: last HTF bar whose window has closed by this bar.
    ends = np.asarray(htf_ts, dtype="int64") + int(target_ms)
    for i in range(chart_len):
        t = int(chart_ts[i])
        idx = (
            int(np.searchsorted(ends, t, side="right")) - 1
            if not lookahead
            else int(np.searchsorted(np.asarray(htf_ts, dtype="int64"), t, side="right")) - 1
        )
        if 0 <= idx < len(htf_values):
            out[i] = float(htf_values[idx])
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
    lookahead: bool = False,
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
        # Inside a security() call Pine's `timeframe.*` refers to the requested
        # timeframe, not the chart's.
        chart_interval=_interval_label(target_min, chart_iv),
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

    chart_ts = parent_ctx.arrays.get("ts")
    htf_ts = htf_df["ts"].to_numpy(dtype="int64") if "ts" in htf_df.columns else None
    return align_htf_to_ltf(
        htf_arr,
        parent_ctx.n,
        factor,
        chart_ts=chart_ts,
        htf_ts=htf_ts,
        target_ms=target_min * _MIN_MS,
        lookahead=lookahead,
    )


def _interval_label(target_minutes: int, fallback: str) -> str:
    from .timeframe import minutes_to_interval

    try:
        return minutes_to_interval(target_minutes)
    except Exception:  # noqa: BLE001 — off-ladder TF: keep the chart's label
        return fallback
