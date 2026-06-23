"""Tests for the Hyperliquid exchange layer (no live network)."""
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.credentials.models import ExchangeCredential, Network

from . import candles, hl_client


def _make_cred():
    User = get_user_model()
    user = User.objects.create_user(username="bob", password="pw")
    cred = ExchangeCredential(
        user=user,
        label="agent",
        wallet_address="0x" + "11" * 20,
        network=Network.TESTNET,
    )
    cred.set_agent_key("0x" + "aa" * 32)
    cred.save()
    return cred


@pytest.mark.django_db
def test_verify_credential_success_marks_active():
    cred = _make_cred()
    fake_info = mock.Mock()
    fake_info.user_state.return_value = {"marginSummary": {}}

    with mock.patch.object(hl_client, "build_info", return_value=fake_info):
        ok, detail = hl_client.verify_credential(cred)

    assert ok is True
    cred.refresh_from_db()
    assert cred.is_active is True
    assert cred.agent_address
    assert cred.last_verified_at is not None


@pytest.mark.django_db
def test_verify_credential_no_state_marks_inactive():
    cred = _make_cred()
    fake_info = mock.Mock()
    fake_info.user_state.return_value = None

    with mock.patch.object(hl_client, "build_info", return_value=fake_info):
        ok, detail = hl_client.verify_credential(cred)

    assert ok is False
    cred.refresh_from_db()
    assert cred.is_active is False


@pytest.mark.django_db
def test_verify_credential_network_error_is_handled():
    cred = _make_cred()
    with mock.patch.object(hl_client, "build_info", side_effect=ConnectionError):
        ok, detail = hl_client.verify_credential(cred)
    assert ok is False
    assert "failed" in detail


def _hl_candle(ts, o, h, l, c, v="100"):
    return {"t": ts, "o": str(o), "h": str(h), "l": str(l), "c": str(c), "v": str(v)}


def test_fetch_candles_normalizes_hl_response():
    rows = [_hl_candle(3000, 10, 11, 9, 10.5), _hl_candle(2000, 9, 10, 8, 9.5)]
    fake_info = mock.Mock()
    fake_info.candles_snapshot.return_value = rows

    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        df = candles.fetch_candles("BTC", "1m", 2, network="testnet")

    assert len(df) == 2
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df.iloc[0]["ts"] == 2000
    assert df.iloc[1]["close"] == 10.5


def test_fetch_candles_raises_on_error():
    fake_info = mock.Mock()
    fake_info.candles_snapshot.side_effect = RuntimeError("api down")

    with mock.patch("hyperliquid.info.Info", return_value=fake_info):
        with pytest.raises(candles.CandleFetchError):
            candles.fetch_candles("BTC", "1m", 10, network="testnet")


def test_publish_closed_candle_pubsub():
    from apps.exchange import subscriptions

    fake_redis = mock.Mock()
    fake_redis.publish.return_value = 1
    with mock.patch.object(subscriptions, "_client", return_value=fake_redis):
        count = subscriptions.publish_closed_candle(
            network="testnet",
            coin="BTC",
            interval="1m",
            ts=1000,
            open_=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=10,
        )
    assert count == 1
    fake_redis.publish.assert_called_once()
