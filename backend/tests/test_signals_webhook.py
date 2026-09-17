"""Q37 — the inbound signal endpoint.

This is the only unauthenticated write surface on the platform, so the tests
split the same way the design does:

  * **the door** — signature, replay window, allowlist, duplicates. Everything
    the panel's session normally provides, carried inside the request;
  * **the vocabulary** — the four verbs and what a payload may not say;
  * **the join** — that a signal reaches the *same* order path a Pine bar does,
    and that an exit closes a position with no percentage configured anywhere.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal as D

import pytest
from cryptography.fernet import Fernet
from django.test import Client, override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.bots.models import BotState, ExitPolicy, SignalSourceKind
from apps.signals.auth import sign
from apps.signals.models import SignalEvent, SignalSource, Verdict
from apps.signals.payload import SignalRejected, Verb, parse
from apps.trading.models import Trade, TradeStatus
from tests.bot_factory import make_bot, make_run

pytestmark = pytest.mark.django_db(transaction=True)

KEY = Fernet.generate_key().decode()
SECRET = "a-test-secret-nobody-would-guess"


@pytest.fixture(autouse=True)
def _encryption_key():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield


def account(label: str = "partner", *, balance: str = "1000") -> ConnectedAccount:
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D(balance),
        last_balance_asset="USDT",
        # A signal routes as a bot does (`source="bot"`), so the account has to
        # be opted into bot trading — the second of the two independent
        # switches in `docs/bots.md` §7. Off by default, deliberately.
        bot_trading_enabled=True,
    )


def webhook_bot(*, state: str = BotState.LIVE, **kwargs):
    defaults = {
        "name": "external",
        "signal_source": SignalSourceKind.WEBHOOK,
        "exit_policy": ExitPolicy.STRATEGY_MANAGED,
        "state": state,
        "symbol": "BTCUSDT",
    }
    bot = make_bot(**{**defaults, **kwargs})
    make_run(bot)
    return bot


def source(bot=None, **kwargs) -> SignalSource:
    bot = bot or webhook_bot()
    row = SignalSource(
        name=kwargs.pop("name", "tradingview"),
        bot=bot,
        token=SignalSource.new_token(),
        enabled=kwargs.pop("enabled", True),
        **kwargs,
    )
    row.set_secret(SECRET)
    row.save()
    return row


def post(src: SignalSource, body: dict, *, secret: str = SECRET, skew: int = 0):
    raw = json.dumps(body).encode()
    stamp = int(time.time()) + skew
    return Client().post(
        src.endpoint,
        raw,
        content_type="application/json",
        HTTP_X_SIGNATURE=sign(secret, raw, stamp),
        HTTP_X_SIGNATURE_TIMESTAMP=str(stamp),
    )


def buy(**extra) -> dict:
    return {"action": "BUY", "symbol": "BTCUSDT", "id": "sig-1", **extra}


# --- the door ---------------------------------------------------------------


def test_an_unknown_token_is_a_404_and_says_nothing_else():
    response = Client().post(
        "/api/signals/hooks/nope/", buy(), content_type="application/json"
    )
    assert response.status_code == 404


def test_a_disabled_source_answers_exactly_like_an_unknown_one():
    """A caller must not be able to tell "wrong URL" from "switched off"."""
    src = source(enabled=False)
    assert post(src, buy()).status_code == 404


def test_a_wrong_signature_is_refused_and_recorded():
    src = source()
    response = post(src, buy(), secret="not-the-secret")
    assert response.status_code == 401
    # Uninformative to the caller...
    assert response.json()["detail"] == "invalid signature"
    # ...and specific to the operator.
    event = SignalEvent.objects.get()
    assert event.verdict == Verdict.REJECTED
    assert event.code == "signature_mismatch"


def test_a_missing_signature_is_refused():
    src = source()
    raw = json.dumps(buy()).encode()
    response = Client().post(src.endpoint, raw, content_type="application/json")
    assert response.status_code == 401


def test_a_stale_delivery_is_refused_even_with_a_valid_signature():
    """A signature with no time bound is replayable forever."""
    src = source(replay_window_seconds=60)
    response = post(src, buy(), skew=-3600)
    assert response.status_code == 401
    assert SignalEvent.objects.get().code == "stale"


def test_an_address_outside_the_allowlist_is_refused():
    src = source(allowed_ips=["203.0.113.7"])
    assert post(src, buy()).status_code == 404


def test_an_empty_allowlist_means_any_address():
    account()
    src = source(allowed_ips=[])
    assert post(src, buy()).status_code == 200


def test_the_same_signal_id_twice_is_handled_once():
    """Alert systems retry. A retry that re-entered a position would be the
    worst bug this endpoint could have."""
    account()
    src = source()
    first = post(src, buy())
    second = post(src, buy())

    assert first.status_code == 200
    assert first.json()["status"] == Verdict.ACCEPTED
    # 200, not 409: a 4xx is what makes an alert system retry the retry.
    assert second.status_code == 200
    assert second.json()["status"] == Verdict.DUPLICATE
    assert Trade.objects.count() == 1


def test_a_body_with_no_id_still_cannot_be_replayed():
    account()
    src = source()
    body = {"action": "BUY", "symbol": "BTCUSDT"}
    assert post(src, body).json()["status"] == Verdict.ACCEPTED
    assert post(src, body).json()["status"] == Verdict.DUPLICATE


# --- the vocabulary ---------------------------------------------------------


@pytest.mark.parametrize(
    "spelling,expected",
    [
        ("BUY", Verb.BUY),
        ("long", Verb.BUY),
        ("SELL", Verb.SELL),
        ("EXIT_BUY", Verb.EXIT_BUY),
        ("exit-long", Verb.EXIT_BUY),
        ("close_short", Verb.EXIT_SELL),
    ],
)
def test_the_accepted_spellings_each_map_to_one_verb(spelling, expected):
    signal = parse({"action": spelling, "symbol": "BTCUSDT"}, expected_symbol="BTCUSDT")
    assert signal.verb is expected


def test_an_unknown_action_is_refused_by_name():
    with pytest.raises(SignalRejected, match="unknown action"):
        parse({"action": "moon", "symbol": "BTCUSDT"}, expected_symbol="BTCUSDT")


@pytest.mark.parametrize("field", ["qty", "leverage", "account_id", "price"])
def test_a_payload_may_not_set_what_belongs_to_the_platform(field):
    """Refused by name rather than ignored — a silently dropped `qty` is a
    strategy author who believes sizing is theirs."""
    with pytest.raises(SignalRejected, match=field):
        parse(
            {"action": "BUY", "symbol": "BTCUSDT", field: 2},
            expected_symbol="BTCUSDT",
        )


def test_a_signal_for_another_pair_is_refused_rather_than_retargeted():
    with pytest.raises(SignalRejected, match="never retargeted"):
        parse({"action": "BUY", "symbol": "ETHUSDT"}, expected_symbol="BTCUSDT")


def test_an_exit_verb_becomes_a_flat_intent():
    signal = parse({"action": "EXIT_BUY", "symbol": "BTCUSDT"}, expected_symbol="BTCUSDT")
    assert signal.as_intent(bar_time=1).desired_side is None


# --- the join ---------------------------------------------------------------


def test_a_buy_opens_a_position_through_the_ordinary_order_path():
    account()
    src = source()
    response = post(src, buy())

    assert response.status_code == 200
    assert response.json()["status"] == Verdict.ACCEPTED
    trade = Trade.objects.get()
    assert trade.side == "long"
    assert trade.status == TradeStatus.OPEN
    # It went through the bot's run, so it is in the bot's history like any
    # other action rather than in a parallel table.
    assert trade.bot_run is not None


def test_an_exit_closes_the_position_with_no_percentages_anywhere():
    """The sentence Q37 exists to make true, end to end over HTTP.

    The bot has no stop and no target, nothing rests at the exchange, and the
    strategy saying EXIT_BUY still closes the trade. No PnL threshold is
    consulted on any step of this path.
    """
    account()
    src = source()
    post(src, buy())
    trade = Trade.objects.get()
    assert trade.sl_pct is None and trade.tp_pct is None

    response = post(src, {"action": "EXIT_BUY", "symbol": "BTCUSDT", "id": "sig-2"})

    assert response.json()["status"] == Verdict.ACCEPTED
    trade.refresh_from_db()
    assert trade.status == TradeStatus.CLOSED


def test_an_exit_closes_the_position_on_every_connected_account():
    """§4: an exit fans out exactly as the entry did.

    "Close this" reaching two of three accounts is worse than it not arriving
    at all — one partner is left holding a position nobody is managing. The
    close goes through the same ``fan_out`` the open did, so the legs on the
    way out are the legs that went in, and this is what says so.
    """
    account("partner-a")
    account("partner-b")
    account("not-opted-in").__class__.objects.filter(label="not-opted-in").update(
        bot_trading_enabled=False
    )
    src = source()
    post(src, buy())
    trade = Trade.objects.get()
    assert sorted(leg.account.label for leg in trade.legs.all()) == ["partner-a", "partner-b"]

    post(src, {"action": "EXIT_BUY", "symbol": "BTCUSDT", "id": "sig-2"})

    trade.refresh_from_db()
    assert trade.status == TradeStatus.CLOSED
    assert sorted(leg.account.label for leg in trade.legs.all()) == ["partner-a", "partner-b"]
    assert all(leg.exit_price is not None for leg in trade.legs.all())


def test_an_exit_for_the_side_that_is_not_held_is_a_no_op_not_a_flatten():
    """A stale duplicate from a retrying sender must not close the other side."""
    account()
    src = source()
    post(src, {"action": "SELL", "symbol": "BTCUSDT", "id": "s1"})
    trade = Trade.objects.get()

    response = post(src, {"action": "EXIT_BUY", "symbol": "BTCUSDT", "id": "s2"})

    assert response.json()["status"] == Verdict.NOOP
    assert response.json()["code"] == "wrong_side"
    trade.refresh_from_db()
    assert trade.status == TradeStatus.OPEN


def test_an_exit_with_nothing_open_is_a_no_op():
    account()
    src = source()
    response = post(src, {"action": "EXIT_BUY", "symbol": "BTCUSDT", "id": "s1"})
    assert response.json()["status"] == Verdict.NOOP
    assert Trade.objects.count() == 0


def test_a_reversal_arrives_as_one_signal_and_leaves_as_two_sequenced_actions():
    account()
    src = source()
    post(src, {"action": "BUY", "symbol": "BTCUSDT", "id": "s1"})
    response = post(src, {"action": "SELL", "symbol": "BTCUSDT", "id": "s2"})

    assert response.json()["status"] == Verdict.ACCEPTED
    types = [row["action"]["type"] for row in response.json()["actions"]]
    assert types == ["close", "open"]
    assert Trade.objects.filter(status=TradeStatus.OPEN).get().side == "short"


def test_a_signal_to_a_stopped_bot_is_refused_and_never_queued():
    account()
    bot = webhook_bot(state=BotState.STOPPED)
    bot.runs.update(stopped_at="2020-01-01T00:00:00Z")
    src = source(bot)

    response = post(src, buy())

    assert response.json()["code"] == "bot_not_running"
    assert Trade.objects.count() == 0


def test_a_paper_bot_records_the_action_and_routes_nothing():
    account()
    src = source(webhook_bot(state=BotState.PAPER))
    response = post(src, buy())

    assert response.json()["status"] == Verdict.ACCEPTED
    assert response.json()["code"] == "paper"
    assert Trade.objects.count() == 0


def test_the_halt_stops_a_webhook_bot_like_any_other():
    """Q22, and the one kind of bot that could otherwise be told to open a
    position by something this process does not control."""
    from apps.trading import killswitch

    account()
    bot = webhook_bot()
    src = source(bot)
    killswitch.set_stop_all(True, actor="test")

    response = post(src, buy())

    bot.refresh_from_db()
    assert bot.state == BotState.STOPPED
    assert response.json()["status"] == Verdict.REJECTED
    assert Trade.objects.count() == 0


def test_every_delivery_is_recorded_including_the_ones_that_did_nothing():
    account()
    src = source()
    post(src, buy())
    post(src, {"action": "EXIT_SELL", "symbol": "BTCUSDT", "id": "s2"})

    verdicts = set(SignalEvent.objects.values_list("verdict", flat=True))
    assert verdicts == {Verdict.ACCEPTED, Verdict.NOOP}
