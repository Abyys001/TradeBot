"""`docs/bot-plan.md` §3 — the parser: precedence, statements, spans."""

from __future__ import annotations

import pytest

from apps.pine import ast_nodes as ast
from apps.pine.errors import PineSyntaxError
from apps.pine.parser import parse
from tests import pine_corpus

HEAD = '//@version=5\nstrategy("t")\n'


def program(body: str) -> ast.Program:
    return parse(HEAD + body)


def first(body: str) -> ast.Node:
    return program(body).body[2 - 1]  # after the strategy() declaration


def expression(source: str) -> ast.Node:
    node = first(f"x = {source}\n")
    assert isinstance(node, ast.Assign)
    return node.value


def shape(node: ast.Node) -> str:
    """A parenthesised rendering, so a precedence assertion reads as one line."""
    if isinstance(node, ast.Binary):
        return f"({shape(node.left)} {node.op} {shape(node.right)})"
    if isinstance(node, ast.Unary):
        return f"({node.op}{shape(node.operand)})"
    if isinstance(node, ast.Ternary):
        return f"({shape(node.cond)} ? {shape(node.then)} : {shape(node.otherwise)})"
    if isinstance(node, ast.NumberLit):
        return node.value
    if isinstance(node, ast.Name):
        return node.name
    if isinstance(node, ast.BoolLit):
        return "true" if node.value else "false"
    if isinstance(node, ast.Index):
        return f"{shape(node.obj)}[{shape(node.offset)}]"
    if isinstance(node, ast.Member):
        return ast.dotted_name(node) or "?"
    if isinstance(node, ast.Call):
        return f"{shape(node.func)}(...)"
    return type(node).__name__


# --- precedence -------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1 + 2 * 3", "(1 + (2 * 3))"),
        ("1 * 2 + 3", "((1 * 2) + 3)"),
        ("1 - 2 - 3", "((1 - 2) - 3)"),
        ("1 / 2 / 3", "((1 / 2) / 3)"),
        ("1 + 2 % 3", "(1 + (2 % 3))"),
        ("-a * b", "((-a) * b)"),
        ("a > b and c < d", "((a > b) and (c < d))"),
        ("a and b or c", "((a and b) or c)"),
        ("a or b and c", "(a or (b and c))"),
        ("not a and b", "((nota) and b)"),
        ("a == b or c != d", "((a == b) or (c != d))"),
        ("a + b == c", "((a + b) == c)"),
        ("a ? b : c ? d : e", "(a ? b : (c ? d : e))"),
        ("a > b ? 1 : 2", "((a > b) ? 1 : 2)"),
        ("close[1] + 2", "(close[1] + 2)"),
    ],
)
def test_operator_precedence(source, expected):
    assert shape(expression(source)) == expected


def test_the_ternary_is_right_associative():
    """`a ? b : c ? d : e` must not read as `(a ? b : c) ? d : e`."""
    node = expression("a ? b : c ? d : e")
    assert isinstance(node.otherwise, ast.Ternary)


def test_parentheses_override_precedence():
    assert shape(expression("(1 + 2) * 3")) == "((1 + 2) * 3)"


# --- assignment forms -------------------------------------------------------


def test_declaration_and_reassignment_are_different_nodes():
    """The whole point: `=` creates, `:=` writes to what exists."""
    body = program("x = 1\nx := 2\n").body
    assert isinstance(body[1], ast.Assign)
    assert isinstance(body[2], ast.Reassign)


@pytest.mark.parametrize("qualifier", ["var", "varip"])
def test_var_qualifiers_are_recorded(qualifier):
    node = first(f"{qualifier} x = 1\n")
    assert node.qualifier == qualifier


@pytest.mark.parametrize(
    "declaration",
    ["int x = 1", "float x = 1.0", "bool x = true", "string x = 'a'", "series float x = na"],
)
def test_a_type_annotation_is_allowed_and_ignored(declaration):
    node = first(declaration + "\n")
    assert isinstance(node, ast.Assign)
    assert node.targets == ("x",)


def test_var_with_a_type_annotation():
    node = first("var int streak = 0\n")
    assert node.qualifier == "var"
    assert node.targets == ("streak",)


def test_a_tuple_declaration_names_every_target():
    node = first("[a, b, c] = ta.macd(close, 12, 26, 9)\n")
    assert node.targets == ("a", "b", "c")


@pytest.mark.parametrize(
    ("source", "op"),
    [("x += 1", "+"), ("x -= 1", "-"), ("x *= 2", "*"), ("x /= 2", "/"), ("x %= 2", "%")],
)
def test_compound_assignment_desugars_to_reassignment(source, op):
    """`a += b` is `a := a + b`, so the runtime keeps one reassignment path."""
    node = first(source + "\n")
    assert isinstance(node, ast.Reassign)
    assert node.target == "x"
    assert isinstance(node.value, ast.Binary)
    assert node.value.op == op
    assert node.value.left.name == "x"


# --- control flow -----------------------------------------------------------


def test_if_else_if_else_chains():
    # `if` is an expression, so a bare one arrives wrapped in an ExprStmt.
    node = first("if a\n    x = 1\nelse if b\n    x = 2\nelse\n    x = 3\n").value
    assert isinstance(node, ast.If)
    assert isinstance(node.otherwise, ast.If)
    assert isinstance(node.otherwise.otherwise, ast.Block)


def test_if_is_also_an_expression():
    node = first("x = if a\n    1\nelse\n    2\n")
    assert isinstance(node.value, ast.If)


def test_switch_with_a_default_arm():
    node = first('x = switch mode\n    "a" => 1\n    "b" => 2\n    => 3\n')
    switch = node.value
    assert isinstance(switch, ast.Switch)
    assert switch.cases[-1].match is None


def test_a_statement_can_follow_a_block_expression():
    """The DEDECT closing the block already consumed the newline."""
    body = program('x = switch m\n    "a" => 1\n    => 2\nfor i = 0 to 3\n    y = i\n').body
    assert isinstance(body[2], ast.For)


@pytest.mark.parametrize(
    ("source", "node_type"),
    [
        ("for i = 0 to 10\n    x = i\n", ast.For),
        ("for i = 10 to 0 by 2\n    x = i\n", ast.For),
        ("for [i, v] in items\n    x = v\n", ast.ForIn),
        ("while a < 3\n    a := a + 1\n", ast.While),
    ],
)
def test_loop_forms(source, node_type):
    assert isinstance(first(source), node_type)


def test_break_and_continue():
    node = first("for i = 0 to 3\n    if i > 1\n        break\n    continue\n")
    kinds = {type(n) for n in ast.walk(node)}
    assert ast.Break in kinds
    assert ast.Continue in kinds


# --- functions and calls ----------------------------------------------------


def test_a_single_line_function():
    node = program("f(x, y) => x + y\n").functions[0]
    assert node.name == "f"
    assert node.params == ("x", "y")


def test_a_multi_line_function_body_is_a_block():
    node = program("f(x) =>\n    a = x * 2\n    a + 1\n").functions[0]
    assert isinstance(node.body, ast.Block)
    assert len(node.body.body) == 2


def test_named_arguments_keep_their_names():
    call = expression("ta.sma(source = close, length = 20)")
    assert [a.name for a in call.args] == ["source", "length"]
    assert call.keyword("length") is not None


def test_a_missing_argument_name_is_positional():
    call = expression("ta.sma(close, 20)")
    assert [a.name for a in call.args] == ["", ""]


def test_calls_chain_with_history():
    node = expression("ta.sma(close, 20)[1]")
    assert isinstance(node, ast.Index)
    assert isinstance(node.obj, ast.Call)


# --- identity and spans -----------------------------------------------------


def test_call_id_is_derived_from_the_source_span():
    """It keys per-call-site state and links a chart marker to its line."""
    call = expression("ta.sma(close, 20)")
    assert call.call_id.startswith("Call@")
    assert str(call.span.line) in call.call_id


def test_two_identical_calls_on_different_lines_are_different_sites():
    body = program("a = ta.sma(close, 20)\nb = ta.sma(close, 20)\n").body
    assert body[1].value.call_id != body[2].value.call_id


def test_every_node_carries_a_span():
    for node in ast.walk(program("x = ta.sma(close, 20) + 1\n")):
        assert node.span is not None


# --- errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "x = (1 + 2\n",
        "x = \n",
        "if\n    x = 1\n",
        "for i = 0\n    x = 1\n",
        "x = 1 +\n",
    ],
)
def test_a_malformed_statement_is_a_located_syntax_error(source):
    with pytest.raises(PineSyntaxError) as caught:
        program(source)
    assert caught.value.span is not None


# --- the corpus -------------------------------------------------------------


@pytest.mark.parametrize("path", pine_corpus.accepted(), ids=lambda p: p.name)
def test_every_accepted_fixture_parses(path):
    result = parse(path.read_text())
    assert result.version == 5
    assert result.body
