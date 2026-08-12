"""Adapter tests against mocked transports.

These check the two things that silently cost real money if wrong:

  1. **Signing.** A bad signature is a rejected order. Each scheme is asserted
     against an independently computed expected value, not against itself.
  2. **Size conversion.** OKX, Gate.io and KuCoin size in *contracts*, not base
     units. Getting the multiplier wrong sizes a position 10x or 100x off.

No network access. Every response is a fixture.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apps.core.money import D
from apps.exchanges.base import (
    MarketType,
    NotSupported,
    OrderType,
    Side,
    WithdrawalPermissionError,
)
from apps.exchanges.binance_family import BinanceAdapter, ToobitAdapter
from apps.exchanges.bybit import BybitAdapter
from apps.exchanges.gateio import GateioAdapter
from apps.exchanges.kucoin import KucoinAdapter
from apps.exchanges.lbank import LbankAdapter
from apps.exchanges.okx import OkxAdapter

pytestmark = pytest.mark.asyncio

KEY, SECRET, PASSPHRASE = "test-key", "test-secret", "test-pass"


def mock(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://mock")


def json_response(payload: dict | list, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


# --- Bybit ------------------------------------------------------------------


async def test_bybit_signature_matches_the_documented_scheme():
    """timestamp + apiKey + recvWindow + queryString, HMAC-SHA256 lowercase hex."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["url"] = str(request.url)
        return json_response({"retCode": 0, "result": {"list": []}})

    adapter = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.request("GET", "/v5/position/list", params={"category": "linear"})

    timestamp = captured["headers"]["X-BAPI-TIMESTAMP"]
    expected = hmac.new(
        SECRET.encode(),
        f"{timestamp}{KEY}5000category=linear".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert captured["headers"]["X-BAPI-SIGN"] == expected
    assert captured["headers"]["X-BAPI-API-KEY"] == KEY


async def test_bybit_post_signs_the_json_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = request.content.decode()
        return json_response({"retCode": 0, "result": {"orderId": "1"}})

    adapter = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.request("POST", "/v5/order/create", body={"symbol": "BTCUSDT"})

    timestamp = captured["headers"]["X-BAPI-TIMESTAMP"]
    expected = hmac.new(
        SECRET.encode(),
        f"{timestamp}{KEY}5000{captured['body']}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert captured["headers"]["X-BAPI-SIGN"] == expected


async def test_bybit_refuses_a_withdrawable_key():
    """Spec §7 is a hard refusal, not a warning."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"retCode": 0, "result": {"permissions": {"Withdraw": ["Withdraw"]}}}
        )

    adapter = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    with pytest.raises(WithdrawalPermissionError):
        await adapter.verify_credentials()


async def test_bybit_accepts_a_trade_only_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"retCode": 0, "result": {"permissions": {"ContractTrade": ["Order"]}}}
        )

    adapter = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.verify_credentials()  # must not raise


async def test_bybit_parses_a_position():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "side": "Buy",
                            "size": "0.5",
                            "avgPrice": "100000",
                            "liqPrice": "90000",
                            "unrealisedPnl": "12.5",
                            "leverage": "10",
                        }
                    ]
                },
            }
        )

    adapter = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    position = await adapter.get_position("BTCUSDT")
    assert position is not None
    assert position.side is Side.LONG
    assert position.size == D("0.5")
    assert position.liquidation_price == D("90000")
    assert position.leverage == 10


async def test_bybit_treats_leverage_not_modified_as_success():
    """110043 means it is already at the requested value — not a failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"retCode": 110043, "retMsg": "leverage not modified"})

    adapter = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.set_leverage("BTCUSDT", 10)  # must not raise


# --- Binance / Toobit -------------------------------------------------------


async def test_binance_signs_the_query_string_and_sends_the_key_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["headers"] = request.headers
        return json_response([])

    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.request("GET", "/fapi/v1/balance")

    query = parse_qs(urlparse(str(captured["url"])).query)
    assert captured["headers"]["X-MBX-APIKEY"] == KEY
    # The signature covers everything except the signature parameter itself.
    unsigned = str(captured["url"]).split("?", 1)[1].rsplit("&signature=", 1)[0]
    expected = hmac.new(SECRET.encode(), unsigned.encode(), hashlib.sha256).hexdigest()
    assert query["signature"][0] == expected


async def test_toobit_uses_its_own_api_key_header():
    """Toobit is Binance-style but the header is X-BB-APIKEY."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return json_response([])

    adapter = ToobitAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.request("GET", "/api/v1/futures/balance")
    assert captured["headers"]["X-BB-APIKEY"] == KEY


async def test_toobit_declares_no_testnet():
    """Q9: the panel must say so rather than pretend one exists."""
    assert ToobitAdapter.capabilities.has_testnet is False
    assert "no test environment" in ToobitAdapter.capabilities.testnet_note


async def test_binance_reads_symbol_filters():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                            {"filterType": "MIN_NOTIONAL", "notional": "100"},
                        ],
                    }
                ]
            }
        )

    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    rules = await adapter.get_symbol_rules("BTCUSDT", MarketType.FUTURES)
    assert rules.price_tick == D("0.10")
    assert rules.qty_step == D("0.001")
    assert rules.min_notional == D("100")


# --- OKX --------------------------------------------------------------------


async def test_okx_signature_is_base64_over_the_iso_prehash():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return json_response({"code": "0", "data": []})

    adapter = OkxAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.request("GET", "/api/v5/account/balance", params={"ccy": "USDT"})

    timestamp = captured["headers"]["OK-ACCESS-TIMESTAMP"]
    message = f"{timestamp}GET/api/v5/account/balance?ccy=USDT"
    expected = base64.b64encode(
        hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()
    assert captured["headers"]["OK-ACCESS-SIGN"] == expected
    assert captured["headers"]["OK-ACCESS-PASSPHRASE"] == PASSPHRASE
    assert timestamp.endswith("Z")


async def test_okx_demo_mode_sets_the_simulated_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return json_response({"code": "0", "data": []})

    adapter = OkxAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, testnet=True, client=mock(handler)
    )
    await adapter.request("GET", "/api/v5/account/config")
    assert captured["headers"]["x-simulated-trading"] == "1"


async def test_okx_maps_symbols_to_instrument_ids():
    adapter = OkxAdapter(api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE,
                        client=mock(lambda r: json_response({})))
    assert adapter._inst_id("BTCUSDT", MarketType.FUTURES) == "BTC-USDT-SWAP"
    assert adapter._inst_id("ETHUSDT", MarketType.SPOT) == "ETH-USDT"
    await adapter.close()


async def test_okx_converts_base_units_to_contracts():
    """ctVal 0.01 BTC per contract: 0.5 BTC is 50 contracts, not 0.5."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "code": "0",
                "data": [
                    {"ctVal": "0.01", "lotSz": "1", "minSz": "1", "tickSz": "0.1", "lever": "10"}
                ],
            }
        )

    adapter = OkxAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    rules = await adapter.get_symbol_rules("BTCUSDT", MarketType.FUTURES)
    # Steps are reported in base units so sizing stays exchange-agnostic.
    assert rules.qty_step == D("0.01")
    assert adapter._to_contracts("BTC-USDT-SWAP", D("0.5")) == "50"


async def test_okx_surfaces_the_inner_error_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"code": "51008", "msg": "", "data": [{"sMsg": "Insufficient margin"}]}
        )

    adapter = OkxAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    with pytest.raises(Exception, match="Insufficient margin"):
        await adapter.request("POST", "/api/v5/trade/order", body={})


# --- KuCoin -----------------------------------------------------------------


async def test_kucoin_signs_and_encrypts_the_passphrase():
    """Key version 2+ requires an HMAC'd, base64 passphrase — plaintext gets 400004."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return json_response({"code": "200000", "data": {}})

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.request("GET", "/api/v1/position", params={"symbol": "XBTUSDTM"})

    timestamp = captured["headers"]["KC-API-TIMESTAMP"]
    expected_sign = base64.b64encode(
        hmac.new(
            SECRET.encode(),
            f"{timestamp}GET/api/v1/position?symbol=XBTUSDTM".encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    expected_pass = base64.b64encode(
        hmac.new(SECRET.encode(), PASSPHRASE.encode(), hashlib.sha256).digest()
    ).decode()

    assert captured["headers"]["KC-API-SIGN"] == expected_sign
    assert captured["headers"]["KC-API-PASSPHRASE"] == expected_pass
    assert captured["headers"]["KC-API-PASSPHRASE"] != PASSPHRASE
    assert captured["headers"]["KC-API-KEY-VERSION"] == "2"


async def test_kucoin_maps_bitcoin_to_its_xbt_contract():
    adapter = KucoinAdapter(api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE,
                           client=mock(lambda r: json_response({})))
    assert adapter._contract("BTCUSDT") == "XBTUSDTM"
    assert adapter._contract("ETHUSDT") == "ETHUSDTM"
    await adapter.close()


async def test_kucoin_converts_contracts_back_to_base_units():
    """multiplier 0.001 BTC: currentQty 500 contracts is 0.5 BTC."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "contracts" in str(request.url):
            return json_response(
                {
                    "code": "200000",
                    "data": {"multiplier": 0.001, "tickSize": 0.1, "maxLeverage": 10},
                }
            )
        return json_response(
            {
                "code": "200000",
                "data": {
                    "currentQty": 500,
                    "avgEntryPrice": 100000,
                    "liquidationPrice": 90000,
                    "unrealisedPnl": 5,
                    "realLeverage": 10,
                },
            }
        )

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.get_symbol_rules("BTCUSDT", MarketType.FUTURES)
    position = await adapter.get_position("BTCUSDT")
    assert position is not None
    assert position.size == D("0.5")
    assert position.side is Side.LONG


# --- Gate.io ----------------------------------------------------------------


async def test_gateio_signature_uses_sha512_over_the_five_line_prehash():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = request.content.decode()
        return json_response({"id": 1, "size": 5, "fill_price": "100000"})

    adapter = GateioAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.request("POST", "/api/v4/futures/usdt/orders", body={"contract": "BTC_USDT"})

    timestamp = captured["headers"]["Timestamp"]
    hashed = hashlib.sha512(captured["body"].encode()).hexdigest()
    message = f"POST\n/api/v4/futures/usdt/orders\n\n{hashed}\n{timestamp}"
    expected = hmac.new(SECRET.encode(), message.encode(), hashlib.sha512).hexdigest()
    assert captured["headers"]["SIGN"] == expected
    assert captured["headers"]["KEY"] == KEY


async def test_gateio_encodes_a_short_as_a_negative_size():
    """Gate has no side field — direction is the sign of size."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "contracts" in str(request.url):
            return json_response(
                {"quanto_multiplier": "0.0001", "order_price_round": "0.1", "leverage_max": "10"}
            )
        captured["body"] = json.loads(request.content)
        return json_response({"id": 7, "size": -5, "fill_price": "100000"})

    adapter = GateioAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.SHORT,
        qty=D("0.0005"),
        order_type=OrderType.MARKET,
    )
    assert captured["body"]["size"] == -5  # 0.0005 / 0.0001 = 5, negative for short
    assert captured["body"]["price"] == "0"
    assert captured["body"]["tif"] == "ioc"


async def test_gateio_maps_symbol_to_underscore_pair():
    adapter = GateioAdapter(api_key=KEY, api_secret=SECRET,
                           client=mock(lambda r: json_response({})))
    assert adapter._contract("BTCUSDT") == "BTC_USDT"
    await adapter.close()


# --- LBank ------------------------------------------------------------------


async def test_lbank_futures_is_refused_with_an_explanation():
    """Q10: no published private futures API, so this must fail loudly."""
    adapter = LbankAdapter(api_key=KEY, api_secret=SECRET,
                          client=mock(lambda r: json_response({})))
    with pytest.raises(NotSupported, match="questions.md Q10"):
        await adapter.get_symbol_rules("BTCUSDT", MarketType.FUTURES)
    with pytest.raises(NotSupported):
        await adapter.close_position("BTCUSDT")
    await adapter.close()


async def test_lbank_declares_spot_only():
    assert MarketType.FUTURES not in LbankAdapter.capabilities.markets
    assert MarketType.SPOT in LbankAdapter.capabilities.markets
    assert LbankAdapter.capabilities.max_leverage == 1


async def test_lbank_echostr_matches_the_documented_length():
    adapter = LbankAdapter(api_key=KEY, api_secret=SECRET,
                          client=mock(lambda r: json_response({})))
    for _ in range(20):
        echostr = adapter._echostr()
        assert 30 <= len(echostr) <= 40
        assert echostr.isalnum()
    await adapter.close()


# --- cross-adapter contract -------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [BinanceAdapter, ToobitAdapter, BybitAdapter, OkxAdapter, KucoinAdapter, GateioAdapter,
     LbankAdapter],
)
async def test_every_adapter_declares_capabilities(cls):
    """The engine branches on these, so a missing declaration is a real bug."""
    capabilities = cls.capabilities
    assert capabilities.markets, f"{cls.__name__} declares no markets"
    assert isinstance(capabilities.has_testnet, bool)
    if not capabilities.has_testnet:
        # Spec §9: the panel must be able to explain why.
        assert capabilities.testnet_note, f"{cls.__name__} has no testnet note"


async def test_rate_limiters_are_per_instance_not_shared():
    """Spec §2: one account exhausting its budget must not throttle another."""
    a = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(lambda r: json_response({})))
    b = BybitAdapter(api_key=KEY, api_secret=SECRET, client=mock(lambda r: json_response({})))
    assert a._limiter is not b._limiter
    assert a._client is not b._client
    await a.close()
    await b.close()
