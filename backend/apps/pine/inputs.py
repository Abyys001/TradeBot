"""What a script asks to be *set* — its inputs, grouped, classified and gated.

``properties.py`` is the broker's half of TradingView's settings dialog; this is
the author's half, and the difference between the two halves is not cosmetic. A
property describes the simulated account, so changing one changes the *report*.
An input is a number the strategy computes with, so changing one changes the
*signals* — and on a live bot that is a different trade, not a different
rendering of the same one.

``validate.py`` does the transcription: one AST walk records every ``input.*``
call site as an `InputSpec` — name, title, default, bounds, options, ``group``,
``inline``, ``tooltip``. That is everything the call site *says*. This module
takes that list plus the same AST and derives the three things a settings form
needs that the call site does not say:

**A widget.** ``input.int`` with ``options=`` is a dropdown and without one is a
number field; ``input.source`` is a choice over the built-in series, not free
text. The mapping lives here as data, so the panel renders from the schema
rather than from a switch statement per Pine type.

**A category.** Which of trading logic, risk, execution, backtest window or
pure decoration a setting belongs to — read off the **sinks its value reaches**,
never off its name. ``tp1Percent`` is a risk input because it flows into
``strategy.exit(qty_percent=)``, and a script that spells the same idea ``x1``
gets the same answer. Naming heuristics would classify one published strategy
correctly and the next one wrong, and the failure mode of "wrong" here is a
setting filed under Colours that moves real money.

**A dependency.** ``useTargets = input.bool(...)`` gating six other inputs is
not written anywhere in the input declarations — it is in the *strategy logic*,
as the ``if`` that every use of those six sits under. So the guards are read off
the AST and intersected: a dependency is claimed only when **every** non-visual
use of a value sits under the same condition. One use outside the guard drops
it.

That conservatism is deliberate and it runs one way. A dependency here is
**advisory** — a gated input is drawn dimmed with the reason next to it, its
value is still submitted, and nothing on the execution path reads the flag. An
input wrongly greyed out is a setting the operator cannot reach on a live book,
which is a worse failure than a setting that stays bright while it does nothing.

Stdlib only, like the rest of ``apps.pine`` — the same object serves the
backtest form, the bot's settings tab and the live loop.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from apps.pine import ast_nodes as ast
from apps.pine.subset import DRAWING_NAMESPACES, VISUAL_FUNCTIONS


class Category(StrEnum):
    """Which half of the bot a setting reaches."""

    #: Sizes an exit, a stop or a partial — the settings that decide how much is
    #: risked and where it is given back.
    RISK = "risk"
    #: Order plumbing: when an order is allowed out, what it is tagged with,
    #: what the alert says. Not the signal, and not the size.
    EXECUTION = "execution"
    #: The replay's own window — a start date compared against ``time``.
    BACKTEST = "backtest"
    #: Lengths, multipliers, thresholds: what the strategy computes with.
    LOGIC = "logic"
    #: Colours, labels, dashboards. Reaches a drawing call and nothing else.
    VISUAL = "visual"


#: Precedence, and the order the panel lists them in. A value that reaches two
#: sinks is filed under the more consequential one: a length used by both a stop
#: and a plot is a risk setting that happens to be drawn.
CATEGORY_ORDER: tuple[Category, ...] = (
    Category.RISK,
    Category.EXECUTION,
    Category.BACKTEST,
    Category.LOGIC,
    Category.VISUAL,
)

#: English labels, so a category is legible before anybody writes a translation.
CATEGORY_LABELS: dict[str, str] = {
    Category.RISK: "Risk management",
    Category.EXECUTION: "Execution",
    Category.BACKTEST: "Backtesting",
    Category.LOGIC: "Trading logic",
    Category.VISUAL: "Visual",
}

#: ``input.<kind>`` → the control that edits it. Every kind the subset accepts
#: has a row: a kind with no row would render as a text box that silently
#: accepts anything, which is the one outcome worse than refusing it.
WIDGETS: dict[str, str] = {
    "bool": "toggle",
    "int": "number",
    "float": "number",
    "string": "text",
    "text_area": "textarea",
    "source": "source",
    "color": "color",
    "time": "datetime",
    "price": "number",
    "session": "session",
    "symbol": "text",
    "timeframe": "timeframe",
}

#: What ``input.source`` may be set to. The runtime resolves the submitted name
#: against ``ctx.series``, so this list is exactly the series that exist —
#: offering ``ta.ema(close, 9)`` as a source would be offering a series the
#: runtime has no way to build from a string.
SOURCE_CHOICES: tuple[str, ...] = (
    "close",
    "open",
    "high",
    "low",
    "hl2",
    "hlc3",
    "ohlc4",
    "hlcc4",
    "volume",
)

#: Kinds whose value is a number, and so is held to ``minval``/``maxval``.
NUMERIC_KINDS = frozenset({"int", "float", "price"})

#: Kinds whose value is plain text.
TEXT_KINDS = frozenset({"string", "text_area", "symbol", "session", "timeframe"})

#: ``strategy.*`` arguments that decide how much is risked or given back. An
#: input reaching one of these is a risk setting whatever it is called.
#:
#: The percent trio is what the subset accepts — §5 requires the same percentage
#: on every account, so an absolute ``stop=``/``limit=`` price is refused at
#: validation. The absolute names are listed anyway: they cost nothing while
#: unreachable, and the day one is accepted it is a risk argument on the first
#: upload rather than after somebody remembers this table.
RISK_ARGS = frozenset(
    {
        "loss_pct",
        "profit_pct",
        "qty_percent",
        "qty",
        "stop",
        "limit",
        "loss",
        "profit",
        "trail_price",
        "trail_points",
        "trail_offset",
    }
)

#: ``strategy.*`` arguments that shape *whether and how* an order goes out,
#: rather than what it is worth.
EXECUTION_ARGS = frozenset(
    {
        "when",
        "oca_name",
        "oca_type",
        "disable_alert",
    }
)

#: Arguments that only *describe* an order. A value named in an alert message or
#: a trade comment changes nothing about the order, and counting one as an
#: execution setting files half a strategy's inputs under Execution the moment
#: its author builds an informative alert string — which every published one
#: does.
TEXT_ARGS = frozenset({"alert_message", "comment", "text", "title", "tooltip"})

#: The calls that move a position. ``strategy.exit`` is treated apart because
#: the condition guarding it is a risk decision rather than a signal.
TRIGGER_CALLS = frozenset(
    {
        "strategy.entry",
        "strategy.order",
        "strategy.close",
        "strategy.close_all",
        "strategy.exit",
    }
)

#: Alerts are operational rather than decorative: the text of one is what a
#: person is woken up by, and no part of it is drawn on the chart.
NOTICE_CALLS = frozenset({"alert", "alertcondition"})

#: The names whose presence on the other side of a comparison make it a *date
#: window* rather than arithmetic.
CLOCK_NAMES = frozenset({"time", "time_close", "last_bar_time", "timenow"})

COMPARISONS = frozenset({"<", "<=", ">", ">=", "==", "!="})


@dataclass(frozen=True, slots=True)
class Dependency:
    """One input doing nothing unless another holds one of these values.

    Read off the strategy's own ``if``s. ``values`` is the set the *controller*
    must be in, as literals the form can compare against what it is holding —
    ``[true]`` for a bool gate, ``["ATR Baseline"]`` for a mode dropdown.
    """

    controller: str
    values: tuple[object, ...]

    def as_dict(self) -> dict:
        return {"controller": self.controller, "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class InputSpec:
    """One ``input.*`` call, as the settings form needs it.

    The first block is transcription — what the call site says. The second is
    derived by `analyse` from the rest of the script, and is what turns thirty
    rows in declaration order into a panel somebody can use.
    """

    name: str
    kind: str
    default: object
    title: str
    minval: object = None
    maxval: object = None
    options: tuple = ()
    #: ``step``, ``group``, ``inline`` and ``tooltip`` are the *layout* half of
    #: an input. A form that drops them turns thirty labelled, grouped controls
    #: into thirty rows in declaration order — technically the same settings,
    #: and unusable, which is a control problem rather than a cosmetic one.
    step: object = None
    group: str = ""
    inline: str = ""
    tooltip: str = ""

    # --- derived by `analyse` ----------------------------------------------

    #: Declaration order. TradingView's panel is in source order and so is this
    #: one: an author who put the length first meant it to be first.
    order: int = 0
    #: The control that edits it — `WIDGETS`, narrowed to a dropdown when the
    #: call carries ``options=``. Filled in at construction when it is left
    #: blank, so a spec built anywhere is drawable.
    widget: str = ""
    category: str = Category.LOGIC
    #: Why it landed in that category, as the sink that decided it. Shown on the
    #: row, because "this is a risk input" is a claim and the argument it
    #: reaches is the evidence.
    reason: str = ""
    depends_on: tuple[Dependency, ...] = ()
    #: False when nothing in the script reads it. Declared-and-unused is a real
    #: thing in published scripts and worth saying quietly, rather than leaving
    #: the operator to wonder why the number changes nothing.
    used: bool = True

    @property
    def choices(self) -> tuple:
        """What a dropdown offers — the script's ``options=``, or the sources."""
        if self.options:
            return tuple(self.options)
        if self.kind == "source":
            return SOURCE_CHOICES
        return ()

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "default": self.default,
            "title": self.title,
            "minval": self.minval,
            "maxval": self.maxval,
            "options": list(self.options),
            "step": self.step,
            "group": self.group,
            "inline": self.inline,
            "tooltip": self.tooltip,
            "order": self.order,
            "widget": self.widget,
            "category": str(self.category),
            "reason": self.reason,
            "depends_on": [row.as_dict() for row in self.depends_on],
            "used": self.used,
            "choices": list(self.choices),
        }

    @classmethod
    def from_data(cls, data: dict) -> InputSpec:
        """Rebuild one from stored JSON.

        The version's schema is written once, when the source is saved, and read
        back on every form load and every save. Re-parsing the source to
        validate a value would let a change in the parser silently retitle — or
        drop — a running bot's settings.
        """
        return cls(
            name=str(data.get("name") or ""),
            kind=str(data.get("kind") or "float"),
            default=data.get("default"),
            title=str(data.get("title") or data.get("name") or ""),
            minval=data.get("minval"),
            maxval=data.get("maxval"),
            options=tuple(data.get("options") or ()),
            step=data.get("step"),
            group=str(data.get("group") or ""),
            inline=str(data.get("inline") or ""),
            tooltip=str(data.get("tooltip") or ""),
            order=int(data.get("order") or 0),
            # Derived rather than defaulted when it is missing: a row stored
            # before the analyser existed carries a kind and no widget, and
            # falling back to "text" would draw a published strategy's whole
            # panel as free-text boxes.
            widget=str(data.get("widget") or ""),
            category=str(data.get("category") or Category.LOGIC),
            reason=str(data.get("reason") or ""),
            depends_on=tuple(
                Dependency(
                    controller=str(row.get("controller") or ""),
                    values=tuple(row.get("values") or ()),
                )
                for row in data.get("depends_on") or ()
                if isinstance(row, dict) and row.get("controller")
            ),
            used=bool(data.get("used", True)),
        )

    def __post_init__(self) -> None:
        # Derived here rather than defaulted, so that a spec transcribed by the
        # validator, one rebuilt from a row stored before the analyser existed,
        # and one built in a test all draw the same control.
        if not self.widget:
            object.__setattr__(self, "widget", _widget(self))


@dataclass(frozen=True, slots=True)
class InputGroup:
    """One ``group=`` heading, with the inputs that named it.

    The key *is* the string the script wrote — ``"03. Targets / Stop"`` —
    because that string is the only identity the group has. Scripts number their
    groups to force an order, and keeping the text keeps the ordering the author
    already did.
    """

    key: str
    title: str
    order: int
    names: tuple[str, ...]
    #: The ``inline=`` runs inside this group, in first-appearance order. A run
    #: is drawn as one line, which is what ``inline`` means in TradingView.
    rows: tuple[tuple[str, ...], ...] = ()

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "order": self.order,
            "names": list(self.names),
            "rows": [list(row) for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class InputSchema:
    """Everything the settings form is drawn from, and validated against."""

    fields: tuple[InputSpec, ...] = ()
    groups: tuple[InputGroup, ...] = ()

    def by_name(self, name: str) -> InputSpec | None:
        return next((row for row in self.fields if row.name == name), None)

    def defaults(self) -> dict:
        """What the script itself chose. "Reset to default" is this dict."""
        return {row.name: row.default for row in self.fields}

    def as_dict(self) -> dict:
        return {
            "fields": [row.as_dict() for row in self.fields],
            "groups": [row.as_dict() for row in self.groups],
            "categories": [
                {"key": str(key), "label": CATEGORY_LABELS[key]} for key in CATEGORY_ORDER
            ],
            "defaults": self.defaults(),
        }

    @classmethod
    def from_data(cls, data: object) -> InputSchema:
        """Rebuild from stored JSON — a dict as written by `as_dict`, or the
        bare field list that ``StrategyVersion.inputs_schema`` has always held.
        """
        if isinstance(data, list):
            fields = tuple(InputSpec.from_data(row) for row in data if isinstance(row, dict))
            return cls(fields=fields, groups=_group(fields))
        if not isinstance(data, dict):
            return cls()
        fields = tuple(
            InputSpec.from_data(row) for row in data.get("fields") or () if isinstance(row, dict)
        )
        groups = tuple(
            InputGroup(
                key=str(row.get("key") or ""),
                title=str(row.get("title") or ""),
                order=int(row.get("order") or 0),
                names=tuple(row.get("names") or ()),
                rows=tuple(tuple(inner) for inner in row.get("rows") or ()),
            )
            for row in data.get("groups") or ()
            if isinstance(row, dict)
        )
        return cls(fields=fields, groups=groups or _group(fields))


# --- the derivation ---------------------------------------------------------


def analyse(program: ast.Program | None, specs) -> InputSchema:
    """Widget, category, dependency and grouping, from the specs and the AST.

    With no AST — a script that did not parse — the widgets and the grouping
    still resolve, because those are properties of the declarations alone. Only
    the two analyses that read the *logic* are skipped, and the form still draws.
    """
    ordered = tuple(replace(spec, order=index) for index, spec in enumerate(specs))
    if program is None:
        return InputSchema(fields=ordered, groups=_group(ordered))

    reader = _Reader(program, {spec.name: spec for spec in ordered})
    reader.run()
    fields = tuple(
        replace(
            spec,
            category=str(reader.category(spec)),
            reason=reader.reason(spec),
            depends_on=reader.dependencies(spec),
            used=bool(reader.sites.get(spec.name)),
        )
        for spec in ordered
    )
    return InputSchema(fields=fields, groups=_group(fields))


def _widget(spec: InputSpec) -> str:
    """A dropdown the moment there is a fixed set to pick from, whatever the
    underlying type: ``input.int(2, options=[1, 2, 3])`` is three choices, and
    rendering it as a spinner invites a fourth the script cannot handle."""
    if spec.options:
        return "select"
    return WIDGETS.get(spec.kind, "text")


def _group(fields: tuple[InputSpec, ...]) -> tuple[InputGroup, ...]:
    """Groups in first-appearance order, each holding its inputs in source order.

    Ungrouped inputs keep their own bucket under the empty key rather than being
    swept into the first named group — TradingView shows them above the
    headings, and moving them changes which settings read as belonging together.
    """
    order: list[str] = []
    members: dict[str, list[str]] = {}
    runs: dict[tuple[str, str], list[str]] = {}
    for spec in fields:
        key = spec.group
        if key not in members:
            order.append(key)
            members[key] = []
        members[key].append(spec.name)
        if spec.inline:
            runs.setdefault((key, spec.inline), []).append(spec.name)
    return tuple(
        InputGroup(
            key=key,
            title=key,
            order=index,
            names=tuple(members[key]),
            rows=tuple(
                tuple(names)
                for (group_key, _), names in runs.items()
                if group_key == key and len(names) > 1
            ),
        )
        for index, key in enumerate(order)
    )


@dataclass(frozen=True, slots=True)
class _Guard:
    """One condition in force at a use site, and which way it has to go."""

    cond: ast.Node
    holds: bool


@dataclass(frozen=True, slots=True)
class _Site:
    """One place a value is consumed, and what it was consumed *as*."""

    category: Category
    #: The argument or call that decided it, for the row's `reason`.
    label: str
    guards: tuple[_Guard, ...]


class _Reader:
    """One walk of the AST, carrying the conditions in force.

    Two passes, and the order matters. The first follows values through
    assignments — ``tp1Price = entry + tp1RR * risk`` means every use of
    ``tp1Price`` is also a use of ``tp1RR``, and a panel that missed that would
    file the input that sets a target as unused. The second records where those
    values are consumed, and under which ``if``s.
    """

    def __init__(self, program: ast.Program, inputs: dict[str, InputSpec]) -> None:
        self.program = program
        self.inputs = inputs
        #: variable name → the inputs whose value flows into it.
        self.taint: dict[str, frozenset[str]] = {name: frozenset({name}) for name in inputs}
        #: input name → every place its value is consumed.
        self.sites: dict[str, list[_Site]] = {}
        self.functions = {fn.name: fn for fn in program.functions}
        #: Methods by *name* only. Dispatch is by receiver type, and resolving
        #: it would need the type inference the runtime does; taking every
        #: method of that name unions two parameter sets that a real call would
        #: have kept apart, which over-reports a use and never invents one.
        self.methods: dict[str, list[ast.MethodDef]] = {}
        for method in program.methods:
            self.methods.setdefault(method.name, []).append(method)

    def run(self) -> None:
        # Repeated, because a value can be assigned after the line that reads it
        # — a `var` declared at the top and reassigned inside a block is the
        # usual shape — and because an argument reaching a parameter opens a
        # chain that only the next pass can follow. It settles: taint sets only
        # ever union, so the fixpoint is reached or the cap stops a pathological
        # script from paying for a fourth walk.
        for _ in range(4):
            before = sum(len(row) for row in self.taint.values())
            for node in ast.walk(self.program):
                if isinstance(node, ast.Assign):
                    flowed = self._sources(node.value)
                    for target in node.targets:
                        self._taint(target, flowed)
                elif isinstance(node, ast.Reassign):
                    self._taint(node.target, self._sources(node.value))
                elif isinstance(node, ast.FieldAssign):
                    flowed = self._sources(node.value)
                    dotted = ast.dotted_name(node.obj)
                    if dotted:
                        self._taint(f"{dotted}.{node.attr}", flowed)
                    # And under the bare field name, which is what carries a
                    # value back *out* of a method: the body writes `c.t1` on
                    # its receiver parameter and the caller reads `campaign.t1`
                    # off its own variable. Two objects with a field of the same
                    # name share the taint, which over-reports a use — the
                    # direction this reader is allowed to be wrong in.
                    self._taint(f".{node.attr}", flowed)
                elif isinstance(node, ast.Call):
                    self._bind(node)
            if sum(len(row) for row in self.taint.values()) == before:
                break
        self._visit(self.program, (), None)

    # --- pass one: where values go -----------------------------------------

    def _taint(self, target: str, flowed: frozenset[str]) -> None:
        if not flowed or target in self.inputs:
            # An input's own declaration is not a use of itself, and nothing may
            # overwrite the identity taint that makes it findable.
            return
        self.taint[target] = self.taint.get(target, frozenset()) | flowed

    def _bind(self, node: ast.Call) -> None:
        """An argument to a user function or method taints its parameter.

        Without this a published strategy's settings mostly vanish: the shape it
        is written in is ``campaign.open(step, tp1RR, tp2RR, tp3RR)``, and a
        reader that stops at the call boundary reports six of the most important
        inputs on the panel as unused. The body is then walked like any other
        code, so the parameter's uses inside it are the input's uses.

        The call site's own guards do **not** travel with the binding. A body
        visited once cannot carry the conditions of every call, and inventing a
        gate is the one error this whole analysis is arranged not to make; the
        guards inside the body still count, so a dependency written there is
        still found.
        """
        dotted = ast.dotted_name(node.func) or ""
        name = dotted.rsplit(".", 1)[-1]
        targets: list[tuple[tuple[str, ...], ast.Node | None]] = []
        if "." not in dotted and name in self.functions:
            fn = self.functions[name]
            targets.append((fn.params, None))
        for method in self.methods.get(name, ()) if "." in dotted else ():
            targets.append(((method.receiver_name, *method.params), node.func))
        for params, receiver in targets:
            if receiver is not None and isinstance(receiver, ast.Member):
                self._taint(params[0], self._sources(receiver.obj))
                params = params[1:]
            positional = [arg.value for arg in node.args if not arg.name]
            for param, value in zip(params, positional, strict=False):
                self._taint(param, self._sources(value))
            for arg in node.args:
                if arg.name and arg.name in params:
                    self._taint(arg.name, self._sources(arg.value))

    def _sources(self, node: ast.Node | None) -> frozenset[str]:
        """Which inputs feed this expression.

        Names only — a user function is followed through its *arguments* rather
        than into its body, which is enough because the argument is written at
        the call site. It over-reports rather than under-reports, and that is
        the safe direction: the cost is an input filed as logic that only draws.
        """
        if node is None:
            return frozenset()
        found: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                found |= self.taint.get(child.name, frozenset())
            elif isinstance(child, ast.Member):
                dotted = ast.dotted_name(child)
                if dotted:
                    found |= self.taint.get(dotted, frozenset())
                found |= self.taint.get(f".{child.attr}", frozenset())
        return frozenset(found)

    # --- pass two: what consumes them --------------------------------------

    def _record(self, node: ast.Node | None, site: _Site) -> None:
        for name in self._sources(node):
            self.sites.setdefault(name, []).append(site)

    def _visit(self, node: ast.Node, guards: tuple[_Guard, ...], sink: _Site | None) -> None:
        """Depth-first, carrying the guards and the sink currently in force.

        The sink is pushed *down* rather than resolved at the argument, so that
        ``strategy.exit(stop = useAtr ? atrStop : swingStop)`` records
        ``atrStop`` as a risk input **guarded by** ``useAtr`` — resolving at the
        argument would have flattened the ternary and lost the gate.
        """
        if sink is not None and isinstance(node, ast.Name | ast.Member):
            # The leaf is where a use is recorded, not the argument that
            # contains it: by here the guards are the ones actually in force at
            # this name, ternaries and short-circuits included.
            self._record(node, sink)
            return
        if isinstance(node, ast.If):
            self._visit(node.cond, guards, sink)
            self._visit(node.then, guards + (_Guard(node.cond, True),), sink)
            if node.otherwise is not None:
                self._visit(node.otherwise, guards + (_Guard(node.cond, False),), sink)
            return
        if isinstance(node, ast.Ternary):
            self._visit(node.cond, guards, sink)
            self._visit(node.then, guards + (_Guard(node.cond, True),), sink)
            self._visit(node.otherwise, guards + (_Guard(node.cond, False),), sink)
            return
        if isinstance(node, ast.Switch) and node.subject is not None:
            self._visit(node.subject, guards, sink)
            for case in node.cases:
                if case.match is None:
                    self._visit(case.body, guards, sink)
                    continue
                match = ast.Binary(case.match.span, "==", node.subject, case.match)
                self._visit(case.body, guards + (_Guard(match, True),), sink)
            return
        if isinstance(node, ast.Binary) and node.op in ("and", "or"):
            # The right-hand side of `a and b` runs only when `a` holds. Pine's
            # `and` short-circuits, and so does the reading of it here.
            self._visit(node.left, guards, sink)
            self._visit(node.right, guards + (_Guard(node.left, node.op == "and"),), sink)
            return
        if isinstance(node, ast.Binary) and node.op in COMPARISONS:
            self._window(node, guards)
        if isinstance(node, ast.Call):
            self._visit_call(node, guards, sink)
            return
        for child in ast.children(node):
            self._visit(child, guards, sink)

    def _window(self, node: ast.Binary, guards: tuple[_Guard, ...]) -> None:
        """``time >= startTime`` — the one comparison that means "backtest window".

        Recognised by the *clock* on the other side, so a script that writes it
        the other way round, or against ``time_close``, or with ``timestamp()``
        inline, all land in the same place.
        """
        left, right = self._sources(node.left), self._sources(node.right)
        if bool(left) == bool(right):
            return
        clocked = node.right if left else node.left
        if not _is_clock(clocked):
            return
        self._record(
            node.left if left else node.right,
            _Site(Category.BACKTEST, "compared against time", guards),
        )

    def _visit_call(self, node: ast.Call, guards: tuple[_Guard, ...], sink: _Site | None) -> None:
        dotted = ast.dotted_name(node.func) or ""
        root = dotted.split(".", 1)[0]
        visual = dotted in VISUAL_FUNCTIONS or root in DRAWING_NAMESPACES
        notice = dotted in NOTICE_CALLS
        trigger = dotted in TRIGGER_CALLS

        if trigger or visual or notice:
            # A condition that decides whether an order goes out is as much a
            # trading setting as the length inside it — more so, usually. The
            # guard is attributed at the call, keeping the guards outside it, so
            # a gate on a gate still reads correctly.
            # A condition is a *signal*, whichever call it guards — including
            # `strategy.exit`. Filing an exit's guard as risk read well for the
            # take-profit toggle and badly for everything else: the usual shape
            # is one `if` holding both the entry and its exit, and every length
            # in that condition would have come back as a risk setting.
            decided = (
                Category.LOGIC if trigger else Category.EXECUTION if notice else Category.VISUAL
            )
            for index, guard in enumerate(guards):
                self._record(guard.cond, _Site(decided, f"condition on {dotted}", guards[:index]))

        for arg in node.args:
            self._visit(
                arg.value,
                guards,
                self._sink_for(dotted, arg, guards, sink, visual=visual, notice=notice),
            )

    def _sink_for(
        self,
        dotted: str,
        arg: ast.Argument,
        guards: tuple[_Guard, ...],
        outer: _Site | None,
        *,
        visual: bool,
        notice: bool,
    ) -> _Site | None:
        """What this argument makes of the value inside it.

        ``input.*``'s own arguments are excluded on purpose: the title, the
        bounds and the group are metadata *about* the setting, not a use of it,
        and counting them would make every input "used" and every ``group=``
        constant a logic input.
        """
        if dotted.split(".", 1)[0] == "input":
            return None
        if dotted in TRIGGER_CALLS:
            if arg.name in RISK_ARGS:
                return _Site(Category.RISK, f"{dotted}({arg.name}=)", guards)
            if arg.name in EXECUTION_ARGS:
                return _Site(Category.EXECUTION, f"{dotted}({arg.name}=)", guards)
            if arg.name in TEXT_ARGS:
                return _Site(Category.VISUAL, f"{dotted}({arg.name}=)", guards)
            if dotted == "strategy.exit":
                return _Site(Category.RISK, f"{dotted}()", guards)
            return _Site(Category.LOGIC, f"{dotted}()", guards)
        if dotted.startswith("strategy.risk"):
            return _Site(Category.RISK, f"{dotted}()", guards)
        if notice:
            return _Site(Category.EXECUTION, f"{dotted}()", guards)
        if visual:
            return _Site(Category.VISUAL, f"{dotted}()", guards)
        # Anything else — `ta.*`, `math.*`, a user function — is a computation,
        # and carries whatever it was already being computed *for*: a length
        # inside an ATR inside a stop is a risk setting, and the same length
        # inside a plot is not.
        return outer

    # --- what the walk concluded -------------------------------------------

    def category(self, spec: InputSpec) -> Category:
        sites = self.sites.get(spec.name) or []
        if not sites:
            # Nothing reads it. Colours and free text fall to decoration,
            # anything else to logic — the safe side, since a number filed as
            # decoration is a number nobody checks before going live.
            return Category.VISUAL if spec.kind in ("color", "text_area") else Category.LOGIC
        found = {site.category for site in sites}
        return next((row for row in CATEGORY_ORDER if row in found), Category.LOGIC)

    def reason(self, spec: InputSpec) -> str:
        """The evidence for the category — a direct use in preference to a
        guard. "``strategy.exit(stop=)``" tells the reader more than "it is in a
        condition on ``strategy.exit``", and both are true of the same input."""
        decided = self.category(spec)
        matching = [site for site in self.sites.get(spec.name) or [] if site.category is decided]
        direct = next((s for s in matching if not s.label.startswith("condition on")), None)
        chosen = direct or (matching[0] if matching else None)
        return chosen.label if chosen else ""

    def dependencies(self, spec: InputSpec) -> tuple[Dependency, ...]:
        """The conditions every non-visual use of this input sits under.

        Visual uses are left out of the intersection rather than out of the
        analysis: a target price that is *plotted* unconditionally and *traded*
        only when take-profit is on is still gated for the purpose that matters.
        A dependency here says "this changes nothing about the orders", never
        "this changes nothing".
        """
        sites = [
            site for site in self.sites.get(spec.name) or [] if site.category is not Category.VISUAL
        ]
        if not sites:
            return ()
        common: dict[str, frozenset] | None = None
        for site in sites:
            atoms = self._atoms(site.guards)
            if not atoms:
                return ()
            if common is None:
                common = atoms
                continue
            # Two uses under different arms of the same controller mean the
            # input is live either way, so the arms are unioned and the gate
            # widens; a controller missing from one of the two disappears.
            common = {
                name: values | atoms[name] for name, values in common.items() if name in atoms
            }
            if not common:
                return ()
        declared = {name: index for index, name in enumerate(self.inputs)}
        rows = [
            Dependency(controller=name, values=tuple(sorted(values, key=_sort_key)))
            for name, values in (common or {}).items()
            if name != spec.name
            and name in self.inputs
            # A gate that lets everything through is not a gate. It shows up
            # when a use sits under `mode != "off"` and every option was
            # collected on the way.
            and 0 < len(values) < len(self._domain(name) or values | {None})
        ]
        rows.sort(key=lambda row: declared.get(row.controller, 0))
        return tuple(rows[:3])

    def _domain(self, name: str) -> tuple:
        """Every value the controller can take, for deciding whether a gate
        narrows anything at all."""
        spec = self.inputs.get(name)
        if spec is None:
            return ()
        if spec.options:
            return tuple(spec.options)
        if spec.kind == "bool":
            return (True, False)
        return ()

    def _atoms(self, guards: tuple[_Guard, ...]) -> dict[str, frozenset]:
        """The guard stack reduced to "input X must be one of these values".

        Only the shapes a form can act on survive: a bool read, its negation and
        an equality against one of a dropdown's options. Everything else — two
        series compared, a call — contributes nothing, which is what makes an
        unrecognised guard *drop* the dependency rather than invent one.
        """
        atoms: dict[str, frozenset] = {}
        for guard in guards:
            for name, values in self._atom(guard.cond, guard.holds):
                atoms[name] = atoms[name] & values if name in atoms else values
        return atoms

    def _atom(self, node: ast.Node, holds: bool):
        """Yield ``(controller, the values it must hold)`` for one condition."""
        if isinstance(node, ast.Unary) and node.op in ("not", "!"):
            yield from self._atom(node.operand, not holds)
            return
        if isinstance(node, ast.Binary) and node.op in ("and", "or"):
            # `a and b` holding means both hold; `not (a or b)` means neither
            # does. The other two combinations say nothing about either side.
            if (node.op == "and") == holds:
                yield from self._atom(node.left, holds)
                yield from self._atom(node.right, holds)
            return
        if isinstance(node, ast.Name) and node.name in self.inputs:
            if self.inputs[node.name].kind == "bool":
                yield node.name, frozenset({holds})
            return
        if isinstance(node, ast.Binary) and node.op in ("==", "!="):
            equal = holds if node.op == "==" else not holds
            for side, other in ((node.left, node.right), (node.right, node.left)):
                if not isinstance(side, ast.Name) or side.name not in self.inputs:
                    continue
                literal = _literal_value(other)
                if literal is None:
                    return
                if equal:
                    yield side.name, frozenset({literal})
                else:
                    domain = self._domain(side.name)
                    if domain:
                        yield side.name, frozenset(v for v in domain if v != literal)
                return


def _is_clock(node: ast.Node) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.name in CLOCK_NAMES:
            return True
        if isinstance(child, ast.Call) and ast.dotted_name(child.func) == "timestamp":
            return True
    return False


def _literal_value(node: ast.Node) -> object:
    if isinstance(node, ast.StringLit):
        return node.value
    if isinstance(node, ast.BoolLit):
        return node.value
    if isinstance(node, ast.NumberLit):
        return int(node.value) if node.value.isdigit() else float(node.value)
    return None


def _sort_key(value: object) -> tuple:
    """Numbers before text, each in its own order — one comparable key, because
    a dependency's values can be a bool set, a string set or neither."""
    if isinstance(value, bool):
        return (1, "", str(value))
    if isinstance(value, int | float):
        return (0, f"{value:020.6f}", "")
    return (2, "", str(value))


# --- the values, on the way back in -----------------------------------------

#: What a colour field may hold. Pine writes ``#RRGGBB`` and ``#RRGGBBAA``; the
#: form's picker writes the first and the transparency variant is what a script
#: default arrives as, so both are accepted and nothing else is.
_HEX = frozenset("0123456789abcdefABCDEF")


def validate_values(schema: InputSchema, raw: object) -> tuple[dict, list[dict]]:
    """The submitted settings, coerced to the shapes the script declared.

    Returns ``(clean, errors)``. Two rules make this the same shape as
    ``properties.validate_overrides`` on purpose:

    **Only differences are kept.** A value equal to the script's own default is
    dropped, so "reset to default" is a deleted key rather than a copy of a
    number that then never follows the script. A bot points at an immutable
    version, so the default it falls back to cannot move under it.

    **A bad value is named, not dropped.** Somebody is looking at the field. A
    silently discarded value would come back as the default on the next load,
    with nothing on screen to say the change never happened — and on this panel
    the change is a stop distance.
    """
    errors: list[dict] = []
    if raw in (None, ""):
        return {}, errors
    if not isinstance(raw, dict):
        return {}, [{"name": "", "message": "inputs must be an object of name → value"}]

    clean: dict = {}
    for name, value in raw.items():
        spec = schema.by_name(str(name))
        if spec is None:
            errors.append(
                {
                    "name": str(name),
                    "message": (
                        f"'{name}' is not an input of this strategy version — it was "
                        "renamed or removed"
                    ),
                }
            )
            continue
        coerced, problem = _coerce(spec, value)
        if problem:
            errors.append({"name": spec.name, "message": problem})
            continue
        if _same(coerced, spec.default):
            continue
        clean[spec.name] = coerced
    return clean, errors


def resolve_values(schema: InputSchema, overrides: object) -> dict:
    """Every input's effective value: the script's default under the override.

    One direction, one function, exactly like ``properties.resolve`` — the panel
    is handed outcomes rather than two dictionaries and the rule for combining
    them, because the browser recomputing the merge is a second place for it to
    be got wrong and the backtest header is what would disagree.
    """
    values = schema.defaults()
    clean, _ = validate_values(schema, overrides)
    values.update(clean)
    return values


def _same(value: object, default: object) -> bool:
    if isinstance(value, bool) or isinstance(default, bool):
        return value is default
    if isinstance(value, int | float) and isinstance(default, int | float):
        return float(value) == float(default)
    return value == default


def _coerce(spec: InputSpec, value: object) -> tuple[object, str]:
    """One value against one declaration. ``("", message)`` on refusal."""
    if value is None:
        return None, "no value"
    kind = spec.kind

    if kind == "bool":
        if isinstance(value, bool):
            return value, ""
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true", ""
        return None, "must be true or false"

    if kind == "time":
        # Milliseconds, Pine's unit and the panel's. A seconds value from before
        # the switch is read as the same moment, not as a date in 1970.
        from apps.pine.builtins import as_pine_ms

        value = as_pine_ms(value)
    if kind in NUMERIC_KINDS or kind == "time":
        number, problem = _number(value, whole=kind in ("int", "time"))
        if problem:
            return None, problem
        if spec.choices and number not in spec.choices:
            return None, f"must be one of {', '.join(str(row) for row in spec.choices)}"
        low, high = spec.minval, spec.maxval
        if isinstance(low, int | float) and not isinstance(low, bool) and number < low:
            return None, f"must be at least {low}"
        if isinstance(high, int | float) and not isinstance(high, bool) and number > high:
            return None, f"must be at most {high}"
        return number, ""

    if kind == "source":
        text = str(value)
        if text not in SOURCE_CHOICES:
            return None, f"must be one of {', '.join(SOURCE_CHOICES)}"
        return text, ""

    if kind == "color":
        text = str(value).strip()
        body = text[1:]
        if not text.startswith("#") or len(body) not in (6, 8) or set(body) - _HEX:
            return None, "must be a colour like #00E5A8"
        return "#" + body.upper(), ""

    if kind in TEXT_KINDS:
        text = str(value)
        if spec.choices and text not in [str(row) for row in spec.choices]:
            return None, f"must be one of {', '.join(str(row) for row in spec.choices)}"
        return text, ""

    # An unknown kind is a kind the subset accepted and this table has not
    # caught up with. Refuse it rather than storing a value the runtime will
    # coerce into something nobody chose.
    return None, f"'{kind}' inputs cannot be set from the panel yet"


def _number(value: object, *, whole: bool) -> tuple[object, str]:
    if isinstance(value, bool):
        return None, "must be a number"
    if isinstance(value, int | float):
        number = value
    else:
        try:
            number = float(str(value))
        except (TypeError, ValueError):
            return None, "must be a number"
    if whole:
        if float(number) != int(number):
            return None, "must be a whole number"
        return int(number), ""
    # Kept as a float rather than a Decimal because it is a *script parameter*,
    # not money: the runtime re-reads it as `Decimal(str(value))` against the
    # script's own default, which is where the Decimal rule applies.
    return float(number), ""
