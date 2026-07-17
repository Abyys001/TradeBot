"""Tests for copy-trading sizing, fees, and signal fan-out (no network)."""
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.credentials.models import Exchange, ExchangeCredential, Network
from apps.strategies.models import Strategy

from . import tasks
from .models import CopySignal, FeeLedger, InvestorPosition, Subscription
from .sizing import accrue_fee, compute_size, realized_pnl


# ---- pure sizing / fee logic ------------------------------------------
def test_compute_size_risk_pct():
    # 1% of 10_000 balance = 100 notional; ×2 leverage = 200; /50 price = 4
    size = compute_size(
        balance=10_000,
        price=50,
        sizing_mode=Subscription.Sizing.RISK_PCT,
        risk_pct=Decimal("1.0"),
        fixed_notional=Decimal("0"),
        leverage=2,
    )
    assert size == pytest.approx(4.0)


def test_compute_size_fixed_notional():
    size = compute_size(
        balance=0,
        price=100,
        sizing_mode=Subscription.Sizing.FIXED_NOTIONAL,
        risk_pct=Decimal("0"),
        fixed_notional=Decimal("500"),
        leverage=1,
    )
    assert size == pytest.approx(5.0)


def test_compute_size_zero_price_is_safe():
    assert compute_size(
        balance=1000, price=0, sizing_mode=Subscription.Sizing.RISK_PCT,
        risk_pct=1, fixed_notional=0, leverage=1,
    ) == 0.0


def test_realized_pnl_long_and_short():
    assert realized_pnl(entry_price=100, exit_price=110, size=2) == pytest.approx(20)
    assert realized_pnl(entry_price=100, exit_price=90, size=-2) == pytest.approx(20)


def test_accrue_fee_high_water_mark():
    # First profit of 100 → fee 20, hwm 100
    fee, realized, hwm = accrue_fee(
        prior_realized=0, prior_hwm=0, realized_delta=100, fee_rate=0.20
    )
    assert (fee, realized, hwm) == (pytest.approx(20), pytest.approx(100), pytest.approx(100))
    # Loss of 40 → no fee, hwm unchanged
    fee, realized, hwm = accrue_fee(
        prior_realized=100, prior_hwm=100, realized_delta=-40, fee_rate=0.20
    )
    assert fee == 0
    assert realized == pytest.approx(60)
    assert hwm == pytest.approx(100)
    # Recovery of 30 (to 90) still below hwm → no fee
    fee, realized, hwm = accrue_fee(
        prior_realized=60, prior_hwm=100, realized_delta=30, fee_rate=0.20
    )
    assert fee == 0
    # New profit above hwm: from 90 to 120 → fee only on the 20 above hwm(100)
    fee, realized, hwm = accrue_fee(
        prior_realized=90, prior_hwm=100, realized_delta=30, fee_rate=0.20
    )
    assert fee == pytest.approx(4.0)  # (120 - 100) * 0.20
    assert hwm == pytest.approx(120)


# ---- fan-out with a fake exchange client ------------------------------
class FakeClient:
    def __init__(self, credential, balance=10_000):
        self.credential = credential
        self._balance = balance
        self.orders = []
        self.closed = []

    def balance(self):
        return self._balance

    def set_leverage(self, coin, leverage, **k):
        return {"ok": True}

    def place_order(self, coin, is_buy, size, price=None, reduce_only=False):
        self.orders.append((coin, is_buy, size))
        return {"ok": True}

    def close_position(self, coin):
        self.closed.append(coin)
        return {"ok": True}


def _investor_with_sub(sizing=Subscription.Sizing.FIXED_NOTIONAL):
    User = get_user_model()
    admin = User.objects.create_user("admin1", password="pw", role=User.Role.ADMIN)
    investor = User.objects.create_user(
        "inv1", password="pw", role=User.Role.INVESTOR, is_trading_enabled=True
    )
    master = Strategy.objects.create(
        user=admin, name="M", type="pine", symbol="BTC",
        is_master=True, published=True,
    )
    cred = ExchangeCredential(
        user=investor, exchange=Exchange.TABDEAL, label="c",
        api_key="k", network=Network.MAINNET, is_active=True,
    )
    cred.set_api_secret("s")
    cred.save()
    sub = Subscription.objects.create(
        investor=investor, master_strategy=master, credential=cred,
        sizing_mode=sizing, fixed_notional=Decimal("500"), leverage=1,
    )
    return master, sub


@pytest.mark.django_db
def test_fanout_entry_opens_position():
    master, sub = _investor_with_sub()
    signal = CopySignal.objects.create(
        master_strategy=master, action="entry", direction="long",
        coin="BTC", price=Decimal("100"), ts=1,
    )
    with mock.patch.object(tasks, "get_client", lambda c: FakeClient(c)):
        res = tasks.fanout_signal(signal)
    assert res["mirrored"] == 1
    pos = InvestorPosition.objects.get(subscription=sub, coin="BTC")
    assert pos.size == Decimal("5")  # 500 notional / 100 price


@pytest.mark.django_db
def test_fanout_close_accrues_fee():
    master, sub = _investor_with_sub()
    InvestorPosition.objects.create(
        subscription=sub, coin="BTC", size=Decimal("5"), entry_price=Decimal("100")
    )
    signal = CopySignal.objects.create(
        master_strategy=master, action="close", direction="",
        coin="BTC", price=Decimal("120"), ts=2,
    )
    with mock.patch.object(tasks, "get_client", lambda c: FakeClient(c)):
        res = tasks.fanout_signal(signal)
    assert res["mirrored"] == 1
    assert not InvestorPosition.objects.filter(subscription=sub, coin="BTC").exists()
    ledger = FeeLedger.objects.get(subscription=sub)
    # realized = (120-100)*5 = 100 profit; fee = 20
    assert ledger.realized_pnl == Decimal("100")
    assert ledger.fee_accrued == Decimal("20.00000000")


@pytest.mark.django_db
def test_fanout_skips_when_kill_switch_off():
    master, sub = _investor_with_sub()
    sub.investor.is_trading_enabled = False
    sub.investor.save(update_fields=["is_trading_enabled"])
    signal = CopySignal.objects.create(
        master_strategy=master, action="entry", direction="long",
        coin="BTC", price=Decimal("100"), ts=1,
    )
    with mock.patch.object(tasks, "get_client", lambda c: FakeClient(c)):
        res = tasks.fanout_signal(signal)
    assert res["skipped"] == 1
    assert res["mirrored"] == 0
    assert not InvestorPosition.objects.filter(subscription=sub).exists()


# ---- API permission / isolation ---------------------------------------
@pytest.mark.django_db
def test_investor_forbidden_from_admin_endpoints(client):
    User = get_user_model()
    User.objects.create_user("inv", password="pw", role=User.Role.INVESTOR)
    client.login(username="inv", password="pw")
    for url in (
        "/api/copytrading/admin/investors/",
        "/api/copytrading/admin/fee-ledger/",
        "/api/copytrading/admin/fee-config/",
    ):
        assert client.get(url).status_code == 403, url


@pytest.mark.django_db
def test_admin_forbidden_from_investor_subscriptions(client):
    User = get_user_model()
    User.objects.create_user("adm", password="pw", role=User.Role.ADMIN)
    client.login(username="adm", password="pw")
    # SubscriptionViewSet is investor-only.
    assert client.get("/api/copytrading/subscriptions/").status_code == 403


@pytest.mark.django_db
def test_admin_can_list_investors(client):
    User = get_user_model()
    User.objects.create_user("adm2", password="pw", role=User.Role.ADMIN)
    User.objects.create_user("inv2", password="pw", role=User.Role.INVESTOR)
    client.login(username="adm2", password="pw")
    resp = client.get("/api/copytrading/admin/investors/")
    assert resp.status_code == 200
    usernames = {row["username"] for row in resp.json()}
    assert "inv2" in usernames


@pytest.mark.django_db
def test_investor_cannot_subscribe_with_foreign_credential(client):
    """A subscription must bind the investor's own credential."""
    User = get_user_model()
    other = User.objects.create_user("other", password="pw", role=User.Role.INVESTOR)
    admin = User.objects.create_user("adm3", password="pw", role=User.Role.ADMIN)
    master = Strategy.objects.create(
        user=admin, name="M", type="pine", symbol="BTC", is_master=True, published=True
    )
    foreign_cred = ExchangeCredential(
        user=other, exchange=Exchange.TABDEAL, label="x", api_key="k", network=Network.MAINNET
    )
    foreign_cred.set_api_secret("s")
    foreign_cred.save()

    User.objects.create_user("inv3", password="pw", role=User.Role.INVESTOR)
    client.login(username="inv3", password="pw")
    resp = client.post(
        "/api/copytrading/subscriptions/",
        {"master_strategy": master.id, "credential": foreign_cred.id},
        content_type="application/json",
    )
    assert resp.status_code == 400  # rejected: credential not owned


@pytest.mark.django_db
def test_record_and_fanout_noop_for_unpublished_master():
    User = get_user_model()
    admin = User.objects.create_user("a", password="pw", role=User.Role.ADMIN)
    strat = Strategy.objects.create(
        user=admin, name="s", type="pine", symbol="BTC", is_master=False, published=False
    )
    with mock.patch.object(tasks.fanout_copy_signal_task, "delay") as delay:
        out = tasks.record_and_fanout(
            strat, action="entry", direction="long", coin="BTC", price=1.0, ts=1
        )
    assert out is None
    delay.assert_not_called()
    assert CopySignal.objects.count() == 0
