"""Q37 through the execution path and the HTTP surface.

`test_exit_policy` proves the policy as a pure function. This proves the two
places it has to be true against something that behaves like an exchange:

  * `executor.open_trade` / `amend_sltp`, where the refusal has to happen
    before any account is touched;
  * `/api/trading/orders/`, where the panel and any other caller reach it.

The regression half matters as much as the new half — every assertion about
`protected` here is a statement that nothing changed for a caller who did not
ask for anything.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.engine.executor import TradeIntent, amend_sltp, open_trade
from apps.exchanges.base import MarketType, OrderType, Side
from apps.exchanges.paper import PaperAdapter
from apps.trading.models import Trade
from apps.trading.protection import ExitPolicy

OPEN = "/api/trading/orders/open/"
KEY = Fernet.generate_key().decode()


def intent(**overrides) -> TradeIntent:
    base = dict(
        symbol="BTCUSDT",
        side=Side.LONG,
        market=MarketType.FUTURES,
        order_type=OrderType.MARKET,
        leverage=10,
        sl_pct=D("0.2"),
        tp_pct=D("0.4"),
        limit_price=D("100000"),
    )
    return TradeIntent(**{**base, **overrides})


def managed(**overrides) -> TradeIntent:
    base = {
        "exit_policy": ExitPolicy.STRATEGY_MANAGED,
        "sl_pct": None,
        "tp_pct": None,
    }
    return intent(**{**base, **overrides})


# --- the engine -------------------------------------------------------------


async def test_a_strategy_managed_entry_routes_with_no_protection_at_all():
    """The position opens, and nothing rests at the venue. Legal, and reported."""
    adapter = PaperAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], managed())

    assert result.all_ok
    leg = result.succeeded[0]
    assert leg.value.stop_loss is None
    assert leg.value.take_profit is None
    assert await adapter.get_position("BTCUSDT") is not None


async def test_a_strategy_managed_entry_still_sends_whatever_it_was_given():
    """Optional is not ignored: a take profit with a strategy-decided stop is a
    real configuration and the target must reach the exchange."""
    adapter = PaperAdapter(balance=D("1000"))
    result = await open_trade([(1, adapter)], managed(tp_pct=D("0.4")))

    leg = result.succeeded[0]
    assert leg.value.take_profit is not None
    assert leg.value.stop_loss is None


async def test_the_safety_net_is_what_rests_when_no_stop_was_given():
    """1x, so liquidation is 100% away and a 20% net is comfortably inside it."""
    adapter = PaperAdapter(balance=D("1000"))
    result = await open_trade(
        [(1, adapter)], managed(leverage=1, safety_net_pct=D("20"))
    )

    leg = result.succeeded[0]
    assert leg.value.stop_loss is not None
    # 20% below a 100,000 entry, and nowhere near a 0.2% stop.
    assert leg.value.stop_loss == D("80000.00")


async def test_a_net_past_liquidation_is_named_rather_than_left_to_fail_per_leg():
    """At 10x liquidation sits 10% away, so a 20% net can never fire. The
    operator is told that, once, instead of every account reporting "stop sits
    below liquidation" from inside a fan-out that opened nothing."""
    adapter = PaperAdapter(balance=D("1000"))
    with pytest.raises(ValueError, match="past liquidation"):
        await open_trade([(1, adapter)], managed(leverage=10, safety_net_pct=D("20")))
    assert await adapter.get_position("BTCUSDT") is None


async def test_a_real_stop_wins_over_the_net_so_only_one_ever_rests():
    """Two stops on one position is the state Q5d exists to prevent."""
    adapter = PaperAdapter(balance=D("1000"))
    result = await open_trade(
        [(1, adapter)], managed(leverage=1, sl_pct=D("0.2"), safety_net_pct=D("20"))
    )
    assert result.succeeded[0].value.stop_loss == D("99800.00")


@pytest.mark.parametrize("missing", ["sl_pct", "tp_pct"])
async def test_the_protected_policy_still_refuses_before_any_account_is_touched(missing):
    """The §3 rule, unchanged, for every caller that did not opt out."""
    adapter = PaperAdapter(balance=D("1000"))
    with pytest.raises(ValueError, match="stop loss and a take profit"):
        await open_trade([(1, adapter)], intent(**{missing: None}))
    assert await adapter.get_position("BTCUSDT") is None


async def test_a_strategy_managed_amend_may_clear_the_resting_pair():
    """"Stop managing this by levels, I will close it myself" is a real request,
    and `apply_sltp` replacing the pair wholesale is how it takes effect."""
    adapter = PaperAdapter(balance=D("1000"))
    adapter.capabilities = replace(adapter.capabilities, native_sltp_on_entry=False)
    await open_trade([(1, adapter)], intent())
    assert adapter._state["sltp"] != (None, None)

    result = await amend_sltp(
        [(1, adapter)],
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        sl_pct=None,
        tp_pct=None,
        admin_entry=D("100000"),
        exit_policy=ExitPolicy.STRATEGY_MANAGED,
    )
    assert result.all_ok


@pytest.mark.parametrize("missing", ["sl_pct", "tp_pct"])
async def test_a_protected_amend_carrying_one_side_is_still_refused(missing):
    adapter = PaperAdapter(balance=D("1000"))
    await open_trade([(1, adapter)], intent())
    kwargs = {"sl_pct": D("0.3"), "tp_pct": D("0.9"), missing: None}
    with pytest.raises(ValueError, match="stop loss and a take profit"):
        await amend_sltp(
            [(1, adapter)],
            symbol="BTCUSDT",
            side=Side.LONG,
            leverage=10,
            admin_entry=D("100000"),
            **kwargs,
        )


# --- the HTTP surface -------------------------------------------------------

http = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _encryption_key():
    with override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY]):
        yield


def account(label: str, *, balance: str = "1000") -> ConnectedAccount:
    return ConnectedAccount.objects.create(
        label=label,
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D(balance),
        last_balance_asset="USDT",
    )


def staff_client() -> Client:
    User.objects.create_user("boss", password="pw", is_staff=True)
    client = Client()
    client.login(username="boss", password="pw")
    return client


def order(**overrides) -> dict:
    return {
        "symbol": "BTCUSDT",
        "side": "long",
        "market": "futures",
        "order_type": "market",
        "leverage": 10,
        "limit_price": "100000",
        **overrides,
    }


@http
def test_the_api_accepts_an_order_with_no_levels_when_the_policy_says_so():
    account("partner")
    client = staff_client()
    response = client.post(
        OPEN,
        order(exit_policy="strategy_managed"),
        content_type="application/json",
    )
    assert response.status_code == 200
    trade = Trade.objects.get(id=response.json()["trade_id"])
    assert trade.exit_policy == ExitPolicy.STRATEGY_MANAGED
    assert trade.sl_pct is None and trade.tp_pct is None


@http
@pytest.mark.parametrize("field", ["sl_pct", "tp_pct"])
def test_the_api_still_refuses_a_bare_order_by_default(field):
    """No `exit_policy` in the body is the old behaviour, exactly."""
    account("partner")
    client = staff_client()
    body = order(sl_pct="0.5", tp_pct="1")
    del body[field]
    response = client.post(OPEN, body, content_type="application/json")
    assert response.status_code == 400
    assert field in response.json()["detail"]


@http
def test_an_unknown_policy_is_a_400_rather_than_a_silent_default():
    account("partner")
    client = staff_client()
    response = client.post(
        OPEN, order(exit_policy="whatever"), content_type="application/json"
    )
    assert response.status_code == 400


@http
def test_the_policy_is_recorded_on_the_trade_so_history_stays_readable():
    """A bot's policy can change tomorrow; what this trade was protected by
    cannot, or the trade log starts describing today's setting."""
    account("partner")
    client = staff_client()
    response = client.post(
        OPEN,
        # 8% at 10x: inside the 10% liquidation distance, so it can actually fire.
        order(exit_policy="strategy_managed", safety_net_pct="8"),
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    trade = Trade.objects.get(id=response.json()["trade_id"])
    assert trade.safety_net_pct == D("8")
    assert trade.exit_policy == ExitPolicy.STRATEGY_MANAGED


@http
def test_a_net_past_liquidation_is_a_400_naming_the_field():
    account("partner")
    client = staff_client()
    response = client.post(
        OPEN,
        order(exit_policy="strategy_managed", safety_net_pct="20"),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "past liquidation" in response.json()["detail"]
