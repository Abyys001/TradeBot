"""Phase 2 verification tests for the Tabdeal client scaffold (no real network calls)."""
from unittest.mock import MagicMock, patch

from .tabdeal_errors import parse_response
from .tabdeal_signing import build_signed_query, sign_query


def test_sign_query_is_deterministic():
    assert sign_query("secret", "a=1&b=2") == sign_query("secret", "a=1&b=2")


def test_sign_query_changes_with_secret():
    assert sign_query("secret1", "a=1") != sign_query("secret2", "a=1")


def test_build_signed_query_includes_signature_and_timestamp():
    query = build_signed_query("secret", {"symbol": "BTCIRT"}, recv_window_ms=5000)
    assert "symbol=BTCIRT" in query
    assert "timestamp=" in query
    assert "recvWindow=5000" in query
    assert "&signature=" in query


def test_parse_response_ok_on_no_code():
    ok, err = parse_response({"balances": []})
    assert ok is True
    assert err is None


def test_parse_response_known_error_code():
    ok, err = parse_response({"code": -2010, "msg": "Account has insufficient balance"})
    assert ok is False
    assert err is not None
    assert err.code == "-2010"


def test_parse_response_unknown_error_code():
    ok, err = parse_response({"code": -9999, "msg": "some new error"})
    assert ok is False
    assert err.code == "-9999"
    assert err.message == "some new error"


def test_tabdeal_client_signed_request_hits_expected_url():
    from .tabdeal_client import TabdealClient

    credential = MagicMock()
    credential.get_api_key.return_value = "test-key"
    credential.get_api_secret.return_value = "test-secret"

    with patch("apps.exchange.tabdeal_client.requests.request") as mock_request:
        mock_request.return_value.json.return_value = {"code": None, "balances": []}
        client = TabdealClient(credential)
        result = client.get_balance()

    assert result == {}
    called_url = mock_request.call_args.args[1]
    assert called_url.startswith(client._base_url + "/api/v1/account?")
    assert mock_request.call_args.kwargs["headers"] == {"X-MBX-APIKEY": "test-key"}
