"""Subset enforcement and the semantic checks the runtime cannot make.

Everything here runs **once, at upload time**, and everything it reports carries
a line and a column. Two rules shape the whole file:

  **Reject by name (Q24).** A construct outside the v1 subset never loads and is
  never ignored. The message says which construct and why, from the one registry
  in ``subset.py``, so a rejection cannot ship without its message.

  **Report what is reinterpreted (Q20).** A script's ``qty`` is parsed and then
  ignored — but with a warning, at upload time, never silently. Same for a
  ``varip`` under Q23's confirmed-bars-only rule.

The checks that are here rather than in the runtime are the ones whose failure
mode is a *repeating* one: an order call inside a loop fires N entries per bar,
at 99% of every account, once per bar, forever. Catching it when someone presses
Save costs nothing; catching it at 03:00 costs the book.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from apps.pine import ast_nodes as ast
from apps.pine import properties
from apps.pine.errors import PineError, PineNameError, PineSyntaxError, PineUnsupported, PineWarning
from apps.pine.lexer import declared_version, tokenize
from apps.pine.limits import DEFAULT_LIMITS, Limits
from apps.pine.parser import Parser
from apps.pine.properties import StrategyProperties
from apps.pine.subset import (
    BARE_FUNCTIONS,
    BUILTIN_SERIES,
    BUILTIN_VALUES,
    CLOSE_SIZE_ARGS,
    DECLARATION_CONSTANTS,
    DECORATIVE_NAMESPACES,
    DRAWING_NAMESPACES,
    DRAWING_READBACKS,
    DRAWING_TYPES,
    EXIT_PERCENT_ARGS,
    NAMESPACE_FUNCTIONS,
    NAMESPACE_VALUES,
    REJECTED_CLOSE_ARGS,
    REJECTED_EXIT_ARGS,
    REJECTED_KEYWORDS,
    REJECTED_NAMES,
    REJECTED_NAMESPACES,
    REJECTED_STRATEGY_ARGS,
    STRATEGY_ACCEPTED_ARGS,
    STRATEGY_PROPERTY_ARGS,
    VISUAL_FUNCTIONS,
)
from apps.pine.tokens import TokenKind

ORDER_CALLS = frozenset({"strategy.entry", "strategy.close", "strategy.close_all", "strategy.exit"})

#: The Pine versions this platform reads. v5 is what Q24 named; v6 is accepted
#: because the subset's semantics are the shared ones — the operators, the
#: execution model and every ``ta.*`` formula are identical between them, and
#: ``reference/pinescriptv6/`` is what the implementation is checked against.
#: The v5→v6 differences that could bite inside the subset are boolean
#: short-circuiting and ``na``-in-a-condition; both are recorded as Q34 and
#: neither is reachable from a construct this subset accepts without the script
#: relying on a side effect inside an operand, which it has nowhere to put.
SUPPORTED_VERSIONS = frozenset({5, 6})

#: ``strategy.entry`` arguments that name a size. Parsed, ignored, reported (Q20).
SIZE_ARGS = frozenset({"qty", "qty_percent"})

#: The built-in types a UDT field or a method receiver may be declared as. A UDT
#: may also be declared as another, already-declared UDT — checked against
#: ``_Checker.types`` rather than this set. ``objects.md`` "Shadowing": these
#: names cannot themselves be used for a UDT.
FUNDAMENTAL_TYPES = frozenset({"int", "float", "bool", "string", "color"})


@dataclass(frozen=True, slots=True)
class InputSpec:
    """One ``input.*`` call, as the Phase 8 parameter form needs it."""

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
        }


@dataclass(slots=True)
class ValidationResult:
    """Everything one pass found. Mutable — the validator accumulates into it."""

    program: ast.Program | None = None
    errors: list[PineError] = field(default_factory=list)
    warnings: list[PineWarning] = field(default_factory=list)
    inputs: list[InputSpec] = field(default_factory=list)
    ta_call_sites: int = 0
    node_count: int = 0
    #: ``ta.*`` call sites the runtime cannot hoist to the top of the bar. See
    #: ``_check_hoistable`` — each one is a warning, never a silent difference.
    unhoistable: list[str] = field(default_factory=list)
    #: TradingView's Properties tab as ``strategy()`` declared it, over the
    #: platform's defaults. The panel's form and the backtest read this one
    #: object, so the numbers a report was produced with are the numbers the
    #: form showed.
    properties: StrategyProperties = field(default_factory=StrategyProperties)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": [e.as_dict() for e in self.errors],
            "warnings": [w.as_dict() for w in self.warnings],
            "inputs": [i.as_dict() for i in self.inputs],
            "ta_call_sites": self.ta_call_sites,
            "node_count": self.node_count,
            "properties": self.properties.as_dict(),
            "property_notes": {
                "live_departures": self.properties.live_departures(),
                "inert": self.properties.inert_here(),
            },
        }


def validate(source: str, *, limits: Limits = DEFAULT_LIMITS) -> ValidationResult:
    """Parse and check ``source``. Never raises: every fault comes back as data.

    Collecting rather than raising is what the Phase 8 editor needs — a script
    with four mistakes should underline four, not send the author round the loop
    four times. ``pine_check`` and the ``validate`` endpoint both render this.
    """
    result = ValidationResult()

    if len(source.encode("utf-8")) > limits.max_script_bytes:
        result.errors.append(
            PineUnsupported(
                f"this script is larger than the {limits.max_script_bytes}-byte limit",
                code="script_too_large",
            )
        )
        return result

    # The rejected keywords are lexed as keywords and would otherwise come back
    # as a bare syntax error. Checking the token stream first is what turns
    # "unexpected 'import'" into the message Q24 requires.
    try:
        tokens = tokenize(source)
    except PineError as exc:
        result.errors.append(exc)
        return result

    for token in tokens:
        if token.kind == TokenKind.KEYWORD and token.value in REJECTED_KEYWORDS:
            row = REJECTED_KEYWORDS[token.value]
            result.errors.append(
                PineUnsupported(row.message, code=row.code, span=token.span)
            )
    if result.errors:
        return result

    try:
        program = Parser(tokens, version=declared_version(source)).parse()
    except PineError as exc:
        # A construct outside the subset can also be outside the *grammar* —
        # `array.new<float>()` fails on the type parameters before anything
        # looks at the namespace. Q24 wants the construct named, so the token
        # stream is swept for a rejected namespace.
        #
        # Only a namespace *at or before* the failure explains it. A sweep of
        # the whole file used to replace the parse error outright, which turned
        # one unreadable line into sixty confident errors about lines that were
        # fine — the failure mode this branch is supposed to prevent, pointed
        # the other way.
        named = [
            row
            for row in _rejected_namespace_tokens(tokens)
            if exc.span is None or row.span is None or row.span.line <= exc.span.line
        ]
        result.errors.extend(named or [exc])
        return result

    result.program = program
    _Checker(program, result, limits).run()
    return result


def _rejected_namespace_tokens(tokens) -> list[PineError]:
    """Rejected namespaces spotted in the raw token stream: ``array.``, ``map.``…

    Only used when the parse failed. A bare ``label = high - low`` is a perfectly
    good variable, so the dot is what makes it a namespace reference.
    """
    found: list[PineError] = []
    seen: set[tuple[str, int, int]] = set()
    for index, token in enumerate(tokens):
        if token.kind != TokenKind.NAME:
            continue
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if following is None or following.kind != TokenKind.OP or following.value != ".":
            continue
        row = REJECTED_NAMESPACES.get(token.value)
        if row is None:
            continue
        key = (row.code, token.span.line, token.span.col)
        if key in seen:
            continue
        seen.add(key)
        found.append(PineUnsupported(row.message, code=row.code, span=token.span))
    return found


class _Checker:
    def __init__(self, program: ast.Program, result: ValidationResult, limits: Limits) -> None:
        self.program = program
        self.result = result
        self.limits = limits
        self.functions = {fn.name: fn for fn in program.functions}
        self.types = {t.name: t for t in program.types}
        self.enums = {e.name: e for e in program.enums}
        #: method name -> {receiver type name}. A name may carry several
        #: overloads, one per receiver type (methods.md "Method overloading").
        self.methods: dict[str, set[str]] = {}
        for method in program.methods:
            self.methods.setdefault(method.name, set()).add(method.receiver_type)
        self.globals: set[str] = set()
        #: Best-effort ``variable -> UDT name`` from ``T x = na`` / ``x = T.new()``
        #: declarations. Populated in ``_collect_globals``; used to check field
        #: and method access without a full type inference pass.
        self.var_types: dict[str, str] = {}
        #: ``name -> literal`` for a top-level constant declaration. Only read
        #: for an input's display metadata, never for anything that decides.
        self.const_strings: dict[str, object] = {}

    # --- entry point --------------------------------------------------------

    def run(self) -> None:
        self._collect_unconditional()
        self._check_version()
        self._check_declaration()
        self._count_nodes()
        self._collect_globals()
        self._check_type_defs()
        self._check_enum_defs()
        self._check_method_defs()
        self._walk(self.program, ancestors=())
        self._check_recursion()
        self._check_exit_reachability()

    def _collect_unconditional(self) -> None:
        """Which user functions and methods run on **every** bar.

        One a bar always reaches is, for the purposes of a stateful ``ta.*``
        inside it, the same as top level: the indicator advances once per bar
        either way. A function reached only from inside an ``if`` is not, and
        that is what ``_check_hoistable`` warns about.

        Fixpoint rather than one pass, because "unconditional" is transitive:
        a helper called only from another helper is unconditional exactly when
        that one is. Conservative in the direction that warns — a callee with
        no call site at all is left out.
        """
        callers: dict[str, list[str | None]] = {}

        def visit(node: ast.Node, ancestors: tuple[ast.Node, ...]) -> None:
            if isinstance(node, ast.Call):
                name = ast.dotted_name(node.func)
                callee = name if name in self.functions else None
                if callee is None and isinstance(node.func, ast.Member):
                    attr = node.func.attr
                    callee = attr if attr in self.methods else None
                if callee is not None and not any(
                    isinstance(a, ast.If | ast.Ternary | ast.Switch | ast.For | ast.ForIn
                               | ast.While)
                    for a in ancestors
                ):
                    owner = next(
                        (
                            a.name
                            for a in reversed(ancestors)
                            if isinstance(a, ast.FuncDef | ast.MethodDef)
                        ),
                        None,
                    )
                    callers.setdefault(callee, []).append(owner)
            for child in ast.children(node):
                visit(child, (*ancestors, node))

        visit(self.program, ())

        #: ``None`` as a caller means "called straight from the bar".
        self._unconditional: set[str] = set()
        changed = True
        while changed:
            changed = False
            for callee, owners in callers.items():
                if callee in self._unconditional:
                    continue
                if any(owner is None or owner in self._unconditional for owner in owners):
                    self._unconditional.add(callee)
                    changed = True

    def _error(self, message: str, *, code: str, span, cls=PineUnsupported) -> None:
        self.result.errors.append(cls(message, code=code, span=span))

    def _warn(self, message: str, *, code: str, span) -> None:
        self.result.warnings.append(PineWarning(message, code=code, span=span))

    # --- header -------------------------------------------------------------

    def _check_version(self) -> None:
        version = self.program.version
        if version is None:
            self._error(
                "no //@version= annotation — this platform runs Pine v5",
                code="missing_version",
                span=self.program.span,
                cls=PineSyntaxError,
            )
        elif version not in SUPPORTED_VERSIONS:
            self._error(
                f"this script declares Pine v{version}; this platform runs v5 and v6",
                code="wrong_version",
                span=self.program.span,
            )

    def _check_declaration(self) -> None:
        """Exactly one ``strategy()`` call, and it is the first statement."""
        calls = [
            node
            for node in ast.walk(self.program)
            if isinstance(node, ast.Call) and ast.dotted_name(node.func) == "strategy"
        ]
        indicators = [
            node
            for node in ast.walk(self.program)
            if isinstance(node, ast.Call) and ast.dotted_name(node.func) in ("indicator", "study")
        ]
        if indicators and not calls:
            self._error(
                "this is an indicator, not a strategy — a bot needs strategy() so it has "
                "entries and exits to route",
                code="not_a_strategy",
                span=indicators[0].span,
            )
            return
        if not calls:
            self._error(
                "no strategy() declaration — it must be the first statement",
                code="missing_strategy",
                span=self.program.span,
            )
            return
        if len(calls) > 1:
            self._error(
                "more than one strategy() declaration",
                code="duplicate_strategy",
                span=calls[1].span,
            )

        first = self.program.body[0] if self.program.body else None
        declared_first = (
            isinstance(first, ast.ExprStmt)
            and isinstance(first.value, ast.Call)
            and ast.dotted_name(first.value.func) == "strategy"
        )
        if not declared_first:
            self._error(
                "strategy() must be the first statement in the script",
                code="strategy_not_first",
                span=calls[0].span,
            )
        self._check_strategy_args(calls[0])

    def _check_strategy_args(self, call: ast.Call) -> None:
        for index, arg in enumerate(call.args):
            name = arg.name
            if not name:
                # Positional: title, then shorttitle. Both harmless.
                if index > 1:
                    self._error(
                        "pass strategy() options by name — a positional argument past "
                        "shorttitle cannot be checked against the subset",
                        code="strategy_positional",
                        span=arg.span,
                    )
                continue
            if name in REJECTED_STRATEGY_ARGS:
                row = REJECTED_STRATEGY_ARGS[name]
                # pyramiding=0 is the platform's own behaviour stated explicitly,
                # so it is accepted; any other value contradicts §5 sizing.
                if name == "pyramiding" and _literal_is_zero(arg.value):
                    continue
                if name == "calc_on_every_tick" and _literal_is_false(arg.value):
                    continue
                self._error(row.message, code=row.code, span=arg.span)
                continue
            if name in STRATEGY_PROPERTY_ARGS:
                continue
            if name not in STRATEGY_ACCEPTED_ARGS:
                self._error(
                    f"strategy() has no supported argument named {name!r}",
                    code="unknown_strategy_arg",
                    span=arg.span,
                )

        declared, notes = properties.parse(call)
        self.result.properties = properties.resolve(declared=declared)
        for name, reason, span in notes:
            # Q20's rule, widened to the Properties tab: a property that will
            # not be honoured, or is honoured only in the backtest, says so at
            # upload time rather than in a footnote nobody reads.
            self.result.warnings.append(
                PineWarning(reason, code=_PROPERTY_CODES[name in properties.INERT], span=span)
            )

    # --- caps ---------------------------------------------------------------

    def _count_nodes(self) -> None:
        nodes = list(ast.walk(self.program))
        self.result.node_count = len(nodes)
        if len(nodes) > self.limits.max_ast_nodes:
            self._error(
                f"this script has {len(nodes)} nodes, over the {self.limits.max_ast_nodes} limit",
                code="script_too_complex",
                span=self.program.span,
            )
        ta_sites = [
            node
            for node in nodes
            if isinstance(node, ast.Call)
            and (ast.dotted_name(node.func) or "").startswith("ta.")
        ]
        self.result.ta_call_sites = len(ta_sites)
        if len(ta_sites) > self.limits.max_ta_call_sites:
            self._error(
                f"this script has {len(ta_sites)} ta.* call sites, over the "
                f"{self.limits.max_ta_call_sites} limit — every one of them advances "
                f"on every bar",
                code="too_many_indicators",
                span=self.program.span,
            )

    # --- names --------------------------------------------------------------

    def _collect_globals(self) -> None:
        for node in ast.walk(self.program):
            if isinstance(node, ast.Assign):
                self.globals.update(node.targets)
                if len(node.targets) == 1:
                    udt = self._constructed_type(node.value)
                    if udt is not None:
                        self.var_types[node.targets[0]] = udt
                    literal = _literal(node.value)
                    if literal is not None and not node.qualifier:
                        # `string G_TARGET = "03. Targets / Stop"`, then
                        # `group = G_TARGET` on every input below it. Without
                        # this the form loses every group heading in a script
                        # that names them the way the style guide asks for.
                        self.const_strings[node.targets[0]] = literal
            elif isinstance(node, ast.Reassign):
                self.globals.add(node.target)
                self.const_strings.pop(node.target, None)
            elif isinstance(node, ast.FuncDef):
                self.globals.add(node.name)
                self.globals.update(node.params)
            elif isinstance(node, ast.MethodDef):
                self.globals.add(node.receiver_name)
                self.globals.update(node.params)
            elif isinstance(node, ast.For):
                self.globals.add(node.var)
            elif isinstance(node, ast.ForIn):
                self.globals.update(node.vars)

    def _constructed_type(self, value: ast.Node) -> str | None:
        """The UDT name a declaration's right-hand side yields, or ``None``.

        Catches ``T.new(...)``, ``T.copy(...)`` and a bare ``na`` behind a
        ``T x = na`` annotation the parser dropped — enough to check most field
        and method access without a full inference pass.
        """
        if isinstance(value, ast.Call):
            dotted = ast.dotted_name(value.func) or ""
            root, _, tail = dotted.partition(".")
            if root in self.types and tail in ("new", "copy"):
                return root
        return None

    def _known(self, name: str) -> bool:
        return (
            name in self.globals
            or name in self.types
            or name in self.enums
            or name in self.methods
            or name in BUILTIN_SERIES
            or name in BUILTIN_VALUES
            or name in BARE_FUNCTIONS
            or name in VISUAL_FUNCTIONS
            or name in NAMESPACE_FUNCTIONS
            or name in NAMESPACE_VALUES
            or name in REJECTED_NAMESPACES
            or name in DECORATIVE_NAMESPACES
            or name in DRAWING_NAMESPACES
        )

    def _suggest(self, name: str) -> str:
        pool = (
            set(self.globals)
            | BUILTIN_SERIES
            | BUILTIN_VALUES
            | BARE_FUNCTIONS
            | VISUAL_FUNCTIONS
            | set(NAMESPACE_FUNCTIONS)
        )
        close = difflib.get_close_matches(name, pool, n=1, cutoff=0.8)
        return f" — did you mean {close[0]!r}?" if close else ""

    # --- user-defined types, enums, methods -------------------------------

    def _known_type(self, name: str) -> bool:
        return name in FUNDAMENTAL_TYPES or name in DRAWING_TYPES or name in self.types

    def _check_type_defs(self) -> None:
        seen: set[str] = set()
        for type_def in self.program.types:
            if type_def.name in FUNDAMENTAL_TYPES:
                self._error(
                    f"a type cannot be named {type_def.name!r} — that is a built-in type",
                    code="type_name_reserved",
                    span=type_def.span,
                )
            if type_def.name in seen:
                self._error(
                    f"type {type_def.name!r} is declared more than once",
                    code="duplicate_type",
                    span=type_def.span,
                )
            seen.add(type_def.name)
            fields: set[str] = set()
            for field_node in type_def.fields:
                if field_node.name in fields:
                    self._error(
                        f"field {field_node.name!r} is declared more than once in "
                        f"{type_def.name!r}",
                        code="duplicate_field",
                        span=field_node.span,
                    )
                fields.add(field_node.name)
                if not self._known_type(field_node.type_name):
                    self._error(
                        f"field {field_node.name!r} has unknown type "
                        f"{field_node.type_name!r} — use a built-in type or a type "
                        f"declared above",
                        code="unknown_field_type",
                        span=field_node.span,
                    )
                if field_node.qualifier == "varip":
                    self._warn(
                        "a varip field is treated as var — this platform evaluates on "
                        "bar close only (Q23), so there is no intrabar update for it to "
                        "survive",
                        code="varip_as_var",
                        span=field_node.span,
                    )

    def _check_enum_defs(self) -> None:
        seen: set[str] = set()
        for enum_def in self.program.enums:
            if enum_def.name in FUNDAMENTAL_TYPES:
                self._error(
                    f"an enum cannot be named {enum_def.name!r} — that is a built-in type",
                    code="type_name_reserved",
                    span=enum_def.span,
                )
            if enum_def.name in seen or enum_def.name in self.types:
                self._error(
                    f"{enum_def.name!r} is declared more than once",
                    code="duplicate_type",
                    span=enum_def.span,
                )
            seen.add(enum_def.name)
            members: set[str] = set()
            for member in enum_def.members:
                if member.name in members:
                    self._error(
                        f"enum member {member.name!r} is declared more than once in "
                        f"{enum_def.name!r}",
                        code="duplicate_field",
                        span=member.span,
                    )
                members.add(member.name)

    def _check_method_defs(self) -> None:
        seen: set[tuple[str, str]] = set()
        for method in self.program.methods:
            known = (
                self._known_type(method.receiver_type)
                or method.receiver_type in self.enums
            )
            if not known:
                self._error(
                    f"method {method.name!r} is declared on unknown type "
                    f"{method.receiver_type!r}",
                    code="unknown_receiver_type",
                    span=method.span,
                )
            key = (method.name, method.receiver_type)
            if key in seen:
                self._error(
                    f"method {method.name!r} is declared twice for {method.receiver_type!r} "
                    f"— overloads must differ by receiver type",
                    code="duplicate_method",
                    span=method.span,
                )
            seen.add(key)

    # --- the walk -----------------------------------------------------------

    def _walk(self, node: ast.Node, *, ancestors: tuple[ast.Node, ...]) -> None:
        self._visit(node, ancestors)
        child_ancestors = (*ancestors, node)
        for child in ast.children(node):
            self._walk(child, ancestors=child_ancestors)

    def _visit(self, node: ast.Node, ancestors: tuple[ast.Node, ...]) -> None:
        if isinstance(node, ast.Assign) and node.qualifier == "varip":
            self._warn(
                "varip is treated as var — its whole purpose is surviving an intrabar "
                "recalculation, and this platform evaluates on bar close only (Q23)",
                code="varip_as_var",
                span=node.span,
            )
        if isinstance(node, ast.While):
            self._check_while(node)
        if isinstance(node, ast.Index):
            self._check_history(node)
        if isinstance(node, ast.Member):
            self._check_member(node, ancestors)
        if isinstance(node, ast.Name):
            self._check_name(node, ancestors)
        if isinstance(node, ast.Call):
            self._check_call(node, ancestors)

    def _check_history(self, node: ast.Index) -> None:
        """``expr[n]`` — which expressions actually keep a past.

        A variable and a built-in series do, and so does a ``ta.*`` call site
        (``runtime.RunContext.outputs``). Everything else — a member, an
        arithmetic expression, a user function's result — has no per-bar record
        behind it, and answering ``na`` would be a signal that quietly never
        fires. Rejected by name instead, which is Q24's whole rule.
        """
        if isinstance(node.obj, ast.Name):
            return
        if isinstance(node.obj, ast.Call):
            dotted = ast.dotted_name(node.obj.func) or ""
            if dotted.startswith("ta."):
                return
        if _literal(node.offset) == 0:
            return
        self._error(
            "history is only kept for a variable, a built-in series or a ta.* call — "
            "assign this to a variable first, then read that variable's [n]",
            code="unsupported_history",
            span=node.span,
        )

    def _check_member(self, node: ast.Member, ancestors: tuple[ast.Node, ...]) -> None:
        dotted = ast.dotted_name(node)
        if dotted is None:
            return
        root = dotted.split(".", 1)[0]

        for prefix, row in REJECTED_NAMESPACES.items():
            if dotted == prefix or dotted.startswith(prefix + "."):
                self._error(row.message, code=row.code, span=node.span)
                return
        if dotted in REJECTED_NAMES:
            row = REJECTED_NAMES[dotted]
            self._error(row.message, code=row.code, span=node.span)
            return

        if _is_declaration_constant(dotted):
            if not _inside_strategy_declaration(ancestors):
                self._error(
                    f"{dotted} is a strategy() property constant — it has no meaning "
                    f"outside the declaration's argument list",
                    code="declaration_constant_outside",
                    span=node.span,
                )
            return

        if dotted in DRAWING_READBACKS:
            self._error(
                f"{dotted} reads a value back out of a drawing, and this platform draws "
                f"none — it would return na into logic that places orders. Keep the "
                f"coordinate in a variable of your own and read that",
                code="drawing_readback",
                span=node.span,
            )
            return

        if root in DECORATIVE_NAMESPACES or root in DRAWING_NAMESPACES:
            # Inert: a colour, a style, a corner, or a handle to something this
            # platform does not draw. None of them has arithmetic that produces
            # a side, a price or a percent — see the subset module docstring.
            return

        if root in NAMESPACE_FUNCTIONS or root in NAMESPACE_VALUES:
            attr = dotted.split(".", 1)[1] if "." in dotted else ""
            allowed = NAMESPACE_FUNCTIONS.get(root, frozenset()) | NAMESPACE_VALUES.get(
                root, frozenset()
            )
            if attr not in allowed:
                close = difflib.get_close_matches(attr, allowed, n=1, cutoff=0.75)
                hint = f" — did you mean {root}.{close[0]!r}?" if close else ""
                self._error(
                    f"{dotted} is not in the v1 subset{hint}",
                    code="unsupported_member",
                    span=node.span,
                )
            return

        # Not a built-in namespace: the root is an enum, a type, an object
        # variable — or a typo. ``attr`` is the segment immediately after it.
        attr = dotted.split(".")[1] if "." in dotted else ""

        if root in self.enums:
            names = {m.name for m in self.enums[root].members}
            if attr and attr not in names:
                close = difflib.get_close_matches(attr, names, n=1, cutoff=0.6)
                hint = f" — did you mean {root}.{close[0]!r}?" if close else ""
                self._error(
                    f"{root!r} has no member {attr!r}{hint}",
                    code="unknown_enum_member",
                    span=node.span,
                )
            return

        if root in self.types:
            if attr not in ("new", "copy"):
                self._error(
                    f"{root!r} is a type — the only calls on it are {root}.new() and "
                    f"{root}.copy()",
                    code="unknown_type_member",
                    span=node.span,
                )
            return

        if not isinstance(node.obj, ast.Name):
            return  # a nested access like ``a.b.c`` — the inner ``a.b`` is checked on its own
        if not (
            root in self.globals or root in BUILTIN_SERIES or root in BUILTIN_VALUES
        ):
            self._error(
                f"{root!r} is not defined{self._suggest(root)}",
                code="undefined_name",
                span=node.obj.span,
                cls=PineNameError,
            )
            return

        udt = self.var_types.get(root)
        if udt is None or not attr:
            return
        is_method_call = (
            bool(ancestors)
            and isinstance(ancestors[-1], ast.Call)
            and ancestors[-1].func is node
        )
        type_def = self.types.get(udt)
        if is_method_call:
            if attr != "copy" and attr not in self.methods:
                self._error(
                    f"{udt!r} has no method {attr!r} — declare it with "
                    f"`method {attr}({udt} self, ...) =>`",
                    code="unknown_method",
                    span=node.span,
                )
        elif type_def is not None and attr not in {f.name for f in type_def.fields}:
            close = difflib.get_close_matches(
                attr, [f.name for f in type_def.fields], n=1, cutoff=0.6
            )
            hint = f" — did you mean {close[0]!r}?" if close else ""
            self._error(
                f"{udt!r} has no field {attr!r}{hint}",
                code="unknown_field",
                span=node.span,
            )

    def _check_name(self, node: ast.Node, ancestors: tuple[ast.Node, ...]) -> None:
        # A member's attribute is not a free name, and neither is a call's
        # target once the member check above has passed it.
        if ancestors and isinstance(ancestors[-1], ast.Member):
            return
        if self._known(node.name):
            return
        self._error(
            f"{node.name!r} is not defined{self._suggest(node.name)}",
            code="undefined_name",
            span=node.span,
            cls=PineNameError,
        )

    def _check_call(self, node: ast.Call, ancestors: tuple[ast.Node, ...]) -> None:
        dotted = ast.dotted_name(node.func)
        if dotted is None:
            return

        if dotted in ORDER_CALLS:
            self._check_order_call(node, dotted, ancestors)
        if dotted == "strategy.entry":
            for arg in node.args:
                if arg.name in SIZE_ARGS:
                    self._warn(
                        f"{arg.name} is parsed and then ignored (Q20) — the platform sizes "
                        f"every account at 99% of its own balance, so honouring a fixed "
                        f"quantity would be a different strategy on each account",
                        code="ignored_qty",
                        span=arg.span,
                    )
        if dotted in ("strategy.close", "strategy.close_all"):
            self._check_close_call(node, dotted)
        if dotted == "strategy.exit":
            self._check_exit_call(node)
        if dotted and dotted.startswith("ta."):
            self._check_hoistable(node, dotted, ancestors)
        if dotted.startswith("input.") or dotted == "input":
            self._collect_input(node, dotted, ancestors)
        root, _, tail = (dotted or "").partition(".")
        if root in self.types and tail == "new":
            self._check_new_call(node, root)

    def _check_new_call(self, node: ast.Call, type_name: str) -> None:
        field_names = [f.name for f in self.types[type_name].fields]
        positional = [arg for arg in node.args if not arg.name]
        if len(positional) > len(field_names):
            self._error(
                f"{type_name}.new() takes at most {len(field_names)} positional field "
                f"value(s), got {len(positional)}",
                code="too_many_fields",
                span=node.span,
            )
        seen: set[str] = set()
        for arg in node.args:
            if not arg.name:
                continue
            if arg.name not in field_names:
                close = difflib.get_close_matches(arg.name, field_names, n=1, cutoff=0.6)
                hint = f" — did you mean {close[0]!r}?" if close else ""
                self._error(
                    f"{type_name!r} has no field {arg.name!r}{hint}",
                    code="unknown_field",
                    span=arg.span,
                )
            if arg.name in seen:
                self._error(
                    f"field {arg.name!r} is set twice in {type_name}.new()",
                    code="duplicate_field",
                    span=arg.span,
                )
            seen.add(arg.name)

    def _check_order_call(
        self, node: ast.Call, dotted: str, ancestors: tuple[ast.Node, ...]
    ) -> None:
        if any(isinstance(a, ast.For | ast.ForIn | ast.While) for a in ancestors):
            self._error(
                f"{dotted} cannot be called inside a loop — a loop that fires N entries "
                f"per bar is the classic runaway, and under Q20 every one of them is 99% "
                f"of the account",
                code="order_in_loop",
                span=node.span,
            )
        if any(isinstance(a, ast.FuncDef | ast.MethodDef) for a in ancestors):
            self._error(
                f"{dotted} cannot be called inside a user function or method — the "
                f"validator must be able to see every order site in the bar to enforce "
                f"one entry per bar",
                code="order_in_function",
                span=node.span,
            )

    def _check_close_call(self, node: ast.Call, dotted: str) -> None:
        """A close takes a share of the position, never a number of contracts.

        ``qty_percent`` is honoured (Q33): a percentage is identical across
        accounts and only the dollar size differs, which is spec §5's rule for
        leverage and SL/TP applied to the exit. ``qty`` has no such reading —
        each account is sized against its own balance, so one contract count
        cannot mean the same thing on all of them — and ``strategy.entry(qty=)``
        is only a warning because there the platform's own sizing *is* a
        complete answer to the question the argument asked.

        A literal ``qty_percent`` outside ``0 < p <= 100`` is refused here
        rather than clamped: TradingView clamps, and a clamp would turn what is
        plainly a bug in the arithmetic into a full exit without saying so.
        """
        for arg in node.args:
            if arg.name in CLOSE_SIZE_ARGS:
                row = REJECTED_CLOSE_ARGS[arg.name]
                self._error(row.message, code=row.code, span=arg.span)
            elif arg.name == "qty_percent":
                self._check_close_percent(arg)

    def _check_close_percent(self, arg: ast.Argument) -> None:
        percent = _literal(arg.value)
        if not isinstance(percent, int | float):
            # Computed at run time — the runtime raises there instead, with the
            # same message. A validator that guessed at the value of an
            # expression would refuse working scripts.
            return
        if percent <= 0 or percent > 100:
            self._error(
                f"qty_percent is {percent:g}, which is not a percentage of a position "
                f"— it has to be above 0 and at most 100",
                code="bad_close_percent",
                span=arg.span,
            )

    def _check_exit_call(self, node: ast.Call) -> None:
        percent_given = False
        rejected_given = False
        for arg in node.args:
            if arg.name in REJECTED_EXIT_ARGS:
                row = REJECTED_EXIT_ARGS[arg.name]
                self._error(row.message, code=row.code, span=arg.span)
                rejected_given = True
                continue
            if arg.name in EXIT_PERCENT_ARGS:
                percent_given = True
        # A rejected argument has already said what to use instead; adding
        # "and you gave no percent" on top is noise pointing at the same line.
        if not percent_given and not rejected_given:
            self._error(
                "strategy.exit needs loss_pct= or profit_pct= — this platform's SL/TP is a "
                "percentage identical across accounts (§5, Q21)",
                code="exit_without_percent",
                span=node.span,
            )

    def _check_hoistable(
        self, node: ast.Call, dotted: str, ancestors: tuple[ast.Node, ...]
    ) -> None:
        """Warn when a ``ta.*`` call site cannot be advanced once per bar.

        Pine evaluates every ``ta.*`` call on every bar regardless of which
        branch ran — a strategy whose EMA only updates on days it is used is a
        different strategy. The runtime honours that by *hoisting*: every
        ``ta.*`` site whose arguments read only globals is evaluated first, in
        source order, before the statement walk.

        A site inside a loop, or inside a function the bar might not reach,
        advances only when it is reached — which is Pine's behaviour for the
        *first* call in a bar and not for a skipped one. A real difference, so
        it is reported rather than left for someone to discover from a backtest
        that will not reproduce.

        A site inside a function that **every bar calls anyway** is not that
        case, and used to be warned about anyway. A textbook T3 is six
        ``ta.ema`` calls in one helper invoked once at the top level: six
        warnings about a function that advances exactly once per bar, on the
        one screen where a real warning has to stand out. ``_unconditional``
        is the difference.
        """
        enclosing = next(
            (a for a in reversed(ancestors) if isinstance(a, ast.FuncDef | ast.MethodDef)),
            None,
        )
        in_loop = any(isinstance(a, ast.For | ast.ForIn | ast.While) for a in ancestors)
        if not in_loop and (enclosing is None or enclosing.name in self._unconditional):
            return

        self.result.unhoistable.append(node.call_id)
        where = "a loop" if in_loop else "a function the bar may not reach"
        self._warn(
            f"{dotted} here is inside {where}, so it advances only on the bars that "
            f"reach it. Move it to the top level to have it advance every bar the way "
            f"TradingView does",
            code="ta_not_hoisted",
            span=node.span,
        )

    def _collect_input(
        self, node: ast.Call, dotted: str, ancestors: tuple[ast.Node, ...]
    ) -> None:
        assignment = next((a for a in reversed(ancestors) if isinstance(a, ast.Assign)), None)
        if assignment is None or len(assignment.targets) != 1:
            self._error(
                "every input.* must be assigned to a single name — that name is what the "
                "bot's parameter form shows",
                code="input_not_assigned",
                span=node.span,
            )
            return
        kind = dotted.split(".", 1)[1] if "." in dotted else "float"
        given = node.args[0].value if node.args and not node.args[0].name else None
        if given is None:
            given = node.keyword("defval")
        default = _input_default(kind, given)
        if default is None:
            self._error(
                "this input has no default — a bot cannot start without one",
                code="input_without_default",
                span=node.span,
            )
            return
        title = self._const(node.keyword("title"))
        if title is None and len(node.args) > 1 and not node.args[1].name:
            title = self._const(node.args[1].value)
        self.result.inputs.append(
            InputSpec(
                name=assignment.targets[0],
                kind=kind,
                default=default,
                title=str(title) if title is not None else assignment.targets[0],
                minval=_literal(node.keyword("minval")),
                maxval=_literal(node.keyword("maxval")),
                options=tuple(
                    _literal(item)
                    for item in getattr(node.keyword("options"), "items", ())
                ),
                step=_literal(node.keyword("step")),
                group=str(self._const(node.keyword("group")) or ""),
                inline=str(self._const(node.keyword("inline")) or ""),
                tooltip=str(self._const(node.keyword("tooltip")) or ""),
            )
        )

    # --- loops and recursion ------------------------------------------------

    def _const(self, node) -> object:
        """A literal, or the literal a top-level constant name stands for."""
        literal = _literal(node)
        if literal is not None:
            return literal
        if isinstance(node, ast.Name):
            return self.const_strings.get(node.name)
        return None

    def _check_while(self, node: ast.While) -> None:
        """Reject a ``while`` nothing in its own body can end.

        Bounded loops still get ``max_loop_iterations`` enforced at runtime —
        "bounded" is a static judgement and the runtime is where it is actually
        true or not — but a loop that provably cannot terminate should never
        reach a bar at all.
        """
        if isinstance(node.cond, ast.BoolLit) and node.cond.value:
            has_break = any(isinstance(n, ast.Break) for n in ast.walk(node.body))
            if not has_break:
                self._error(
                    "this while loop cannot end — `while true` with no break",
                    code="unbounded_loop",
                    span=node.span,
                )
            return
        touched = {n.target for n in ast.walk(node.body) if isinstance(n, ast.Reassign)}
        read = {n.name for n in ast.walk(node.cond) if isinstance(n, ast.Name)}
        has_break = any(isinstance(n, ast.Break) for n in ast.walk(node.body))
        if not has_break and not (touched & read):
            self._error(
                "this while loop's condition is never changed inside it and it has no "
                "break, so nothing can end it",
                code="unbounded_loop",
                span=node.span,
            )

    def _check_recursion(self) -> None:
        """Reject a cycle in the call graph. Pine has no recursion and neither
        does this runtime — an unbounded stack inside a bar's budget is a hang.

        Methods share the graph with functions: a method calling itself, or two
        methods calling each other, is the same hang. A call is matched by its
        bare name, so an overload set is treated as one node — conservative, and
        the message names the cycle either way.
        """
        bodies: dict[str, list[ast.Block]] = {}
        spans: dict[str, ast.Span] = {}
        for fn in self.program.functions:
            bodies.setdefault(fn.name, []).append(fn.body)
            spans.setdefault(fn.name, fn.span)
        for method in self.program.methods:
            bodies.setdefault(method.name, []).append(method.body)
            spans.setdefault(method.name, method.span)

        graph: dict[str, set[str]] = {}
        for name, blocks in bodies.items():
            called: set[str] = set()
            for block in blocks:
                for n in ast.walk(block):
                    if not isinstance(n, ast.Call):
                        continue
                    dotted = ast.dotted_name(n.func)
                    if dotted in bodies:
                        called.add(dotted)
                    elif isinstance(n.func, ast.Member) and n.func.attr in bodies:
                        called.add(n.func.attr)
            graph[name] = called

        state: dict[str, int] = {}

        def visit(name: str, path: tuple[str, ...]) -> None:
            if state.get(name) == 1:
                cycle = " → ".join((*path, name))
                self._error(
                    f"recursion is not supported: {cycle}",
                    code="recursion",
                    span=spans[name],
                )
                return
            if state.get(name) == 2:
                return
            state[name] = 1
            for callee in graph.get(name, ()):
                visit(callee, (*path, name))
            state[name] = 2

        for name in graph:
            visit(name, ())

    def _check_exit_reachability(self) -> None:
        """Warn when one bar can reach two ``strategy.exit`` calls.

        The platform holds **one** SL/TP pair per trade, identical across
        accounts (§5) — so two exits with different percentages in one bar is not
        expressible. Last call in the bar wins, decided here rather than in
        Phase 5 where it would look like a bug (``bot-plan.md`` §1.8).
        """
        exits = [
            node
            for node in ast.walk(self.program)
            if isinstance(node, ast.Call) and ast.dotted_name(node.func) == "strategy.exit"
        ]
        if len(exits) > 1:
            self._warn(
                f"this script has {len(exits)} strategy.exit calls. The platform holds one "
                f"SL/TP pair per trade, identical across accounts (§5), so if a bar reaches "
                f"more than one the last call wins",
                code="multiple_exits",
                span=exits[1].span,
            )


# --- helpers ----------------------------------------------------------------


#: A property that cannot work here is reported under a different code from one
#: that works but only in the backtest — the panel colours them differently and
#: the first is the one an author has to act on.
_PROPERTY_CODES = {True: "inert_strategy_property", False: "backtest_only_strategy_property"}


def _is_declaration_constant(dotted: str) -> bool:
    """``strategy.percent_of_equity``, or the ``strategy.commission`` under one.

    The walker visits the inner member of a three-segment constant too, so a
    prefix counts: rejecting ``strategy.commission`` on its way to
    ``strategy.commission.percent`` would report one mistake as two.
    """
    return dotted in DECLARATION_CONSTANTS or any(
        constant.startswith(dotted + ".") for constant in DECLARATION_CONSTANTS
    )


def _inside_strategy_declaration(ancestors: tuple[ast.Node, ...]) -> bool:
    return any(
        isinstance(node, ast.Call) and ast.dotted_name(node.func) == "strategy"
        for node in ancestors
    )


def _inside_visual_call(ancestors: tuple[ast.Node, ...]) -> bool:
    """True when this node sits in the argument list of a recorded-only call.

    ``plot`` and friends are annotations: nothing they are handed can reach an
    order. Used by the ``ta.*`` hoisting check, which does not need to warn
    about a call whose value is only ever drawn.
    """
    return any(
        isinstance(node, ast.Call) and ast.dotted_name(node.func) in VISUAL_FUNCTIONS
        for node in ancestors
    )


# --- literal helpers --------------------------------------------------------


def _literal(node) -> object:
    """The Python value of a literal node, or ``None`` when it is an expression.

    Used only for inputs and ``strategy()`` arguments, both of which must be
    constant — a default that depends on a series is not a default.
    """
    if isinstance(node, ast.NumberLit):
        text = node.value
        return int(text) if text.isdigit() else float(text)
    if isinstance(node, ast.StringLit):
        return node.value
    if isinstance(node, ast.BoolLit):
        return node.value
    if isinstance(node, ast.Unary) and node.op == "-":
        inner = _literal(node.operand)
        return -inner if isinstance(inner, int | float) else None
    return None


#: An ``input.*`` whose default is not a plain literal. ``input.source(close)``
#: takes a *series*, ``input.color(#00E5A8)`` a colour and ``input.time(
#: timestamp(...))`` a call — all three are perfectly good defaults, and reading
#: only literals reported every one of them as "this input has no default".
def _input_default(kind: str, node) -> object:
    """The recorded default for an input, or ``None`` when there really is none.

    The value stored here is what the parameter form shows and what the runtime
    falls back to, so a shape it cannot render is stored by its source spelling
    rather than dropped — ``"close"``, ``"#00E5A8"`` — which is exactly what the
    form needs to show and what ``_coerce_input`` maps back.
    """
    if node is None:
        return None
    literal = _literal(node)
    if literal is not None:
        return literal
    if isinstance(node, ast.ColorLit):
        return node.value
    if kind == "source" and isinstance(node, ast.Name) and node.name in BUILTIN_SERIES:
        return node.name
    dotted = ast.dotted_name(node) if isinstance(node, ast.Member | ast.Name) else None
    if dotted and dotted.split(".", 1)[0] in DECORATIVE_NAMESPACES:
        return dotted
    if isinstance(node, ast.Call):
        called = ast.dotted_name(node.func) or ""
        if called == "timestamp":
            # Folded to the number it is, so the "Backtest Start" field the
            # panel draws holds a date rather than the word "timestamp".
            return _fold_timestamp(node)
        if called.split(".", 1)[0] in DECORATIVE_NAMESPACES:
            return called
    return None


def _fold_timestamp(node: ast.Call) -> object:
    """``timestamp(...)`` evaluated at validation, or ``None`` when it cannot be.

    Runs the *runtime's own* implementation rather than a second copy of the
    date arithmetic, so the number the form shows and the number the first bar
    computes cannot disagree.
    """
    from apps.pine import builtins as bi

    args = [_literal(arg.value) for arg in node.args]
    if any(value is None for value in args):
        return None
    try:
        return bi.builtin_timestamp(None, *args)
    except Exception:  # noqa: BLE001 - a bad date is "no default", not a crash here
        return None


def _literal_is_zero(node) -> bool:
    return _literal(node) in (0, 0.0)


def _literal_is_false(node) -> bool:
    return _literal(node) is False
