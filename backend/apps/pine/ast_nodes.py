"""The AST. Every node is frozen, carries a span, and has a stable ``call_id``.

**``call_id`` is the load-bearing decision of the whole design.** Phase 2 keys
every stateful ``ta.*`` object on it, so ``ta.ema(close, 20)`` on line 12 and the
same text on line 30 are two different EMAs — which they are. Phase 4 links a
chart marker back through it to the line that drew the marker.

It is derived from the source span, which gives it the two properties that
matter: it survives a re-parse of unchanged source, so restarting a bot does not
reset its indicators; and it *changes* when the line moves, so editing a running
strategy is correctly treated as a different strategy rather than silently
inheriting the old one's converged state.

Frozen throughout, per ``bot-plan.md`` §1.6: an AST node is a value. The things
that accumulate — ``Series``, the indicator state, the run context — are not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.pine.tokens import Span


@dataclass(frozen=True, slots=True)
class Node:
    span: Span

    @property
    def call_id(self) -> str:
        """Stable identity: where it is, plus what it is."""
        return f"{type(self).__name__}@{self.span.key()}"


# --- expressions ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NumberLit(Node):
    value: str  # kept as text; the runtime makes it a Decimal, never a float


@dataclass(frozen=True, slots=True)
class StringLit(Node):
    value: str


@dataclass(frozen=True, slots=True)
class BoolLit(Node):
    value: bool


@dataclass(frozen=True, slots=True)
class ColorLit(Node):
    value: str


@dataclass(frozen=True, slots=True)
class Name(Node):
    name: str


@dataclass(frozen=True, slots=True)
class Member(Node):
    """``ta.ema``, ``strategy.position_size``. The dotted chain, unflattened."""

    obj: Node
    attr: str


@dataclass(frozen=True, slots=True)
class Index(Node):
    """History access: ``close[1]``. Distinct from a tuple literal by position."""

    obj: Node
    offset: Node


@dataclass(frozen=True, slots=True)
class Unary(Node):
    op: str
    operand: Node


@dataclass(frozen=True, slots=True)
class Binary(Node):
    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Ternary(Node):
    cond: Node
    then: Node
    otherwise: Node


@dataclass(frozen=True, slots=True)
class Argument(Node):
    """One call argument. ``name`` is set for ``length=20``, empty for positional."""

    name: str
    value: Node


@dataclass(frozen=True, slots=True)
class Call(Node):
    func: Node
    args: tuple[Argument, ...]

    def positional(self) -> tuple[Node, ...]:
        return tuple(a.value for a in self.args if not a.name)

    def keyword(self, name: str) -> Node | None:
        for arg in self.args:
            if arg.name == name:
                return arg.value
        return None


@dataclass(frozen=True, slots=True)
class TupleExpr(Node):
    """``[a, b]`` in target position. Only ever a declaration target in v1."""

    items: tuple[Node, ...]


# --- statements -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Block(Node):
    """A statement list. Its value is the value of its last statement."""

    body: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Assign(Node):
    """``x = expr`` and ``x := expr`` are **different nodes**, on purpose.

    Conflating them is a real bug source rather than a tidiness point: inside an
    ``if`` body, ``x = 1`` declares a *new local* that vanishes at the end of the
    block, while ``x := 1`` mutates the outer variable. A strategy that flips a
    flag with the wrong one silently never flips it.
    """

    targets: tuple[str, ...]
    value: Node
    #: "", "var" or "varip"
    qualifier: str = ""


@dataclass(frozen=True, slots=True)
class Reassign(Node):
    target: str
    value: Node


@dataclass(frozen=True, slots=True)
class If(Node):
    """Statement *and* expression — Pine allows ``x = if c \\n 1 \\n else \\n 2``."""

    cond: Node
    then: Block
    otherwise: Node | None  # Block, or another If for `else if`


@dataclass(frozen=True, slots=True)
class SwitchCase(Node):
    match: Node | None  # None is the `=>` default arm
    body: Node


@dataclass(frozen=True, slots=True)
class Switch(Node):
    subject: Node | None  # `switch` with no subject is a cond-chain
    cases: tuple[SwitchCase, ...]


@dataclass(frozen=True, slots=True)
class For(Node):
    var: str
    start: Node
    end: Node
    step: Node | None
    body: Block


@dataclass(frozen=True, slots=True)
class ForIn(Node):
    vars: tuple[str, ...]
    iterable: Node
    body: Block


@dataclass(frozen=True, slots=True)
class While(Node):
    cond: Node
    body: Block


@dataclass(frozen=True, slots=True)
class Break(Node):
    pass


@dataclass(frozen=True, slots=True)
class Continue(Node):
    pass


@dataclass(frozen=True, slots=True)
class FuncDef(Node):
    name: str
    params: tuple[str, ...]
    body: Block


@dataclass(frozen=True, slots=True)
class ExprStmt(Node):
    value: Node


@dataclass(frozen=True, slots=True)
class Program(Node):
    body: tuple[Node, ...]
    #: The ``//@version=N`` annotation as the lexer read it, for the validator.
    version: int | None = None
    functions: tuple[FuncDef, ...] = field(default_factory=tuple)


# --- walking ----------------------------------------------------------------

_CHILD_FIELDS: dict[type, tuple[str, ...]] = {
    Member: ("obj",),
    Index: ("obj", "offset"),
    Unary: ("operand",),
    Binary: ("left", "right"),
    Ternary: ("cond", "then", "otherwise"),
    Argument: ("value",),
    Call: ("func", "args"),
    TupleExpr: ("items",),
    Block: ("body",),
    Assign: ("value",),
    Reassign: ("value",),
    If: ("cond", "then", "otherwise"),
    SwitchCase: ("match", "body"),
    Switch: ("subject", "cases"),
    For: ("start", "end", "step", "body"),
    ForIn: ("iterable", "body"),
    While: ("cond", "body"),
    FuncDef: ("body",),
    ExprStmt: ("value",),
    Program: ("body",),
}


def children(node: Node):
    """Direct child nodes, in source order. One table, so a new node type that
    forgets to register here is invisible to *every* walk rather than to one."""
    for name in _CHILD_FIELDS.get(type(node), ()):
        value = getattr(node, name)
        if value is None:
            continue
        if isinstance(value, tuple):
            yield from (item for item in value if isinstance(item, Node))
        elif isinstance(value, Node):
            yield value


def walk(node: Node):
    """Depth-first pre-order over the whole tree, ``node`` included."""
    yield node
    for child in children(node):
        yield from walk(child)


def dotted_name(node: Node) -> str | None:
    """``ta.ema`` for a ``Member`` chain of plain names, else ``None``.

    Returns ``None`` for anything that is not a simple dotted path — the
    validator uses that to tell a namespace reference from an expression it
    cannot reason about statically.
    """
    parts: list[str] = []
    current = node
    while isinstance(current, Member):
        parts.append(current.attr)
        current = current.obj
    if not isinstance(current, Name):
        return None
    parts.append(current.name)
    return ".".join(reversed(parts))
