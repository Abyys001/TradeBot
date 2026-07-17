"""Tests for the Tabdeal Futures (FAPI) client — no real network calls."""
from unittest.mock import MagicMock, patch

import pytest

from .tabdeal_errors import TabdealAPIError, parse_response
from .tabdeal_signing import build_signed_query, sign_query


# ----- signing -----

def test_sign_query_is_deterministic():
    assert sign_query("secret", "a=1&b=2") == sign_query("secret", "a=1&b=2")


def test_sign_query_changes_with_secret():
    assert sign_query("secret1", "a=1") != sign_query("secret2", "a=1")


def test_build_signed_query_includes_signature_and_timestamp():
    query = build_signed_query("secret", {"symbol": "BTCUSDT"})
    assert "symbol=BTCUSDT" in query
    assert "timestamp=" in query
    assert "&signature=" in query


def test_build_signed_query_recv_window_optional():
    assert "recvWindow" not in build_signed_query("s", {"a": 1})
    assert "recvWindow=5000" in build_signed_query("s", {"a": 1}, recv_window_ms=5000)


def test_build_signed_query_drops_none_params():
    assert "price" not in build_signed_query("s", {"symbol": "BTCUSDT", "price": None})


# ----- error parsing -----

def test_parse_response_ok_on_no_code():
    ok, err = parse_response({"positions": []})
    assert ok is True and err is None


def test_parse_response_ok_on_list_like_dict():
    ok, err = parse_response({"canTrade": True})
    assert ok is True


def test_parse_response_known_error_code():
    ok, err = parse_response({"code": 1218, "msg": "Insufficient balance/credit"})
    assert ok is False and err.code == "1218"
    assert "nsufficient" in err.message


def test_parse_response_futures_not_active():
    ok, err = parse_response({"code": 1207, "msg": "Futures not active"})
    assert ok is False and err.code == "1207"


def test_parse_response_unknown_error_code():
    ok, err = parse_response({"code": 9999, "msg": "some new error"})
    assert ok is False and err.code == "9999" and err.message == "some new error"


# ----- futures client -----

def _client():
    from .tabdeal_futures import TabdealFuturesClient

    cred = MagicMock()
    cred.get_api_key.return_value = "test-key"
    cred.get_api_secret.return_value = "test-secret"
    return TabdealFuturesClient(cred)


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    return r


def test_place_market_order_hits_fapi_order_with_params():
    client = _client()
    with patch("apps.exchange.tabdeal_futures.requests.request") as mock_req:
        mock_req.return_value = _resp({"orderId": 123, "status": "FILLED"})
        out = client.place_market_order(symbol="BTC_USDT", side="buy", quantity=0.01)
    assert out["orderId"] == 123
    url = mock_req.call_args.args[1]
    assert url.startswith(client._base_url + "/fapi/v1/order?")
    assert mock_req.call_args.args[0] == "POST"
    assert "type=MARKET" in url and "side=BUY" in url and "symbol=BTC_USDT" in url
    assert mock_req.call_args.kwargs["headers"] == {"X-MBX-APIKEY": "test-key"}


def test_api_error_raised_on_error_envelope():
    client = _client()
    with patch("apps.exchange.tabdeal_futures.requests.request") as mock_req:
        mock_req.return_value = _resp({"code": 1218, "msg": "Insufficient balance/credit"})
        with pytest.raises(TabdealAPIError) as exc:
            client.place_market_order(symbol="BTC_USDT", side="buy", quantity=99.0)
    assert exc.value.info.code == "1218"


def test_available_usdt_reads_futures_balance():
    client = _client()
    with patch("apps.exchange.tabdeal_futures.requests.request") as mock_req:
        mock_req.return_value = _resp([
            {"asset": "BTC", "availableBalance": "0.5"},
            {"asset": "USDT", "availableBalance": "250.75", "walletBalance": "300"},
        ])
        assert client.available_usdt() == 250.75


def test_get_position_filters_zero_amount():
    client = _client()
    with patch("apps.exchange.tabdeal_futures.requests.request") as mock_req:
        mock_req.return_value = _resp([
            {"symbol": "BTC_USDT", "positionAmt": "0"},
        ])
        assert client.get_position("BTC_USDT") is None
        mock_req.return_value = _resp([
            {"symbol": "BTC_USDT", "positionAmt": "0.3", "entryPrice": "50000"},
        ])
        pos = client.get_position("BTC_USDT")
    assert pos and float(pos["positionAmt"]) == 0.3


def test_close_position_uses_delete():
    client = _client()
    with patch("apps.exchange.tabdeal_futures.requests.request") as mock_req:
        mock_req.return_value = _resp({"msg": "success"})
        client.close_position("BTC_USDT")
    assert mock_req.call_args.args[0] == "DELETE"
    assert mock_req.call_args.args[1].startswith(client._base_url + "/fapi/v1/position?")


def test_set_position_sl_tp_requires_a_level():
    client = _client()
    with pytest.raises(ValueError):
        client.set_position_sl_tp(position_id=1)


def test_verify_credentials_ok():
    client = _client()
    with patch("apps.exchange.tabdeal_futures.requests.request") as mock_req:
        mock_req.return_value = _resp({"canTrade": True, "assets": []})
        ok, detail = client.verify_credentials()
    assert ok is True


def test_verify_credentials_futures_not_active():
    client = _client()
    with patch("apps.exchange.tabdeal_futures.requests.request") as mock_req:
        mock_req.return_value = _resp({"code": 1207, "msg": "Futures not active"})
        ok, detail = client.verify_credentials()
    assert ok is False and "1207" in detail
