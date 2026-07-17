"""Tests for paper trading (virtual balance, simulated fills + PnL)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.paper.broker import PaperBroker
from apps.paper.models import PaperAccount, PaperTrade
from apps.strategies.models import Strategy


def _account():
    User = get_user_model()
    user = User.objects.create_user(username="paper", password="pw")
    strat = Strategy.objects.create(user=user, name="S", type="pine", symbol="BTC")
    return PaperAccount.objects.create(user=user, strategy=strat, balance=Decimal("10000"), equity=Decimal("10000"))


@pytest.mark.django_db
def test_paper_broker_persists_closed_trade_and_pnl():
    account = _account()
    broker = PaperBroker(account, default_qty=1.0, initial_balance=10_000.0)

    broker.entry("long", "long", price=100.0, bar_index=0)
    # close at 110 -> +10 pnl on 1 unit
    broker.close("long", price=110.0, bar_index=1)

    trades = PaperTrade.objects.filter(account=account)
    assert trades.count() == 1
    t = trades.first()
    assert t.side == "long"
    assert float(t.pnl) == pytest.approx(10.0)


@pytest.mark.django_db
def test_paper_broker_sync_account_updates_balance_and_equity():
    account = _account()
    broker = PaperBroker(account, default_qty=2.0, initial_balance=10_000.0)
    broker.entry("long", "long", price=100.0, bar_index=0)
    broker.close("long", price=105.0, bar_index=1)  # +10 cash

    broker.sync_account(mark_price=105.0)
    account.refresh_from_db()
    assert float(account.balance) == pytest.approx(10_010.0)
    assert float(account.equity) == pytest.approx(10_010.0)


@pytest.mark.django_db
def test_paper_broker_open_position_equity_reflects_mark():
    account = _account()
    broker = PaperBroker(account, default_qty=1.0, initial_balance=10_000.0)
    broker.entry("long", "long", price=100.0, bar_index=0)
    # unrealized: mark at 120 -> +20 over cash
    broker.sync_account(mark_price=120.0)
    account.refresh_from_db()
    assert float(account.equity) == pytest.approx(10_020.0)
