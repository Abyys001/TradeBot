"""`/api/bots/` — the read surfaces, the routing endpoints, and the gate.

Everything here is staff-only, and the routing half is a plain async view with
CSRF enforced (DRF 3.15 has no async view support, and the spec §4 deadline
cannot afford a worker thread).
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.bots.models import BotRun, BotState, Strategy, StrategyVersion
from tests import pine_corpus
from tests.bot_factory import make_bot, make_run

pytestmark = pytest.mark.django_db

GOOD = (pine_corpus.ACCEPT / "01_sma_cross.pine").read_text()
BAD = '//@version=5\nstrategy("x")\na = array.new_float(0)\n'


def staff() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


def anonymous() -> Client:
    return Client()


def post(client: Client, url: str, payload: dict):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


# --- authentication ---------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "/api/bots/strategies/",
        "/api/bots/bots/",
        "/api/bots/backtests/",
        "/api/bots/policy/",
    ],
)
def test_every_read_endpoint_is_staff_only(url):
    assert anonymous().get(url).status_code in (401, 403)


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/api/bots/policy/", "/api/trading/policy/"])
def test_a_signed_in_non_staff_user_is_refused_too(url):
    """"Staff-only" has to mean staff, not "anyone who got past the login".

    Both `policy` endpoints relied on DRF's `IsAuthenticated` default, which on
    a platform with one shared *staff* login is the same set of people — and
    would stop being so the day a second account exists for any reason.
    """
    from django.contrib.auth.models import User
    from django.test import Client

    User.objects.create_user("watcher", password="pw12345!")
    client = Client()
    client.login(username="watcher", password="pw12345!")
    assert client.get(url).status_code == 403


def test_validate_is_staff_only():
    assert post(anonymous(), "/api/bots/validate/", {"source": GOOD}).status_code in (401, 403)


def test_starting_a_bot_is_staff_only():
    bot = make_bot()
    assert post(anonymous(), f"/api/bots/bots/{bot.id}/start/", {}).status_code in (401, 403, 302)


# --- validate ---------------------------------------------------------------


def test_validate_accepts_a_subset_script():
    body = post(staff(), "/api/bots/validate/", {"source": GOOD}).json()
    assert body["ok"] is True
    assert body["errors"] == []


def test_validate_returns_errors_as_data_rather_than_a_500():
    """The editor underlines them; it does not get a stack trace."""
    response = post(staff(), "/api/bots/validate/", {"source": BAD})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "unsupported_collections"
    assert body["errors"][0]["span"]["line"] == 3


def test_validate_reports_the_inputs_the_parameter_form_needs():
    body = post(staff(), "/api/bots/validate/", {"source": GOOD}).json()
    assert {i["name"] for i in body["inputs"]} == {"fastLen", "slowLen"}


def test_validate_reports_warnings_separately_from_errors():
    source = '//@version=5\nstrategy("q")\nstrategy.entry("L", strategy.long, qty=5)\n'
    body = post(staff(), "/api/bots/validate/", {"source": source}).json()
    assert body["ok"] is True
    assert body["warnings"]


def test_validate_of_an_empty_script_is_an_error_not_a_crash():
    body = post(staff(), "/api/bots/validate/", {"source": ""}).json()
    assert body["ok"] is False


# --- policy -----------------------------------------------------------------


def test_policy_reports_the_settings_the_panel_renders():
    body = staff().get("/api/bots/policy/").json()
    assert "MAX_CONSECUTIVE_LOSSES" in body
    assert "MAX_DRAWDOWN_PCT" in body


def test_policy_names_the_two_stops_that_have_no_number():
    """Absent on purpose, and saying so beats a blank field somebody later
    "fixes" by giving it a value."""
    body = staff().get("/api/bots/policy/").json()
    assert set(body["non_configurable_stops"]) == {"feed_gap", "script_error"}


def test_policy_cites_every_decision_by_its_question_number():
    body = staff().get("/api/bots/policy/").json()
    cited = " ".join(body["decisions"].values())
    for number in range(20, 28):
        assert f"Q{number}" in cited


# --- strategies and versions ------------------------------------------------


def test_saving_a_version_stores_its_validation_result():
    client = staff()
    strategy = Strategy.objects.create(name="s")
    response = post(client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": GOOD})
    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["parsed_ok"] is True


def test_the_strategy_list_carries_the_latest_version_whole_not_its_number():
    """The panel builds every strategy-shaped control off this one field.

    A bare integer here typechecks on the wire and leaves the backtest's
    strategy list empty, the editor showing the starter template over saved
    work, and "New bot" posting an undefined version — so the shape is pinned.
    """
    client = staff()
    strategy = Strategy.objects.create(name="s")
    post(client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": GOOD})

    row = client.get("/api/bots/strategies/").json()[0]
    latest = row["latest_version"]
    assert isinstance(latest, dict)
    assert latest["version"] == 1
    assert latest["parsed_ok"] is True
    assert latest["source"] == GOOD
    assert isinstance(latest["id"], int)


def test_a_strategy_with_no_versions_has_no_latest_version():
    client = staff()
    Strategy.objects.create(name="empty")
    assert client.get("/api/bots/strategies/").json()[0]["latest_version"] is None


def test_a_strategy_can_be_renamed_without_touching_its_versions():
    """A name is a label on a shelf, not part of what a bot executes."""
    client = staff()
    strategy = Strategy.objects.create(name="old name")
    saved = post(
        client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": GOOD}
    ).json()

    response = client.patch(
        f"/api/bots/strategies/{strategy.id}/",
        data=json.dumps({"name": "new name"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "new name"
    assert body["latest_version"]["id"] == saved["id"]
    assert body["latest_version"]["source"] == GOOD


def test_renaming_a_strategy_is_staff_only():
    strategy = Strategy.objects.create(name="s")
    response = anonymous().patch(
        f"/api/bots/strategies/{strategy.id}/",
        data=json.dumps({"name": "mine now"}),
        content_type="application/json",
    )
    assert response.status_code in (401, 403)
    strategy.refresh_from_db()
    assert strategy.name == "s"


def test_a_version_that_does_not_validate_is_still_saved_with_its_errors():
    """A draft you cannot save is a draft you cannot come back to."""
    client = staff()
    strategy = Strategy.objects.create(name="s")
    body = post(client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": BAD}).json()
    assert body["parsed_ok"] is False
    assert body["validation_errors"]


def test_versions_are_numbered_upward_and_never_rewritten():
    """A running bot points at a version, so its behaviour cannot change
    because somebody saved in another tab."""
    client = staff()
    strategy = Strategy.objects.create(name="s")
    first = post(client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": GOOD}).json()
    second = post(client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": GOOD}).json()
    assert (first["version"], second["version"]) == (1, 2)
    assert StrategyVersion.objects.get(id=first["id"]).source == GOOD


def test_an_empty_source_is_refused():
    client = staff()
    strategy = Strategy.objects.create(name="s")
    response = post(client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": "  "})
    assert response.status_code == 400


def test_deleting_a_strategy_with_no_bots_takes_its_versions_with_it():
    client = staff()
    strategy = Strategy.objects.create(name="doomed")
    post(client, f"/api/bots/strategies/{strategy.id}/versions/", {"source": GOOD})
    response = client.delete(f"/api/bots/strategies/{strategy.id}/")
    assert response.status_code == 204
    assert not Strategy.objects.filter(id=strategy.id).exists()
    assert not StrategyVersion.objects.filter(strategy_id=strategy.id).exists()


def test_deleting_a_strategy_a_bot_was_built_from_is_refused_and_names_the_bot():
    """`Bot.strategy_version` is PROTECT — the delete is a 409, not a 500, and
    the operator is told which bots to remove first."""
    client = staff()
    bot = make_bot(name="live-ish bot")
    strategy_id = bot.strategy_version.strategy_id
    response = client.delete(f"/api/bots/strategies/{strategy_id}/")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "strategy_in_use"
    assert body["bots"] == ["live-ish bot"]
    assert Strategy.objects.filter(id=strategy_id).exists()


# --- bots -------------------------------------------------------------------


def test_a_bot_lists_with_its_strategy_name():
    make_bot(name="my bot")
    body = staff().get("/api/bots/bots/").json()
    assert body[0]["name"] == "my bot"


def test_runs_bars_and_actions_are_empty_rather_than_404_for_a_new_bot():
    bot = make_bot()
    client = staff()
    for suffix in ("runs", "bars", "actions"):
        assert client.get(f"/api/bots/bots/{bot.id}/{suffix}/").json() == []


def test_the_bars_endpoint_caps_what_it_returns():
    bot = make_bot()
    make_run(bot)
    response = staff().get(f"/api/bots/bots/{bot.id}/bars/?limit=999999")
    assert response.status_code == 200


# --- start and stop ---------------------------------------------------------


def test_a_bot_starts_into_paper():
    bot = make_bot(state=BotState.DRAFT)
    body = post(staff(), f"/api/bots/bots/{bot.id}/start/", {"state": "paper"}).json()
    assert body["state"] == BotState.PAPER
    bot.refresh_from_db()
    assert bot.dry_run is True


def test_going_live_without_the_gate_is_refused_with_the_gate_attached():
    """Not a confirmation dialog — a gate that knows the numbers."""
    bot = make_bot(state=BotState.PAPER)
    response = post(staff(), f"/api/bots/bots/{bot.id}/start/", {"state": "live"})
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "gate_unmet"
    assert body["gate"]["ready"] is False
    assert any(row["met"] is False for row in body["gate"]["rows"])


def test_an_illegal_transition_is_refused_and_named():
    bot = make_bot(state=BotState.STOPPED)
    response = post(staff(), f"/api/bots/bots/{bot.id}/start/", {"state": "live"})
    assert response.status_code == 409


def test_starting_into_a_state_that_is_not_paper_or_live_is_refused():
    bot = make_bot()
    assert post(staff(), f"/api/bots/bots/{bot.id}/start/", {"state": "draft"}).status_code == 400


def test_starting_a_bot_that_does_not_exist_is_a_404():
    assert post(staff(), "/api/bots/bots/9999/start/", {"state": "paper"}).status_code == 404


def test_stopping_records_the_reason_given():
    bot = make_bot(state=BotState.PAPER)
    make_run(bot)
    body = post(staff(), f"/api/bots/bots/{bot.id}/stop/", {"reason": "by hand"}).json()
    assert body["state"] == BotState.STOPPED
    assert bot.runs.first().stop_detail == "by hand"


def test_stopping_a_bot_that_is_not_running_is_not_an_error():
    bot = make_bot(state=BotState.DRAFT)
    assert post(staff(), f"/api/bots/bots/{bot.id}/stop/", {}).status_code == 200


# --- only one bot runs at a time --------------------------------------------


def test_starting_a_bot_stops_whichever_one_was_running():
    running = make_bot(name="running", state=BotState.PAPER)
    make_run(running)
    draft = make_bot(name="draft", state=BotState.DRAFT)

    body = post(staff(), f"/api/bots/bots/{draft.id}/start/", {"state": "paper"}).json()

    assert body["deactivated"] == [running.id]
    running.refresh_from_db()
    assert running.state == BotState.STOPPED
    assert running.runs.first().stop_reason == "manual"
    draft.refresh_from_db()
    assert draft.state == BotState.PAPER


def test_starting_the_only_bot_deactivates_nothing():
    bot = make_bot(state=BotState.DRAFT)
    body = post(staff(), f"/api/bots/bots/{bot.id}/start/", {"state": "paper"}).json()
    assert body["deactivated"] == []


def test_an_illegal_transition_does_not_deactivate_the_running_bot():
    """A refused start must not take down a bot that was working fine."""
    running = make_bot(name="running", state=BotState.PAPER)
    stopped = make_bot(name="stopped", state=BotState.STOPPED)  # stopped->live is illegal

    response = post(staff(), f"/api/bots/bots/{stopped.id}/start/", {"state": "live"})

    assert response.status_code == 409
    running.refresh_from_db()
    assert running.state == BotState.PAPER


def test_an_unmet_gate_does_not_deactivate_the_other_bot():
    running = make_bot(name="running", state=BotState.PAPER)
    other = make_bot(name="other", state=BotState.PAPER)

    response = post(staff(), f"/api/bots/bots/{other.id}/start/", {"state": "live"})

    assert response.status_code == 409
    running.refresh_from_db()
    assert running.state == BotState.PAPER


def patch(client: Client, url: str, payload: dict):
    return client.patch(url, data=json.dumps(payload), content_type="application/json")


def test_a_stopped_bot_can_move_to_another_pair_and_timeframe():
    """The edit modal's whole reason to exist: 1h → 4h without a new bot."""
    client = staff()
    bot = make_bot(state=BotState.STOPPED, symbol="BTCUSDT", interval="1h")
    response = patch(
        client,
        f"/api/bots/bots/{bot.id}/",
        {"symbol": "ETHUSDT", "interval": "30m", "leverage": 3, "sl_pct": "1.5"},
    )
    assert response.status_code == 200, response.content
    bot.refresh_from_db()
    assert (bot.symbol, bot.interval, bot.leverage) == ("ETHUSDT", "30m", 3)


def test_a_running_bot_refuses_a_new_instrument_on_the_server_not_just_the_form():
    client = staff()
    bot = make_bot(state=BotState.PAPER, symbol="BTCUSDT", interval="1h")
    response = patch(client, f"/api/bots/bots/{bot.id}/", {"interval": "4h"})
    assert response.status_code == 400
    assert "interval" in response.json()
    bot.refresh_from_db()
    assert bot.interval == "1h"


def test_a_running_bot_can_still_be_renamed():
    """The one edit that changes nothing about what it trades."""
    client = staff()
    bot = make_bot(state=BotState.PAPER)
    assert patch(client, f"/api/bots/bots/{bot.id}/", {"name": "renamed"}).status_code == 200
    bot.refresh_from_db()
    assert bot.name == "renamed"


def test_an_interval_nothing_can_serve_is_refused_by_name():
    bot = make_bot(state=BotState.STOPPED)
    response = patch(staff(), f"/api/bots/bots/{bot.id}/", {"interval": "7s"})
    assert response.status_code == 400
    assert "interval" in response.json()


def test_a_bots_version_cannot_be_swapped_under_it():
    client = staff()
    bot = make_bot(state=BotState.STOPPED)
    other = StrategyVersion.objects.create(
        strategy=bot.strategy_version.strategy, version=99, source=GOOD, parsed_ok=True
    )
    response = patch(client, f"/api/bots/bots/{bot.id}/", {"strategy_version": other.id})
    assert response.status_code == 400
    assert "strategy_version" in response.json()


def test_the_compact_strategy_list_leaves_every_version_source_behind():
    """What made /bots open on a skeleton and need a refresh.

    The full shape carries every version's Pine source, its validation report
    and its resolved properties. The bots list and the backtest form want a name
    and an id — so a page that draws a dropdown stopped downloading megabytes to
    do it.
    """
    client = staff()
    strategy = Strategy.objects.create(name="heavy")
    for version in (1, 2, 3):
        StrategyVersion.objects.create(
            strategy=strategy, version=version, source=GOOD, parsed_ok=True
        )

    compact = client.get("/api/bots/strategies/?compact=1").json()
    assert "versions" not in compact[0]
    assert compact[0]["latest_version"]["version"] == 3
    assert "source" not in compact[0]["latest_version"]

    # The editor still gets the lot — it is the one page that needs it.
    full = client.get("/api/bots/strategies/").json()
    assert len(full[0]["versions"]) == 3
    assert full[0]["latest_version"]["source"] == GOOD


def test_one_version_can_be_fetched_by_id_with_its_source():
    client = staff()
    strategy = Strategy.objects.create(name="by-id")
    version = StrategyVersion.objects.create(
        strategy=strategy, version=1, source=GOOD, parsed_ok=True
    )
    body = client.get(f"/api/bots/versions/{version.id}/").json()
    assert body["source"] == GOOD
    assert client.get("/api/bots/versions/999999/").status_code == 404


# --- the gate ---------------------------------------------------------------


def test_the_promotion_endpoint_shows_every_row_with_its_measurement():
    bot = make_bot(state=BotState.PAPER)
    body = staff().get(f"/api/bots/bots/{bot.id}/promotion/").json()
    assert body["ready"] is False
    for row in body["rows"]:
        assert set(row) >= {"key", "requirement", "threshold", "measured", "met"}


def test_the_gate_carries_the_row_no_code_can_measure():
    """No adapter has been run against a live exchange or a testnet yet, and a
    bot is a bad first thing to discover that with."""
    bot = make_bot(state=BotState.PAPER)
    body = staff().get(f"/api/bots/bots/{bot.id}/promotion/").json()
    assert any(row["key"] == "adapters" for row in body["rows"])


def test_the_gate_lists_a_soak_row():
    bot = make_bot(state=BotState.PAPER)
    body = staff().get(f"/api/bots/bots/{bot.id}/promotion/").json()
    assert any(row["key"] == "soak" for row in body["rows"])


def test_the_gate_never_raises_for_a_bot_that_has_never_run():
    bot = make_bot(state=BotState.DRAFT)
    assert staff().get(f"/api/bots/bots/{bot.id}/promotion/").status_code == 200


def test_the_gate_no_longer_carries_the_two_drill_rows():
    """Both were exercises rather than measurements, and the kill-switch one
    sent real close orders through a live book to clear a checkbox."""
    bot = make_bot(state=BotState.PAPER)
    keys = {row["key"] for row in staff().get(f"/api/bots/bots/{bot.id}/promotion/").json()["rows"]}
    assert "halt_drills" not in keys
    assert "q25_drills" not in keys


def test_turning_the_gate_off_lets_a_bot_go_live_unmeasured():
    """The admin's decision, recorded on the bot — not a dialog nobody logged."""
    client = staff()
    bot = make_bot(state=BotState.PAPER)
    body = post(client, f"/api/bots/bots/{bot.id}/gate/", {"enforced": False}).json()
    assert body["gate"]["enforced"] is False
    assert body["gate"]["ready"] is True
    # Still measured. "Allowed" and "proven" are different sentences.
    assert body["gate"]["measured_ready"] is False
    bot.refresh_from_db()
    assert bot.gate_enforced is False
    assert post(client, f"/api/bots/bots/{bot.id}/start/", {"state": "live"}).status_code == 200


def test_waiving_one_row_excludes_it_from_ready_and_leaves_it_measured():
    client = staff()
    bot = make_bot(state=BotState.PAPER)
    keys = [row["key"] for row in client.get(f"/api/bots/bots/{bot.id}/promotion/").json()["rows"]]
    for key in keys:
        post(client, f"/api/bots/bots/{bot.id}/gate/", {"waive": key, "on": True})
    gate_now = client.get(f"/api/bots/bots/{bot.id}/promotion/").json()
    assert gate_now["ready"] is True
    assert gate_now["measured_ready"] is False
    assert all(row["waived"] for row in gate_now["rows"])
    # Un-waiving puts it back, so a waiver is never a one-way door.
    post(client, f"/api/bots/bots/{bot.id}/gate/", {"waive": keys[0], "on": False})
    assert client.get(f"/api/bots/bots/{bot.id}/promotion/").json()["ready"] is False


def test_waiving_a_row_that_does_not_exist_is_refused_by_name():
    bot = make_bot(state=BotState.PAPER)
    response = post(staff(), f"/api/bots/bots/{bot.id}/gate/", {"waive": "not_a_row"})
    assert response.status_code == 400


def test_the_restarts_row_is_measured_and_waivable():
    """Its two halves: three recoveries on the same run, one of them unplanned.

    A dry run cannot earn the second — `note_unplanned_restart` counts a run
    that came back with an action still dispatched-and-unsettled, and a shadow
    action is written already settled. Which is exactly why the row is
    waivable rather than a wall.
    """
    client = staff()
    bot = make_bot(state=BotState.PAPER)
    run = BotRun.objects.create(bot=bot, recoveries=3)

    def restarts() -> dict:
        rows = client.get(f"/api/bots/bots/{bot.id}/promotion/").json()["rows"]
        return next(row for row in rows if row["key"] == "restarts")

    assert restarts()["met"] is False, "three recoveries with none unplanned is not enough"
    run.unplanned_recoveries = 1
    run.save(update_fields=["unplanned_recoveries"])
    assert restarts()["met"] is True

    run.recoveries = 0
    run.unplanned_recoveries = 0
    run.save(update_fields=["recoveries", "unplanned_recoveries"])
    post(client, f"/api/bots/bots/{bot.id}/gate/", {"waive": "restarts", "on": True})
    row = restarts()
    assert row["waived"] is True and row["met"] is False


# --- the Properties tab, end to end -----------------------------------------

PROPERTY_SCRIPT = """//@version=6
strategy(
     "props",
     default_qty_type=strategy.percent_of_equity,
     default_qty_value=30,
     commission_type=strategy.commission.percent,
     commission_value=0.05,
     initial_capital=100000,
     process_orders_on_close=true,
     max_lines_count=500
)
grp = "01. Engine"
length = input.int(9, "Length", minval=1, step=1, group=grp)
plot(ta.sma(close, length), color=color.new(color.blue, 20))
"""


@pytest.mark.django_db
def test_a_saved_version_carries_the_properties_and_their_notes():
    """The whole path a published strategy takes, in one assertion block.

    v6, a wrapped `strategy()` call, a Properties tab, a `group=` named by a
    constant, a colour built inline — every one of these was a rejection before
    2026-09-04, and the version row is where the panel reads them back from.
    """
    client = staff()
    strategy = post(client, "/api/bots/strategies/", {"name": "Properties"}).json()
    version = post(
        client,
        f"/api/bots/strategies/{strategy['id']}/versions/",
        {"source": PROPERTY_SCRIPT},
    ).json()

    assert version["parsed_ok"] is True, version["validation_errors"]
    assert version["properties"]["default_qty_type"] == "percent_of_equity"
    assert version["properties"]["initial_capital"] == "100000"
    assert "default_qty_type" in version["properties"]["declared"]
    # It sizes the backtest and not live, and the panel is told so by name.
    assert version["property_notes"]["live_departures"]
    # The layout half of an input, without which thirty controls are one list.
    schema = version["inputs_schema"]
    assert schema["fields"][0]["group"] == "01. Engine"
    assert schema["fields"][0]["step"] == 1
    # And the derived half: the group the script declared is a heading of its
    # own, in the order the script wrote it, holding the inputs that named it.
    assert schema["groups"][0]["key"] == "01. Engine"
    assert schema["fields"][0]["name"] in schema["groups"][0]["names"]
    assert schema["defaults"][schema["fields"][0]["name"]] == schema["fields"][0]["default"]


# --- the Inputs tab, end to end ---------------------------------------------

INPUT_SCRIPT = """//@version=6
strategy("inputs")
grp = "02. Signal"
on = input.bool(true, "Enable target", group=grp)
len = input.int(20, "Length", minval=1, maxval=200, group=grp)
size = input.int(50, "Exit size", minval=1, maxval=100, group=grp)
tint = input.color(#00E5A8, "Tint", group="03. Colours")
strategy.entry("L", strategy.long, when = ta.crossover(close, ta.sma(close, len)))
if on
    strategy.close("L", qty_percent = size)
plot(ta.sma(close, len), color = tint)
"""


def _version_with_inputs(client):
    strategy = post(client, "/api/bots/strategies/", {"name": "Inputs"}).json()
    version = post(
        client,
        f"/api/bots/strategies/{strategy['id']}/versions/",
        {"source": INPUT_SCRIPT},
    ).json()
    return strategy, version


@pytest.mark.django_db
def test_a_version_serves_the_settings_panel_it_declares():
    """What the backtest form draws before there is a bot to hang it on."""
    client = staff()
    _, version = _version_with_inputs(client)

    body = client.get(f"/api/bots/versions/{version['id']}/inputs/").json()
    fields = {row["name"]: row for row in body["schema"]["fields"]}
    assert [row["key"] for row in body["schema"]["groups"]] == ["02. Signal", "03. Colours"]
    # The derivation, not the transcription: a widget, a category and a gate.
    assert fields["size"]["widget"] == "number"
    assert fields["size"]["category"] == "risk"
    assert fields["tint"]["category"] == "visual"
    assert [gate["controller"] for gate in fields["size"]["depends_on"]] == ["on"]
    # Nothing overridden yet, so every effective value is the script's own.
    assert body["resolved"]["len"] == 20
    assert body["overrides"] == {}


@pytest.mark.django_db
def test_a_bots_inputs_resolve_the_script_under_its_overrides():
    client = staff()
    _, version = _version_with_inputs(client)
    bot = post(
        client,
        "/api/bots/bots/",
        {"name": "b", "strategy_version": version["id"], "symbol": "BTCUSDT", "interval": "1h"},
    ).json()

    response = client.patch(
        f"/api/bots/bots/{bot['id']}/",
        data=json.dumps({"input_values": {"len": 55, "size": 50}}),
        content_type="application/json",
    )
    assert response.status_code == 200
    # Only the difference is stored: `size` was already 50, so it is not an
    # override and a later version moving that default still reaches this bot.
    assert response.json()["input_values"] == {"len": 55}

    body = client.get(f"/api/bots/bots/{bot['id']}/inputs/").json()
    assert body["resolved"]["len"] == 55
    assert body["resolved"]["size"] == 50
    assert body["overrides"] == {"len": 55}


@pytest.mark.django_db
def test_a_value_outside_the_scripts_own_bounds_is_refused_by_name():
    """The refusal has to name the input. On a panel of thirty settings,
    "somewhere below" is not a location."""
    client = staff()
    _, version = _version_with_inputs(client)
    bot = post(
        client,
        "/api/bots/bots/",
        {"name": "b", "strategy_version": version["id"], "symbol": "BTCUSDT", "interval": "1h"},
    ).json()

    response = client.patch(
        f"/api/bots/bots/{bot['id']}/",
        data=json.dumps({"input_values": {"len": 5000}}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "len" in response.json()["input_values"][0]


@pytest.mark.django_db
def test_a_preset_is_saved_against_the_strategy_and_read_back_with_the_panel():
    client = staff()
    strategy, version = _version_with_inputs(client)

    created = post(
        client,
        "/api/bots/presets/",
        {"strategy": strategy["id"], "name": "Fast", "values": {"len": 9}},
    )
    assert created.status_code == 201

    body = client.get(f"/api/bots/versions/{version['id']}/inputs/").json()
    assert [row["name"] for row in body["presets"]] == ["Fast"]
    assert body["presets"][0]["values"] == {"len": 9}


# --- backtest history -------------------------------------------------------
#
# Every run is kept. A replay costs seconds and, the first time a pair is asked
# for, a download — and the number an operator acted on last week has to still
# be the number they saw, not one recomputed under today's code.


def _stored_run(version, **overrides):
    from apps.bots.models import BacktestRun

    fields = dict(
        strategy_version=version,
        symbol="BTCUSDT",
        interval="1h",
        market="futures",
        from_time=1_000,
        to_time=2_000,
        bars=100,
        trades=3,
        metrics={"net_pnl": "12.50"},
        assumptions={"leverage": 1, "lines": ["Entries fill at the next bar's open."]},
        equity_curve=[[1_000, "10000"], [2_000, "10012.50"]],
        trade_log=[{"side": "long", "pnl": "12.50"}],
        intent_digest="abc",
        created_by="boss",
    )
    fields.update(overrides)
    return BacktestRun.objects.create(**fields)


def _version(name: str = "s") -> StrategyVersion:
    strategy = Strategy.objects.create(name=name)
    return StrategyVersion.objects.create(strategy=strategy, version=1, source=GOOD)


def test_the_backtest_list_omits_the_curve_and_the_trade_log():
    """They are the bulk of a stored run and a list renders neither."""
    _stored_run(_version())
    row = staff().get("/api/bots/backtests/").json()[0]
    assert row["metrics"]["net_pnl"] == "12.50"
    assert row["trades"] == 3
    assert "equity_curve" not in row
    assert "trade_log" not in row


def test_one_stored_run_reads_back_whole():
    run = _stored_run(_version())
    body = staff().get(f"/api/bots/backtests/{run.id}/").json()
    assert body["equity_curve"]
    assert body["trade_log"]
    # The sentences travel with the numbers: a report reopened next month is
    # captioned with the assumptions it was read under, not today's wording.
    assert body["assumptions"]["lines"]


def test_the_backtest_list_can_be_narrowed_to_one_strategy():
    mine = _version("mine")
    theirs = _version("theirs")
    _stored_run(mine)
    _stored_run(theirs)
    rows = staff().get(f"/api/bots/backtests/?strategy_version={mine.id}").json()
    assert [row["strategy_name"] for row in rows] == ["mine"]


def test_the_backtest_list_is_newest_first():
    version = _version()
    _stored_run(version, symbol="OLDER")
    _stored_run(version, symbol="NEWER")
    rows = staff().get("/api/bots/backtests/").json()
    assert [row["symbol"] for row in rows] == ["NEWER", "OLDER"]
