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

from apps.bots.models import BotState, Strategy, StrategyVersion
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
    assert version["inputs_schema"][0]["group"] == "01. Engine"
    assert version["inputs_schema"][0]["step"] == 1
