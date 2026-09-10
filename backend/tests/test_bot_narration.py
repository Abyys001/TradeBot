"""The three read surfaces added for "what is this bot actually doing".

`explain` reads the strategy's own source and reports what it computes and what
makes it trade; `narrate` projects the stored bars and actions into journal
events; `drills` records the one gate row nothing can measure from inside.

Every one of them is a *projection*: nothing here is stored, and nothing here
is allowed to invent a number the bot did not record.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.bots import drills, narrate
from apps.bots.models import ActionType, BotBar, BotRun, StopReason
from apps.pine import explain
from tests.bot_factory import make_bot, make_run

pytestmark = pytest.mark.django_db


SOURCE = """//@version=5
strategy("demo", overlay=true)
length = input.int(14, "RSI length")
rsi = ta.rsi(close, length)
fast = ta.sma(close, 9)
slow = ta.sma(close, 21)
plot(rsi, title="RSI")
longCond = ta.crossover(fast, slow) and rsi > 50
if longCond
    strategy.entry("long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("long")
"""


def staff() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


# --- explain ----------------------------------------------------------------


def test_every_named_series_the_script_computes_is_reported():
    result = explain.explain(SOURCE)
    assert {i.name for i in result.indicators} == {"rsi", "fast", "slow"}


def test_a_plotted_series_is_marked_plotted_once_not_listed_twice():
    result = explain.explain(SOURCE)
    rsi = [i for i in result.indicators if i.name == "rsi"]
    assert len(rsi) == 1, "plot(rsi, title=…) must mark the series, not add a second row"
    assert rsi[0].plotted is True
    assert rsi[0].label == "RSI"


def test_an_unplotted_series_is_reported_and_says_so():
    result = explain.explain(SOURCE)
    fast = next(i for i in result.indicators if i.name == "fast")
    assert fast.plotted is False


def test_every_position_change_is_a_trigger_with_the_condition_that_guards_it():
    result = explain.explain(SOURCE)
    kinds = [t.kind for t in result.triggers]
    assert kinds == ["entry", "close"]
    entry = result.triggers[0]
    assert entry.conditions == ("longCond",)


def test_a_condition_named_once_is_expanded_to_what_it_was_assigned():
    entry = explain.explain(SOURCE).triggers[0]
    assert entry.expanded == ("ta.crossover(fast, slow) and rsi > 50",)


def test_the_script_inputs_come_back_by_their_titles():
    result = explain.explain(SOURCE)
    assert "RSI length" in result.inputs


def test_a_script_that_never_trades_reports_no_triggers():
    result = explain.explain('//@version=5\nstrategy("x")\nplot(close)\n')
    assert result.triggers == ()


# --- narrate ----------------------------------------------------------------


def bar(run: BotRun, *, at: int, close: str, intent: dict | None = None, plots=None) -> BotBar:
    price = Decimal(close)
    return BotBar.objects.create(
        run=run,
        bar_time=at,
        open=price,
        high=price,
        low=price,
        close=price,
        plots=plots or {},
        intent=intent or {},
    )


def codes(run: BotRun) -> list[str]:
    return [event["code"] for event in narrate.journal(run)]


def test_a_run_always_opens_with_the_fact_that_it_started():
    run = make_run(make_bot())
    assert codes(run)[0] == "started"


def test_a_quiet_bar_is_recorded_rather_than_dropped():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100")
    assert any(code.startswith("watching_") for code in codes(run))


def test_a_bar_that_opens_a_position_reads_as_a_signal_not_as_quiet():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", intent={"side": "long"})
    assert "signalLong" in codes(run)


def test_holding_the_same_side_across_two_bars_is_not_a_second_entry():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", intent={"side": "long"})
    bar(run, at=1_700_000_060, close="101", intent={"side": "long"})
    assert len([c for c in codes(run) if c == "signalLong"]) == 1
    assert any(c.startswith("holdingLong") for c in codes(run))


def test_long_to_short_on_one_bar_reads_as_a_reversal():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", intent={"side": "long"})
    bar(run, at=1_700_000_060, close="99", intent={"side": "short"})
    assert "reversal" in codes(run)


def test_going_flat_reads_as_an_exit():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", intent={"side": "long"})
    bar(run, at=1_700_000_060, close="101", intent={})
    assert "exitSignal" in codes(run)


def test_a_smaller_share_of_the_same_position_is_a_scale_out():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", intent={"side": "long", "position_fraction": "1"})
    bar(run, at=1_700_000_060, close="101", intent={"side": "long", "position_fraction": "0.5"})
    events = {e["code"]: e for e in narrate.journal(run)}
    assert "scaleOut" in events
    assert events["scaleOut"]["params"]["remaining"] == "50.00"


def test_asking_to_enter_a_position_that_is_already_open_is_said_out_loud():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", intent={"side": "long"})
    bar(run, at=1_700_000_060, close="101", intent={"side": "long", "entry_signal": True})
    assert "entryRepeated" in codes(run)


def test_the_script_moving_its_own_stop_is_reported():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", intent={"side": "long", "sl_pct": "2"})
    bar(run, at=1_700_000_060, close="101", intent={"side": "long", "sl_pct": "1"})
    assert "protectionChanged" in codes(run)


def test_a_stopped_run_says_why_it_stopped():
    run = make_run(make_bot())
    run.stopped_at = timezone.now()
    run.stop_reason = StopReason.DRAWDOWN
    run.stop_detail = "over the limit"
    run.save()
    stopped = next(e for e in narrate.journal(run) if e["code"] == "stopped")
    assert stopped["params"]["reason"] == StopReason.DRAWDOWN
    assert stopped["level"] == narrate.DANGER


def test_an_action_that_was_dispatched_and_never_settled_is_flagged():
    run = make_run(make_bot())
    run.actions.create(
        bar_time=1_700_000_000,
        action_type=ActionType.OPEN,
        idempotency_key="k1",
        dispatched_at=timezone.now(),
    )
    assert "unsettled" in codes(run)


def test_a_journal_event_carries_codes_and_params_never_a_finished_sentence():
    run = make_run(make_bot())
    bar(run, at=1_700_000_000, close="100", plots={"rsi": "55"})
    for event in narrate.journal(run):
        assert set(event) >= {"at", "kind", "code", "level", "params"}
        assert "message" not in event, "the panel renders the sentence, so all six locales can"


# --- the adapters acknowledgement -------------------------------------------


def test_acknowledging_the_adapters_row_records_who_and_when():
    bot = make_bot()
    config = drills.acknowledge_adapters(bot, actor="boss", on=True)
    assert config["adapters_tested_on_testnet"] is True
    assert config["adapters_acknowledged_by"] == "boss"
    assert config["adapters_acknowledged_at"]


def test_un_acknowledging_removes_the_answer_rather_than_recording_a_no():
    bot = make_bot(risk_config={"adapters_tested_on_testnet": True})
    config = drills.acknowledge_adapters(bot, actor="boss", on=False)
    assert "adapters_tested_on_testnet" not in config
    assert "adapters_acknowledged_by" not in config


# --- the endpoints ----------------------------------------------------------


def test_the_journal_endpoint_returns_the_run_and_its_events():
    bot = make_bot()
    run = make_run(bot)
    bar(run, at=1_700_000_000, close="100")
    response = staff().get(f"/api/bots/bots/{bot.id}/journal/")
    assert response.status_code == 200
    body = response.json()
    assert body["run"] is not None
    assert body["events"]


def test_the_journal_of_a_bot_that_has_never_run_is_empty_not_an_error():
    bot = make_bot()
    body = staff().get(f"/api/bots/bots/{bot.id}/journal/").json()
    assert body["run"] is None
    assert body["events"] == []


def test_the_logic_endpoint_reports_the_triggers_the_source_actually_has():
    bot = make_bot(source=SOURCE)
    body = staff().get(f"/api/bots/bots/{bot.id}/logic/").json()
    assert [t["kind"] for t in body["triggers"]] == ["entry", "close"]


def test_the_accounts_endpoint_says_which_accounts_this_bot_can_reach():
    bot = make_bot()
    body = staff().get(f"/api/bots/bots/{bot.id}/accounts/").json()
    assert "accounts" in body
    assert all({"bot_trading_enabled", "eligible"} <= set(row) for row in body["accounts"])


def test_acknowledging_the_adapters_row_over_the_api_records_the_signed_in_user():
    bot = make_bot()
    client = staff()
    response = client.post(
        f"/api/bots/bots/{bot.id}/acknowledge-adapters/",
        data=json.dumps({"on": True}),
        content_type="application/json",
    )
    assert response.status_code == 200
    bot.refresh_from_db()
    assert bot.risk_config["adapters_acknowledged_by"] == "boss"


def test_every_new_read_surface_is_staff_only():
    bot = make_bot()
    anonymous = Client()
    for url in (
        f"/api/bots/bots/{bot.id}/journal/",
        f"/api/bots/bots/{bot.id}/logic/",
        f"/api/bots/bots/{bot.id}/chart/",
        f"/api/bots/bots/{bot.id}/accounts/",
    ):
        assert anonymous.get(url).status_code in (401, 403), url


# --- the backtest history, and the job in front of it ------------------------


def make_backtest(version, *, symbol: str = "BTCUSDT"):
    from apps.bots.models import BacktestRun

    return BacktestRun.objects.create(
        strategy_version=version,
        symbol=symbol,
        interval="1h",
        market="futures",
        from_time=0,
        to_time=3600,
        metrics={"return_pct": "1"},
        assumptions={},
    )


def test_one_stored_backtest_can_be_deleted_on_its_own():
    from apps.bots.models import BacktestRun

    bot = make_bot()
    row = make_backtest(bot.strategy_version)
    assert staff().delete(f"/api/bots/backtests/{row.id}/").status_code == 204
    assert not BacktestRun.objects.filter(id=row.id).exists()


def test_clearing_the_history_answers_with_how_many_it_deleted():
    from apps.bots.models import BacktestRun

    bot = make_bot()
    make_backtest(bot.strategy_version)
    make_backtest(bot.strategy_version)
    body = staff().delete("/api/bots/backtests/clear/").json()
    assert body["deleted"] >= 2
    assert not BacktestRun.objects.exists()


def test_clearing_one_version_leaves_the_other_versions_alone():
    from apps.bots.models import BacktestRun

    mine = make_bot(name="mine")
    theirs = make_bot(name="theirs")
    make_backtest(mine.strategy_version)
    kept = make_backtest(theirs.strategy_version)
    url = f"/api/bots/backtests/clear/?strategy_version={mine.strategy_version_id}"
    assert staff().delete(url).json()["deleted"] >= 1
    assert list(BacktestRun.objects.values_list("id", flat=True)) == [kept.id]


def test_the_coverage_endpoint_refuses_a_request_with_no_pair():
    assert staff().get("/api/bots/backtest/coverage/").status_code == 400


def test_the_coverage_endpoint_reports_an_empty_archive_as_nothing_cached():
    url = "/api/bots/backtest/coverage/?symbol=BTCUSDT&interval=1h&from_time=0&to_time=36000"
    body = staff().get(url).json()
    assert body["stored"] == 0
    assert body["cached"] is False
    assert body["expected"] > 0


def test_a_job_that_does_not_exist_is_a_404_not_a_blank_progress_bar():
    assert staff().get("/api/bots/backtest/jobs/999999/").status_code == 404


def test_a_job_reports_a_phase_and_a_number_the_panel_can_draw():
    from apps.bots import jobs
    from apps.bots.models import BacktestJob, JobStatus

    bot = make_bot()
    job = BacktestJob.objects.create(
        strategy_version=bot.strategy_version,
        request={},
        status=JobStatus.DOWNLOADING,
        progress=0.4,
    )
    state = jobs.state(job)
    assert state["status"] == JobStatus.DOWNLOADING
    assert 0.0 <= state["progress"] <= 1.0
    assert state["finished"] is False


def test_the_properties_of_a_version_resolve_without_a_bot_in_the_picture():
    bot = make_bot()
    body = staff().get(f"/api/bots/versions/{bot.strategy_version_id}/properties/").json()
    assert body["resolved"]["initial_capital"]
    assert body["schema"]
