"""Tests for the Tabdeal futures client (no live network)."""
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.credentials.models import Exchange, ExchangeCredential, Network

from .base import ExchangeClient, get_client
from .tabdeal_client import TabdealClient


def _make_cred(secret="sekret"):
    User = get_user_model()
    user = User.objects.create_user(username="tab", password="pw")
    cred = ExchangeCredential(
        user=user,
        exchange=Exchange.TABDEAL,
        label="tab",
        api_key="APIKEY123",
        network=Network.MAINNET,
    )
    cred.set_api_secret(secret)
    cred.save()
    return cred


def _resp(status_code=200, json_body=None):
    m = mock.Mock()
    m.status_code = status_code
    m.json.return_value = json_body if json_body is not None else {}
    m.text = str(json_body)
    return m


def test_client_conforms_to_protocol(db):
    cred = _make_cred()
    client = get_client(cred)
    assert isinstance(client, TabdealClient)
    assert isinstance(client, ExchangeClient)


def test_symbol_mapping():
    assert TabdealClient._symbol("BTC") == "BTCUSDT"
    assert TabdealClient._symbol("ethusdt") == "ETHUSDT"


@pytest.mark.django_db
def test_verify_success_marks_active():
    cred = _make_cred()
    client = TabdealClient(cred)
    with mock.patch.object(client._session, "request", return_value=_resp(200, {"assets": []})):
        ok, detail = client.verify()
    assert ok is True
    cred.refresh_from_db()
    assert cred.is_active is True
    assert cred.last_verified_at is not None


@pytest.mark.django_db
def test_verify_missing_secret_fails_fast():
    cred = _make_cred()
    cred.api_secret_enc = None
    cred.save(update_fields=["api_secret_enc"])
    ok, detail = TabdealClient(cred).verify()
    assert ok is False
    assert "missing" in detail


@pytest.mark.django_db
def test_verify_auth_error_marks_inactive():
    cred = _make_cred()
    client = TabdealClient(cred)
    with mock.patch.object(
        client._session, "request", return_value=_resp(401, {"code": -2015, "msg": "bad key"})
    ):
        ok, detail = client.verify()
    assert ok is False
    cred.refresh_from_db()
    assert cred.is_active is False


@pytest.mark.django_db
def test_place_order_market_signs_and_posts():
    cred = _make_cred()
    client = TabdealClient(cred)
    with mock.patch.object(client._session, "request", return_value=_resp(200, {"orderId": 1})) as req:
        out = client.place_order("BTC", is_buy=True, size=0.5)
    assert out["ok"] is True
    _, kwargs = req.call_args
    params = kwargs["params"]
    assert params["symbol"] == "BTCUSDT"
    assert params["side"] == "BUY"
    assert params["type"] == "MARKET"
    assert "signature" in params and "timestamp" in params
    assert kwargs["headers"]["X-MBX-APIKEY"] == "APIKEY123"


@pytest.mark.django_db
def test_rate_limit_retries_then_raises():
    cred = _make_cred()
    client = TabdealClient(cred)
    with mock.patch("time.sleep"), mock.patch.object(
        client._session, "request", return_value=_resp(200, {"code": 1216, "msg": "rate"})
    ) as req:
        out = client.place_order("ETH", is_buy=False, size=1)
    assert out["ok"] is False
    assert req.call_count == 3  # exhausted retries


@pytest.mark.django_db
def test_positions_filters_zero_size():
    cred = _make_cred()
    client = TabdealClient(cred)
    rows = [
        {"symbol": "BTCUSDT", "positionAmt": "0.3", "entryPrice": "50000", "unRealizedProfit": "10"},
        {"symbol": "ETHUSDT", "positionAmt": "0", "entryPrice": "0", "unRealizedProfit": "0"},
    ]
    with mock.patch.object(client._session, "request", return_value=_resp(200, rows)):
        pos = client.positions()
    assert len(pos) == 1
    assert pos[0]["coin"] == "BTCUSDT"
    assert pos[0]["size"] == 0.3
