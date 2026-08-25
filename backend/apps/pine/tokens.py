"""Token kinds and source spans.

``Span`` is frozen because it is a value (``bot-plan.md`` §1.6): every AST node
carries one, and a node's span never changes once it is parsed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TokenKind(StrEnum):
    NAME = "name"
    NUMBER = "number"
    STRING = "string"
    COLOR = "color"
    KEYWORD = "keyword"
    OP = "op"
    NEWLINE = "newline"
    INDENT = "indent"
    DEDENT = "dedent"
    EOF = "eof"


#: Reserved words. ``na`` is deliberately **not** here: it is both a value and a
#: function (``na(x)``), so it stays a NAME and the runtime resolves it.
KEYWORDS = frozenset(
    {
        "if",
        "else",
        "for",
        "to",
        "by",
        "in",
        "while",
        "break",
        "continue",
        "switch",
        "var",
        "varip",
        "and",
        "or",
        "not",
        "true",
        "false",
        "import",
        "export",
        "type",
        "method",
        "enum",
    }
)

#: Longest first — the lexer matches greedily, so ``:=`` must be tried before
#: ``:`` and ``==`` before ``=``.
OPERATORS = (
    "=>",
    ":=",
    "==",
    "!=",
    "<=",
    ">=",
    # Compound assignment. Longest-first matters twice over here: these must be
    # tried before "+"/"-"/"*"/"/"/"%" *and* before "=", or `a += b` lexes as
    # `a` `+` `= b`.
    "+=",
    "-=",
    "*=",
    "/=",
    "%=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "<",
    ">",
    "=",
    "?",
    ":",
    "(",
    ")",
    "[",
    "]",
    "{",
    "}",
    ",",
    ".",
)


@dataclass(frozen=True, slots=True)
class Span:
    """A half-open character range in the source. 1-based line, 1-based column.

    1-based on both axes because that is what an editor's gutter shows and what
    a compiler error reads like; converting once here beats converting at every
    display site.
    """

    line: int
    col: int
    end_line: int
    end_col: int

    def to(self, other: Span) -> Span:
        """The span covering this one through ``other`` — used to span a subtree."""
        return Span(self.line, self.col, other.end_line, other.end_col)

    def as_dict(self) -> dict:
        return {
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }

    def key(self) -> str:
        """The stable part of a ``call_id`` (see ``ast_nodes.node_id``)."""
        return f"{self.line}:{self.col}:{self.end_line}:{self.end_col}"


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    value: str
    span: Span

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind}, {self.value!r}, {self.span.line}:{self.span.col})"
