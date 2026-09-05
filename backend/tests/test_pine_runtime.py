"""`docs/bot-plan.md` §4 — one bar at a time: state, intents, budget, snapshots."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.pine.bar import Bar
from apps.pine.errors import PineRuntimeError
from apps.pine.intent import Side
from apps.pine.limits import DEFAULT_LIMITS, Limits
from apps.pine.parser import parse
from apps.pine.runtime import Runtime
from apps.pine.series import is_na
from apps.pine.validate import validate
from tests import pine_corpus

D = Decimal
HEAD = '//@version=5\nstrategy("t")\n'


def runtime(body: str, *, inputs: dict | None = None, limits: Limits = DEFAULT_LIMITS) -> Runtime:
    result = validate(HEAD + body, limits=limits)
    assert result.errors == [], [e.as_dict() for e in result.errors]
    return Runtime(result.program, symbol="BTCUSDT", inputs=inputs, limits=limits)


def bar(close: str, *, time: int = 0, high: str | None = None, low: str | None = None) -> Bar:
    price = D(close)
    return Bar(
        time=time,
        open=price,
        high=D(high) if high else price,
        low=D(low) if low else price,
        close=price,
        volume=D("1"),
    )


def run(rt: Runtime, closes: list[str]):
    results = []
    for index, close in enumerate(closes):
        results.append(rt.run_bar(bar(close, time=index * 900)))
    return results


# --- built-in series --------------------------------------------------------


def test_the_builtin_series_advance_one_bar_at_a_time():
    rt = runtime("x = close\nplot(x)\n")
    run(rt, ["1", "2", "3"])
    assert rt.ctx.series["close"][0] == D("3")
    assert rt.ctx.series["close"][2] == D("1")


def test_bar_index_starts_at_zero():
    rt = runtime("plot(bar_index)\n")
    run(rt, ["1", "2"])
    assert rt.ctx.bar_index == 1


@pytest.mark.parametrize("name", ["hl2", "hlc3", "ohlc4"])
def test_the_derived_series_are_computed_per_bar(name):
    rt = runtime(f"x = {name}\nplot(x)\n")
    rt.run_bar(Bar(time=0, open=D("10"), high=D("20"), low=D("0"), close=D("10"), volume=D("1")))
    assert rt.ctx.globals["x"].value == {"hl2": D("10"), "hlc3": D("10"), "ohlc4": D("10")}[name]


def test_history_reads_the_previous_bar():
    rt = runtime("prev = close[1]\nplot(prev)\n")
    run(rt, ["1", "2", "3"])
    assert rt.ctx.globals["prev"].value == D("2")


def test_history_before_the_first_bar_is_na():
    rt = runtime("prev = close[1]\nplot(prev)\n")
    run(rt, ["1"])
    assert is_na(rt.ctx.globals["prev"].value)


# --- var and reassignment ---------------------------------------------------


def test_var_survives_the_bar():
    rt = runtime("var int n = 0\nn := n + 1\nplot(n)\n")
    run(rt, ["1", "2", "3"])
    assert rt.ctx.globals["n"].value == D("3")


def test_a_plain_declaration_is_recomputed_every_bar():
    rt = runtime("n = 0\nn := n + 1\nplot(n)\n")
    run(rt, ["1", "2", "3"])
    assert rt.ctx.globals["n"].value == D("1")


def test_a_var_keeps_its_history():
    rt = runtime("var float last = 0.0\nlast := close\nprev = last[1]\nplot(prev)\n")
    run(rt, ["1", "2", "3"])
    assert rt.ctx.globals["prev"].value == D("2")


def test_compound_assignment_accumulates():
    rt = runtime("var float total = 0.0\ntotal += close\nplot(total)\n")
    run(rt, ["1", "2", "3"])
    assert rt.ctx.globals["total"].value == D("6")


# --- control flow -----------------------------------------------------------

def test_an_if_expression_yields_the_taken_branch():
    rt = runtime("x = if close > 2\n    10\nelse\n    20\nplot(x)\n")
    run(rt, ["1"])
    assert rt.ctx.globals["x"].value == D("20")
    run(rt, ["3"])
    assert rt.ctx.globals["x"].value == D("10")


def test_a_switch_falls_through_to_its_default():
    rt = runtime('m = "z"\nx = switch m\n    "a" => 1\n    => 9\nplot(x)\n')
    run(rt, ["1"])
    assert rt.ctx.globals["x"].value == D("9")


def test_a_for_loop_runs_its_body():
    rt = runtime("total = 0.0\nfor i = 0 to 4\n    total := total + 1\nplot(total)\n")
    run(rt, ["1"])
    assert rt.ctx.globals["total"].value == D("5")


def test_break_leaves_the_loop():
    rt = runtime(
        "total = 0.0\nfor i = 0 to 100\n    if i > 2\n        break\n    total := total + 1\n"
        "plot(total)\n"
    )
    run(rt, ["1"])
    assert rt.ctx.globals["total"].value == D("3")


def test_a_runaway_loop_is_stopped_by_the_iteration_limit():
    """A bot that never returns from a bar is a bot that never closes a position."""
    limits = Limits(max_loop_iterations=50)
    rt = runtime("i = 0\nwhile i < 1000000\n    i := i + 1\nplot(i)\n", limits=limits)
    with pytest.raises(PineRuntimeError) as caught:
        run(rt, ["1"])
    assert caught.value.code == "loop_limit"


def test_a_variable_declared_inside_a_block_does_not_escape_it():
    """Pine shadows rather than assigns — the reference is explicit about this."""
    rt = runtime("x = 1\nif close > 0\n    x = 99\nplot(x)\n")
    run(rt, ["1"])
    assert rt.ctx.globals["x"].value == D("1")


# --- user functions ---------------------------------------------------------


def test_a_user_function_returns_its_last_expression():
    rt = runtime("f(a, b) =>\n    c = a + b\n    c * 2\nx = f(2, 3)\nplot(x)\n")
    run(rt, ["1"])
    assert rt.ctx.globals["x"].value == D("10")


def test_a_ta_call_in_a_function_called_twice_is_two_indicators():
    """One converged average per logical call site, not one fed two series."""
    rt = runtime(
        "f(src) =>\n    ta.sma(src, 2)\na = f(close)\nb = f(high)\nplot(a + b)\n"
    )
    for index, (close, high) in enumerate([("10", "20"), ("30", "40")]):
        rt.run_bar(bar(close, time=index * 900, high=high, low=close))
    assert rt.ctx.globals["a"].value == D("20")
    assert rt.ctx.globals["b"].value == D("30")


# --- ta call sites ----------------------------------------------------------


def test_an_indicator_inside_a_branch_still_advances_every_bar():
    """The trap TradingView warns about: an EMA that only updates on its branch's
    days converges to a different series and never says so."""
    rt = runtime(
        "inside = 0.0\nif close > 100\n    inside := ta.sma(close, 3)\nalways = ta.sma(close, 3)\n"
        "plot(always)\n"
    )
    run(rt, ["10", "20", "30", "200"])
    assert rt.ctx.globals["inside"].value == rt.ctx.globals["always"].value
    assert rt.advance_failures == set()


def test_a_ta_call_keeps_its_own_history():
    rt = runtime("now = ta.sma(close, 2)\nbefore = ta.sma(close, 2)[1]\nplot(now)\n")
    run(rt, ["10", "20", "30"])
    assert rt.ctx.globals["now"].value == D("25")
    assert rt.ctx.globals["before"].value == D("15")


def test_two_call_sites_with_the_same_arguments_stay_separate():
    rt = runtime("a = ta.sma(close, 2)\nb = ta.sma(close, 2)\nplot(a + b)\n")
    run(rt, ["10", "20"])
    assert rt.ctx.globals["a"].value == rt.ctx.globals["b"].value == D("15")
    assert len(rt.stateful_sites) == 2


# --- inputs -----------------------------------------------------------------


def test_an_input_falls_back_to_the_scripts_default():
    rt = runtime('len = input.int(5, "Length")\nplot(len)\n')
    run(rt, ["1"])
    assert rt.ctx.globals["len"].value == 5


def test_a_configured_input_overrides_the_default():
    rt = runtime('len = input.int(5, "Length")\nplot(len)\n', inputs={"len": 20})
    run(rt, ["1"])
    assert rt.ctx.globals["len"].value == 20


def test_an_input_is_keyed_on_the_variable_not_the_title():
    """A retitled input keeps the value the operator configured."""
    rt = runtime('len = input.int(5, "Renamed since")\nplot(len)\n', inputs={"len": 7})
    run(rt, ["1"])
    assert rt.ctx.globals["len"].value == 7


def test_a_configured_value_takes_the_shape_of_the_default():
    rt = runtime('mult = input.float(1.0, "Mult")\nplot(mult)\n', inputs={"mult": "2.5"})
    run(rt, ["1"])
    assert rt.ctx.globals["mult"].value == D("2.5")


# --- intents ----------------------------------------------------------------


def test_an_entry_becomes_a_long_intent():
    rt = runtime('if close > 5\n    strategy.entry("L", strategy.long)\n')
    result = run(rt, ["10"])[-1]
    assert result.intent.desired_side is Side.LONG


def test_a_short_entry_becomes_a_short_intent():
    rt = runtime('if close > 5\n    strategy.entry("S", strategy.short)\n')
    assert run(rt, ["10"])[-1].intent.desired_side is Side.SHORT


def test_a_quiet_bar_does_not_ask_to_close_a_position():
    """An intent is what should be true *after* the bar, not what the bar said."""
    rt = runtime('if close > 100\n    strategy.entry("L", strategy.long)\n')
    rt.sync_position(size_sign=1, avg_price=D("100"))
    assert run(rt, ["10"])[-1].intent.desired_side is Side.LONG


def test_a_close_flattens_the_intent():
    rt = runtime('if close < 5\n    strategy.close_all()\n')
    rt.sync_position(size_sign=1, avg_price=D("100"))
    assert run(rt, ["1"])[-1].intent.desired_side is None


def test_the_intent_carries_the_bar_time_and_symbol():
    rt = runtime('strategy.entry("L", strategy.long)\n')
    intent = rt.run_bar(bar("10", time=1700000000)).intent
    assert intent.bar_time == 1700000000
    assert intent.symbol == "BTCUSDT"


def test_the_intent_carries_the_source_span_of_the_order():
    """It is what links a chart marker back to the line that placed it."""
    rt = runtime('strategy.entry("L", strategy.long)\n')
    intent = rt.run_bar(bar("10")).intent
    assert intent.source_span.line == 3


def test_an_exit_percent_rides_on_the_intent():
    rt = runtime(
        'strategy.entry("L", strategy.long)\nstrategy.exit("x", "L", loss_pct=2, profit_pct=5)\n'
    )
    intent = rt.run_bar(bar("10")).intent
    assert intent.sl_pct == D("2")
    assert intent.tp_pct == D("5")


def test_the_intent_carries_no_quantity_at_all():
    """Q20: the platform decides size, so there is nowhere for one to hide."""
    rt = runtime('strategy.entry("L", strategy.long, qty=99)\n')
    assert "qty" not in rt.run_bar(bar("10")).intent.as_dict()


def test_position_state_comes_from_the_driver_not_from_the_script():
    rt = runtime("size = strategy.position_size\nplot(size)\n")
    rt.sync_position(size_sign=-1, avg_price=D("50"), equity=D("1000"))
    run(rt, ["10"])
    assert rt.ctx.globals["size"].value == D("-1")


def test_position_size_is_a_direction_not_a_quantity():
    """Q20 again: no single quantity is true across every account."""
    rt = runtime("size = strategy.position_size\nplot(size)\n")
    rt.sync_position(size_sign=99)
    run(rt, ["10"])
    assert rt.ctx.globals["size"].value == D("1")


# --- annotations ------------------------------------------------------------


def test_a_plot_is_recorded_rather_than_executed():
    rt = runtime("plot(close, title='price')\n")
    result = rt.run_bar(bar("10"))
    assert any(a.kind == "plot" for a in result.annotations)


def test_an_alert_is_recorded_on_the_intent():
    rt = runtime("alert('fired')\n")
    assert "fired" in rt.run_bar(bar("10")).intent.alerts


# --- budget -----------------------------------------------------------------


def test_the_bar_is_timed():
    rt = runtime("plot(close)\n")
    assert rt.run_bar(bar("10")).elapsed_ms >= 0


def test_the_budget_is_only_enforced_when_the_driver_asks():
    """A backtest runs thousands of bars flat out; only live evaluation is timed."""
    limits = Limits(bar_budget_ms=0, max_loop_iterations=100000)
    body = "total = 0.0\nfor i = 0 to 5000\n    total := total + 1\nplot(total)\n"
    rt = runtime(body, limits=limits)
    rt.run_bar(bar("10"))  # no enforcement: fine
    with pytest.raises(PineRuntimeError) as caught:
        rt.run_bar(bar("11"), enforce_budget=True)
    assert caught.value.code == "bar_budget_exceeded"


# --- snapshots --------------------------------------------------------------


def test_a_snapshot_restores_indicator_state():
    rt = runtime("x = ta.sma(close, 3)\nplot(x)\n")
    run(rt, ["10", "20", "30"])
    saved = rt.snapshot()
    run(rt, ["40", "50"])
    moved = rt.ctx.globals["x"].value
    rt.restore(saved)
    run(rt, ["40", "50"])
    assert rt.ctx.globals["x"].value == moved


def test_a_snapshot_is_a_copy_not_a_view():
    rt = runtime("var float n = 0.0\nn := n + 1\nplot(n)\n")
    run(rt, ["1"])
    saved = rt.snapshot()
    run(rt, ["1", "1"])
    rt.restore(saved)
    assert rt.ctx.globals["n"].value == D("1")


# --- determinism ------------------------------------------------------------


def test_the_same_bars_produce_the_same_intents_twice():
    source = pine_corpus.ACCEPT.joinpath("01_sma_cross.pine").read_text()
    bars = pine_corpus.bars(200)

    def sequence():
        rt = Runtime(parse(source), symbol="BTCUSDT")
        return [rt.run_bar(b).intent.as_dict() for b in bars]

    assert sequence() == sequence()


@pytest.mark.parametrize("path", pine_corpus.accepted(), ids=lambda p: p.name)
def test_every_accepted_fixture_runs_two_hundred_bars(path):
    result = validate(path.read_text())
    rt = Runtime(result.program, symbol="BTCUSDT")
    for candle in pine_corpus.bars(200):
        rt.run_bar(candle)
    assert rt.advance_failures == set()


# --- user-defined types, enums, methods -----------------------------------


def test_an_object_field_is_read_and_written():
    rt = runtime(
        "type P\n    float x\n    int n = 0\n"
        "p = P.new(close)\n"
        "p.x := close + 1\n"
        "p.n := p.n + 5\n"
        "plot(p.x)\n"
    )
    run(rt, ["10"])
    assert rt.ctx.globals["p"].value.fields["x"] == D("11")
    assert rt.ctx.globals["p"].value.fields["n"] == D("5")


def test_a_field_default_is_used_when_no_value_is_given():
    rt = runtime("type P\n    float x = 7.0\n    int n = 0\np = P.new()\nplot(p.x)\n")
    run(rt, ["1"])
    assert rt.ctx.globals["p"].value.fields["x"] == D("7.0")


def test_var_keeps_one_object_across_bars_and_its_fields_persist():
    rt = runtime(
        "type Counter\n    int n = 0\n"
        "var Counter c = Counter.new()\n"
        "c.n := c.n + 1\n"
        "plot(c.n)\n"
    )
    results = run(rt, ["1", "2", "3", "4"])
    assert [r.intent.plots["plot_1"] for r in results] == [D("1"), D("2"), D("3"), D("4")]


def test_objects_are_assigned_by_reference():
    rt = runtime(
        "type P\n    float x\n"
        "a = P.new(1.0)\n"
        "b = a\n"
        "b.x := 2.0\n"
        "plot(a.x)\n"
    )
    results = run(rt, ["1"])
    assert results[0].intent.plots["plot_1"] == D("2.0")


def test_copy_breaks_the_reference():
    rt = runtime(
        "type P\n    float x\n"
        "a = P.new(1.0)\n"
        "b = P.copy(a)\n"
        "b.x := 2.0\n"
        "plot(a.x)\n"
    )
    results = run(rt, ["1"])
    assert results[0].intent.plots["plot_1"] == D("1.0")


def test_a_user_method_receives_the_object_and_returns_a_value():
    rt = runtime(
        "type Acc\n    float total = 0.0\n"
        "method add(Acc self, float v) =>\n    self.total := self.total + v\n    self.total\n"
        "var Acc acc = Acc.new()\n"
        "running = acc.add(close)\n"
        "plot(running)\n"
    )
    results = run(rt, ["10", "20", "30"])
    assert [r.intent.plots["plot_1"] for r in results] == [D("10"), D("30"), D("60")]


def test_a_method_default_argument_is_applied():
    rt = runtime(
        "type P\n    int n = 0\n"
        "method bump(P self, int amount = 3) =>\n    self.n := self.n + amount\n    self.n\n"
        "var P p = P.new()\n"
        "plot(p.bump())\n"
    )
    results = run(rt, ["1", "1"])
    assert [r.intent.plots["plot_1"] for r in results] == [D("3"), D("6")]


def test_method_overload_dispatches_on_receiver_type():
    rt = runtime(
        "type A\n    float v\n"
        "type B\n    float v\n"
        "method tag(A self) =>\n    1\n"
        "method tag(B self) =>\n    2\n"
        "a = A.new(0.0)\n"
        "b = B.new(0.0)\n"
        "plot(a.tag() * 10 + b.tag())\n"
    )
    results = run(rt, ["1"])
    assert results[0].intent.plots["plot_1"] == D("12")


def test_enum_members_compare_by_identity_and_drive_a_switch():
    rt = runtime(
        'enum Dir\n    up = "U"\n    down = "D"\n    flat\n'
        "d = close > open ? Dir.up : close < open ? Dir.down : Dir.flat\n"
        "s = switch d\n    Dir.up => 1\n    Dir.down => -1\n    => 0\n"
        "plot(s)\n"
    )
    r_up = rt.run_bar(bar("10", time=0, high="10", low="1"))
    # open == close on the helper bar → flat
    assert r_up.intent.plots["plot_1"] == D("0")


def test_an_unknown_field_write_raises_a_located_error():
    rt = runtime("type P\n    float x\np = P.new(1.0)\np.y := 2.0\nplot(p.x)\n")
    with pytest.raises(PineRuntimeError) as caught:
        run(rt, ["1"])
    assert caught.value.code == "unknown_field"
    assert caught.value.span is not None


def test_a_udt_strategy_snapshot_round_trips():
    rt = runtime(
        "type P\n    int n = 0\n"
        "var P p = P.new()\n"
        "p.n := p.n + 1\n"
        "plot(p.n)\n"
    )
    run(rt, ["1", "1", "1"])
    saved = rt.snapshot()
    run(rt, ["1"])
    assert rt.ctx.globals["p"].value.fields["n"] == D("4")
    rt.restore(saved)
    assert rt.ctx.globals["p"].value.fields["n"] == D("3")


# --- the instrument, the timeframe and the chart -----------------------------


def info_runtime(body: str, *, symbol: str = "BTCUSDT", interval: str = "1h") -> Runtime:
    from apps.pine.symbol import SymbolInfo, TimeframeInfo

    result = validate(HEAD + body)
    assert result.errors == [], [e.as_dict() for e in result.errors]
    return Runtime(
        result.program,
        symbol=symbol,
        symbol_info=SymbolInfo.for_symbol(symbol, mintick=D("0.5")),
        timeframe=TimeframeInfo.for_interval(interval),
    )


def test_syminfo_describes_the_bots_own_pair():
    rt = info_runtime(
        'plot(1, "ticker" + syminfo.ticker + syminfo.basecurrency + syminfo.currency)\n'
    )
    rt.run_bar(bar("100"))
    assert "tickerBTCUSDTBTCUSDT" in "".join(rt.ctx.plots)


def test_syminfo_mintick_is_the_exchanges_tick_not_a_guess():
    rt = info_runtime("x = math.round_to_mintick(close)\nplot(x)\n")
    result = rt.run_bar(bar("100.3"))
    assert result.intent.plots["plot_1"] == D("100.5")


def test_timeframe_answers_in_tradingviews_own_spelling():
    rt = info_runtime('plot(1, timeframe.period)\n', interval="4h")
    result = rt.run_bar(bar("100"))
    assert "240" in result.intent.plots


def test_the_chart_is_standard_candles_definitely_not_unknown():
    """A strategy guarding against synthetic prices needs a definite answer."""
    rt = info_runtime("x = chart.is_heikinashi ? 1 : 0\nplot(x)\n")
    assert rt.run_bar(bar("100")).intent.plots["plot_1"] == 0


# --- the dashboard figures ---------------------------------------------------


def test_the_performance_figures_come_from_the_driver():
    rt = runtime("plot(strategy.closedtrades)\nplot(strategy.netprofit_percent, 'pnl')\n")
    rt.sync_position(
        size_sign=0,
        performance={"closedtrades": D("7"), "netprofit_percent": D("12.5")},
    )
    result = rt.run_bar(bar("100"))
    assert result.intent.plots["plot_1"] == D("7")
    assert result.intent.plots["pnl"] == D("12.5")


def test_a_figure_the_driver_has_not_supplied_is_zero_not_na():
    """A fresh run really has closed no trades, and `na` would poison the ratio
    every dashboard computes on its first bar."""
    rt = runtime("plot(strategy.wintrades)\n")
    assert rt.run_bar(bar("100")).intent.plots["plot_1"] == 0


# --- strategy.close takes an entry id ----------------------------------------


CLOSE_THE_OTHER_SIDE = (
    "if close > open\n"
    "    strategy.close('Short')\n"
    "    strategy.entry('Long', strategy.long)\n"
)


def test_closing_an_id_nothing_is_holding_does_nothing():
    """The ubiquitous "close the other side, then enter" pair.

    On TradingView `strategy.close("Short")` while long is a no-op. This used to
    flatten regardless, so the pair read as close-then-open every bar.
    """
    rt = runtime(CLOSE_THE_OTHER_SIDE)
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="Long")
    result = rt.run_bar(bar("110", low="90"))
    assert result.intent.desired_side is Side.LONG


def test_closing_the_id_that_is_held_still_closes():
    rt = runtime("strategy.close('Long')\n")
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="Long")
    assert rt.run_bar(bar("110")).intent.desired_side is None


def test_close_all_ignores_the_id_entirely():
    rt = runtime("strategy.close_all()\n")
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="Long")
    assert rt.run_bar(bar("110")).intent.desired_side is None


def test_a_restored_position_with_no_recorded_name_can_still_be_closed():
    """Refusing to close a real position over a missing label is the dangerous
    direction, so an unknown name matches any close."""
    rt = runtime("strategy.close('Long')\n")
    rt.sync_position(size_sign=1, avg_price=D("100"))
    assert rt.run_bar(bar("110")).intent.desired_side is None


# --- drawings ----------------------------------------------------------------


def test_a_drawing_constructor_returns_a_handle_not_na():
    """`if na(myLine)` decides create-or-move; `na` would create every bar."""
    rt = runtime(
        "var line l = na\n"
        "created = 0\n"
        "if na(l)\n"
        "    l := line.new(bar_index, high, bar_index, low)\n"
        "    created := 1\n"
        "plot(created)\n"
    )
    first = rt.run_bar(bar("100", time=0))
    second = rt.run_bar(bar("101", time=3600))
    assert first.intent.plots["plot_1"] == 1
    assert second.intent.plots["plot_1"] == 0


def test_a_drawing_setter_is_a_no_op_and_does_not_raise():
    rt = runtime(
        "var label t = na\n"
        "t := label.new(bar_index, high, 'x')\n"
        "label.set_text(t, 'y')\n"
        "label.delete(t)\n"
        "plot(close)\n"
    )
    assert rt.run_bar(bar("100")).intent.plots


def test_a_remembered_entry_name_cannot_veto_a_close_of_the_other_side():
    """The name is this runtime's memory of a call *it* made.

    A driver that reports the opposite position has proved that memory stale, so
    it is dropped — a name kept past that point would refuse to close a real
    position, which is the dangerous direction.
    """
    rt = runtime("strategy.close('Short')\n")
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="Long")
    rt.run_bar(bar("100", time=0))
    # The venue flipped underneath: the platform now holds a short.
    rt.sync_position(size_sign=-1, avg_price=D("100"))
    assert rt.run_bar(bar("100", time=3600)).intent.desired_side is None


def test_going_flat_forgets_who_entered():
    rt = runtime("strategy.close('Long')\n")
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="Long")
    rt.run_bar(bar("100", time=0))
    rt.sync_position(size_sign=0)
    assert rt.ctx.position_entry_name == ""


def test_a_keyword_is_a_legal_member_name():
    """`syminfo.type` — nothing after a dot can start a statement.

    Refusing it made a perfectly ordinary built-in a syntax error pointing at
    the dot, which is the least useful place it could point.
    """
    rt = info_runtime("plot(1, syminfo.type)\n")
    assert "crypto" in rt.run_bar(bar("100")).intent.plots


def test_time_close_is_the_bars_open_plus_one_interval():
    """The interval is a fact about the bot, not about the bar.

    Deriving it from the gap to the previous bar would read a *missing* bar as
    a longer timeframe.
    """
    rt = info_runtime("plot(time_close - time, 'span')\n", interval="4h")
    assert rt.run_bar(bar("100", time=0)).intent.plots["span"] == 4 * 3600


def test_timeframe_in_seconds_answers_for_the_bot_and_for_a_named_interval():
    rt = info_runtime("plot(timeframe.in_seconds(), 'own')\n", interval="15m")
    assert rt.run_bar(bar("100")).intent.plots["own"] == 900


def test_a_dashboard_figure_that_is_not_a_number_defaults_to_a_string():
    """Everything else defaults to zero; a currency code is not a number."""
    rt = runtime("plot(1, 'ccy:' + strategy.account_currency)\n")
    assert "ccy:" in rt.run_bar(bar("100")).intent.plots
    rt.sync_position(size_sign=0, performance={"account_currency": "USDT"})
    assert "ccy:USDT" in rt.run_bar(bar("101", time=3600)).intent.plots


# --- the scale-out (Q33) ----------------------------------------------------


def test_a_partial_close_leaves_the_position_open_and_reports_what_survived():
    rt = runtime('strategy.close("L", qty_percent=40)\n')
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L")
    intent = run(rt, ["10"])[-1].intent
    assert intent.desired_side is Side.LONG
    assert intent.position_fraction == D("0.6")


def test_the_levels_compound_the_way_tradingview_compounds_them():
    """`qty_percent` is a share of what is *still* held, not of the entry — so
    40/30/30 leaves 29.4% running, not zero. That is what the script does on
    TradingView, and a runner nobody expected is worse than an odd number."""
    rt = runtime(
        'if bar_index == 1\n'
        '    strategy.close("L", qty_percent=40)\n'
        'if bar_index == 2\n'
        '    strategy.close("L", qty_percent=30)\n'
        'if bar_index == 3\n'
        '    strategy.close("L", qty_percent=30)\n'
    )
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L")
    fractions = []
    for index, close in enumerate(["10", "10", "10", "10"]):
        result = rt.run_bar(bar(close, time=index * 900))
        fractions.append(result.intent.position_fraction)
        rt.sync_position(
            size_sign=1, avg_price=D("100"), entry_name="L",
            fraction=result.intent.position_fraction,
        )
    assert fractions == [D("1"), D("0.6"), D("0.42"), D("0.294")]


def test_a_whole_close_after_a_scale_out_still_reads_flat():
    rt = runtime(
        'if bar_index == 1\n'
        '    strategy.close("L", qty_percent=40)\n'
        'if bar_index == 2\n'
        '    strategy.close("L")\n'
    )
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L")
    rt.run_bar(bar("10", time=0))
    rt.run_bar(bar("10", time=900))
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L", fraction=D("0.6"))
    intent = rt.run_bar(bar("10", time=1800)).intent
    assert intent.desired_side is None
    assert intent.position_fraction == D("1")


def test_a_new_entry_is_a_whole_position_again():
    rt = runtime(
        'if bar_index == 0\n'
        '    strategy.close("L", qty_percent=40)\n'
        'if bar_index == 1\n'
        '    strategy.entry("S", strategy.short)\n'
    )
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L")
    rt.run_bar(bar("10", time=0))
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L", fraction=D("0.6"))
    intent = rt.run_bar(bar("10", time=900)).intent
    assert intent.desired_side is Side.SHORT
    assert intent.position_fraction == D("1")


def test_closing_a_percent_of_an_id_nothing_holds_does_nothing():
    rt = runtime('strategy.close("S", qty_percent=40)\n')
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L")
    intent = run(rt, ["10"])[-1].intent
    assert intent.desired_side is Side.LONG
    assert intent.position_fraction == D("1")


def test_a_computed_percent_out_of_range_stops_the_bar_rather_than_clamping():
    rt = runtime("pct = close * 20\nstrategy.close(\"L\", qty_percent=pct)\n")
    rt.sync_position(size_sign=1, avg_price=D("100"), entry_name="L")
    with pytest.raises(PineRuntimeError) as exc:
        run(rt, ["10"])
    assert exc.value.code == "bad_close_percent"


def test_a_flat_position_resets_the_fraction():
    """Otherwise a fresh entry opens already 40% taken."""
    rt = runtime("plot(close)\n")
    rt.ctx.position_fraction = D("0.6")
    rt.sync_position(size_sign=0)
    assert rt.run_bar(bar("10")).intent.position_fraction == D("1")
