"""AST node types for the Pine v5 subset.

Plain dataclasses produced by `parser.PineTransformer`. The rest of the
pipeline (semantic analysis, interpreter) depends only on these — never on
Lark's tree types. Each node carries optional source position for diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Node:
    line: Optional[int] = field(default=None, kw_only=True)
    column: Optional[int] = field(default=None, kw_only=True)


# --- Top level ---
@dataclass
class ProgramNode(Node):
    header: Optional["StrategyHeaderNode"]
    body: list  # list[Node]
    functions: list = field(default_factory=list)  # list[FunctionDefNode]


@dataclass
class FunctionDefNode(Node):
    """User-defined function: `name(params) => body`."""

    name: str
    params: list[str]
    body: list  # expr wrapped as one-element list, or suite statements


@dataclass
class TupleAssignNode(Node):
    """`[a, b, c] = expr` — multi-return destructuring."""

    names: list[str]
    value: "Node"


@dataclass
class StrategyHeaderNode(Node):
    args: list  # list[ArgNode]


# --- Statements ---
@dataclass
class StateDeclarationNode(Node):
    """`var x = expr` / `varip x = expr`."""

    kind: str  # "var" | "varip"
    name: str
    value: "Node"


@dataclass
class AssignNode(Node):
    """`x = expr` (declaration) or `x := expr` (reassignment)."""

    name: str
    value: "Node"
    reassign: bool  # True for :=


@dataclass
class IfNode(Node):
    condition: "Node"
    then_body: list
    elif_clauses: list  # list[(condition, body)]
    else_body: Optional[list]


@dataclass
class ForNode(Node):
    var: str
    start: "Node"
    end: "Node"
    body: list


@dataclass
class OrderExecutionNode(Node):
    """strategy.entry / strategy.close / strategy.exit."""

    action: str  # "entry" | "close" | "exit"
    args: list  # list[ArgNode]


@dataclass
class ExprStatementNode(Node):
    expr: "Node"


# --- Expressions ---
@dataclass
class BinaryOpNode(Node):
    op: str
    left: "Node"
    right: "Node"


@dataclass
class UnaryOpNode(Node):
    op: str
    operand: "Node"


@dataclass
class TernaryNode(Node):
    condition: "Node"
    if_true: "Node"
    if_false: "Node"


@dataclass
class HistoryAccessNode(Node):
    """`expr[n]` — value n bars ago."""

    series: "Node"
    offset: "Node"


@dataclass
class BuiltinFunctionNode(Node):
    """Namespaced call: ta.sma(...), math.max(...), or bare nz(...)."""

    namespace: Optional[str]  # "ta" | "math" | "syminfo" | None
    name: str
    args: list  # list[ArgNode]


@dataclass
class ArgNode(Node):
    """Positional (name=None) or keyword call argument."""

    value: "Node"
    name: Optional[str] = None


@dataclass
class IdentifierNode(Node):
    name: str


@dataclass
class LiteralNode(Node):
    value: object  # float | int | str | bool | None(=na)
    type: str  # "float" | "int" | "string" | "bool" | "na"


@dataclass
class ArrayLiteralNode(Node):
    """`[a, b, c]` — TradingView option lists (compile-time only)."""

    elements: list  # list[Node]
