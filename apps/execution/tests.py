"""Tests for execution order-sync (orderUpdates + userFills handlers)."""
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.credentials.models import ExchangeCredential
from apps.execution.models import ExecutionLog, OrderRecord
from apps.execution import order_sync
from apps.strategies.models import Strategy


def _order(**overrides):
    User = get_user_model()
    user = User.objects.create_user(username="exec", password="pw")
    cred = ExchangeCredential(user=user, label="c1", wallet_address="0x" + "a" * 40)
    cred.set_agent_key("ab" * 32)
    cred.save()
    strat = Strategy.objects.create(user=user, name="S", type="pine", symbol="BTC", credential=cred)
    rec = OrderRecord.objects.create(
        strategy=strat,
        exchange_order_id="oid-1",
        client_order_id="cloid-1",
        symbol="BTC",
        side="buy",
        order_type="market",
        size=Decimal("4"),
        **overrides,
    )
    return cred, rec


@pytest.mark.django_db
def test_apply_order_update_maps_status():
    cred, rec = _order()
    with mock.patch.object(order_sync, "publish_update"):
        order_sync.apply_order_update(credential_id=cred.id, update={"oid": "oid-1", "status": "resting"})
    rec.refresh_from_db()
    assert rec.status == "submitted"
    assert ExecutionLog.objects.filter(strategy=rec.strategy, event="order.update").exists()


@pytest.mark.django_db
def test_apply_order_update_unknown_order_is_noop():
    cred, rec = _order()
    with mock.patch.object(order_sync, "publish_update"):
        order_sync.apply_order_update(credential_id=cred.id, update={"oid": "does-not-exist", "status": "filled"})
    rec.refresh_from_db()
    assert rec.status == "pending"


@pytest.mark.django_db
def test_apply_user_fill_aggregates_weighted_average():
    cred, rec = _order()
    with mock.patch.object(order_sync, "publish_update"):
        order_sync.apply_user_fill(credential_id=cred.id, fill={"oid": "oid-1", "px": "100", "sz": "2"})
        order_sync.apply_user_fill(credential_id=cred.id, fill={"oid": "oid-1", "px": "110", "sz": "2"})
    rec.refresh_from_db()
    assert float(rec.filled_size) == pytest.approx(4.0)
    # weighted avg of (100*2 + 110*2)/4 = 105
    assert float(rec.avg_fill_price) == pytest.approx(105.0)
    assert rec.status == "partially_filled"


@pytest.mark.django_db
def test_apply_user_fill_matches_by_cloid():
    cred, rec = _order()
    with mock.patch.object(order_sync, "publish_update"):
        order_sync.apply_user_fill(credential_id=cred.id, fill={"cloid": "cloid-1", "px": "50", "sz": "1"})
    rec.refresh_from_db()
    assert float(rec.filled_size) == pytest.approx(1.0)
    assert ExecutionLog.objects.filter(event="order.fill").exists()
