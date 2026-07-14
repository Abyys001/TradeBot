"""Copy-trading fan-out + profit-share (high-water mark) tests."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.models import User
from apps.credentials.models import Exchange, ExchangeCredential
from apps.strategies.models import Strategy

from .fees import apply_profit_share
from .models import CopyOrder, CopySignal, CopySubscription, CopyTrade, FeeLedgerEntry


def _make_investor(username="inv", trading=True):
    u = User.objects.create_user(username=username, password="x", role=User.Role.INVESTOR, is_trading_enabled=trading)
    cred = ExchangeCredential(user=u, exchange=Exchange.TABDEAL, label="td", is_active=True)
    cred.set_api_credentials("key", "secret")
    cred.save()
    return u, cred


def _make_signal_strategy(admin, pct=100):
    strat = Strategy.objects.create(
        user=admin, name="sig", symbol="BTC", source="//x", validation_status="ok",
        live_config={"copy_trading": True, "leverage": 1},
    )
    signal = CopySignal.objects.create(
        owner=admin, strategy=strat, name="sig", secret_token="tok", default_position_size_pct=pct,
        platform_share_pct=20,
    )
    return strat, signal


def _fake_client(usdt=1000.0, entry_px=100.0, exit_px=110.0):
    client = MagicMock()
    client.available_usdt.return_value = usdt
    client.symbol_precision.return_value = (2, 3)
    client.set_leverage.return_value = {}
    client.place_market_order.return_value = {"orderId": 1, "avgPrice": str(entry_px)}
    client.close_position.return_value = {"avgPrice": str(exit_px)}
    return client


@pytest.mark.django_db
def test_tabdeal_broker_entry_then_close_records_trade_and_fee():
    from apps.transpiler.runtime.tabdeal_broker import TabdealBroker

    admin = User.objects.create_user(username="admin1", password="x", role=User.Role.ADMIN)
    _inv, cred = _make_investor()
    strat, signal = _make_signal_strategy(admin)
    sub = CopySubscription.objects.create(signal=signal, credential=cred)

    client = _fake_client(usdt=1000.0, entry_px=100.0, exit_px=110.0)
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        broker = TabdealBroker(sub, strat, "BTC", leverage=1)
        broker.entry("o1", "long", 100.0, 1)
        order = CopyOrder.objects.get(subscription=sub, side=CopyOrder.Side.BUY)
        assert float(order.size) == 10.0  # 1000 USDT * 100% / 100 price
        assert CopyTrade.objects.filter(subscription=sub, status=CopyTrade.Status.OPEN).count() == 1

        broker.close("o1", 110.0, 2, reason="signal")

    trade = CopyTrade.objects.get(subscription=sub)
    assert trade.status == CopyTrade.Status.CLOSED
    assert float(trade.gross_pnl) == 100.0  # (110-100) * 10
    assert float(trade.platform_share_amount) == 20.0  # 20%
    fee = FeeLedgerEntry.objects.get(trade=trade)
    assert float(fee.amount) == 20.0
    sub.refresh_from_db()
    assert float(sub.high_water_mark) == 100.0


@pytest.mark.django_db
def test_high_water_mark_no_double_charge_on_recovery():
    admin = User.objects.create_user(username="admin2", password="x", role=User.Role.ADMIN)
    _inv, cred = _make_investor(username="inv2")
    strat, signal = _make_signal_strategy(admin)
    sub = CopySubscription.objects.create(signal=signal, credential=cred, high_water_mark=Decimal("100"))

    e1 = CopyOrder.objects.create(subscription=sub, pair="BTC_USDT", side="buy", size=1, avg_fill_price=100)
    losing = CopyTrade.objects.create(subscription=sub, entry_order=e1, status=CopyTrade.Status.CLOSED, gross_pnl=Decimal("-40"))
    assert apply_profit_share(losing) is None
    assert FeeLedgerEntry.objects.filter(subscription=sub).count() == 0

    e2 = CopyOrder.objects.create(subscription=sub, pair="BTC_USDT", side="buy", size=1, avg_fill_price=100)
    recover = CopyTrade.objects.create(subscription=sub, entry_order=e2, status=CopyTrade.Status.CLOSED, gross_pnl=Decimal("30"))
    assert apply_profit_share(recover) is None  # cumulative -10, still under HWM 100

    e3 = CopyOrder.objects.create(subscription=sub, pair="BTC_USDT", side="buy", size=1, avg_fill_price=100)
    winner = CopyTrade.objects.create(subscription=sub, entry_order=e3, status=CopyTrade.Status.CLOSED, gross_pnl=Decimal("160"))
    entry = apply_profit_share(winner)
    # cumulative = -40+30+160 = 150; above HWM(100) by 50; fee 20% = 10
    assert entry is not None and float(entry.amount) == 10.0
    sub.refresh_from_db()
    assert float(sub.high_water_mark) == 150.0


@pytest.mark.django_db
def test_fan_out_task_isolates_per_investor_failures():
    from apps.copytrading.tasks import fan_out_signal_task

    admin = User.objects.create_user(username="admin3", password="x", role=User.Role.ADMIN)
    _i1, c1 = _make_investor(username="good")
    _i2, c2 = _make_investor(username="bad")
    strat, signal = _make_signal_strategy(admin)
    CopySubscription.objects.create(signal=signal, credential=c1)
    CopySubscription.objects.create(signal=signal, credential=c2)

    good_client = _fake_client()
    bad_client = MagicMock()
    bad_client.available_usdt.side_effect = RuntimeError("network down")

    # Bad subscriber processed first: its failure must not stop the good one.
    clients = iter([bad_client, good_client])
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", side_effect=lambda *a, **k: next(clients)):
        actions = [{"type": "entry", "oid": "o1", "direction": "long", "price": 100.0, "bar_index": 1}]
        out = fan_out_signal_task(strat.pk, actions)

    assert out["ok"] is True and out["subscribers"] == 1  # good one completed despite bad one failing
    assert CopyTrade.objects.count() == 1  # only the good investor opened a trade


@pytest.mark.django_db
def test_sync_subscriptions_auto_follows_active_investors():
    from .subscriptions import sync_subscriptions

    admin = User.objects.create_user(username="admin4", password="x", role=User.Role.ADMIN)
    _make_investor(username="a")
    _make_investor(username="b")
    ac = ExchangeCredential(user=admin, exchange=Exchange.TABDEAL, label="admincred", is_active=True)
    ac.set_api_credentials("k", "s")
    ac.save()

    strat = Strategy.objects.create(user=admin, name="s", symbol="BTC", validation_status="ok", live_config={"copy_trading": True})
    result = sync_subscriptions(strat)
    assert result["active_total"] == 2  # only the two investors, not the admin
