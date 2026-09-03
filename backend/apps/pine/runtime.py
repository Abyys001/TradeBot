"""Bars in, ``StrategyIntent`` out. No I/O, no Django, no clock that changes the answer.

The runtime is the same object in a backtest and in a live run. That is the
whole argument of Phase 4: if the two ever produce different intents from the
same bars, it is a bug in the *feed* or the *driver*, never a difference between
two implementations of Pine, because there is only one.

Three decisions inside deserve reading before changing anything here.

**The driver owns position state.** ``strategy.position_size``,
``.position_avg_price``, ``.equity`` and ``.netprofit`` are not simulated in
here — the driver (``apps.bots.backtest`` or the supervisor) calls
``sync_position`` before each bar with what is actually true. A runtime that
kept its own idea of the position would be a second source of truth alongside
the exchange, and this codebase already has a rule about that.

``position_size`` is therefore a **direction**, +1 / -1 / 0, not a quantity.
Under Q20 the platform sizes each account at 99% of *its own* balance, so there
is no single number that is true across accounts; a script asking
``strategy.position_size > 0`` gets the right answer and a script doing
arithmetic on it is asking a question this platform cannot answer.

**Every registered ``ta.*`` call site advances on every bar.** A site inside a
branch that did not run is advanced at the end of the bar with its arguments
evaluated in the global scope, and its value discarded. A strategy whose EMA
only updates on the days it is used is a different strategy from the one that
was backtested. See ``_advance_untouched``.

**Determinism is a property, not an aspiration.** No wall-clock read reaches a
value; ``math.random`` comes from a per-run seeded generator whose seed is
recorded with the run. The per-bar time budget is the one clock read, it is
opt-in, and it can only stop a run — never change what a bar produced.
"""

from __future__ import annotations

import copy
import random
import time as _time
from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation

from apps.pine import ast_nodes as ast
from apps.pine import builtins as bi
from apps.pine import ta as ta_lib
from apps.pine.bar import Bar
from apps.pine.errors import PineNameError, PineRuntimeError
from apps.pine.intent import Annotation, Side, StrategyIntent
from apps.pine.limits import DEFAULT_LIMITS, Limits
from apps.pine.objects import EnumType, EnumValue, PineObject
from apps.pine.series import NA, Series, is_na
from apps.pine.subset import BUILTIN_SERIES, DECORATIVE_NAMESPACES, VISUAL_FUNCTIONS
from apps.pine.tokens import Span

ZERO = Decimal("0")

#: ``_member_base`` / ``_call`` sentinel: the thing before the dot is a
#: namespace (``ta``, ``math``, ``strategy`` …), not a value we hold.
_NOT_A_VALUE = object()
_MISSING = object()

#: Which declared receiver types a runtime value satisfies, for method
#: overload resolution. A UDT matches its own name only.
_PRIMITIVE_RECEIVERS: dict[type, frozenset[str]] = {
    bool: frozenset({"bool"}),
    str: frozenset({"string", "color"}),
    Decimal: frozenset({"int", "float"}),
}


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


@dataclass(slots=True)
class BarState:
    isfirst: bool = False
    islast: bool = False
    isconfirmed: bool = True  # Q23: this platform only ever sees closed bars.
    isnew: bool = True
    ishistory: bool = False

    @property
    def isrealtime(self) -> bool:
        return not self.ishistory


@dataclass(slots=True)
class BarResult:
    """One evaluated bar: what the strategy wants, and what it drew."""

    intent: StrategyIntent
    annotations: list[Annotation] = field(default_factory=list)
    #: Wall-clock milliseconds spent in ``run_bar``. Reported, and compared
    #: against the budget only when the driver asks for it.
    elapsed_ms: float = 0.0


class RunContext:
    """The mutable half — bar, scopes, indicator state, per-bar accumulators."""

    __slots__ = (
        "bar",
        "bar_index",
        "state",
        "series",
        "globals",
        "locals",
        "call_path",
        "indicators",
        "outputs",
        "touched",
        "ta_pushed",
        "random",
        "scratch",
        "current_call_id",
        "plots",
        "alerts",
        "annotations",
        "desired_side",
        "reason",
        "order_span",
        "sl_pct",
        "tp_pct",
        "position_size",
        "position_avg_price",
        "equity",
        "netprofit",
        "opentrades",
        "limits",
    )

    def __init__(self, *, limits: Limits, seed: int) -> None:
        self.limits = limits
        self.bar: Bar | None = None
        self.bar_index = -1
        self.state = BarState()
        self.series: dict[str, Series] = {
            name: Series(limits.series_depth) for name in BUILTIN_SERIES
        }
        self.globals: dict[str, Series] = {}
        self.locals: list[dict] = []
        #: The user-function call sites currently on the stack, innermost last.
        #: Identity for `_ta_key`, and deliberately **not** `locals`: a block
        #: scope is not a separate logical call site, and its dict is a new
        #: object every bar — keying on that gave every `ta.*` inside an `if` a
        #: brand new indicator per bar, which is `na` forever.
        self.call_path: tuple[str, ...] = ()
        self.indicators: dict[str, ta_lib.Indicator] = {}
        #: Each ``ta.*`` site's own past values, so ``ta.rsi(close, 14)[1]``
        #: reads the previous bar's reading instead of ``na``. Keyed the same
        #: way ``indicators`` is — see ``_ta_key``.
        self.outputs: dict[str, Series] = {}
        self.touched: set[str] = set()
        self.ta_pushed: set[str] = set()
        self.random = random.Random(seed)
        self.scratch: dict = {}
        self.current_call_id = ""
        self.plots: dict[str, object] = {}
        self.alerts: list[str] = []
        self.annotations: list[Annotation] = []
        self.desired_side: Side | None = None
        self.reason = ""
        self.order_span: Span | None = None
        self.sl_pct: Decimal | None = None
        self.tp_pct: Decimal | None = None
        self.position_size = 0
        self.position_avg_price: Decimal | None = None
        self.equity = ZERO
        self.netprofit = ZERO
        self.opentrades = 0

    def builtin(self, name: str):
        return self.series[name].value


class Runtime:
    """One loaded strategy, ready to be fed bars."""

    def __init__(
        self,
        program: ast.Program,
        *,
        symbol: str,
        inputs: dict | None = None,
        limits: Limits = DEFAULT_LIMITS,
        seed: int = 0,
    ) -> None:
        self.program = program
        self.symbol = symbol
        self.input_values = dict(inputs or {})
        self.limits = limits
        self.seed = seed
        self.functions = {fn.name: fn for fn in program.functions}
        self.types = {t.name: t for t in program.types}
        self.enums = {e.name: EnumType.from_def(e) for e in program.enums}
        #: method name -> its overloads, ordered by declaration. Dispatch picks
        #: the one whose ``receiver_type`` matches the receiver's runtime type.
        self.methods: dict[str, list[ast.MethodDef]] = {}
        for method in program.methods:
            self.methods.setdefault(method.name, []).append(method)
        self.ctx = RunContext(limits=limits, seed=seed)
        #: ``ta.*`` sites the end-of-bar sweep is responsible for. Registered in
        #: one AST walk at load, in source order.
        self.stateful_sites: list[ast.Call] = []
        #: ``input.*`` call site → the variable it is assigned to. That variable
        #: name is what the validator records and what the panel's parameter
        #: form keys on, so resolving it once at load beats guessing from a
        #: title string at every bar.
        self._input_names: dict[str, str] = {}
        self._var_names: set[str] = set()
        self._advance_failures: set[str] = set()
        self._register()

    # --- load ---------------------------------------------------------------

    def _register(self) -> None:
        """One AST walk at load: which sites are stateful, and which are inputs."""

        def visit(node: ast.Node, ancestors: tuple[ast.Node, ...]) -> None:
            if isinstance(node, ast.Assign) and node.qualifier:
                self._var_names.update(node.targets)
            if isinstance(node, ast.Call):
                dotted = ast.dotted_name(node.func) or ""
                nested = any(
                    isinstance(a, ast.FuncDef | ast.MethodDef | ast.For | ast.ForIn | ast.While)
                    for a in ancestors
                )
                if dotted.startswith("ta.") and not nested:
                    self.stateful_sites.append(node)
                if dotted.startswith("input"):
                    owner = next(
                        (a for a in reversed(ancestors) if isinstance(a, ast.Assign)), None
                    )
                    if owner is not None and len(owner.targets) == 1:
                        self._input_names[node.call_id] = owner.targets[0]
            for child in ast.children(node):
                visit(child, (*ancestors, node))

        visit(self.program, ())

    # --- driver-facing state ------------------------------------------------

    def sync_position(
        self,
        *,
        size_sign: int,
        avg_price: Decimal | None = None,
        equity: Decimal = ZERO,
        netprofit: Decimal = ZERO,
        opentrades: int = 0,
    ) -> None:
        """Tell the runtime what is actually true before the next bar.

        Called by the backtest and by the supervisor with the same shape, which
        is what keeps ``strategy.position_size`` from becoming a second, private
        idea of the position.
        """
        if size_sign not in (-1, 0, 1):
            size_sign = (size_sign > 0) - (size_sign < 0)
        self.ctx.position_size = size_sign
        self.ctx.position_avg_price = avg_price
        self.ctx.equity = equity
        self.ctx.netprofit = netprofit
        self.ctx.opentrades = opentrades

    # --- the bar ------------------------------------------------------------

    def run_bar(
        self,
        bar: Bar,
        *,
        ishistory: bool = False,
        islast: bool = False,
        enforce_budget: bool = False,
    ) -> BarResult:
        """Evaluate one **confirmed** bar (Q23) and return what the strategy wants."""
        started = _time.perf_counter()
        ctx = self.ctx
        ctx.bar = bar
        ctx.bar_index += 1
        ctx.state = BarState(
            isfirst=ctx.bar_index == 0,
            islast=islast,
            isconfirmed=True,
            isnew=True,
            ishistory=ishistory,
        )
        self._push_builtin_series(bar)
        self._carry_var_series()

        ctx.touched = set()
        ctx.ta_pushed = set()
        ctx.plots = {}
        ctx.alerts = []
        ctx.annotations = []
        ctx.reason = ""
        ctx.order_span = None
        ctx.locals = []
        # A position persists until something closes it — an intent is "what
        # should be true *after* this bar", not "what this bar asked for". So the
        # bar starts from what the driver says is actually held, and only the
        # script's own order calls move it. Resetting to flat here would make
        # every quiet bar an instruction to close, which is a strategy that
        # trades once and then flattens itself for ever.
        ctx.desired_side = (
            Side.LONG
            if ctx.position_size > 0
            else Side.SHORT
            if ctx.position_size < 0
            else None
        )
        if ctx.desired_side is None:
            ctx.sl_pct = None
            ctx.tp_pct = None

        try:
            for statement in self.program.body:
                self._exec(statement)
        except PineRuntimeError:
            raise
        except _Break as exc:
            raise PineRuntimeError(
                "break outside a loop", code="stray_break", span=self.program.span
            ) from exc
        except _Continue as exc:
            raise PineRuntimeError(
                "continue outside a loop", code="stray_continue", span=self.program.span
            ) from exc
        except RecursionError as exc:
            raise PineRuntimeError(
                "this script nests too deeply to evaluate", code="too_deep", span=self.program.span
            ) from exc

        self._advance_untouched()

        elapsed_ms = (_time.perf_counter() - started) * 1000
        if enforce_budget and elapsed_ms > self.limits.bar_budget_ms:
            raise PineRuntimeError(
                f"this bar took {elapsed_ms:.0f}ms, over the {self.limits.bar_budget_ms}ms "
                f"budget — the runtime shares an event loop with a fan-out that has a "
                f"per-leg deadline, so a slow script is a latency incident for every account",
                code="bar_budget_exceeded",
                span=self.program.span,
            )

        intent = StrategyIntent(
            bar_time=bar.time,
            symbol=self.symbol,
            desired_side=ctx.desired_side,
            sl_pct=ctx.sl_pct,
            tp_pct=ctx.tp_pct,
            reason=ctx.reason,
            source_span=ctx.order_span,
            plots=dict(ctx.plots),
            alerts=tuple(ctx.alerts),
        )
        return BarResult(intent=intent, annotations=list(ctx.annotations), elapsed_ms=elapsed_ms)

    def _push_builtin_series(self, bar: Bar) -> None:
        series = self.ctx.series
        series["open"].push(bar.open)
        series["high"].push(bar.high)
        series["low"].push(bar.low)
        series["close"].push(bar.close)
        series["volume"].push(bar.volume)
        series["hl2"].push((bar.high + bar.low) / 2)
        series["hlc3"].push((bar.high + bar.low + bar.close) / 3)
        series["ohlc4"].push((bar.open + bar.high + bar.low + bar.close) / 4)
        series["hlcc4"].push((bar.high + bar.low + bar.close + bar.close) / 4)
        series["time"].push(bar.time)
        series["bar_index"].push(self.ctx.bar_index)

    def _carry_var_series(self) -> None:
        """``var`` survives the bar; a plain declaration is recomputed.

        Carrying the value forward here is what makes ``x[1]`` mean the previous
        bar's value rather than the previous *write*, which are different things
        the moment a bar takes a branch that skips the assignment.
        """
        for name in self._var_names:
            series = self.ctx.globals.get(name)
            if series is not None and len(series):
                series.push(series.value)

    def _advance_untouched(self) -> None:
        """Advance every registered ``ta.*`` site the bar did not reach.

        Pine's own behaviour for a stateful call inside a branch is a known trap
        — TradingView warns about it rather than defining it away — and the
        failure it produces is silent: an EMA that only updates on the days its
        branch runs converges to a different series and never says so. The
        platform's answer is that every registered site advances every bar.

        Arguments are re-evaluated in the *global* scope at end of bar, so a site
        whose arguments read a variable assigned later in the script still sees
        this bar's value. A site whose arguments cannot be evaluated at all
        (they read a local that only exists inside its branch) is skipped and
        reported once — the validator already warned about that shape at upload.
        """
        for node in self.stateful_sites:
            if node.call_id in self.ctx.touched:
                continue
            try:
                self._call_ta(node, discard=True)
            except (PineRuntimeError, PineNameError):
                self._advance_failures.add(node.call_id)

    @property
    def advance_failures(self) -> set[str]:
        """Call sites that could not be advanced. Surfaced by the supervisor."""
        return set(self._advance_failures)

    # --- snapshot -----------------------------------------------------------

    def snapshot(self) -> dict:
        """A restorable copy of everything that carries across bars.

        Built now although Q23 means nothing needs it yet: Phase 6's crash
        recovery and any future intrabar mode both do, and retrofitting it means
        touching every stateful object in ``ta.py`` rather than this one method.

        Not used for recovery across a *deploy* — a code change silently
        invalidates a snapshot, so the supervisor re-warms from bars instead.
        """
        ctx = self.ctx
        return copy.deepcopy(
            {
                "bar_index": ctx.bar_index,
                "series": ctx.series,
                "globals": ctx.globals,
                "indicators": ctx.indicators,
                "outputs": ctx.outputs,
                "scratch": ctx.scratch,
                "position": (
                    ctx.position_size,
                    ctx.position_avg_price,
                    ctx.equity,
                    ctx.netprofit,
                    ctx.opentrades,
                ),
                "random": ctx.random.getstate(),
            }
        )

    def restore(self, snap: dict) -> None:
        ctx = self.ctx
        restored = copy.deepcopy(snap)
        ctx.bar_index = restored["bar_index"]
        ctx.series = restored["series"]
        ctx.globals = restored["globals"]
        ctx.indicators = restored["indicators"]
        ctx.outputs = restored.get("outputs", {})
        ctx.scratch = restored["scratch"]
        (
            ctx.position_size,
            ctx.position_avg_price,
            ctx.equity,
            ctx.netprofit,
            ctx.opentrades,
        ) = restored["position"]
        ctx.random.setstate(restored["random"])

    # --- statements ---------------------------------------------------------

    def _exec(self, node: ast.Node):
        if isinstance(node, ast.ExprStmt):
            return self._eval(node.value)
        if isinstance(node, ast.Assign):
            return self._exec_assign(node)
        if isinstance(node, ast.Reassign):
            return self._exec_reassign(node)
        if isinstance(node, ast.FuncDef | ast.MethodDef | ast.TypeDef | ast.EnumDef):
            return NA  # bound at load; the definition itself evaluates to nothing
        if isinstance(node, ast.FieldAssign):
            return self._exec_field_assign(node)
        if isinstance(node, ast.For):
            return self._exec_for(node)
        if isinstance(node, ast.ForIn):
            return self._exec_for_in(node)
        if isinstance(node, ast.While):
            return self._exec_while(node)
        if isinstance(node, ast.Break):
            raise _Break
        if isinstance(node, ast.Continue):
            raise _Continue
        if isinstance(node, ast.Block):
            return self._exec_block(node)
        return self._eval(node)

    def _exec_block(self, block: ast.Block):
        value = NA
        for statement in block.body:
            value = self._exec(statement)
        return value

    def _scoped_block(self, block: ast.Block):
        """A block body gets its own scope: ``x = 1`` inside it is a new local."""
        self.ctx.locals.append({})
        try:
            return self._exec_block(block)
        finally:
            self.ctx.locals.pop()

    def _exec_assign(self, node: ast.Assign):
        ctx = self.ctx
        first_bar_only = bool(node.qualifier)

        if len(node.targets) > 1:
            value = self._eval(node.value)
            if not isinstance(value, tuple):
                raise PineRuntimeError(
                    f"{len(node.targets)} names on the left but this call returned one value",
                    code="bad_tuple",
                    span=node.span,
                )
            if len(value) != len(node.targets):
                raise PineRuntimeError(
                    f"{len(node.targets)} names on the left but the call returned {len(value)}",
                    code="bad_tuple",
                    span=node.span,
                )
            for name, item in zip(node.targets, value, strict=True):
                self._bind(name, item, first_bar_only=first_bar_only)
            return value

        name = node.targets[0]
        if first_bar_only and name in ctx.globals and len(ctx.globals[name]):
            # `var x = ...` initialises once and is carried forward after that.
            return ctx.globals[name].value
        value = self._eval(node.value)
        self._bind(name, value, first_bar_only=first_bar_only)
        return value

    def _bind(self, name: str, value, *, first_bar_only: bool) -> None:
        ctx = self.ctx
        if ctx.locals and not first_bar_only:
            ctx.locals[-1][name] = value
            return
        series = ctx.globals.get(name)
        if series is None:
            series = Series(self.limits.series_depth)
            ctx.globals[name] = series
            series.push(value)
            return
        # `_carry_var_series` already pushed this bar's slot for a `var`; a plain
        # declaration pushes its own. Either way one slot per bar, never two.
        if name in self._var_names:
            series.set(value)
        else:
            series.push(value)

    def _exec_reassign(self, node: ast.Reassign):
        ctx = self.ctx
        value = self._eval(node.value)
        for scope in reversed(ctx.locals):
            if node.target in scope:
                scope[node.target] = value
                return value
        series = ctx.globals.get(node.target)
        if series is None:
            raise PineNameError(
                f"{node.target!r} is assigned with := before it is declared with =",
                code="reassign_before_declare",
                span=node.span,
            )
        series.set(value)
        return value

    def _exec_field_assign(self, node: ast.FieldAssign):
        """``obj.field := expr`` — mutate one field of an object in place.

        Objects are held by reference, so this write is visible through every
        variable bound to the same ``PineObject`` (``objects.md``).
        """
        target = self._eval(node.obj)
        value = self._eval(node.value)
        if isinstance(target, PineObject):
            if node.attr not in target.fields:
                raise PineRuntimeError(
                    f"{target.type_name!r} has no field {node.attr!r}",
                    code="unknown_field",
                    span=node.span,
                )
            target.fields[node.attr] = value
            return value
        if is_na(target):
            raise PineRuntimeError(
                f"cannot set field {node.attr!r} on an na object — construct it with "
                f"Type.new() first",
                code="na_field_assign",
                span=node.span,
            )
        raise PineRuntimeError(
            f"{node.attr!r} cannot be assigned — the value on the left is not an object",
            code="not_an_object",
            span=node.span,
        )

    def _bind_args(
        self,
        node: ast.Call,
        param_names: list[str],
        defaults: tuple[ast.Node | None, ...],
    ) -> list:
        """Resolve a call's positional and named arguments against a signature.

        Shared by user functions, user methods and ``Type.new()`` so that
        ``f(len = 20)``, a trailing default and "too many arguments" mean the
        same thing wherever they appear.
        """
        slots: list = [_MISSING] * len(param_names)
        position = 0
        for arg in node.args:
            if arg.name:
                if arg.name not in param_names:
                    raise PineRuntimeError(
                        f"no parameter named {arg.name!r}",
                        code="unknown_arg",
                        span=node.span,
                    )
                slots[param_names.index(arg.name)] = self._eval(arg.value)
            else:
                if position >= len(slots):
                    raise PineRuntimeError(
                        f"too many arguments — this signature takes {len(param_names)}",
                        code="bad_arity",
                        span=node.span,
                    )
                slots[position] = self._eval(arg.value)
                position += 1
        out: list = []
        for index, value in enumerate(slots):
            if value is _MISSING:
                default = defaults[index] if index < len(defaults) else None
                if default is None:
                    raise PineRuntimeError(
                        f"missing argument {param_names[index]!r}",
                        code="bad_arity",
                        span=node.span,
                    )
                value = self._eval(default)
            out.append(value)
        return out

    def _exec_for(self, node: ast.For):
        start = _as_int(self._eval(node.start), "for start", node.span)
        end = _as_int(self._eval(node.end), "for end", node.span)
        step = _as_int(self._eval(node.step), "for step", node.span) if node.step else None
        if step is None:
            step = 1 if end >= start else -1
        if step == 0:
            raise PineRuntimeError("a for loop's step cannot be 0", code="bad_step", span=node.span)

        value = NA
        iterations = 0
        index = start
        while (index <= end) if step > 0 else (index >= end):
            iterations += 1
            self._guard_iterations(iterations, node.span)
            self.ctx.locals.append({node.var: index})
            try:
                value = self._exec_block(node.body)
            except _Break:
                break
            except _Continue:
                pass
            finally:
                self.ctx.locals.pop()
            index += step
        return value

    def _exec_for_in(self, node: ast.ForIn):
        iterable = self._eval(node.iterable)
        if not isinstance(iterable, tuple | list):
            raise PineRuntimeError(
                "for...in needs something with items; collections are not in the v1 subset",
                code="not_iterable",
                span=node.span,
            )
        value = NA
        for iteration, item in enumerate(iterable, start=1):
            self._guard_iterations(iteration, node.span)
            binding = (
                dict(zip(node.vars, (iteration - 1, item), strict=False))
                if len(node.vars) == 2
                else {node.vars[0]: item}
            )
            self.ctx.locals.append(binding)
            try:
                value = self._exec_block(node.body)
            except _Break:
                break
            except _Continue:
                continue
            finally:
                self.ctx.locals.pop()
        return value

    def _exec_while(self, node: ast.While):
        value = NA
        iterations = 0
        while True:
            condition = self._eval(node.cond)
            if is_na(condition) or not bool(condition):
                break
            iterations += 1
            self._guard_iterations(iterations, node.span)
            self.ctx.locals.append({})
            try:
                value = self._exec_block(node.body)
            except _Break:
                break
            except _Continue:
                continue
            finally:
                self.ctx.locals.pop()
        return value

    def _guard_iterations(self, count: int, span: Span) -> None:
        """The runtime half of the loop cap.

        The validator rejects a loop it can prove will not end; this catches the
        ones it cannot prove either way, which is most of them. A hang here is a
        hang inside a bar budget shared with the fan-out.
        """
        if count > self.limits.max_loop_iterations:
            raise PineRuntimeError(
                f"this loop passed {self.limits.max_loop_iterations} iterations in one bar",
                code="loop_limit",
                span=span,
            )

    # --- expressions --------------------------------------------------------

    def _eval(self, node: ast.Node):
        kind = type(node)

        if kind is ast.NumberLit:
            return Decimal(node.value)
        if kind is ast.StringLit:
            return node.value
        if kind is ast.BoolLit:
            return node.value
        if kind is ast.ColorLit:
            return node.value
        if kind is ast.Name:
            return self._lookup(node)
        if kind is ast.Member:
            return self._member(node)
        if kind is ast.Index:
            return self._history(node)
        if kind is ast.Unary:
            return self._unary(node)
        if kind is ast.Binary:
            return self._binary(node)
        if kind is ast.Ternary:
            condition = self._eval(node.cond)
            return self._eval(node.then if bool(condition) else node.otherwise)
        if kind is ast.Call:
            return self._call(node)
        if kind is ast.If:
            return self._if(node)
        if kind is ast.Switch:
            return self._switch(node)
        if kind is ast.TupleExpr:
            return tuple(self._eval(item) for item in node.items)
        if kind is ast.Block:
            return self._exec_block(node)
        return self._exec(node)

    def _if(self, node: ast.If):
        if bool(self._eval(node.cond)):
            return self._scoped_block(node.then)
        if node.otherwise is None:
            return NA
        if isinstance(node.otherwise, ast.Block):
            return self._scoped_block(node.otherwise)
        return self._eval(node.otherwise)

    def _switch(self, node: ast.Switch):
        subject = self._eval(node.subject) if node.subject is not None else None
        for case in node.cases:
            if case.match is None:
                return self._eval(case.body)
            candidate = self._eval(case.match)
            hit = bool(candidate) if subject is None else subject == candidate
            if hit:
                return self._eval(case.body)
        return NA

    def _lookup(self, node: ast.Name):
        name = node.name
        ctx = self.ctx

        for scope in reversed(ctx.locals):
            if name in scope:
                return scope[name]
        if name in ctx.globals:
            return ctx.globals[name].value
        if name in ctx.series:
            return ctx.series[name].value
        if name == "na":
            return NA
        if name == "last_bar_index":
            return ctx.bar_index
        if name in bi.CALENDAR_VALUES:
            return bi.CALENDAR_VALUES[name](ctx)
        if name in self.functions or name in bi.BARE_CALLS or name in VISUAL_FUNCTIONS:
            # A bare reference to a callable. Only reachable as a call target,
            # which `_call` resolves itself, so this is the name of the thing.
            return name
        raise PineNameError(f"{name!r} is not defined", code="undefined_name", span=node.span)

    def _member_base(self, obj_node: ast.Node):
        """The value before the dot, or ``_NOT_A_VALUE`` when it is a namespace.

        ``p`` in ``p.x`` resolves to the object it holds; ``ta`` in ``ta.tr``
        resolves to nothing here and the caller falls back to the built-in
        tables. An enum name resolves to its ``EnumType`` so ``Dir.up`` works.
        """
        ctx = self.ctx
        if isinstance(obj_node, ast.Name):
            name = obj_node.name
            for scope in reversed(ctx.locals):
                if name in scope:
                    return scope[name]
            if name in ctx.globals:
                return ctx.globals[name].value
            if name in ctx.series:
                return ctx.series[name].value
            if name in self.enums:
                return self.enums[name]
            return _NOT_A_VALUE
        if isinstance(
            obj_node, ast.Member | ast.Index | ast.Call | ast.Ternary | ast.If | ast.Switch
        ):
            return self._eval(obj_node)
        return _NOT_A_VALUE

    def _member_of_value(self, base, node: ast.Member):
        attr = node.attr
        if isinstance(base, PineObject):
            if attr not in base.fields:
                raise PineRuntimeError(
                    f"{base.type_name!r} has no field {attr!r}",
                    code="unknown_field",
                    span=node.span,
                )
            return base.fields[attr]
        if isinstance(base, EnumType):
            value = base.member(attr)
            if value is None:
                raise PineNameError(
                    f"{base.name!r} has no member {attr!r}",
                    code="unknown_enum_member",
                    span=node.span,
                )
            return value
        if is_na(base):
            return NA  # a field read on an na object is na (objects.md)
        raise PineNameError(
            f"{self._type_name_of(base)} value has no member {attr!r}",
            code="undefined_member",
            span=node.span,
        )

    def _member(self, node: ast.Member):
        dotted = ast.dotted_name(node)
        ctx = self.ctx

        base = self._member_base(node.obj)
        if base is not _NOT_A_VALUE:
            return self._member_of_value(base, node)

        if dotted == "strategy.position_size":
            return Decimal(ctx.position_size)
        if dotted == "strategy.position_avg_price":
            return ctx.position_avg_price if ctx.position_avg_price is not None else NA
        if dotted == "strategy.equity":
            return ctx.equity
        if dotted == "strategy.netprofit":
            return ctx.netprofit
        if dotted == "strategy.opentrades":
            return Decimal(ctx.opentrades)
        if dotted == "strategy.long":
            return Side.LONG
        if dotted == "strategy.short":
            return Side.SHORT
        if dotted == "ta.tr":
            return self._ta_state("ta.tr:" + node.call_id, "tr").update(ctx, False)
        if dotted is not None and dotted.startswith("barstate."):
            attribute = dotted.split(".", 1)[1]
            return getattr(ctx.state, attribute)
        if dotted is not None and "." in dotted:
            root, attribute = dotted.split(".", 1)
            constants = bi.NAMESPACE_CONSTANTS.get(root)
            if constants and attribute in constants:
                return constants[attribute]
            # Decorative namespaces (color.green, shape.triangleup): the
            # validator has already confined these to visual calls, where the
            # value is recorded and never executed. The name is the value.
            return dotted
        raise PineNameError(
            f"{dotted or 'this member access'} is not defined",
            code="undefined_member",
            span=node.span,
        )

    def _history(self, node: ast.Index):
        offset = _as_int(self._eval(node.offset), "a history offset", node.span)
        target = node.obj
        ctx = self.ctx

        if isinstance(target, ast.Name):
            name = target.name
            for scope in reversed(ctx.locals):
                if name in scope:
                    # A local has no history: it is created and discarded inside
                    # one bar. Offset 0 is the value; anything else is `na`,
                    # which is the honest answer rather than a fabricated one.
                    return scope[name] if offset == 0 else NA
            if name in ctx.globals:
                return ctx.globals[name][offset]
            if name in ctx.series:
                return ctx.series[name][offset]
        if isinstance(target, ast.Call) and (ast.dotted_name(target.func) or "").startswith("ta."):
            value = self._eval(target)
            if offset == 0:
                return value
            history = ctx.outputs.get(self._ta_key(target))
            return history[offset] if history is not None else NA

        value = self._eval(target)
        if offset == 0:
            return value
        # Reached only when the validator let it through. Returning `na` here is
        # what Q24 forbids: a signal that quietly never fires.
        raise PineRuntimeError(
            "only a variable, a built-in series or a ta.* call keeps history",
            code="unsupported_history",
            span=node.span,
        )

    def _unary(self, node: ast.Unary):
        value = self._eval(node.operand)
        if node.op == "not":
            return not bool(value)
        if is_na(value):
            return NA
        return -value if node.op == "-" else +value

    def _binary(self, node: ast.Binary):
        if node.op == "and":
            left = self._eval(node.left)
            return bool(left) and bool(self._eval(node.right))
        if node.op == "or":
            left = self._eval(node.left)
            return bool(left) or bool(self._eval(node.right))

        left = self._eval(node.left)
        right = self._eval(node.right)
        op = node.op

        if op == "+" and (isinstance(left, str) or isinstance(right, str)):
            return f"{left}{right}"

        try:
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                if not is_na(right) and right == 0:
                    raise PineRuntimeError(
                        "division by zero", code="division_by_zero", span=node.span
                    )
                return left / right
            if op == "%":
                if not is_na(right) and right == 0:
                    raise PineRuntimeError(
                        "modulo by zero", code="division_by_zero", span=node.span
                    )
                return left % right
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
        except (DivisionByZero, InvalidOperation) as exc:
            raise PineRuntimeError(
                f"{left!r} {op} {right!r} is not a valid operation",
                code="bad_arithmetic",
                span=node.span,
            ) from exc
        except TypeError as exc:
            raise PineRuntimeError(
                f"cannot apply {op} to {type(left).__name__} and {type(right).__name__}",
                code="type_mismatch",
                span=node.span,
            ) from exc
        raise PineRuntimeError(f"unknown operator {op}", code="unknown_operator", span=node.span)

    # --- calls --------------------------------------------------------------

    def _call(self, node: ast.Call):
        dotted = ast.dotted_name(node.func)
        ctx = self.ctx
        ctx.current_call_id = node.call_id

        # `Point.new(...)` / `Point.copy(obj)` — construct or shallow-copy a UDT.
        if dotted:
            root, _, tail = dotted.partition(".")
            if root in self.types and tail in ("new", "copy"):
                return self._call_type(node, root, tail)

        # `obj.method(...)` — a user method, when the thing before the dot is a
        # value we hold rather than a namespace like `ta` or `strategy`.
        if isinstance(node.func, ast.Member):
            base = self._member_base(node.func.obj)
            if base is not _NOT_A_VALUE and not isinstance(base, EnumType):
                return self._call_method(node, base, node.func.attr)

        if dotted in self.functions:
            return self._call_user_function(node, self.functions[dotted])
        if dotted == "strategy":
            return NA  # the declaration; its arguments were checked at validation
        if dotted in VISUAL_FUNCTIONS:
            return self._call_visual(node, dotted)
        if dotted and dotted.startswith("strategy."):
            return self._call_strategy(node, dotted)
        if dotted and dotted.startswith("ta."):
            return self._call_ta(node)
        if dotted and dotted.startswith("input"):
            return self._call_input(node, dotted)
        if dotted and "." in dotted:
            root, name = dotted.split(".", 1)
            table = bi.NAMESPACE_CALLS.get(root, {})
            if name in table:
                return table[name](ctx, *self._args(node))
        if dotted in bi.BARE_CALLS:
            return bi.BARE_CALLS[dotted](ctx, *self._args(node))
        if dotted and dotted.split(".", 1)[0] in DECORATIVE_NAMESPACES:
            # `color.new(color.green, 90)` and friends. The validator has already
            # confined these to a visual call's arguments, which are recorded and
            # never executed, so the call *is* its own description. Raising here
            # instead would mean a script that validates cannot run.
            return f"{dotted}({', '.join(str(v) for v in self._args(node))})"

        raise PineNameError(
            f"{dotted or 'this expression'} is not a function this platform provides",
            code="unknown_call",
            span=node.span,
        )

    def _args(self, node: ast.Call) -> list:
        return [self._eval(arg.value) for arg in node.args]

    def _call_user_function(self, node: ast.Call, fn: ast.FuncDef):
        values = self._bind_args(node, list(fn.params), fn.defaults)
        ctx = self.ctx
        ctx.locals.append(dict(zip(fn.params, values, strict=True)))
        previous = ctx.call_path
        ctx.call_path = (*previous, node.call_id)
        try:
            return self._exec_block(fn.body)
        finally:
            ctx.call_path = previous
            ctx.locals.pop()

    # --- user-defined types, enums, methods ------------------------------

    def _call_type(self, node: ast.Call, type_name: str, op: str):
        type_def = self.types[type_name]
        if op == "copy":
            values = self._args(node)
            source = values[0] if values else NA
            if isinstance(source, PineObject):
                return source.copy()
            if is_na(source):
                return NA
            raise PineRuntimeError(
                f"{type_name}.copy() needs a {type_name} object",
                code="bad_copy",
                span=node.span,
            )
        # `Type.new()` — a field with no value and no default is `na`, not an
        # error (objects.md). So this is not `_bind_args`, which requires a
        # missing argument to have a default the way a function parameter does.
        field_names = [f.name for f in type_def.fields]
        fields: dict = {name: NA for name in field_names}
        for field_node in type_def.fields:
            if field_node.default is not None:
                fields[field_node.name] = self._eval(field_node.default)
        position = 0
        for arg in node.args:
            if arg.name:
                if arg.name not in fields:
                    raise PineRuntimeError(
                        f"{type_name!r} has no field {arg.name!r}",
                        code="unknown_field",
                        span=node.span,
                    )
                fields[arg.name] = self._eval(arg.value)
            else:
                if position >= len(field_names):
                    raise PineRuntimeError(
                        f"{type_name}.new() takes at most {len(field_names)} field value(s)",
                        code="too_many_fields",
                        span=node.span,
                    )
                fields[field_names[position]] = self._eval(arg.value)
                position += 1
        return PineObject(type_name, fields)

    def _call_method(self, node: ast.Call, receiver, method_name: str):
        if isinstance(receiver, PineObject) and method_name == "copy" and (
            "copy" not in self.methods
        ):
            return receiver.copy()
        overloads = self.methods.get(method_name)
        chosen = self._resolve_overload(overloads, receiver) if overloads else None
        if chosen is None:
            raise PineNameError(
                f"no method {method_name!r} for {self._type_name_of(receiver)}",
                code="unknown_method",
                span=node.span,
            )
        values = self._bind_args(node, list(chosen.params), chosen.defaults)
        ctx = self.ctx
        scope = {chosen.receiver_name: receiver}
        scope.update(zip(chosen.params, values, strict=True))
        ctx.locals.append(scope)
        previous = ctx.call_path
        ctx.call_path = (*previous, node.call_id)
        try:
            return self._exec_block(chosen.body)
        finally:
            ctx.call_path = previous
            ctx.locals.pop()

    def _resolve_overload(self, overloads: list[ast.MethodDef], receiver):
        if len(overloads) == 1:
            return overloads[0]
        if isinstance(receiver, PineObject):
            accepted = {receiver.type_name}
        elif isinstance(receiver, EnumValue):
            accepted = {receiver.enum}
        else:
            accepted = _PRIMITIVE_RECEIVERS.get(type(receiver), frozenset())
        for method in overloads:
            if method.receiver_type in accepted:
                return method
        return overloads[0]

    @staticmethod
    def _type_name_of(value) -> str:
        if isinstance(value, PineObject):
            return value.type_name
        if isinstance(value, EnumValue):
            return value.enum
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, Decimal):
            return "float"
        if isinstance(value, str):
            return "string"
        if is_na(value):
            return "na"
        return type(value).__name__

    def _ta_state(self, key: str, name: str) -> ta_lib.Indicator:
        state = self.ctx.indicators.get(key)
        if state is None:
            state = ta_lib.FACTORIES[name]()
            self.ctx.indicators[key] = state
        return state

    def _call_ta(self, node: ast.Call, *, discard: bool = False):
        """Evaluate one ``ta.*`` call site.

        The state key is ``(call_id, call stack path)``, not ``call_id`` alone:
        a ``ta.*`` call inside a user function invoked twice in one bar is **two
        logical call sites**, each with its own converged state. Keying on the
        node alone makes them one indicator fed two interleaved series, which is
        an indicator of nothing at all.
        """
        name = (ast.dotted_name(node.func) or "").split(".", 1)[1]
        factory = ta_lib.FACTORIES.get(name)
        if factory is None:
            raise PineNameError(
                f"ta.{name} is not in the v1 subset", code="unknown_ta", span=node.span
            )

        ctx = self.ctx
        key = self._ta_key(node)
        state = self._ta_state(key, name)
        values = self._args(node)
        result = state.update(ctx, *values)
        if key not in ctx.ta_pushed:
            history = ctx.outputs.get(key)
            if history is None:
                history = ctx.outputs[key] = Series(self.limits.series_depth)
            history.push(result)
            ctx.ta_pushed.add(key)
        if not discard:
            ctx.touched.add(node.call_id)
        return result

    def _ta_key(self, node: ast.Call) -> str:
        """The state key for one ``ta.*`` site: its span plus the call stack.

        A site inside a user function invoked twice in one bar is **two logical
        call sites**, each with its own converged state; keying on the node
        alone makes them one indicator fed two interleaved series. The path is
        the *call sites* on the stack, not the scope objects — those are new
        dictionaries every bar, so keying on them converges nothing.
        """
        path = "/".join(self.ctx.call_path)
        return f"{node.call_id}#{path}" if path else node.call_id

    def _call_strategy(self, node: ast.Call, dotted: str):
        ctx = self.ctx
        values = self._args(node)
        label = str(values[0]) if values else ""

        if dotted == "strategy.entry":
            direction = node.keyword("direction")
            side = self._eval(direction) if direction is not None else (
                values[1] if len(values) > 1 else Side.LONG
            )
            if not isinstance(side, Side):
                side = Side.LONG if str(side).lower() in ("long", "buy") else Side.SHORT
            # Last entry in the bar wins. Enforced here rather than left to
            # convention, so one intent per bar produces at most one entry.
            ctx.desired_side = side
            ctx.reason = f"entry: {label}" if label else "entry"
            ctx.order_span = node.span
            return NA

        if dotted in ("strategy.close", "strategy.close_all"):
            ctx.desired_side = None
            # The SL/TP a `strategy.exit` set belonged to the trade being closed.
            ctx.sl_pct = None
            ctx.tp_pct = None
            ctx.reason = f"close: {label}" if label else "close all"
            ctx.order_span = node.span
            return NA

        if dotted == "strategy.exit":
            loss = node.keyword("loss_pct")
            profit = node.keyword("profit_pct")
            if loss is not None:
                ctx.sl_pct = _as_decimal(self._eval(loss), "loss_pct", node.span)
            if profit is not None:
                ctx.tp_pct = _as_decimal(self._eval(profit), "profit_pct", node.span)
            return NA

        raise PineNameError(f"{dotted} is not supported", code="unknown_call", span=node.span)

    def _call_input(self, node: ast.Call, dotted: str):
        """An ``input.*`` reads the bot's configured value, or the script's default.

        Keyed on the **variable name** the input is assigned to, resolved once at
        load. The title is a display string an author changes freely; the
        variable name is what ``validate.InputSpec`` records and what the
        parameter form submits, so a retitled input keeps its configured value.
        """
        default = self._eval(node.args[0].value) if node.args and not node.args[0].name else NA
        keyword_default = node.keyword("defval")
        if keyword_default is not None:
            default = self._eval(keyword_default)

        name = self._input_names.get(node.call_id)
        if name and name in self.input_values:
            return _coerce_input(self.input_values[name], default)
        return default

    def _call_visual(self, node: ast.Call, dotted: str):
        """Recorded, never executed. The values ride out on the intent."""
        ctx = self.ctx
        values = self._args(node)
        title = None
        title_node = node.keyword("title")
        if title_node is not None:
            title = str(self._eval(title_node))
        elif len(node.args) > 1 and not node.args[1].name:
            candidate = values[1]
            title = str(candidate) if isinstance(candidate, str) else None
        if not title:
            title = f"{dotted}_{len(ctx.plots) + 1}"

        if dotted == "alert":
            message = str(values[0]) if values else ""
            ctx.alerts.append(message)
            ctx.annotations.append(Annotation("alert", title, message, node.span))
            return NA
        if dotted == "alertcondition":
            condition = values[0] if values else False
            if bool(condition):
                message = str(values[2]) if len(values) > 2 else title
                ctx.alerts.append(message)
                ctx.annotations.append(Annotation("alert", title, message, node.span))
            return NA

        value = values[0] if values else NA
        ctx.plots[title] = None if is_na(value) else value
        ctx.annotations.append(Annotation(dotted, title, ctx.plots[title], node.span))
        return NA


# --- coercion ---------------------------------------------------------------


def _as_int(value, what: str, span: Span) -> int:
    if is_na(value):
        raise PineRuntimeError(f"{what} is na", code="na_value", span=span)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PineRuntimeError(
            f"{what} must be a whole number", code="not_an_int", span=span
        ) from exc


def _as_decimal(value, what: str, span: Span) -> Decimal:
    if is_na(value):
        raise PineRuntimeError(f"{what} is na", code="na_value", span=span)
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise PineRuntimeError(
            f"{what} must be a number", code="not_a_number", span=span
        ) from exc


def _coerce_input(value, default):
    """Match the configured value to the shape of the script's own default."""
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, Decimal):
        return Decimal(str(value))
    if isinstance(default, str):
        return str(value)
    return value
