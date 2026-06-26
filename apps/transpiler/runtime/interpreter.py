"""Bar-by-bar interpreter (the hybrid driver).

Phase A precomputes every series-pure top-level expression into a NumPy array
(`as_array`). Phase B walks bars; statements with state (`var`/`varip`/`:=`),
control flow, and orders are evaluated per bar via `eval_scalar`, indexing the
precomputed arrays. This gives vectorized indicator speed with correct Pine
state/`[]`/order semantics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import ast_nodes as ast
from .context import NA, ExecutionContext, SeriesBuffer, is_na
from .indicators import MULTI_REGISTRY, REGISTRY
from .mathfns import MATH, nz
from .security import evaluate_security
from .timeframe import pine_multiplier, pine_period

_MAX_UDF_DEPTH = 64


class NotVectorizable(Exception):
    """Raised when an expression depends on per-bar state and can't be precomputed."""


# ---------------------------------------------------------------- vectorization
def as_array(node, ctx) -> np.ndarray:
    cached = ctx._array_cache.get(id(node))
    if cached is not None:
        return cached
    arr = _vectorize(node, ctx)
    ctx._array_cache[id(node)] = arr
    return arr


def _const(node, ctx):
    return eval_scalar(node, ctx)


def _vectorize(node, ctx) -> np.ndarray:
    n = ctx.n
    if isinstance(node, ast.LiteralNode):
        if node.type == "na":
            return np.full(n, NA)
        if node.type == "bool":
            return np.full(n, node.value, dtype=bool)
        if node.type in ("int", "float"):
            return np.full(n, float(node.value))
        raise NotVectorizable
    if isinstance(node, ast.ArrayLiteralNode):
        raise NotVectorizable
    if isinstance(node, ast.IdentifierNode):
        if node.name == "na":
            return np.full(n, NA)
        if node.name in ctx.arrays:
            return ctx.arrays[node.name]
        if node.name == "bar_index":
            return np.arange(n, dtype="float64")
        raise NotVectorizable  # scalar/state variable
    if isinstance(node, ast.HistoryAccessNode):
        arr = as_array(node.series, ctx).astype("float64")
        k = int(_const(node.offset, ctx))
        return pd.Series(arr).shift(k).to_numpy()
    if isinstance(node, ast.UnaryOpNode):
        v = as_array(node.operand, ctx)
        return np.logical_not(_as_bool(v)) if node.op == "not" else -v
    if isinstance(node, ast.BinaryOpNode):
        return _vectorize_binop(node, ctx)
    if isinstance(node, ast.TernaryNode):
        cond = _as_bool(as_array(node.condition, ctx))
        return np.where(cond, as_array(node.if_true, ctx), as_array(node.if_false, ctx))
    if isinstance(node, ast.BuiltinFunctionNode):
        return _vectorize_builtin(node, ctx)
    raise NotVectorizable


def _as_bool(arr):
    if arr.dtype == bool:
        return arr
    return np.nan_to_num(arr, nan=0.0) != 0.0


def _vectorize_binop(node, ctx):
    op = node.op
    l, r = as_array(node.left, ctx), as_array(node.right, ctx)
    if op == "and":
        return np.logical_and(_as_bool(l), _as_bool(r))
    if op == "or":
        return np.logical_or(_as_bool(l), _as_bool(r))
    if op == "==":
        return l == r
    if op == "!=":
        return l != r
    if op == "<":
        return l < r
    if op == ">":
        return l > r
    if op == "<=":
        return l <= r
    if op == ">=":
        return l >= r
    if op == "+":
        if isinstance(node.left, ast.LiteralNode) and node.left.type == "string":
            raise NotVectorizable
        if isinstance(node.right, ast.LiteralNode) and node.right.type == "string":
            raise NotVectorizable
        return l + r
    if op == "-":
        return l - r
    if op == "*":
        return l * r
    if op == "/":
        return l / r
    if op == "%":
        return np.mod(l, r)
    raise NotVectorizable


def _state_key(node) -> tuple:
    return (node.line, node.column, node.namespace, node.name)


def _input_default(node, ctx):
    """Resolve an input.*() or bare input() call to its default constant."""
    kind = node.name if node.namespace == "input" else "float"
    kw = {a.name: a.value for a in node.args if a.name is not None}
    pos = [a.value for a in node.args if a.name is None]
    if "defval" in kw:
        return eval_scalar(kw["defval"], ctx)
    if pos:
        return eval_scalar(pos[0], ctx)
    if kind == "source":
        return ctx.close_price
    if kind == "bool":
        return False
    if kind == "string":
        return ""
    if kind == "int":
        return 0
    return 0.0


def _input_default_vector(node, ctx):
    kind = node.name if node.namespace == "input" else "float"
    kw = {a.name: a.value for a in node.args if a.name is not None}
    pos = [a.value for a in node.args if a.name is None]
    if "defval" in kw:
        return _const(kw["defval"], ctx)
    if pos:
        return _const(pos[0], ctx)
    if kind == "source":
        return ctx.arrays["close"]
    if kind == "bool":
        return False
    if kind == "string":
        raise NotVectorizable
    if kind == "int":
        return 0
    return 0.0


def _vectorize_ta(name, argvals, ctx):
    if name == "tr":
        return REGISTRY[name](ctx.arrays["high"], ctx.arrays["low"], ctx.arrays["close"])
    if name == "atr":
        length = int(_const(argvals[0], ctx))
        return REGISTRY[name](ctx.arrays["high"], ctx.arrays["low"], ctx.arrays["close"], length)
    if name == "vwap":
        src = as_array(argvals[0], ctx) if argvals else ctx.arrays["hlc3"]
        return REGISTRY[name](src, ctx.arrays["volume"])
    if name == "vwma":
        length = int(_const(argvals[1], ctx))
        return REGISTRY[name](as_array(argvals[0], ctx), ctx.arrays["volume"], length)
    if name in ("crossover", "crossunder"):
        return REGISTRY[name](as_array(argvals[0], ctx), as_array(argvals[1], ctx))
    if name == "change" and len(argvals) == 1:
        return REGISTRY[name](as_array(argvals[0], ctx), 1)
    if name in ("change", "mom", "roc", "stdev", "variance", "cci", "wma", "hma", "rising", "falling"):
        return REGISTRY[name](as_array(argvals[0], ctx), int(_const(argvals[1], ctx)))
    src = as_array(argvals[0], ctx)
    length = int(_const(argvals[1], ctx))
    return REGISTRY[name](src, length)


def _vectorize_builtin(node, ctx):
    ns, name = node.namespace, node.name
    argvals = [a.value for a in node.args]
    if ns == "ta":
        if name in MULTI_REGISTRY or name in ("barssince", "valuewhen", "cum"):
            raise NotVectorizable
        if name in REGISTRY:
            return _vectorize_ta(name, argvals, ctx)
        raise NotVectorizable
    if ns == "input" or (ns is None and name == "input"):
        default = _input_default_vector(node, ctx)
        n = ctx.n
        if isinstance(default, str):
            raise NotVectorizable
        if isinstance(default, np.ndarray):
            return default.astype("float64")
        if isinstance(default, bool):
            return np.full(n, default, dtype=bool)
        return np.full(n, float(default))
    if ns is None and name in ctx.functions:
        raise NotVectorizable
    if ns == "math":
        a = [as_array(v, ctx) for v in argvals]
        if name == "abs":
            return np.abs(a[0])
        if name == "sqrt":
            return np.sqrt(a[0])
        if name == "floor":
            return np.floor(a[0])
        if name == "ceil":
            return np.ceil(a[0])
        if name == "sign":
            return np.sign(a[0])
        if name == "log":
            return np.log(a[0])
        if name == "log10":
            return np.log10(a[0])
        if name == "exp":
            return np.exp(a[0])
        if name == "max":
            return np.maximum.reduce(a)
        if name == "min":
            return np.minimum.reduce(a)
        if name == "pow":
            return np.power(a[0], a[1])
        if name == "round":
            ndig = int(_const(argvals[1], ctx)) if len(argvals) > 1 else 0
            return np.round(a[0], ndig)
    if ns is None and name == "nz":
        a = as_array(argvals[0], ctx).astype("float64")
        rep = float(_const(argvals[1], ctx)) if len(argvals) > 1 else 0.0
        return np.where(np.isnan(a), rep, a)
    if ns is None and name == "na":
        return np.isnan(as_array(argvals[0], ctx).astype("float64"))
    if ns is None and name == "plot":
        return np.full(ctx.n, NA)
    if ns == "request" and name == "security":
        if ctx.program is None or len(argvals) < 3:
            raise NotVectorizable
        tf_str = str(_const(argvals[1], ctx))
        return evaluate_security(ctx.program, ctx, expr=argvals[2], tf_str=tf_str)
    if ns == "strategy" and name in ("position_size", "equity", "openprofit"):
        raise NotVectorizable
    raise NotVectorizable


# ----------------------------------------------------------------- scalar eval
def eval_scalar(node, ctx):
    i = ctx.bar_index
    if isinstance(node, ast.LiteralNode):
        return NA if node.type == "na" else node.value
    if isinstance(node, ast.ArrayLiteralNode):
        return [eval_scalar(el, ctx) for el in node.elements]
    if isinstance(node, ast.IdentifierNode):
        if node.name == "na":
            return NA
        if node.name in ctx.scalars:
            return ctx.scalars[node.name].current
        if node.name in ctx.arrays:
            return float(ctx.arrays[node.name][i])
        if node.name == "bar_index":
            return i
        return NA
    if isinstance(node, ast.HistoryAccessNode):
        k = int(eval_scalar(node.offset, ctx))
        if isinstance(node.series, ast.IdentifierNode) and node.series.name in ctx.scalars:
            return ctx.scalars[node.series.name].get(k)
        arr = as_array(node.series, ctx)
        idx = i - k
        return float(arr[idx]) if 0 <= idx < len(arr) else NA
    if isinstance(node, ast.UnaryOpNode):
        v = eval_scalar(node.operand, ctx)
        if node.op == "not":
            return not _truthy(v)
        return NA if is_na(v) else -v
    if isinstance(node, ast.BinaryOpNode):
        return _scalar_binop(node, ctx)
    if isinstance(node, ast.TernaryNode):
        return eval_scalar(
            node.if_true if _truthy(eval_scalar(node.condition, ctx)) else node.if_false,
            ctx,
        )
    if isinstance(node, ast.BuiltinFunctionNode):
        return _scalar_builtin(node, ctx)
    return NA


def _scalar_binop(node, ctx):
    op = node.op
    if op in ("and", "or"):
        l = _truthy(eval_scalar(node.left, ctx))
        r = _truthy(eval_scalar(node.right, ctx))
        return (l and r) if op == "and" else (l or r)
    l, r = eval_scalar(node.left, ctx), eval_scalar(node.right, ctx)
    if op == "+" and (isinstance(l, str) or isinstance(r, str)):
        return f"{l}{r}"
    if is_na(l) or is_na(r):
        if op in ("==", "!=", "<", ">", "<=", ">="):
            return False
        return NA
    return _ARITH[op](l, r)


_ARITH = {
    "+": lambda a, b: a + b, "-": lambda a, b: a - b,
    "*": lambda a, b: a * b, "/": lambda a, b: a / b,
    "%": lambda a, b: a % b,
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b, ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
}


def _scalar_series_value(node, ctx, offset: int = 0):
    if isinstance(node, ast.IdentifierNode):
        if node.name in ctx.scalars:
            return ctx.scalars[node.name].get(offset) if offset else ctx.scalars[node.name].current
        if node.name in ctx.arrays:
            idx = ctx.bar_index - offset
            return float(ctx.arrays[node.name][idx]) if idx >= 0 else NA
    if offset == 0:
        return eval_scalar(node, ctx)
    if isinstance(node, ast.HistoryAccessNode):
        k = int(eval_scalar(node.offset, ctx))
        return _scalar_series_value(node.series, ctx, k)
    return NA


def _scalar_ta_simple(name: str, argvals, ctx):
    """Scalar `ta.*` for UDF params backed by SeriesBuffer (no full-series vectorize)."""
    if len(argvals) < 2:
        return None
    length = int(eval_scalar(argvals[1], ctx))
    src_node = argvals[0]
    if not isinstance(src_node, ast.IdentifierNode) or src_node.name not in ctx.scalars:
        return None
    buf = ctx.scalars[src_node.name]
    vals = [v for v in buf.values if not is_na(v)]
    cur = buf.current
    if not is_na(cur):
        vals.append(cur)
    if len(vals) < length:
        return NA
    window = np.asarray(vals[-length:], dtype="float64")
    if name == "sma":
        return float(window.mean())
    if name == "ema":
        return float(pd.Series(window).ewm(span=length, adjust=False).mean().iloc[-1])
    if name == "wma":
        weights = np.arange(1, length + 1, dtype="float64")
        return float(np.dot(window, weights) / weights.sum())
    if name == "rma":
        return float(pd.Series(window).ewm(alpha=1.0 / length, adjust=False).mean().iloc[-1])
    return None


def _scalar_cross(name: str, a_node, b_node, ctx) -> bool:
    a_cur = _scalar_series_value(a_node, ctx, 0)
    b_cur = _scalar_series_value(b_node, ctx, 0)
    a_prev = _scalar_series_value(a_node, ctx, 1)
    b_prev = _scalar_series_value(b_node, ctx, 1)
    if is_na(a_cur) or is_na(b_cur) or is_na(a_prev) or is_na(b_prev):
        return False
    if name == "crossover":
        return a_prev <= b_prev and a_cur > b_cur
    return a_prev >= b_prev and a_cur < b_cur


def _eval_multi_ta(node: ast.BuiltinFunctionNode, ctx) -> tuple:
    name = node.name
    fn, _ = MULTI_REGISTRY[name]
    argvals = [a.value for a in node.args]
    i = ctx.bar_index
    if name == "macd":
        results = fn(
            as_array(argvals[0], ctx),
            int(_const(argvals[1], ctx)),
            int(_const(argvals[2], ctx)),
            int(_const(argvals[3], ctx)),
        )
    elif name == "bb":
        results = fn(
            as_array(argvals[0], ctx),
            int(_const(argvals[1], ctx)),
            float(_const(argvals[2], ctx)),
        )
    elif name == "stoch":
        results = fn(
            as_array(argvals[0], ctx),
            as_array(argvals[1], ctx),
            as_array(argvals[2], ctx),
            int(_const(argvals[3], ctx)),
        )
    else:
        raise NotVectorizable
    return tuple(float(r[i]) for r in results)


def _scalar_ta_stateful(node, ctx, argvals):
    name = node.name
    key = _state_key(node)
    if name == "barssince":
        cond = _truthy(eval_scalar(argvals[0], ctx))
        st = ctx.bar_state.setdefault(key, {"last_true": None})
        if cond:
            st["last_true"] = ctx.bar_index
        if st["last_true"] is None:
            return NA
        return float(ctx.bar_index - st["last_true"])
    if name == "valuewhen":
        cond = _truthy(eval_scalar(argvals[0], ctx))
        src = eval_scalar(argvals[1], ctx)
        occ = int(eval_scalar(argvals[2], ctx)) if len(argvals) > 2 else 0
        st = ctx.bar_state.setdefault(key, {"hits": []})
        if cond and not is_na(src):
            st["hits"].append(src)
        if len(st["hits"]) <= occ:
            return NA
        return st["hits"][-(occ + 1)]
    if name == "cum":
        src = eval_scalar(argvals[0], ctx)
        st = ctx.bar_state.setdefault(key, {"sum": 0.0})
        if not is_na(src):
            st["sum"] += float(src)
        return st["sum"]
    return NA


def _bind_udf_param(ctx, arg_node, value) -> SeriesBuffer:
    """Bind a UDF parameter; series identifiers get bar history from ``ctx.arrays``."""
    buf = SeriesBuffer()
    if isinstance(arg_node, ast.IdentifierNode) and arg_node.name in ctx.arrays:
        arr = ctx.arrays[arg_node.name]
        i = ctx.bar_index
        buf.values = [float(arr[j]) for j in range(i)]
        buf.current = float(arr[i])
    else:
        buf.current = value
    return buf


def _call_user_function(name: str, arg_nodes, ctx) -> object:
    fn = ctx.functions[name]
    depth = ctx.bar_state.get("_udf_depth", 0)
    if depth >= _MAX_UDF_DEPTH:
        raise RuntimeError("maximum UDF recursion depth exceeded")
    args = [eval_scalar(v, ctx) for v in arg_nodes]
    saved: dict[str, SeriesBuffer | None] = {}
    for param, arg_node, value in zip(fn.params, arg_nodes, args):
        buf = _bind_udf_param(ctx, arg_node, value)
        saved[param] = ctx.scalars.get(param)
        ctx.scalars[param] = buf
    ctx.bar_state["_udf_depth"] = depth + 1
    try:
        for stmt in fn.body[:-1]:
            _exec(stmt, ctx)
        last = fn.body[-1]
        if isinstance(last, ast.ExprStatementNode):
            return eval_scalar(last.expr, ctx)
        if isinstance(last, ast.AssignNode):
            _exec(last, ctx)
            return ctx.scalars[last.name].current
        if not isinstance(
            last,
            (ast.StateDeclarationNode, ast.IfNode, ast.ForNode, ast.OrderExecutionNode, ast.TupleAssignNode),
        ):
            return eval_scalar(last, ctx)
        _exec(last, ctx)
        return NA
    finally:
        ctx.bar_state["_udf_depth"] = depth
        for param, prev in saved.items():
            if prev is None:
                ctx.scalars.pop(param, None)
            else:
                ctx.scalars[param] = prev


def _scalar_builtin(node, ctx):
    ns, name = node.namespace, node.name
    argvals = [a.value for a in node.args]
    if ns == "ta" and name in ("crossover", "crossunder"):
        return _scalar_cross(name, argvals[0], argvals[1], ctx)
    if ns == "ta" and name in MULTI_REGISTRY:
        return _eval_multi_ta(node, ctx)
    if ns == "ta" and name in ("barssince", "valuewhen", "cum"):
        return _scalar_ta_stateful(node, ctx, argvals)
    if ns == "ta" and name in REGISTRY:
        simple = _scalar_ta_simple(name, argvals, ctx)
        if simple is not None:
            return simple
        return float(as_array(node, ctx)[ctx.bar_index])
    if ns == "input" or (ns is None and name == "input"):
        return _input_default(node, ctx)
    if ns is None and name in ctx.functions:
        return _call_user_function(name, argvals, ctx)
    if ns == "math" and name in MATH:
        return MATH[name](*[eval_scalar(v, ctx) for v in argvals])
    if ns is None and name == "nz":
        rep = eval_scalar(argvals[1], ctx) if len(argvals) > 1 else 0.0
        return nz(eval_scalar(argvals[0], ctx), rep)
    if ns is None and name == "na":
        return is_na(eval_scalar(argvals[0], ctx))
    if ns is None and name == "plot":
        return NA
    if ns == "str" and name == "tostring":
        v = eval_scalar(argvals[0], ctx)
        if is_na(v):
            return ""
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v)
    if ns == "timeframe":
        if name == "multiplier":
            return pine_multiplier(ctx.chart_interval or "1h")
        if name == "period":
            return pine_period(ctx.chart_interval or "1h")
    if ns == "color":
        return name
    if ns == "barmerge":
        return name
    if ns == "request" and name == "security":
        if ctx.program is None or len(argvals) < 3:
            return NA
        arr = as_array(node, ctx)
        return float(arr[ctx.bar_index])
    if ns == "strategy":
        if name == "position_size":
            fn = getattr(ctx.broker, "position_size", None)
            return float(fn()) if fn else NA
        if name == "equity":
            fn = getattr(ctx.broker, "equity", None)
            return float(fn(ctx.close_price)) if fn else NA
        if name == "openprofit":
            fn = getattr(ctx.broker, "open_profit", None)
            return float(fn(ctx.close_price)) if fn else NA
        return {"long": "long", "short": "short"}.get(name, NA)
    if ns == "syminfo":
        sym = ctx.symbol or ""
        if name == "tickerid":
            return f"{sym}USDT" if sym and "USDT" not in sym.upper() else sym
        if name == "ticker":
            return sym
        if name == "currency":
            return "USDT"
    return NA


def _truthy(v) -> bool:
    if is_na(v):
        return False
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return v != 0


# --------------------------------------------------------------------- bar loop
def _vectorize_tuple_assign(node: ast.TupleAssignNode, ctx) -> None:
    call = node.value
    if not isinstance(call, ast.BuiltinFunctionNode) or call.namespace != "ta":
        raise NotVectorizable
    name = call.name
    if name not in MULTI_REGISTRY:
        raise NotVectorizable
    fn, _ = MULTI_REGISTRY[name]
    argvals = [a.value for a in call.args]
    if name == "macd":
        results = fn(
            as_array(argvals[0], ctx),
            int(_const(argvals[1], ctx)),
            int(_const(argvals[2], ctx)),
            int(_const(argvals[3], ctx)),
        )
    elif name == "bb":
        results = fn(
            as_array(argvals[0], ctx),
            int(_const(argvals[1], ctx)),
            float(_const(argvals[2], ctx)),
        )
    elif name == "stoch":
        results = fn(
            as_array(argvals[0], ctx),
            as_array(argvals[1], ctx),
            as_array(argvals[2], ctx),
            int(_const(argvals[3], ctx)),
        )
    else:
        raise NotVectorizable
    for var_name, arr in zip(node.names, results):
        ctx.arrays[var_name] = np.asarray(arr, dtype="float64")


def vectorize_pass(program: ast.ProgramNode, ctx: ExecutionContext) -> None:
    """Phase A — precompute series-pure top-level assignments."""
    ctx._array_cache.clear()
    for stmt in program.body:
        if isinstance(stmt, ast.TupleAssignNode):
            try:
                _vectorize_tuple_assign(stmt, ctx)
            except NotVectorizable:
                pass
        elif isinstance(stmt, ast.AssignNode) and not stmt.reassign:
            try:
                ctx.arrays[stmt.name] = as_array(stmt.value, ctx)
            except NotVectorizable:
                pass


def _drive_bar(program: ast.ProgramNode, ctx: ExecutionContext, bar_index: int) -> None:
    ctx.bar_index = bar_index
    on_bar = getattr(ctx.broker, "on_bar", None)
    if on_bar:
        ts_arr = ctx.arrays.get("ts")
        ts = int(ts_arr[bar_index]) if ts_arr is not None and bar_index < len(ts_arr) else bar_index
        o = float(ctx.arrays["open"][bar_index])
        h = float(ctx.arrays["high"][bar_index])
        l = float(ctx.arrays["low"][bar_index])
        c = float(ctx.arrays["close"][bar_index])
        on_bar(bar_index, ts, o, h, l, c)
    for stmt in program.body:
        _exec(stmt, ctx)
    for buf in ctx.scalars.values():
        buf.commit()


def run_warmup(program: ast.ProgramNode, ctx: ExecutionContext) -> None:
    """Replay all bars to build indicator/scalar state without placing orders."""
    ctx.functions = {f.name: f for f in program.functions}
    ctx.bar_state.clear()
    vectorize_pass(program, ctx)
    for i in range(ctx.n):
        _drive_bar(program, ctx, i)
    if ctx.n:
        last = ctx.n - 1
        last_price = float(ctx.arrays["close"][last])
        ctx.broker.finalize(last_price, last)


def run_bar(program: ast.ProgramNode, ctx: ExecutionContext, bar_index: int) -> None:
    """Re-vectorize on the current window and execute a single bar."""
    vectorize_pass(program, ctx)
    _drive_bar(program, ctx, bar_index)


def run(program: ast.ProgramNode, ctx: ExecutionContext):
    ctx.functions = {f.name: f for f in program.functions}
    ctx.bar_state.clear()
    vectorize_pass(program, ctx)
    for i in range(ctx.n):
        _drive_bar(program, ctx, i)

    last = ctx.n - 1
    last_price = float(ctx.arrays["close"][last]) if ctx.n else 0.0
    ctx.broker.finalize(last_price, last)


def _exec(node, ctx):
    if isinstance(node, ast.AssignNode):
        if not node.reassign and node.name in ctx.arrays:
            return  # already vectorized in Phase A
        buf = ctx.scalars.setdefault(node.name, SeriesBuffer())
        buf.current = eval_scalar(node.value, ctx)
    elif isinstance(node, ast.StateDeclarationNode):
        buf = ctx.scalars.get(node.name)
        if buf is None:  # first bar: initialise once
            buf = SeriesBuffer()
            ctx.scalars[node.name] = buf
            buf.current = eval_scalar(node.value, ctx)
        else:  # subsequent bars: persist previous value
            buf.current = buf.values[-1] if buf.values else buf.current
    elif isinstance(node, ast.IfNode):
        if _truthy(eval_scalar(node.condition, ctx)):
            _exec_block(node.then_body, ctx)
            return
        for cond, body in node.elif_clauses:
            if _truthy(eval_scalar(cond, ctx)):
                _exec_block(body, ctx)
                return
        if node.else_body is not None:
            _exec_block(node.else_body, ctx)
    elif isinstance(node, ast.ForNode):
        start = int(eval_scalar(node.start, ctx))
        end = int(eval_scalar(node.end, ctx))
        buf = ctx.scalars.setdefault(node.var, SeriesBuffer())
        for v in range(start, end + 1):
            buf.current = float(v)
            _exec_block(node.body, ctx)
    elif isinstance(node, ast.TupleAssignNode):
        if all(n in ctx.arrays for n in node.names):
            return
        vals = _eval_multi_ta(node.value, ctx)
        for var_name, val in zip(node.names, vals):
            buf = ctx.scalars.setdefault(var_name, SeriesBuffer())
            buf.current = val
    elif isinstance(node, ast.OrderExecutionNode):
        _exec_order(node, ctx)
    elif isinstance(node, ast.ExprStatementNode):
        pass
    elif isinstance(node, ast.BuiltinFunctionNode):
        if node.namespace is None and node.name == "plot":
            pass
    elif isinstance(node, ast.FunctionDefNode):
        pass


def _exec_block(body, ctx):
    for s in body:
        _exec(s, ctx)


def _exec_order(node, ctx):
    pos = [a for a in node.args if a.name is None]
    kw = {a.name: a.value for a in node.args if a.name is not None}
    i = ctx.bar_index
    # Backtest brokers fill at the next bar's open ("placed at bar i close,
    # executed at i+1 open"). A signal on the final bar has no next bar -> no fill.
    if getattr(ctx.broker, "fill_at_next_open", False):
        if i + 1 >= ctx.n:
            return
        price = float(ctx.arrays["open"][i + 1])
        i = i + 1
    else:
        price = ctx.close_price

    def _qty():
        q = kw.get("qty")
        return eval_scalar(q, ctx) if q is not None else None

    def _kw_float(name: str):
        v = kw.get(name)
        return float(eval_scalar(v, ctx)) if v is not None else None

    def _alert_payload(direction: str):
        alert_node = kw.get("alert_message")
        if alert_node is None:
            return None
        template = eval_scalar(alert_node, ctx)
        if not isinstance(template, str):
            return None
        action = "buy" if str(direction).lower() in ("long", "strategy.long") else "sell"
        ts_arr = ctx.arrays.get("ts")
        ts_ms = int(ts_arr[ctx.bar_index]) if ts_arr is not None and ctx.bar_index < len(ts_arr) else 0
        pos_fn = getattr(ctx.broker, "position_size", None)
        pos_size = float(pos_fn()) if pos_fn else 0.0
        strategy = getattr(ctx.broker, "strategy", None)
        user = getattr(strategy, "user", None) if strategy else None
        from apps.integrations.signum import build_signum_payload

        return build_signum_payload(
            template,
            user=user,
            action=action,
            ticker=ctx.symbol or "",
            position_size=pos_size,
            timestamp_ms=ts_ms,
        )

    if node.action == "entry":
        oid = eval_scalar(pos[0].value, ctx)
        direction = eval_scalar(pos[1].value, ctx) if len(pos) > 1 else "long"
        alert = _alert_payload(str(direction))
        ctx.broker.entry(
            str(oid),
            direction,
            price,
            i,
            _qty(),
            limit=_kw_float("limit"),
            alert_message=alert,
        )
    elif node.action == "close":
        oid = eval_scalar(pos[0].value, ctx) if pos else "long"
        ctx.broker.close(str(oid), price, i)
    elif node.action == "exit":
        oid = eval_scalar(pos[0].value, ctx) if pos else "exit"
        ctx.broker.exit(str(oid), price, i, stop=_kw_float("stop"), limit=_kw_float("limit"))
