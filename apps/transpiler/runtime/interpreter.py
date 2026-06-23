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
from .indicators import REGISTRY
from .mathfns import MATH, nz


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
    if isinstance(node, ast.IdentifierNode):
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


def _vectorize_builtin(node, ctx):
    ns, name = node.namespace, node.name
    argvals = [a.value for a in node.args]
    if ns == "ta" and name in REGISTRY:
        if name in ("crossover", "crossunder"):
            return REGISTRY[name](as_array(argvals[0], ctx), as_array(argvals[1], ctx))
        src = as_array(argvals[0], ctx)
        length = int(_const(argvals[1], ctx))
        return REGISTRY[name](src, length)
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
    raise NotVectorizable


# ----------------------------------------------------------------- scalar eval
def eval_scalar(node, ctx):
    i = ctx.bar_index
    if isinstance(node, ast.LiteralNode):
        return NA if node.type == "na" else node.value
    if isinstance(node, ast.IdentifierNode):
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


def _scalar_builtin(node, ctx):
    ns, name = node.namespace, node.name
    argvals = [a.value for a in node.args]
    if ns == "ta" and name in REGISTRY:
        return float(as_array(node, ctx)[ctx.bar_index])
    if ns == "math" and name in MATH:
        return MATH[name](*[eval_scalar(v, ctx) for v in argvals])
    if ns is None and name == "nz":
        rep = eval_scalar(argvals[1], ctx) if len(argvals) > 1 else 0.0
        return nz(eval_scalar(argvals[0], ctx), rep)
    if ns is None and name == "na":
        return is_na(eval_scalar(argvals[0], ctx))
    if ns == "strategy":
        return {"long": "long", "short": "short"}.get(name, NA)
    if ns == "syminfo":
        return NA
    return NA


def _truthy(v) -> bool:
    if is_na(v):
        return False
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return v != 0


# --------------------------------------------------------------------- bar loop
def vectorize_pass(program: ast.ProgramNode, ctx: ExecutionContext) -> None:
    """Phase A — precompute series-pure top-level assignments."""
    ctx._array_cache.clear()
    for stmt in program.body:
        if isinstance(stmt, ast.AssignNode) and not stmt.reassign:
            try:
                ctx.arrays[stmt.name] = as_array(stmt.value, ctx)
            except NotVectorizable:
                pass


def _drive_bar(program: ast.ProgramNode, ctx: ExecutionContext, bar_index: int) -> None:
    ctx.bar_index = bar_index
    for stmt in program.body:
        _exec(stmt, ctx)
    for buf in ctx.scalars.values():
        buf.commit()


def run_warmup(program: ast.ProgramNode, ctx: ExecutionContext) -> None:
    """Replay all bars to build indicator/scalar state without placing orders."""
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
    elif isinstance(node, ast.OrderExecutionNode):
        _exec_order(node, ctx)
    # bare expression statements have no side effects in the subset


def _exec_block(body, ctx):
    for s in body:
        _exec(s, ctx)


def _exec_order(node, ctx):
    pos = [a for a in node.args if a.name is None]
    kw = {a.name: a.value for a in node.args if a.name is not None}
    price = ctx.close_price
    i = ctx.bar_index

    def _qty():
        q = kw.get("qty")
        return eval_scalar(q, ctx) if q is not None else None

    if node.action == "entry":
        oid = eval_scalar(pos[0].value, ctx)
        direction = eval_scalar(pos[1].value, ctx) if len(pos) > 1 else "long"
        ctx.broker.entry(str(oid), direction, price, i, _qty())
    elif node.action == "close":
        oid = eval_scalar(pos[0].value, ctx) if pos else "long"
        ctx.broker.close(str(oid), price, i)
    elif node.action == "exit":
        oid = eval_scalar(pos[0].value, ctx) if pos else "exit"
        ctx.broker.exit(str(oid), price, i)
