"""`docs/bot-plan.md` §3 / Q24 — nothing outside the subset loads silently.

The parametrized tests here are the mechanism the plan asks for: a rejection
cannot ship without a fixture proving its message, line and column, and a
fixture cannot drift from the registry without one of these failing.
"""

from __future__ import annotations

import pytest

from apps.pine import subset
from apps.pine.limits import Limits
from apps.pine.validate import validate
from tests import pine_corpus

HEAD = '//@version=5\nstrategy("t")\n'


def check(body: str):
    return validate(HEAD + body)


def codes(result) -> list[str]:
    return [e.code for e in result.errors]


def warning_codes(result) -> list[str]:
    return [w.code for w in result.warnings]


# --- the corpus -------------------------------------------------------------


@pytest.mark.parametrize("path", pine_corpus.accepted(), ids=lambda p: p.name)
def test_every_accepted_fixture_validates(path):
    result = validate(path.read_text())
    assert result.errors == [], [e.as_dict() for e in result.errors]
    assert result.program is not None


@pytest.mark.parametrize("path", pine_corpus.rejected(), ids=lambda p: p.name)
def test_every_rejected_fixture_names_its_construct(path):
    """Q24: rejected **by name, line and column**, never as a bare parse error."""
    code, line, col = pine_corpus.expectation(path)
    result = validate(path.read_text())
    assert not result.ok
    located = [(e.code, e.span.line, e.span.col) for e in result.errors if e.span]
    assert (code, line, col) in located, located


@pytest.mark.parametrize("path", pine_corpus.rejected(), ids=lambda p: p.name)
def test_every_rejection_carries_a_message_a_reader_can_act_on(path):
    result = validate(path.read_text())
    for error in result.errors:
        assert len(str(error)) > 30
        assert error.code


@pytest.mark.parametrize("rejection", subset.REJECTIONS, ids=lambda r: f"{r.kind}:{r.pattern}")
def test_every_rejection_has_a_fixture(rejection):
    """A new row in the registry without a fixture fails here, by design."""
    wanted = {pine_corpus.expectation(p)[0] for p in pine_corpus.rejected()}
    assert rejection.code in wanted


@pytest.mark.parametrize("rejection", subset.REJECTIONS, ids=lambda r: f"{r.kind}:{r.pattern}")
def test_every_rejection_message_survives_to_the_error(rejection):
    """The message lives in the registry, so the error must be it verbatim."""
    matching = [
        p for p in pine_corpus.rejected() if pine_corpus.expectation(p)[0] == rejection.code
    ]
    assert matching
    messages = {str(e) for p in matching for e in validate(p.read_text()).errors}
    assert any(rejection.message in message for message in messages)


# --- version and declaration ------------------------------------------------


def test_a_missing_version_is_refused():
    assert "missing_version" in codes(validate('strategy("t")\nplot(close)\n'))


def test_a_v4_script_is_refused_rather_than_run_as_v5():
    assert "wrong_version" in codes(validate('//@version=4\nstrategy("t")\nplot(close)\n'))


def test_an_indicator_is_told_it_is_not_a_strategy():
    result = validate('//@version=5\nindicator("i")\nplot(close)\n')
    assert "not_a_strategy" in codes(result)


def test_strategy_must_be_the_first_statement():
    result = validate('//@version=5\nlen = 20\nstrategy("t")\n')
    assert "strategy_not_first" in codes(result)


def test_two_strategy_declarations_are_refused():
    result = validate('//@version=5\nstrategy("a")\nstrategy("b")\n')
    assert "duplicate_strategy" in codes(result)


# --- Q20: size arguments are parsed, ignored, and reported ------------------


def test_a_qty_on_an_entry_is_a_warning_not_an_error():
    """Q20: the platform decides size. Accepted, ignored, and said out loud."""
    result = check('strategy.entry("L", strategy.long, qty=5)\n')
    assert result.ok
    assert "ignored_qty" in warning_codes(result)


def test_default_qty_on_the_declaration_is_a_warning():
    result = validate('//@version=5\nstrategy("t", default_qty_value=100)\nplot(close)\n')
    assert result.ok
    assert "ignored_strategy_arg" in warning_codes(result)


def test_an_ignored_argument_is_never_silent():
    """The one rule Q24 turns on: parsed and dropped is only allowed out loud."""
    result = check('strategy.entry("L", strategy.long, qty_percent=50)\n')
    assert warning_codes(result)


# --- Q21: percent exits win, ticks and points are refused -------------------


def test_a_percent_exit_is_accepted():
    result = check('strategy.entry("L", strategy.long)\nstrategy.exit("x", "L", loss_pct=2)\n')
    assert result.ok


def test_a_tick_exit_is_refused_by_name_and_not_reinterpreted():
    """Pine's `loss=` is in ticks. Reading it as percent would silently retune."""
    result = check('strategy.entry("L", strategy.long)\nstrategy.exit("x", "L", loss=10)\n')
    assert "unsupported_exit_ticks" in codes(result)


def test_a_tick_exit_reports_once_not_twice():
    """It is one mistake; `exit_without_percent` on top would be noise."""
    result = check('strategy.entry("L", strategy.long)\nstrategy.exit("x", "L", loss=10)\n')
    assert codes(result).count("exit_without_percent") == 0


def test_an_exit_with_no_percent_at_all_is_refused():
    result = check('strategy.entry("L", strategy.long)\nstrategy.exit("x", "L")\n')
    assert "exit_without_percent" in codes(result)


# --- Q23: confirmed bars only -----------------------------------------------


def test_calc_on_every_tick_is_a_validation_error_not_a_setting():
    result = validate('//@version=5\nstrategy("t", calc_on_every_tick=true)\nplot(close)\n')
    assert "unsupported_intrabar" in codes(result)


def test_varip_is_accepted_as_var_and_says_so():
    result = check("varip float x = 0.0\nplot(x)\n")
    assert result.ok
    assert "varip_as_var" in warning_codes(result)


# --- semantic checks --------------------------------------------------------


def test_an_order_inside_a_loop_is_refused():
    result = check("for i = 0 to 3\n    strategy.entry(\"L\", strategy.long)\n")
    assert "order_in_loop" in codes(result)


def test_an_unbounded_while_is_refused():
    result = check("while true\n    x = 1\nplot(close)\n")
    assert "unbounded_loop" in codes(result)


def test_a_bounded_while_is_accepted():
    result = check("i = 0\nwhile i < 5\n    i := i + 1\nplot(i)\n")
    assert result.ok


def test_recursion_is_refused():
    result = check("f(n) =>\n    n <= 1 ? 1 : f(n - 1)\nplot(f(5))\n")
    assert "recursion" in codes(result)


def test_a_typo_names_the_thing_it_could_not_find():
    result = check("plot(ta.emaa(close, 20))\n")
    assert "unsupported_member" in codes(result)
    assert "emaa" in str(result.errors[0])


def test_a_typo_suggests_the_nearest_name():
    result = check("plot(ta.emaa(close, 20))\n")
    assert "ema" in str(result.errors[0])


def test_an_undefined_variable_is_refused():
    result = check("x = lenght\nplot(x)\n")
    assert "undefined_name" in codes(result)


# --- history ----------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "x = close[1]\nplot(x)\n",
        "y = 1.0\nz = y[1]\nplot(z)\n",
        "r = ta.rsi(close, 14)[1]\nplot(r)\n",
    ],
)
def test_history_is_allowed_where_it_is_actually_kept(body):
    assert check(body).ok


def test_history_on_an_arbitrary_expression_is_refused_not_answered_na():
    """Answering `na` would be a signal that quietly never fires."""
    result = check("spread = (high + low)[1]\nplot(spread)\n")
    assert "unsupported_history" in codes(result)


# --- decorative namespaces --------------------------------------------------


def test_a_colour_inside_a_visual_call_is_accepted():
    assert check("plot(close, color=color.green)\n").ok


def test_a_colour_outside_a_visual_call_is_refused():
    """Nothing decorative may reach an order, so it may not reach a variable."""
    result = check("c = color.green\nplot(close, color=c)\n")
    assert "decorative_outside_visual" in codes(result)


# --- inputs -----------------------------------------------------------------


def test_inputs_are_collected_with_their_bounds():
    result = check('len = input.int(20, "Length", minval=2, maxval=200)\nplot(len)\n')
    spec = result.inputs[0]
    assert (spec.name, spec.kind, spec.default) == ("len", "int", 20)
    assert (spec.minval, spec.maxval) == (2, 200)


def test_an_input_string_records_its_options():
    result = check('m = input.string("a", "Mode", options=["a", "b"])\nplot(close)\n')
    assert result.inputs[0].options == ("a", "b")


def test_an_input_that_is_not_assigned_to_a_name_is_refused():
    """The parameter form keys on the variable name, so there must be one."""
    result = check('plot(close + input.int(1, "Offset"))\n')
    assert "input_not_assigned" in codes(result)


# --- limits -----------------------------------------------------------------


def test_a_script_over_the_byte_limit_is_refused_before_it_is_parsed():
    result = validate(HEAD + "plot(close)\n" * 500, limits=Limits(max_script_bytes=100))
    assert codes(result) == ["script_too_large"]


def test_too_many_indicator_call_sites_is_refused():
    body = "".join(f"a{i} = ta.sma(close, {i + 2})\n" for i in range(20))
    result = validate(HEAD + body, limits=Limits(max_ta_call_sites=5))
    assert "too_many_indicators" in codes(result)


def test_too_many_nodes_is_refused():
    result = validate(HEAD + "x = 1 + 1\n" * 50, limits=Limits(max_ast_nodes=20))
    assert "script_too_complex" in codes(result)


# --- collecting rather than raising ------------------------------------------


def test_four_mistakes_come_back_as_four():
    """The editor underlines all of them; the author does not loop four times."""
    result = check(
        "a = lenght\n"
        "b = wdith\n"
        "c = heigth\n"
        "d = dpeth\n"
        "plot(a + b + c + d)\n"
    )
    assert len(result.errors) == 4


def test_validate_never_raises_even_on_nonsense():
    assert not validate("!!! not pine at all (((").ok


# --- hoisting ---------------------------------------------------------------


def test_a_ta_call_inside_a_function_is_warned_about_not_silently_wrong():
    result = check("f(x) =>\n    ta.sma(x, 10)\nplot(f(close))\n")
    assert result.ok
    assert "ta_not_hoisted" in warning_codes(result)


def test_a_top_level_ta_call_needs_no_warning():
    result = check("plot(ta.sma(close, 10))\n")
    assert "ta_not_hoisted" not in warning_codes(result)


# --- user-defined types, enums, methods (Q24 reversal) ---------------------


def test_a_type_declaration_and_object_use_validate():
    result = check(
        "type Level\n"
        "    float price\n"
        "    int touches = 0\n"
        "p = Level.new(close)\n"
        "p.price := close\n"
        "plot(p.price + p.touches)\n"
    )
    assert result.errors == [], [e.as_dict() for e in result.errors]


def test_an_enum_and_a_method_validate():
    result = check(
        "enum Dir\n    up\n    down\n"
        "type Box\n    float v\n"
        "method sign(Box self) =>\n    self.v > 0 ? Dir.up : Dir.down\n"
        "b = Box.new(close)\n"
        "d = b.sign()\n"
        "plot(close)\n"
    )
    assert result.errors == [], [e.as_dict() for e in result.errors]


def test_an_unknown_field_on_new_is_named():
    result = check("type P\n    float x\np = P.new(y = 1.0)\nplot(p.x)\n")
    assert "unknown_field" in codes(result)


def test_an_unknown_field_read_is_named_when_the_type_is_known():
    result = check("type P\n    float x\np = P.new(1.0)\nplot(p.z)\n")
    assert "unknown_field" in codes(result)


def test_an_unknown_enum_member_is_named():
    result = check("enum Mode\n    fast\n    slow\nm = Mode.turbo\nplot(close)\n")
    assert "unknown_enum_member" in codes(result)


def test_a_field_declared_with_an_unknown_type_is_refused():
    result = check("type Bad\n    Widget w\nplot(close)\n")
    assert "unknown_field_type" in codes(result)


def test_a_type_cannot_be_named_after_a_builtin_type():
    result = check("type float\n    float x\nplot(close)\n")
    assert "type_name_reserved" in codes(result)


def test_a_duplicate_type_is_refused():
    result = check("type D\n    float a\ntype D\n    float b\nplot(close)\n")
    assert "duplicate_type" in codes(result)


def test_a_method_on_an_unknown_type_is_refused():
    result = check("method f(Ghost self) =>\n    self\nplot(close)\n")
    assert "unknown_receiver_type" in codes(result)


def test_two_method_overloads_with_the_same_receiver_are_refused():
    result = check(
        "type P\n    float x\n"
        "method f(P self) =>\n    self.x\n"
        "method f(P self) =>\n    self.x * 2\n"
        "plot(close)\n"
    )
    assert "duplicate_method" in codes(result)


def test_method_overloads_on_different_receivers_are_accepted():
    result = check(
        "type A\n    float x\n"
        "type B\n    float y\n"
        "method f(A self) =>\n    self.x\n"
        "method f(B self) =>\n    self.y\n"
        "plot(close)\n"
    )
    assert result.errors == [], [e.as_dict() for e in result.errors]


def test_an_order_call_inside_a_method_is_refused():
    result = check(
        "type P\n    float x\n"
        "method go(P self) =>\n    strategy.entry(\"L\", strategy.long)\n"
        "p = P.new(close)\n"
        "p.go()\n"
    )
    assert "order_in_function" in codes(result)


def test_mutual_recursion_between_methods_is_refused():
    result = check(
        "type P\n    float x\n"
        "method a(P self) =>\n    self.b()\n"
        "method b(P self) =>\n    self.a()\n"
        "p = P.new(close)\n"
        "plot(p.a())\n"
    )
    assert "recursion" in codes(result)


def test_an_undefined_object_root_in_member_position_is_named():
    result = check("z = bogus.field\nplot(z)\n")
    assert "undefined_name" in codes(result)
