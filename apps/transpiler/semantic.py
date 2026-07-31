"""Semantic analysis: scope tracking, type checking, restriction layer.

Runs after parsing and before execution. Three concerns:
  1. RestrictionLayer — reject UI/visual builtins that make no sense headless.
  2. Scope tracking — use-before-declare and `:=`-before-declare detection.
  3. Type management — a lightweight Pine type lattice; raises on clear
     mismatches (e.g. logical `and` applied to a float) while staying lenient
     where a type is genuinely unknown (avoids false positives on dynamic
     series).
"""
from __future__ import annotations

from . import ast_nodes as ast
from .exceptions import PineSemanticError, UnsupportedFeatureError
from .runtime.indicators import MULTI_REGISTRY, REGISTRY
from .runtime.mathfns import MATH

# Builtin price/series variables and their types.
BUILTIN_VARS = {
    "open": "float", "high": "float", "low": "float", "close": "float",
    "volume": "float", "hl2": "float", "hlc3": "float", "ohlc4": "float",
    "hlcc4": "float", "bar_index": "int", "time": "int", "na": "na",
}

# Plain (namespace-less) builtins that ARE supported.
ALLOWED_PLAIN = {"nz", "na", "input"}

# Plain builtins rejected as visual / non-headless (`plot` allowed as no-op).
FORBIDDEN_PLAIN = {
    "plotshape", "plotchar", "plotcandle", "plotbar", "plotarrow",
    "bgcolor", "barcolor", "hline", "fill", "alert", "alertcondition",
}

# Keyword args ignored for TradingView UI compatibility.
IGNORED_KWARGS = frozenset({
    "options", "minval", "maxval", "min", "max", "step",
    "title", "linewidth", "color", "overlay", "display",
})

# Whole namespaces rejected (drawing objects).
FORBIDDEN_NAMESPACES = {"label", "table", "box", "line"}

# Members the runtime actually implements, per namespace. Anything absent used to
# evaluate to `na` silently, so a script could trade on a nan-valued indicator
# with no error at any stage — see `_restrict`.
SUPPORTED_MEMBERS: dict[str, frozenset] = {
    "ta": frozenset(REGISTRY) | frozenset(MULTI_REGISTRY) | {"barssince", "valuewhen", "cum"},
    "math": frozenset(MATH),
    "str": frozenset({"tostring"}),
    "request": frozenset({"security"}),
    "timeframe": frozenset({"period", "multiplier"}),
    "syminfo": frozenset({"tickerid", "ticker", "currency"}),
    "input": frozenset({
        "int", "float", "bool", "string", "source", "default",
        "timeframe", "symbol", "price", "session", "color",
    }),
    "strategy": frozenset({
        "entry", "close", "close_all", "exit", "cancel", "cancel_all",
        "position_size", "equity", "openprofit", "long", "short",
        "percent_of_equity", "fixed", "cash", "contracts",
    }),
}

# Namespaces of opaque constants (`color.green`, `barmerge.lookahead_off`) — the
# runtime passes the member name through, so any member is harmless.
CONSTANT_NAMESPACES = {"color", "barmerge", "size", "shape", "location", "extend", "xloc", "yloc"}

INPUT_TYPES = {
    "int": "int", "float": "float", "bool": "bool", "string": "string",
    "source": "float", "default": "float",
}

BOOL_TA = {"crossover", "crossunder", "rising", "falling"}

NUMERIC = {"int", "float"}
LENIENT = {"unknown", "na"}


class _Scope:
    def __init__(self):
        self.names: dict[str, str] = {}


class SemanticAnalyzer:
    def __init__(self):
        self.scopes = [_Scope()]
        self.functions: dict[str, ast.FunctionDefNode] = {}

    def analyze(self, program: ast.ProgramNode) -> None:
        for fn in program.functions:
            if fn.name in self.functions:
                raise PineSemanticError(
                    f"function `{fn.name}` is already defined.",
                    fn.line, fn.column,
                )
            self.functions[fn.name] = fn

        for stmt in program.body:
            self._restrict(stmt)
        for fn in program.functions:
            for stmt in fn.body:
                self._restrict(stmt)

        for fn in program.functions:
            self._analyze_function(fn)
        for stmt in program.body:
            self._stmt(stmt)

    def _analyze_function(self, fn: ast.FunctionDefNode) -> None:
        self._push()
        for p in fn.params:
            self._declare(p, "float")
        for stmt in fn.body:
            self._stmt(stmt)
        self._pop()

    def _declare(self, name, type_):
        self.scopes[-1].names[name] = type_

    def _resolve(self, name):
        for scope in reversed(self.scopes):
            if name in scope.names:
                return scope.names[name]
        if name in BUILTIN_VARS:
            return BUILTIN_VARS[name]
        return None

    def _push(self):
        self.scopes.append(_Scope())

    def _pop(self):
        self.scopes.pop()

    def _restrict(self, node):
        if isinstance(node, ast.BuiltinFunctionNode):
            if node.namespace in FORBIDDEN_NAMESPACES:
                raise UnsupportedFeatureError(
                    f"`{node.namespace}.{node.name}` is not supported in a headless "
                    f"backend (drawing/visual only).",
                    node.line, node.column,
                )
            if node.namespace is None and node.name in FORBIDDEN_PLAIN:
                raise UnsupportedFeatureError(
                    f"`{node.name}()` is a chart-only function and is not supported "
                    f"in a headless backend.",
                    node.line, node.column,
                )
            self._check_supported(node)
        for child in _children(node):
            self._restrict(child)

    def _check_supported(self, node) -> None:
        """Reject builtins the runtime does not implement.

        Without this, an unknown member evaluates to `na` at every stage — the
        script compiles, backtests, and trades on a nan-valued series.
        """
        ns, name = node.namespace, node.name
        if ns is None:
            if name not in ALLOWED_PLAIN and name != "plot" and name not in self.functions:
                raise UnsupportedFeatureError(
                    f"`{name}()` is not a supported builtin or user-defined function.",
                    node.line, node.column,
                )
            return
        if ns in CONSTANT_NAMESPACES:
            return
        supported = SUPPORTED_MEMBERS.get(ns)
        if supported is None:
            raise UnsupportedFeatureError(
                f"the `{ns}` namespace is not supported.", node.line, node.column
            )
        if name not in supported:
            raise UnsupportedFeatureError(
                f"`{ns}.{name}` is not implemented by this transpiler.",
                node.line, node.column,
            )

    def _stmt(self, node):
        if isinstance(node, ast.StateDeclarationNode):
            t = self._expr(node.value)
            self._declare(node.name, t if t != "na" else "unknown")
        elif isinstance(node, ast.AssignNode):
            t = self._expr(node.value)
            if node.reassign and self._resolve(node.name) is None:
                raise PineSemanticError(
                    f"`{node.name}` is reassigned with `:=` before it is declared.",
                    node.line, node.column,
                )
            self._declare(node.name, t if t != "na" else "unknown")
        elif isinstance(node, ast.TupleAssignNode):
            self._tuple_assign(node)
        elif isinstance(node, ast.IfNode):
            self._require_bool(node.condition, "if condition")
            self._block(node.then_body)
            for cond, body in node.elif_clauses:
                self._require_bool(cond, "else if condition")
                self._block(body)
            if node.else_body is not None:
                self._block(node.else_body)
        elif isinstance(node, ast.ForNode):
            self._expr(node.start)
            self._expr(node.end)
            self._push()
            self._declare(node.var, "int")
            for s in node.body:
                self._stmt(s)
            self._pop()
        elif isinstance(node, ast.OrderExecutionNode):
            for arg in node.args:
                self._expr(arg.value)
        elif isinstance(node, ast.ExprStatementNode):
            self._expr(node.expr)
        else:
            self._expr(node)

    def _tuple_assign(self, node: ast.TupleAssignNode) -> None:
        if not isinstance(node.value, ast.BuiltinFunctionNode):
            raise PineSemanticError(
                "tuple assignment requires a multi-return builtin call on the right-hand side.",
                node.line, node.column,
            )
        call = node.value
        if call.namespace != "ta" or call.name not in MULTI_REGISTRY:
            raise PineSemanticError(
                f"`{call.namespace}.{call.name}` does not return a tuple.",
                node.line, node.column,
            )
        _, arity = MULTI_REGISTRY[call.name]
        if len(node.names) != arity:
            raise PineSemanticError(
                f"`ta.{call.name}` returns {arity} value(s), but {len(node.names)} name(s) "
                f"were given.",
                node.line, node.column,
            )
        for arg in call.args:
            self._expr(arg.value)
        for n in node.names:
            self._declare(n, "float")

    def _block(self, body):
        self._push()
        for s in body:
            self._stmt(s)
        self._pop()

    def _expr(self, node) -> str:
        if isinstance(node, ast.LiteralNode):
            return node.type
        if isinstance(node, ast.ArrayLiteralNode):
            for el in node.elements:
                self._expr(el)
            return "array"
        if isinstance(node, ast.IdentifierNode):
            t = self._resolve(node.name)
            if t is None:
                raise PineSemanticError(
                    f"`{node.name}` is used before it is declared.",
                    node.line, node.column,
                )
            return t
        if isinstance(node, ast.BinaryOpNode):
            return self._binop(node)
        if isinstance(node, ast.UnaryOpNode):
            if node.op == "not":
                self._require_bool(node.operand, "operand of `not`")
                return "bool"
            t = self._expr(node.operand)
            self._assert_numeric(t, node, "unary `-`")
            return "float" if t != "int" else "int"
        if isinstance(node, ast.TernaryNode):
            self._require_bool(node.condition, "ternary condition")
            a, b = self._expr(node.if_true), self._expr(node.if_false)
            return a if a == b else "unknown"
        if isinstance(node, ast.HistoryAccessNode):
            t = self._expr(node.series)
            self._expr(node.offset)
            return t
        if isinstance(node, ast.BuiltinFunctionNode):
            return self._builtin_type(node)
        return "unknown"

    def _binop(self, node) -> str:
        op = node.op
        lt, rt = self._expr(node.left), self._expr(node.right)
        if op in ("and", "or"):
            self._assert_bool(lt, node, f"left operand of `{op}`")
            self._assert_bool(rt, node, f"right operand of `{op}`")
            return "bool"
        if op in ("==", "!=", "<", ">", "<=", ">="):
            if op in ("<", ">", "<=", ">="):
                self._assert_numeric(lt, node, f"operand of `{op}`")
                self._assert_numeric(rt, node, f"operand of `{op}`")
            return "bool"
        if op == "+" and (lt == "string" or rt == "string"):
            return "string"
        self._assert_numeric(lt, node, f"operand of `{op}`")
        self._assert_numeric(rt, node, f"operand of `{op}`")
        return "int" if (lt == "int" and rt == "int") else "float"

    def _builtin_type(self, node) -> str:
        for arg in node.args:
            self._expr(arg.value)
        ns, name = node.namespace, node.name
        if ns == "ta":
            if name in BOOL_TA:
                return "bool"
            if name in MULTI_REGISTRY:
                return "tuple"
            return "float"
        if ns == "math":
            return "float"
        if ns == "input":
            return INPUT_TYPES.get(name, "unknown")
        if ns == "syminfo":
            return "string" if name in ("tickerid", "ticker", "currency") else "float"
        if ns == "str" and name == "tostring":
            return "string"
        if ns == "timeframe":
            return "int" if name == "multiplier" else "string"
        if ns == "color":
            return "color"
        if ns == "barmerge":
            return "unknown"
        if ns == "request" and name == "security":
            return "float"
        if ns == "strategy":
            return "float" if name in ("position_size", "equity", "openprofit") else "unknown"
        if ns is None:
            if name == "na":
                return "bool"
            if name == "nz":
                return "float"
            if name == "input":
                return "float"
            if name in self.functions:
                fn = self.functions[name]
                pos = [a for a in node.args if a.name is None]
                if len(pos) != len(fn.params):
                    raise PineSemanticError(
                        f"`{name}` expects {len(fn.params)} argument(s), got {len(pos)}.",
                        node.line, node.column,
                    )
                return "float"
        return "unknown"

    def _require_bool(self, node, what):
        self._assert_bool(self._expr(node), node, what)

    def _assert_bool(self, t, node, what):
        if t not in ("bool",) and t not in LENIENT:
            raise PineSemanticError(
                f"{what} must be boolean, got `{t}`.", node.line, node.column
            )

    def _assert_numeric(self, t, node, what):
        if t not in NUMERIC and t not in LENIENT:
            raise PineSemanticError(
                f"{what} must be numeric, got `{t}`.", node.line, node.column
            )


def _children(node):
    if isinstance(node, ast.ProgramNode):
        yield from node.body
        yield from node.functions
    elif isinstance(node, ast.FunctionDefNode):
        yield from node.body
    elif isinstance(node, ast.TupleAssignNode):
        yield node.value
    elif isinstance(node, ast.ExprStatementNode):
        yield node.expr
    elif isinstance(node, ast.StateDeclarationNode):
        yield node.value
    elif isinstance(node, ast.AssignNode):
        yield node.value
    elif isinstance(node, ast.IfNode):
        yield node.condition
        yield from node.then_body
        for cond, body in node.elif_clauses:
            yield cond
            yield from body
        if node.else_body:
            yield from node.else_body
    elif isinstance(node, ast.ForNode):
        yield node.start
        yield node.end
        yield from node.body
    elif isinstance(node, (ast.OrderExecutionNode, ast.BuiltinFunctionNode)):
        for arg in node.args:
            yield arg.value
    elif isinstance(node, ast.BinaryOpNode):
        yield node.left
        yield node.right
    elif isinstance(node, ast.UnaryOpNode):
        yield node.operand
    elif isinstance(node, ast.TernaryNode):
        yield node.condition
        yield node.if_true
        yield node.if_false
    elif isinstance(node, ast.HistoryAccessNode):
        yield node.series
        yield node.offset
    elif isinstance(node, ast.ArrayLiteralNode):
        yield from node.elements


def analyze(program: ast.ProgramNode) -> None:
    SemanticAnalyzer().analyze(program)
