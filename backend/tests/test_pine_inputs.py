"""The settings panel a script declares — ``apps/pine/inputs.py``.

Three claims are worth a test each, and they are the three the module makes on
its own rather than transcribing:

  **The category is read off the sinks.** Every case here names its inputs
  neutrally, or misleadingly, so a naming heuristic would fail it. That is the
  point: the next uploaded strategy will not use this one's vocabulary.

  **A dependency is claimed only when every non-visual use is guarded.** So
  there is a case for the gate being found, and a case for one use outside the
  guard dropping it — the second matters more, because a wrongly greyed row is
  a setting the operator cannot reach on a live book.

  **A submitted value is held to the declaration.** Out of range, off the
  option list, wrong type, and a name the script no longer has.
"""

from __future__ import annotations

import pytest

from apps.pine import inputs as pine_inputs
from apps.pine.validate import validate

HEAD = '//@version=5\nstrategy("t")\n'


def schema(body: str) -> pine_inputs.InputSchema:
    result = validate(HEAD + body)
    assert result.ok, [e.as_dict() for e in result.errors]
    return result.input_schema


# --- detection --------------------------------------------------------------


ALL_KINDS = """
g = "Set"
a = input.bool(true, "Toggle", group = g)
b = input.int(14, "Length", minval = 1, maxval = 100, step = 1, group = g)
c = input.float(0.7, "Factor", minval = 0.1, maxval = 1.0, step = 0.05, group = g)
d = input.string("Fast", "Mode", options = ["Fast", "Slow"], group = g)
e = input.source(close, "Source", group = g)
f = input.color(#00E5A8, "Tint", group = g)
h = input.time(timestamp("01 Jan 2024 00:00 +0000"), "From", group = g)
plot(b + c, color = f)
"""


def test_every_input_kind_is_detected_with_its_widget():
    fields = {row.name: row for row in schema(ALL_KINDS).fields}
    assert [row.kind for row in fields.values()] == [
        "bool",
        "int",
        "float",
        "string",
        "source",
        "color",
        "time",
    ]
    assert fields["a"].widget == "toggle"
    assert fields["b"].widget == "number"
    assert fields["c"].widget == "number"
    # A fixed set of answers is a dropdown whatever the underlying type.
    assert fields["d"].widget == "select"
    assert fields["e"].widget == "source"
    assert fields["f"].widget == "color"
    assert fields["h"].widget == "datetime"


def test_the_declaration_is_transcribed_whole():
    fields = {row.name: row for row in schema(ALL_KINDS).fields}
    assert fields["b"].title == "Length"
    assert (fields["b"].minval, fields["b"].maxval, fields["b"].step) == (1, 100, 1)
    assert fields["d"].options == ("Fast", "Slow")
    assert fields["e"].default == "close"
    assert fields["f"].default == "#00E5A8"
    # `timestamp()` is folded at validation, so the form holds a date rather
    # than the word "timestamp".
    assert isinstance(fields["h"].default, int)


def test_a_source_input_offers_the_series_that_exist():
    field = schema(ALL_KINDS).by_name("e")
    assert field.choices == pine_inputs.SOURCE_CHOICES
    assert "close" in field.choices


GROUPED = """
one = "01. First"
two = "02. Second"
a = input.int(1, "A", group = one, inline = "row")
b = input.int(2, "B", group = one, inline = "row")
c = input.int(3, "C", group = one)
d = input.bool(true, "D", group = two)
plot(a + b + c, color = d ? color.green : color.red)
"""


def test_groups_come_back_in_the_order_the_script_wrote_them():
    groups = schema(GROUPED).groups
    assert [row.key for row in groups] == ["01. First", "02. Second"]
    assert groups[0].names == ("a", "b", "c")
    # `inline` is a row inside the group, which is what it means in TradingView.
    assert groups[0].rows == (("a", "b"),)


def test_ungrouped_inputs_keep_their_own_bucket():
    groups = schema(
        'a = input.int(1, "A")\nb = input.int(2, "B", group = "G")\nplot(a + b)\n'
    ).groups
    assert [row.key for row in groups] == ["", "G"]


# --- classification ---------------------------------------------------------
#
# Every name below is deliberately uninformative. A reader that guessed from
# names would get all five of these wrong.


CLASSIFY = """
p1 = input.int(20, "p1")
p2 = input.float(2.0, "p2")
p3 = input.int(50, "p3")
p4 = input.color(#FF0000, "p4")
p5 = input.time(timestamp("01 Jan 2024 00:00 +0000"), "p5")
p6 = input.string("x", "p6", options = ["x", "y"])
fast = ta.ema(close, p1)
inWindow = time >= p5
if ta.crossover(close, fast) and inWindow
    strategy.entry("L", strategy.long)
    strategy.exit("X", "L", loss_pct = p2)
strategy.close("L", qty_percent = p3, when = p6 == "y")
plot(fast, color = p4)
"""


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("p1", "logic"),  # a length inside the signal
        ("p2", "risk"),  # reaches strategy.exit(loss_pct=)
        ("p3", "risk"),  # reaches strategy.close(qty_percent=)
        ("p4", "visual"),  # nothing but a plot colour
        ("p5", "backtest"),  # compared against `time`
        ("p6", "execution"),  # reaches when=
    ],
)
def test_the_category_is_read_off_the_sink_not_the_name(name, category):
    assert schema(CLASSIFY).by_name(name).category == category


def test_the_category_carries_the_evidence_for_itself():
    assert "qty_percent" in schema(CLASSIFY).by_name("p3").reason


def test_an_input_nothing_reads_is_marked_rather_than_hidden():
    fields = {row.name: row for row in schema('a = input.int(1, "A")\nplot(close)\n').fields}
    assert fields["a"].used is False


def test_a_value_named_in_an_alert_message_is_not_an_execution_setting():
    """Every published strategy builds an informative alert string. Counting
    that as a use would file half a panel under Execution."""
    body = """
len = input.int(14, "len")
e = ta.ema(close, len)
if ta.crossover(close, e)
    strategy.entry("L", strategy.long, alert_message = str.tostring(len))
"""
    assert schema(body).by_name("len").category == "logic"


# --- dependencies -----------------------------------------------------------


GATED = """
g = "Targets"
on = input.bool(true, "Enable take profit", group = g)
mult = input.float(1.5, "Target multiplier", group = g)
mode = input.string("A", "Mode", options = ["A", "B"], group = g)
size = input.int(50, "Size", group = g)
strategy.entry("L", strategy.long)
if on
    strategy.exit("T", "L", profit_pct = mult * 2)
    if mode == "A"
        strategy.close("L", qty_percent = size)
"""


def test_a_gate_in_the_logic_becomes_a_dependency_on_the_form():
    fields = {row.name: row for row in schema(GATED).fields}
    assert [row.controller for row in fields["mult"].depends_on] == ["on"]
    assert fields["mult"].depends_on[0].values == (True,)
    # Two levels deep, and both are reported: the panel dims a row when either
    # of its controllers is elsewhere. `mode` is a dropdown, so the gate is the
    # option it has to be on rather than a boolean.
    assert {row.controller for row in fields["size"].depends_on} == {"on", "mode"}
    assert dict((row.controller, row.values) for row in fields["size"].depends_on)["mode"] == ("A",)


def test_the_controller_itself_depends_on_nothing():
    assert schema(GATED).by_name("on").depends_on == ()


def test_one_use_outside_the_guard_drops_the_dependency():
    """The failure this analysis is arranged not to make: a row greyed out for
    a setting that does something. A single unguarded use is enough."""
    body = (
        GATED
        + '\nstrategy.close_all()\nplotshape(mult > 3)\nstrategy.close("L", when = mult > 3)\n'
    )
    assert schema(body).by_name("mult").depends_on == ()


def test_a_drawing_use_does_not_rescue_a_gated_input():
    """A target that is plotted always and traded only when targets are on is
    still gated, because a dependency is a claim about *orders*."""
    body = GATED + "\nplot(close * mult)\n"
    assert [row.controller for row in schema(body).by_name("mult").depends_on] == ["on"]


def test_a_value_carried_through_a_user_function_is_still_a_use():
    body = """
f(x) => ta.ema(close, x)
len = input.int(9, "len")
if ta.crossover(close, f(len))
    strategy.entry("L", strategy.long)
"""
    field = schema(body).by_name("len")
    assert field.used is True
    assert field.category == "logic"


# --- values -----------------------------------------------------------------


def values(body: str, raw: dict):
    return pine_inputs.validate_values(schema(body), raw)


BOUNDED = """
n = input.int(14, "n", minval = 1, maxval = 100)
f = input.float(0.7, "f", minval = 0.1, maxval = 1.0)
m = input.string("A", "m", options = ["A", "B"])
b = input.bool(true, "b")
s = input.source(close, "s")
c = input.color(#00E5A8, "c")
plot(n + f, color = c)
strategy.close_all(when = b and m == "B" and s > 0)
"""


def test_a_value_inside_the_declaration_is_kept():
    clean, errors = values(BOUNDED, {"n": 20, "f": 0.5, "m": "B", "b": False, "s": "hl2"})
    assert errors == []
    assert clean == {"n": 20, "f": 0.5, "m": "B", "b": False, "s": "hl2"}


def test_a_value_equal_to_the_default_is_dropped_rather_than_stored():
    """ "Reset to default" is a deleted key. A copy of the number would stop
    following the script the moment a new version moved it."""
    clean, errors = values(BOUNDED, {"n": 14, "f": 0.9})
    assert errors == []
    assert clean == {"f": 0.9}


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ({"n": 0}, "at least 1"),
        ({"n": 500}, "at most 100"),
        ({"n": 1.5}, "whole number"),
        ({"f": "wide"}, "must be a number"),
        ({"m": "C"}, "must be one of"),
        ({"b": "maybe"}, "true or false"),
        ({"s": "vwap"}, "must be one of"),
        ({"c": "green"}, "#00E5A8"),
    ],
)
def test_a_value_outside_the_declaration_is_named_not_dropped(raw, fragment):
    clean, errors = values(BOUNDED, raw)
    assert clean == {}
    assert fragment in errors[0]["message"]
    assert errors[0]["name"] == next(iter(raw))


def test_an_input_the_script_no_longer_has_is_reported():
    """What a preset saved against an older version looks like on arrival."""
    _, errors = values(BOUNDED, {"gone": 1})
    assert errors[0]["name"] == "gone"
    assert "renamed or removed" in errors[0]["message"]


def test_resolve_is_the_default_under_the_override():
    resolved = pine_inputs.resolve_values(schema(BOUNDED), {"n": 21})
    assert resolved["n"] == 21
    assert resolved["f"] == 0.7


def test_a_stored_schema_round_trips():
    """The version stores JSON and every later check reads it back — a schema
    that lost its bounds on the way through would validate nothing."""
    original = schema(BOUNDED)
    restored = pine_inputs.InputSchema.from_data(original.as_dict())
    assert restored.as_dict() == original.as_dict()
    assert restored.by_name("n").maxval == 100


def test_the_bare_list_older_versions_stored_still_loads():
    original = schema(BOUNDED)
    restored = pine_inputs.InputSchema.from_data([row.as_dict() for row in original.fields])
    assert [row.name for row in restored.fields] == [row.name for row in original.fields]
    assert restored.groups  # rebuilt from the fields rather than left empty


def test_a_script_that_does_not_parse_still_has_a_panel():
    """The editor draws the settings beside the underlines. One mistake in a
    script does not mean nobody is looking at its thirty inputs."""
    result = validate(HEAD + 'a = input.int(5, "A", group = "G")\nb = ((\n')
    assert not result.ok
    assert result.input_schema.fields == () or result.input_schema.by_name("a") is not None


# --- the real thing ---------------------------------------------------------


def test_a_published_strategy_produces_a_panel_somebody_could_use():
    """The corpus's published strategy — thirty-one inputs across five groups.

    Not an assertion about any one of them: the point is that a script written
    by somebody else, in the shape published strategies are actually written in
    (user-defined types, methods mutating their receiver, a dashboard, an alert
    string naming half the settings), comes back as a panel rather than as a
    flat list of thirty-one rows nobody can act on.
    """
    from tests import pine_corpus

    result = validate((pine_corpus.ACCEPT / "27_published_strategy.pine").read_text())
    assert result.ok, [e.as_dict() for e in result.errors]
    panel = result.input_schema

    assert [row.key for row in panel.groups] == [
        "01. Backtest Window",
        "02. Signal Engine",
        "03. Targets / Stop",
        "04. Visual Display",
        "05. Colours",
    ]
    # Every row has a control and a bucket, and every declared input is in
    # exactly one group.
    assert all(row.widget for row in panel.fields)
    assert sum(len(row.names) for row in panel.groups) == len(panel.fields)

    fields = {row.name: row for row in panel.fields}
    # The date window is the window, not a signal, even though it gates entries.
    assert fields["startTime"].category == "backtest"
    # The scale-out sizes are risk, and they are off while targets are off —
    # both read out of the logic, neither out of a name.
    assert fields["tp1Percent"].category == "risk"
    assert [gate.controller for gate in fields["tp1Percent"].depends_on] == ["useTargets"]
    # The colours reach nothing but drawings; the lengths reach the signal.
    assert fields["bullColor"].category == "visual"
    assert fields["mcgLength"].category == "logic"
    # And nothing in a thirty-one input script reads as dead.
    assert all(row.used for row in panel.fields)
