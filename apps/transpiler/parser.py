"""Lark front end: source -> parse tree -> our AST.

LALR parser with an indentation postlex (Pine uses Python-like indented
blocks). A Transformer rewrites Lark's tree into the dataclasses in
ast_nodes so nothing downstream depends on Lark.
"""
from __future__ import annotations

from pathlib import Path

from lark import Lark, Token, Transformer, v_args
from lark.exceptions import LarkError
from lark.indenter import Indenter

from . import ast_nodes as ast
from .exceptions import PineSyntaxError

_GRAMMAR_PATH = Path(__file__).parent / "grammar" / "pine.lark"


class PineIndenter(Indenter):
    NL_type = "_NL"
    OPEN_PAREN_types = ["LPAR", "LSQB"]
    CLOSE_PAREN_types = ["RPAR", "RSQB"]
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    tab_len = 8


def _build_parser() -> Lark:
    grammar = _GRAMMAR_PATH.read_text()
    return Lark(
        grammar,
        parser="lalr",
        postlex=PineIndenter(),
        propagate_positions=True,
        maybe_placeholders=True,
    )


_PARSER = None


def _parser() -> Lark:
    global _PARSER
    if _PARSER is None:
        _PARSER = _build_parser()
    return _PARSER


def _pos(meta):
    if meta is None or getattr(meta, "empty", False):
        return {}
    return {"line": meta.line, "column": meta.column}


@v_args(meta=True)
class PineTransformer(Transformer):
    # --- top level ---
    def start(self, meta, children):
        body = [c for c in children if c is not None]
        header = None
        # A leading `strategy(...)` call becomes the strategy header.
        if body and isinstance(body[0], ast.BuiltinFunctionNode) and (
            body[0].namespace is None and body[0].name == "strategy"
        ):
            h = body.pop(0)
            header = ast.StrategyHeaderNode(args=h.args, line=h.line, column=h.column)
        return ast.ProgramNode(header=header, body=body, **_pos(meta))

    def simple_stmt(self, meta, children):
        return children[0]

    # --- statements ---
    def state_declaration(self, meta, children):
        # children: [KW_VAR, TYPE|None, NAME, value]
        kw, _type, name, value = children
        return ast.StateDeclarationNode(
            kind=str(kw), name=str(name), value=value, **_pos(meta)
        )

    def assignment(self, meta, children):
        # children: [TYPE|None, NAME, value]
        _type, name, value = children
        return ast.AssignNode(name=str(name), value=value, reassign=False, **_pos(meta))

    def reassignment(self, meta, children):
        name, value = children
        return ast.AssignNode(name=str(name), value=value, reassign=True, **_pos(meta))

    def if_stmt(self, meta, children):
        condition = children[0]
        then_body = children[1]
        elifs, else_body = [], None
        for c in children[2:]:
            if isinstance(c, tuple) and c and c[0] == "elif":
                elifs.append((c[1], c[2]))
            elif isinstance(c, tuple) and c and c[0] == "else":
                else_body = c[1]
        return ast.IfNode(
            condition=condition,
            then_body=then_body,
            elif_clauses=elifs,
            else_body=else_body,
            **_pos(meta),
        )

    def elif_clause(self, meta, children):
        return ("elif", children[0], children[1])

    def else_clause(self, meta, children):
        return ("else", children[0])

    def for_stmt(self, meta, children):
        var, start, end, body = children
        return ast.ForNode(
            var=str(var), start=start, end=end, body=body, **_pos(meta)
        )

    def suite(self, meta, children):
        return [c for c in children if c is not None]

    # --- expressions ---
    def ternary(self, meta, children):
        cond, if_true, if_false = children
        return ast.TernaryNode(
            condition=cond, if_true=if_true, if_false=if_false, **_pos(meta)
        )

    def binop(self, meta, children):
        left, op, right = children
        return ast.BinaryOpNode(op=str(op), left=left, right=right, **_pos(meta))

    def unary(self, meta, children):
        op, operand = children
        return ast.UnaryOpNode(op=str(op), operand=operand, **_pos(meta))

    def neg(self, meta, children):
        return ast.UnaryOpNode(op="-", operand=children[0], **_pos(meta))

    def history(self, meta, children):
        series, offset = children
        return ast.HistoryAccessNode(series=series, offset=offset, **_pos(meta))

    def member_call(self, meta, children):
        ns, name, args = children[0], children[1], children[2]
        arglist = args if args is not None else []
        node = ast.BuiltinFunctionNode(
            namespace=str(ns), name=str(name), args=arglist, **_pos(meta)
        )
        if str(ns) == "strategy":
            return ast.OrderExecutionNode(
                action=str(name), args=arglist, **_pos(meta)
            )
        return node

    def call(self, meta, children):
        name, args = children[0], children[1]
        arglist = args if args is not None else []
        return ast.BuiltinFunctionNode(
            namespace=None, name=str(name), args=arglist, **_pos(meta)
        )

    def member(self, meta, children):
        ns, name = children
        return ast.BuiltinFunctionNode(
            namespace=str(ns), name=str(name), args=[], **_pos(meta)
        )

    def arguments(self, meta, children):
        return list(children)

    def kwarg(self, meta, children):
        name, value = children
        return ast.ArgNode(value=value, name=str(name), **_pos(meta))

    def posarg(self, meta, children):
        return ast.ArgNode(value=children[0], name=None, **_pos(meta))

    def identifier(self, meta, children):
        return ast.IdentifierNode(name=str(children[0]), **_pos(meta))

    # --- literals ---
    def float_lit(self, meta, children):
        return ast.LiteralNode(value=float(children[0]), type="float", **_pos(meta))

    def int_lit(self, meta, children):
        return ast.LiteralNode(value=int(children[0]), type="int", **_pos(meta))

    def string_lit(self, meta, children):
        return ast.LiteralNode(value=str(children[0])[1:-1], type="string", **_pos(meta))

    def true_lit(self, meta, children):
        return ast.LiteralNode(value=True, type="bool", **_pos(meta))

    def false_lit(self, meta, children):
        return ast.LiteralNode(value=False, type="bool", **_pos(meta))

    def na_lit(self, meta, children):
        return ast.LiteralNode(value=None, type="na", **_pos(meta))


_TRANSFORMER = PineTransformer()


def parse(source: str) -> ast.ProgramNode:
    """Parse Pine source into a ProgramNode, or raise PineSyntaxError."""
    # Indenter needs a trailing newline to close the final block.
    if not source.endswith("\n"):
        source += "\n"
    try:
        tree = _parser().parse(source)
    except LarkError as exc:
        line = getattr(exc, "line", None)
        column = getattr(exc, "column", None)
        raise PineSyntaxError(str(exc).strip().splitlines()[0], line, column) from exc
    return _TRANSFORMER.transform(tree)
