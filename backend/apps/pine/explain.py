"""What a strategy actually does, said back in the script's own words.

The bot page has to be able to answer "why would this thing trade?" without the
reader parsing Pine in their head. That question has exactly one honest source:
the script. So this walks the AST the validator already built and reports three
things, each one anchored to the line it came from —

  **Indicators.** Every ``ta.*`` call bound to a name, plus every ``plot``/
  ``hline``/``plotshape`` title. These are the series the chart draws; the
  runtime emits their values per bar as ``intent.plots``, so the name here and
  the key there are deliberately the same string.

  **Triggers.** Every ``strategy.entry`` / ``close`` / ``exit`` / ``order``
  call, with the chain of ``if`` conditions guarding it rendered as the source
  text that produced them. "if RSI goes above 50 we take a long" is not
  paraphrased into English here — the reader is shown ``ta.crossover(rsi, 50)``
  on line 14, which is the thing that will actually be evaluated.

  **Inputs.** Named, so a condition mentioning ``rsiLen`` can be read.

Nothing is guessed. A condition this cannot render — a call inside a
user-defined function, a ``switch`` arm — comes back with ``conditions`` empty
and ``inside_function`` set, rather than with a plausible sentence nobody can
check against the source.

Pure like the rest of ``apps/pine``: text in, data out, no clock and no database.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.pine import ast_nodes as ast
from apps.pine.errors import PineError
from apps.pine.parser import parse
from apps.pine.tokens import Span

#: The ``strategy.*`` calls that move a position. ``strategy.cancel`` and the
#: performance readers are deliberately absent — they are not triggers.
TRIGGER_CALLS = {
    "strategy.entry": "entry",
    "strategy.order": "order",
    "strategy.close": "close",
    "strategy.close_all": "close",
    "strategy.exit": "exit",
}

#: Drawing calls whose first string argument names a series the chart can show.
PLOT_CALLS = {"plot", "plotshape", "plotchar", "plotarrow", "hline", "bgcolor"}


@dataclass(frozen=True, slots=True)
class Indicator:
    """One named series the script computes, and where it came from."""

    #: The key the runtime emits it under, when it emits one at all.
    name: str
    #: ``ta.rsi``, ``ta.ema`` … or "" for a plot of a plain expression.
    func: str
    #: The call's arguments as written, e.g. ``close, 14``.
    args: str
    line: int
    #: True when a ``plot()`` draws it — those are the ones worth a chart line.
    plotted: bool = False
    #: A ``plot(..., title=)`` for this series. The chart legend prefers it; the
    #: ``name`` stays the runtime's key, because that is what the values arrive
    #: under and a legend that renamed them would break the join.
    label: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "func": self.func,
            "args": self.args,
            "line": self.line,
            "plotted": self.plotted,
            "label": self.label or self.name,
        }


@dataclass(frozen=True, slots=True)
class Trigger:
    """One place the script asks for a position change, and what guards it."""

    #: "entry" | "order" | "close" | "exit"
    kind: str
    #: "long" | "short" | None — from the call's own direction argument only.
    side: str | None
    #: The order id argument when it is a string literal, else "".
    order_id: str
    line: int
    #: The call as written, e.g. ``strategy.entry("L", strategy.long)``.
    call_text: str
    #: The enclosing ``if`` conditions, outermost first, as source text.
    conditions: tuple[str, ...] = ()
    #: The same conditions with any single-use boolean alias replaced by what it
    #: was assigned. ``longCond`` tells a reader nothing; ``ta.crossover(fast,
    #: slow) and rsi > 50`` is the actual test. Both are kept — the short form is
    #: what the source says on that line, and this is what it means.
    expanded: tuple[str, ...] = ()
    #: True when the call sits inside a user-defined function, where the guard
    #: is wherever the function is called from and this cannot know it.
    inside_function: bool = False

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "side": self.side,
            "order_id": self.order_id,
            "line": self.line,
            "call_text": self.call_text,
            "conditions": list(self.conditions),
            "expanded": list(self.expanded or self.conditions),
            "inside_function": self.inside_function,
        }


@dataclass(frozen=True, slots=True)
class Explanation:
    indicators: tuple[Indicator, ...] = ()
    triggers: tuple[Trigger, ...] = ()
    inputs: tuple[str, ...] = ()
    #: Set when the source would not parse. Everything else is then empty —
    #: a partial explanation of a script that does not compile is a lie.
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "indicators": [row.as_dict() for row in self.indicators],
            "triggers": [row.as_dict() for row in self.triggers],
            "inputs": list(self.inputs),
            "error": self.error,
        }


def explain(source: str) -> Explanation:
    """Read ``source`` and report what it computes and what makes it trade."""
    try:
        program = parse(source)
    except PineError as exc:
        return Explanation(error=str(exc))
    except RecursionError:  # pragma: no cover - a pathological nesting depth
        return Explanation(error="this script nests too deeply to explain")

    lines = source.splitlines()
    walker = _Walker(lines)
    walker.walk_program(program)
    return Explanation(
        indicators=tuple(walker.indicators),
        triggers=tuple(walker.triggers),
        inputs=tuple(dict.fromkeys(walker.inputs)),
    )


def slice_span(lines: list[str], span: Span) -> str:
    """The source text a span covers, flattened to one line.

    Pine wraps freely, so a condition can be three physical lines; the panel
    shows it inline, and joining on a single space is what makes that readable
    without inventing punctuation the author did not write.
    """
    if span.line < 1 or span.line > len(lines):
        return ""
    if span.line == span.end_line:
        return lines[span.line - 1][span.col - 1 : span.end_col - 1].strip()
    parts = [lines[span.line - 1][span.col - 1 :]]
    parts.extend(lines[index] for index in range(span.line, span.end_line - 1))
    if span.end_line <= len(lines):
        parts.append(lines[span.end_line - 1][: span.end_col - 1])
    return " ".join(part.strip() for part in parts if part.strip())


def dotted(node: ast.Node) -> str:
    """``ta.ema`` from the Member chain, "" for anything that is not one."""
    if isinstance(node, ast.Name):
        return node.name
    if isinstance(node, ast.Member):
        root = dotted(node.obj)
        return f"{root}.{node.attr}" if root else ""
    return ""


class _Walker:
    """One pass. Conditions are carried down as a stack, which is the whole trick."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.indicators: list[Indicator] = []
        self.triggers: list[Trigger] = []
        self.inputs: list[str] = []
        self._plotted: set[str] = set()
        self._titles: dict[str, str] = {}
        self._conditions: list[str] = []
        self._in_function = False
        #: Name → the expression it was assigned, as source text. Only names
        #: assigned once at the top level, so an expansion cannot be wrong about
        #: which assignment was in force.
        self._aliases: dict[str, str] = {}
        self._reassigned: set[str] = set()

    # --- entry points -------------------------------------------------------

    def walk_program(self, program: ast.Program) -> None:
        for statement in program.body:
            self.walk(statement)
        # Function bodies last, so a trigger inside one is reported after the
        # top-level ones a reader looks for first.
        self._in_function = True
        for func in program.functions:
            self.walk(func.body)
        for method in getattr(program, "methods", ()) or ():
            self.walk(method.body)
        self._in_function = False
        # `plot(rsi)` is what promotes a computed series to a chart line, and it
        # can appear after the assignment, so the flag is applied at the end.
        self.indicators[:] = [
            Indicator(
                name=row.name,
                func=row.func,
                args=row.args,
                line=row.line,
                plotted=row.plotted or row.name in self._plotted,
                label=row.label or self._titles.get(row.name, ""),
            )
            for row in self.indicators
        ]
        # Conditions are expanded once the whole file has been read, so a
        # trigger on line 11 can be explained by an alias assigned on line 9.
        self.triggers[:] = [
            Trigger(
                kind=row.kind,
                side=row.side,
                order_id=row.order_id,
                line=row.line,
                call_text=row.call_text,
                conditions=row.conditions,
                expanded=tuple(self.expand(text) for text in row.conditions),
                inside_function=row.inside_function,
            )
            for row in self.triggers
        ]

    def expand(self, text: str) -> str:
        """Replace a bare alias with what it was assigned. One level, no more.

        One level because the point is readability, not inlining the program: a
        chain expanded three deep is longer than the source and no clearer. A
        name assigned more than once is never expanded at all — which of the two
        was in force is a runtime question this cannot answer.
        """
        stripped = text.strip()
        negated = stripped.startswith("not (") and stripped.endswith(")")
        inner = stripped[5:-1].strip() if negated else stripped
        definition = self._aliases.get(inner)
        if definition is None or inner in self._reassigned:
            return text
        return f"not ({definition})" if negated else definition

    def walk(self, node: object) -> None:
        if node is None:
            return
        if isinstance(node, ast.Block):
            for statement in node.body:
                self.walk(statement)
            return
        if isinstance(node, ast.If):
            self.walk_expr(node.cond)
            self._conditions.append(slice_span(self.lines, node.cond.span))
            self.walk(node.then)
            self._conditions.pop()
            if node.otherwise is not None:
                # An `else` branch is guarded by the negation of the same test.
                # Said as `not (...)` rather than left unstated: a close sitting
                # in an else arm with no condition listed reads as unconditional.
                self._conditions.append(f"not ({slice_span(self.lines, node.cond.span)})")
                self.walk(node.otherwise)
                self._conditions.pop()
            return
        if isinstance(node, ast.Assign):
            self.record_assign(node)
            self.walk_expr(node.value)
            return
        if isinstance(node, ast.Reassign):
            self._reassigned.add(node.target)
            self.walk_expr(node.value)
            return
        if isinstance(node, ast.ExprStmt):
            self.walk_expr(node.value)
            return
        if isinstance(node, ast.Switch):
            self.walk_expr(node.subject) if node.subject is not None else None
            for case in node.cases:
                self.walk(case.body)
            return
        if isinstance(node, ast.For | ast.ForIn | ast.While):
            self.walk(getattr(node, "body", None))
            return
        if isinstance(node, ast.FuncDef | ast.MethodDef):
            was, self._in_function = self._in_function, True
            self.walk(node.body)
            self._in_function = was
            return
        if isinstance(node, ast.Node):
            self.walk_expr(node)

    # --- expressions --------------------------------------------------------

    def walk_expr(self, node: object) -> None:
        if not isinstance(node, ast.Node):
            return
        if isinstance(node, ast.Call):
            self.record_call(node)
            for argument in node.args:
                self.walk_expr(argument.value)
            return
        if isinstance(node, ast.Binary):
            self.walk_expr(node.left)
            self.walk_expr(node.right)
            return
        if isinstance(node, ast.Unary):
            self.walk_expr(node.operand)
            return
        if isinstance(node, ast.Ternary):
            self.walk_expr(node.cond)
            self.walk_expr(node.then)
            self.walk_expr(node.otherwise)
            return
        if isinstance(node, ast.Index):
            self.walk_expr(node.obj)
            return
        if isinstance(node, ast.Member):
            self.walk_expr(node.obj)
            return
        if isinstance(node, ast.TupleExpr):
            for item in node.items:
                self.walk_expr(item)
            return
        if isinstance(node, ast.If):
            self.walk(node)

    # --- the three things this reports --------------------------------------

    def record_assign(self, node: ast.Assign) -> None:
        """``rsi = ta.rsi(close, 14)`` — the name the chart will label a line."""
        value = node.value
        if len(node.targets) == 1 and not self._in_function:
            name = node.targets[0]
            if name in self._aliases:
                self._reassigned.add(name)
            self._aliases[name] = slice_span(self.lines, value.span)
        if not isinstance(value, ast.Call):
            return
        func = dotted(value.func)
        if not func.startswith("ta."):
            return
        for target in node.targets:
            self.indicators.append(
                Indicator(
                    name=target,
                    func=func,
                    args=self.args_text(value),
                    line=node.span.line,
                )
            )

    def record_call(self, node: ast.Call) -> None:
        func = dotted(node.func)
        if func in TRIGGER_CALLS:
            self.triggers.append(self.trigger_from(node, func))
            return
        if func.startswith("input"):
            title = self.string_argument(node, "title") or self.string_argument(node, "")
            if title:
                self.inputs.append(title)
            return
        if func in PLOT_CALLS:
            self.record_plot(node, func)

    def record_plot(self, node: ast.Call, func: str) -> None:
        """A drawn series. Its title is what the runtime keys the value under."""
        positional = node.positional()
        expression = positional[0] if positional else None
        title = self.string_argument(node, "title")
        name = title or (dotted(expression) if expression is not None else "")
        if not name and expression is not None:
            name = slice_span(self.lines, expression.span)
        if not name:
            return
        # `plot(rsi, title="RSI")` is the RSI series being drawn, not a second
        # series called "RSI". Keying on the expression rather than the title is
        # what keeps the chart's legend joined to the runtime's plot values.
        series = dotted(expression) if expression is not None else ""
        known = {row.name for row in self.indicators}
        if series and series in known:
            self._plotted.add(series)
            if title:
                self._titles[series] = title
            return
        self._plotted.add(name)
        if name in known:
            return
        called = expression if isinstance(expression, ast.Call) else None
        self.indicators.append(
            Indicator(
                name=name,
                func=dotted(called.func) if called is not None else "",
                args=self.args_text(called) if called is not None else "",
                line=node.span.line,
                plotted=func == "plot",
            )
        )

    def trigger_from(self, node: ast.Call, func: str) -> Trigger:
        return Trigger(
            kind=TRIGGER_CALLS[func],
            side=self.side_of(node),
            order_id=self.string_argument(node, "id") or self.string_argument(node, ""),
            line=node.span.line,
            call_text=slice_span(self.lines, node.span),
            conditions=tuple(self._conditions),
            inside_function=self._in_function,
        )

    def side_of(self, node: ast.Call) -> str | None:
        """``strategy.long`` / ``strategy.short``, wherever the call put it."""
        candidates = [argument.value for argument in node.args]
        for candidate in candidates:
            name = dotted(candidate)
            if name == "strategy.long":
                return "long"
            if name == "strategy.short":
                return "short"
        return None

    def string_argument(self, node: ast.Call, name: str) -> str:
        """A named string argument, or the first positional one when ``name`` is ""."""
        if name:
            value = node.keyword(name)
            return value.value if isinstance(value, ast.StringLit) else ""
        for argument in node.args:
            if not argument.name and isinstance(argument.value, ast.StringLit):
                return argument.value.value
        return ""

    def args_text(self, node: ast.Call | None) -> str:
        if node is None or not node.args:
            return ""
        first, last = node.args[0], node.args[-1]
        return slice_span(self.lines, first.span.to(last.span))
