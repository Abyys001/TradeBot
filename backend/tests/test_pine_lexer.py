"""`docs/bot-plan.md` §3 — the lexer: literals, indentation, continuation."""

from __future__ import annotations

import pytest

from apps.pine.errors import PineSyntaxError
from apps.pine.lexer import declared_version, tokenize
from apps.pine.tokens import TokenKind
from tests import pine_corpus


def kinds(source: str) -> list[TokenKind]:
    return [t.kind for t in tokenize(source)]


def values(source: str) -> list[str]:
    return [t.value for t in tokenize(source) if t.kind not in (TokenKind.NEWLINE, TokenKind.EOF)]


# --- version ----------------------------------------------------------------


def test_version_is_read_from_the_comment_the_lexer_discards():
    assert declared_version("//@version=5\nstrategy('x')") == 5


def test_no_version_annotation_is_none_rather_than_a_guess():
    assert declared_version("strategy('x')") is None


# --- literals ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("1", "1"),
        ("1.5", "1.5"),
        (".5", ".5"),
        ("1e3", "1e3"),
        ("1.5e-3", "1.5e-3"),
        ("0.0001", "0.0001"),
    ],
)
def test_number_literals(source, expected):
    token = tokenize(source)[0]
    assert token.kind == TokenKind.NUMBER
    assert token.value == expected


@pytest.mark.parametrize("quote", ['"', "'"])
def test_strings_take_either_quote(quote):
    token = tokenize(f"{quote}hello{quote}")[0]
    assert token.kind == TokenKind.STRING
    assert token.value == "hello"


def test_a_string_keeps_its_escapes():
    assert tokenize(r'"a\"b"')[0].value == 'a"b'


def test_an_unterminated_string_is_a_located_error():
    with pytest.raises(PineSyntaxError) as caught:
        tokenize('x = "open')
    assert caught.value.span.line == 1


@pytest.mark.parametrize("literal", ["#FF0000", "#ff000080"])
def test_colour_literals(literal):
    token = tokenize(literal)[0]
    assert token.kind == TokenKind.COLOR
    assert token.value == literal


def test_booleans_lex_as_keywords():
    """`true` cannot be reassigned, so it is a keyword; the parser makes the literal."""
    assert [t.kind for t in tokenize("true false")][:2] == [TokenKind.KEYWORD, TokenKind.KEYWORD]


def test_na_is_a_name_not_a_keyword():
    """It is a *value*, and `na(x)` is also a call — a keyword could be neither."""
    assert tokenize("na")[0].kind == TokenKind.NAME


# --- comments and continuation ----------------------------------------------


def test_a_comment_runs_to_the_end_of_the_line():
    assert values("x = 1 // this is ignored\ny = 2") == ["x", "=", "1", "y", "=", "2"]


def test_a_backslash_continues_the_line():
    """One statement, so one terminator — the break inside it emits nothing."""
    assert kinds("x = 1 + \\\n    2").count(TokenKind.NEWLINE) == 1


def test_a_bracket_suspends_the_newline_terminator():
    """A call split over lines is one statement, not three."""
    source = "plot(close,\n     color=red,\n     linewidth=2)"
    assert kinds(source).count(TokenKind.NEWLINE) == 1


# --- indentation ------------------------------------------------------------


def test_an_indented_block_emits_indent_and_dedent():
    source = "if close > open\n    x = 1\ny = 2\n"
    seen = kinds(source)
    assert TokenKind.INDENT in seen
    assert TokenKind.DEDENT in seen


def test_nested_blocks_close_in_order():
    source = "if a\n    if b\n        x = 1\ny = 2\n"
    seen = [k for k in kinds(source) if k in (TokenKind.INDENT, TokenKind.DEDENT)]
    assert seen == [TokenKind.INDENT, TokenKind.INDENT, TokenKind.DEDENT, TokenKind.DEDENT]


def test_a_tab_counts_as_four_columns():
    """Mixing them is how a script indents differently here than on TradingView."""
    spaces = kinds("if a\n    x = 1\ny = 2\n")
    tabs = kinds("if a\n\tx = 1\ny = 2\n")
    assert spaces == tabs


def test_a_bracket_suspends_indentation_too():
    """A wrapped argument list is not a block, however far it is indented."""
    source = "plot(close,\n        color=red)\nx = 1\n"
    assert TokenKind.INDENT not in kinds(source)


def test_a_blank_line_inside_a_block_does_not_close_it():
    source = "if a\n    x = 1\n\n    y = 2\nz = 3\n"
    assert [k for k in kinds(source) if k == TokenKind.DEDENT] == [TokenKind.DEDENT]


# --- spans ------------------------------------------------------------------


def test_a_span_points_at_the_column_the_editor_draws():
    token = tokenize("x = close")[2]
    assert (token.span.line, token.span.col) == (1, 5)


def test_crlf_does_not_shift_every_column():
    """A file saved on Windows must underline the same character."""
    unix = tokenize("x = 1\ny = 2")
    windows = tokenize("x = 1\r\ny = 2")
    assert [t.span.as_dict() for t in unix] == [t.span.as_dict() for t in windows]


# --- operators --------------------------------------------------------------


@pytest.mark.parametrize("op", ["+=", "-=", "*=", "/=", "%="])
def test_compound_assignment_lexes_as_one_operator(op):
    """Longest-first, or `a += b` becomes `a` `+` `= b`."""
    assert values(f"a {op} b") == ["a", op, "b"]


@pytest.mark.parametrize("op", [":=", "==", "!=", "<=", ">=", "=>"])
def test_two_character_operators_beat_their_prefixes(op):
    assert values(f"a {op} b") == ["a", op, "b"]


# --- the corpus -------------------------------------------------------------


@pytest.mark.parametrize("path", pine_corpus.accepted(), ids=lambda p: p.name)
def test_every_accepted_fixture_lexes(path):
    tokens = tokenize(path.read_text())
    assert tokens[-1].kind == TokenKind.EOF


# --- line wrapping ----------------------------------------------------------
#
# TradingView's own rule (`style_guide.md`): four spaces open a block, so *any
# other* indentation continues the line above. Every published strategy wraps
# its ternary chains this way, and the lexer used to accept only a trailing
# backslash — which no exported script contains.


@pytest.mark.parametrize("indent", [" ", "  ", "   ", "     ", "      "])
def test_an_indent_that_is_not_a_multiple_of_four_continues_the_line(indent):
    assert values(f"x = close +\n{indent}open") == ["x", "=", "close", "+", "open"]


def test_a_wrapped_ternary_chain_is_one_statement():
    source = "basis =\n     useA ? a :\n     useB ? b :\n     c\n"
    assert TokenKind.INDENT not in kinds(source)
    assert values(source)[:5] == ["basis", "=", "useA", "?", "a"]


def test_four_spaces_still_open_a_block():
    """The other half of the same rule — a wrap must not swallow a body."""
    assert TokenKind.INDENT in kinds("if close > open\n    x = 1\n")


def test_a_wrap_inside_a_block_does_not_close_it():
    source = "if close > open\n    x = 1 +\n     2\n    y = 2\n"
    assert kinds(source).count(TokenKind.INDENT) == 1
    assert kinds(source).count(TokenKind.DEDENT) == 1
    assert [
        t.value
        for t in tokenize(source)
        if t.kind not in (TokenKind.NEWLINE, TokenKind.EOF, TokenKind.INDENT, TokenKind.DEDENT)
    ] == ["if", "close", ">", "open", "x", "=", "1", "+", "2", "y", "=", "2"]


def test_a_first_line_that_is_oddly_indented_opens_a_block_rather_than_wrapping():
    """There is nothing above it to be a continuation *of*.

    The lexer emits the INDENT and the parser reports it — the failure has to
    say "this is indented and nothing opened a block", not glue the line onto
    a statement that does not exist.
    """
    assert TokenKind.INDENT in kinds("  x = 1\ny = 2\n")


def test_the_backslash_form_still_works():
    """Kept alongside the indentation rule: it survives an editor that reindents."""
    assert values("x = close + \\\n    open") == ["x", "=", "close", "+", "open"]
