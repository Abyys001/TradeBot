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
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apps.core.money import D
from apps.exchanges.base import (
    AdapterError,
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


# --- Binance §7 permission check (G3) ---------------------------------------


def _binance(handler) -> BinanceAdapter:
    return BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))


async def test_binance_asks_the_spot_host_for_key_permissions():
    """G3: `/sapi/v1` exists only on the spot host.

    The adapter's base_url is the futures host, so the request went to
    fapi.binance.com/sapi/... and 4xx'd every single time — which meant the
    spec §7 refusal below could never fire and every Binance account landed
    paused with "could not verify credentials".
    """
    seen: list[str] = []
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return json_response({"enableWithdrawals": False, "enableSpotAndMarginTrading": True})

    adapter = _binance(handler)
    real_host_client = adapter.host_client
    adapter.host_client = lambda url: (hosts.append(url), real_host_client(url))[1]

    await adapter.verify_credentials()  # must not raise

    assert hosts == ["https://api.binance.com"], "the permission call stayed on fapi"
    assert urlparse(seen[0]).path == "/sapi/v1/account/apiRestrictions"
    await adapter.close()


async def test_the_spot_host_client_is_a_real_second_client_per_account(monkeypatch):
    """Spec §2 isolation survives the second host: the extra client belongs to
    this adapter instance, is made once, and is closed with the adapter."""
    made: list[str] = []

    class FakeClient:
        def __init__(self, *, base_url: str = "", **_) -> None:
            made.append(base_url)
            self.base_url = base_url
            self.is_closed = False

        async def aclose(self) -> None:
            self.is_closed = True

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET)
    spot = adapter.host_client(adapter.spot_url)

    assert made == ["https://fapi.binance.com", "https://api.binance.com"]
    assert adapter.host_client(adapter.spot_url) is spot, "a new client per call"

    await adapter.close()
    assert spot.is_closed, "the second client outlived the adapter"


async def test_binance_refuses_a_withdrawable_key():
    """Spec §7: proven withdrawable is a hard refusal, as on Bybit."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"enableWithdrawals": True})

    adapter = _binance(handler)
    with pytest.raises(WithdrawalPermissionError):
        await adapter.verify_credentials()
    await adapter.close()


async def test_binance_says_so_when_the_key_cannot_reach_the_spot_host():
    """A futures-only key proves nothing either way — that is NotSupported
    (flagged in the panel), not a broken credential."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."}, 401
        )

    adapter = _binance(handler)
    with pytest.raises(NotSupported, match="no spot API access"):
        await adapter.verify_credentials()
    await adapter.close()


async def test_binance_testnet_does_not_pretend_to_check_permissions():
    adapter = BinanceAdapter(
        api_key=KEY, api_secret=SECRET, testnet=True,
        client=mock(lambda r: json_response({})),
    )
    with pytest.raises(NotSupported, match="testnet"):
        await adapter.verify_credentials()
    await adapter.close()


# --- Q5d: the conditional orders an amend has to take away (G2) -------------


async def test_binance_lists_only_its_own_conditional_orders():
    """A working order the partner placed by hand must survive an SL/TP change."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            [
                {"orderId": 1, "type": "STOP_MARKET"},
                {"orderId": 2, "type": "TAKE_PROFIT_MARKET"},
                {"orderId": 3, "type": "LIMIT"},
            ]
        )

    adapter = _binance(handler)
    assert await adapter.list_conditional_orders("BTCUSDT") == ["1", "2"]
    await adapter.close()


async def test_binance_cancels_each_stale_order_and_shrugs_at_a_gone_one():
    cancelled: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        order_id = parse_qs(urlparse(str(request.url)).query)["orderId"][0]
        cancelled.append(order_id)
        if order_id == "2":
            # Triggered between the snapshot and this call: a race, not a failure.
            return json_response({"code": -2011, "msg": "Unknown order sent."}, 400)
        return json_response({"orderId": order_id, "status": "CANCELED"})

    adapter = _binance(handler)
    await adapter.cancel_orders("BTCUSDT", ["1", "2"])  # must not raise
    assert cancelled == ["1", "2"]
    await adapter.close()


async def test_binance_still_raises_when_a_cancel_genuinely_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"code": -1000, "msg": "An unknown error occurred."}, 400)

    adapter = _binance(handler)
    with pytest.raises(AdapterError):
        await adapter.cancel_orders("BTCUSDT", ["1"])
    await adapter.close()


async def test_okx_no_longer_claims_an_amend_it_never_performs():
    """G2: set_sltp POSTs a fresh OCO to order-algo — it does not call
    amend-algos. The capability flag has to say that, or the platform skips the
    cancel and leaves the replaced stop live on the position."""
    assert OkxAdapter.capabilities.native_sltp_amend is False


async def test_okx_lists_and_cancels_its_algo_orders():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            captured["query"] = parse_qs(urlparse(str(request.url)).query)
            return json_response(
                {"code": "0", "data": [{"algoId": "a1"}, {"algoId": "a2"}]}
            )
        captured["body"] = json.loads(request.content.decode())
        return json_response({"code": "0", "data": [{"algoId": "a1"}]})

    adapter = OkxAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    assert await adapter.list_conditional_orders("BTCUSDT") == ["a1", "a2"]
    assert captured["query"]["ordType"] == ["oco"]

    await adapter.cancel_orders("BTCUSDT", ["a1", "a2"])
    assert captured["body"] == [
        {"algoId": "a1", "instId": "BTC-USDT-SWAP"},
        {"algoId": "a2", "instId": "BTC-USDT-SWAP"},
    ]
    await adapter.close()


async def test_gateio_lists_open_price_triggered_orders_only():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = parse_qs(urlparse(str(request.url)).query)
        return json_response([{"id": 11}, {"id": 12}])

    adapter = GateioAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    assert await adapter.list_conditional_orders("BTCUSDT") == ["11", "12"]
    assert captured["query"] == {"status": ["open"], "contract": ["BTC_USDT"]}
    await adapter.close()


async def test_kucoin_refuses_a_key_that_can_transfer_funds_out():
    """KuCoin *does* publish key permissions — on the spot host
    (`GET /api/v1/user/api-key`, reference/exchanges/kucoin/universal-sdk).
    "Transfer" moves funds out of the account, so spec §7 refuses it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"code": "200000", "data": {"permission": "General,Futures,Spot,Transfer"}}
        )

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    with pytest.raises(WithdrawalPermissionError):
        await adapter.verify_credentials()
    await adapter.close()


async def test_kucoin_accepts_a_trade_only_key():
    """InnerTransfer moves funds between the user's own accounts. It is not a
    withdrawal right and must not be treated as one."""

    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"code": "200000", "data": {"permission": "General,Futures,InnerTransfer"}}
        )

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.verify_credentials()  # must not raise
    await adapter.close()


async def test_kucoin_sandbox_says_it_cannot_check():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"code": "200000", "data": {"availableBalance": "10"}})

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE,
        testnet=True, client=mock(handler),
    )
    with pytest.raises(NotSupported, match="sandbox"):
        await adapter.verify_credentials()
    await adapter.close()


async def test_kucoin_lists_untriggered_stop_orders():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"code": "200000", "data": {"items": [{"id": "s1"}, {"id": "s2"}]}}
        )

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    assert await adapter.list_conditional_orders("BTCUSDT") == ["s1", "s2"]
    await adapter.close()


# --- LBank ------------------------------------------------------------------


async def test_lbank_futures_is_refused_with_an_explanation():
    """Q10: no published private futures API, so this must fail loudly."""
    adapter = LbankAdapter(api_key=KEY, api_secret=SECRET,
                          client=mock(lambda r: json_response({})))
    with pytest.raises(NotSupported, match="questions.md Q10"):
        await adapter.get_symbol_rules("BTCUSDT", MarketType.FUTURES)
    with pytest.raises(NotSupported, match="questions.md Q10"):
        await adapter.set_sltp(symbol="BTCUSDT", stop_loss=D("1"), take_profit=None)
    await adapter.close()


async def test_lbank_spot_round_trip_buys_in_quote_and_sells_in_base():
    """G8: a spot leg has to be closable, or the platform buys one-way.

    LBank's market orders are asymmetric (api/spot.md): a **buy** carries the
    quote amount to spend as `price`, a **sell** carries the base quantity as
    `amount`. Sending a base quantity to a market buy buys the wrong size.
    """
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/supplement/ticker/price.do":
            return json_response({"result": True, "data": [{"price": "100"}]})
        if path == "/v2/accuracy.do":
            return json_response(
                {
                    "result": True,
                    "data": [
                        {
                            "symbol": "btc_usdt",
                            "quantityAccuracy": "4",
                            "priceAccuracy": "2",
                            "minTranQua": "0.001",
                        }
                    ],
                }
            )
        if path == "/v2/supplement/user_info.do":
            return json_response(
                {"result": True, "data": [{"asset": "BTC", "free": "2", "locked": "0"}]}
            )
        sent.append(dict(parse_qs(request.content.decode())))
        return json_response({"result": True, "data": {"order_id": "1"}})

    adapter = LbankAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.SPOT,
        side=Side.LONG,
        qty=D("1.5"),
        order_type=OrderType.MARKET,
    )
    buy = sent[0]
    assert buy["type"] == ["buy_market"]
    assert D(buy["price"][0]) == D("150"), "a market buy spends quote, not base"
    assert "amount" not in buy

    result = await adapter.close_position("BTCUSDT")
    sell = sent[1]
    assert sell["type"] == ["sell_market"]
    assert sell["amount"] == ["1.5"], "a market sell is sized in base"
    assert result.filled_qty == D("1.5")
    await adapter.close()


async def test_lbank_spot_close_never_sells_more_than_the_free_balance():
    """The fallback path: a fresh adapter has no memory of the entry."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/supplement/ticker/price.do":
            return json_response({"result": True, "data": [{"price": "100"}]})
        if path == "/v2/accuracy.do":
            return json_response(
                {
                    "result": True,
                    "data": [
                        {
                            "symbol": "btc_usdt",
                            "quantityAccuracy": "4",
                            "priceAccuracy": "2",
                            "minTranQua": "0.001",
                        }
                    ],
                }
            )
        if path == "/v2/supplement/user_info.do":
            return json_response(
                {"result": True, "data": [{"asset": "BTC", "free": "0.25", "locked": "0"}]}
            )
        return json_response({"result": True, "data": {"order_id": "1"}})

    adapter = LbankAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    result = await adapter.close_position("BTCUSDT")
    assert result.filled_qty == D("0.25")

    empty = LbankAdapter(api_key=KEY, api_secret=SECRET, client=mock(
        lambda r: json_response({"result": True, "data": []})
    ))
    with pytest.raises(AdapterError, match="no BTC balance"):
        await empty.close_position("BTCUSDT")
    await adapter.close()
    await empty.close()


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


# --- Binance: the endpoints, pinned ------------------------------------------
#
# Every test above this block uses a catch-all handler that answers any path.
# That is why the suite stayed green while the adapter called /fapi/v1/balance,
# an endpoint that does not exist. These assert the path itself.


def route(routes: dict, captured: dict | None = None):
    """Handler that answers by path and records what was asked for.

    Anything not in ``routes`` fails the test loudly rather than returning a
    friendly empty body — an adapter calling an endpoint nobody declared is
    exactly the bug class this file exists to catch.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if captured is not None:
            captured.setdefault("paths", []).append(path)
            captured[path] = request
        for prefix, payload in routes.items():
            if path == prefix:
                return json_response(payload)
        return json_response({"code": -1121, "msg": f"unrouted path {path}"}, status=400)

    return handler


async def test_binance_balance_uses_v3_because_v1_does_not_exist():
    captured: dict = {}
    handler = route(
        {"/fapi/v3/balance": [{"asset": "USDT", "availableBalance": "500", "balance": "600"}]},
        captured,
    )
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    balance = await adapter.get_balance()

    assert "/fapi/v3/balance" in captured["paths"]
    # 99% sizing must use what is free, not what includes committed margin.
    assert balance.available == D("500")
    assert balance.total == D("600")


async def test_binance_never_sends_stop_loss_or_take_profit_on_an_entry():
    """POST /fapi/v1/order has no such parameters; sending them is rejected."""
    captured: dict = {}
    handler = route(
        {
            "/fapi/v1/positionSide/dual": {"dualSidePosition": False},
            "/fapi/v1/order": {"orderId": 7, "executedQty": "0.5", "avgPrice": "100"},
        },
        captured,
    )
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    result = await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.5"),
        order_type=OrderType.MARKET,
        stop_loss=D("90"),
        take_profit=D("110"),
    )

    body = captured["/fapi/v1/order"].content.decode()
    assert "stopLoss" not in body and "takeProfit" not in body
    assert "newOrderRespType=RESULT" in body
    # RESULT carries the real fill, so no mark price is invented for the entry.
    assert result.avg_price == D("100")
    assert result.filled_qty == D("0.5")


async def test_binance_hedge_mode_sends_position_side_and_never_reduce_only():
    """-4061 otherwise, on every single order."""
    captured: dict = {}
    handler = route(
        {
            "/fapi/v1/positionSide/dual": {"dualSidePosition": True},
            "/fapi/v1/order": {"orderId": 8, "executedQty": "1", "avgPrice": "100"},
        },
        captured,
    )
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.SHORT,
        qty=D("1"),
        order_type=OrderType.MARKET,
        reduce_only=True,
    )

    body = captured["/fapi/v1/order"].content.decode()
    assert "positionSide=SHORT" in body
    assert "reduceOnly" not in body


async def test_binance_position_reads_v3_and_takes_leverage_from_symbol_config():
    """v3 positionRisk dropped the leverage field; it lives in symbolConfig now."""
    captured: dict = {}
    handler = route(
        {
            "/fapi/v3/positionRisk": [
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "-2",
                    "entryPrice": "100",
                    "liquidationPrice": "150",
                    "unRealizedProfit": "-5",
                }
            ],
            "/fapi/v1/symbolConfig": [{"symbol": "BTCUSDT", "leverage": 7}],
        },
        captured,
    )
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    position = await adapter.get_position("BTCUSDT")

    assert "/fapi/v3/positionRisk" in captured["paths"]
    assert position.side is Side.SHORT
    assert position.size == D("2")
    assert position.leverage == 7


async def test_binance_mark_price_is_the_mark_not_the_last_trade():
    """Stops trigger on MARK_PRICE, so sizing must read the same number."""
    captured: dict = {}
    handler = route({"/fapi/v1/premiumIndex": {"markPrice": "101.5"}}, captured)
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    assert await adapter.get_mark_price("BTCUSDT") == D("101.5")
    assert "/fapi/v1/premiumIndex" in captured["paths"]


async def test_binance_protection_closes_the_whole_position_on_the_mark():
    captured: dict = {}
    orders: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path == "/fapi/v3/positionRisk":
            return json_response([{"symbol": "BTCUSDT", "positionAmt": "1", "entryPrice": "100"}])
        if path == "/fapi/v1/symbolConfig":
            return json_response([{"symbol": "BTCUSDT", "leverage": 5}])
        if path == "/fapi/v1/positionSide/dual":
            return json_response({"dualSidePosition": False})
        if path == "/fapi/v1/order":
            orders.append(request.content.decode())
            return json_response({"orderId": 1})
        return json_response({}, status=404)

    captured["h"] = handler
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    await adapter.set_sltp(symbol="BTCUSDT", stop_loss=D("90"), take_profit=D("110"))

    assert len(orders) == 2
    assert any("type=STOP_MARKET" in o and "stopPrice=90" in o for o in orders)
    assert any("type=TAKE_PROFIT_MARKET" in o and "stopPrice=110" in o for o in orders)
    for order in orders:
        assert "closePosition=true" in order
        assert "workingType=MARK_PRICE" in order
        # closePosition is mutually exclusive with both of these.
        assert "quantity=" not in order and "reduceOnly" not in order


async def test_binance_symbol_rules_take_the_stricter_of_the_two_lot_filters():
    """LOT_SIZE governs limit orders, MARKET_LOT_SIZE market ones."""
    handler = route(
        {
            "/fapi/v1/exchangeInfo": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                            {
                                "filterType": "MARKET_LOT_SIZE",
                                "stepSize": "0.01",
                                "minQty": "0.05",
                            },
                            {"filterType": "MIN_NOTIONAL", "notional": "100"},
                        ],
                    }
                ]
            }
        }
    )
    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    rules = await adapter.get_symbol_rules("BTCUSDT", MarketType.FUTURES)
    assert rules.qty_step == D("0.01")
    assert rules.min_qty == D("0.05")
    assert rules.min_notional == D("100")


async def test_binance_resyncs_its_clock_and_retries_once():
    """A drifting clock rejects every signed call with -1021 and nothing else."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        calls.append(path)
        if path == "/fapi/v1/time":
            return json_response({"serverTime": int(time.time() * 1000) + 9000})
        if calls.count("/fapi/v3/balance") == 1:
            return json_response(
                {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow"},
                status=400,
            )
        return json_response([{"asset": "USDT", "availableBalance": "10", "balance": "10"}])

    adapter = BinanceAdapter(api_key=KEY, api_secret=SECRET, client=mock(handler))
    balance = await adapter.get_balance()

    assert "/fapi/v1/time" in calls
    assert calls.count("/fapi/v3/balance") == 2
    assert balance.available == D("10")


# --- KuCoin: the two order endpoints -----------------------------------------


async def test_kucoin_attaches_sltp_via_st_orders_not_the_plain_order_endpoint():
    """triggerStop* belong to /api/v1/st-orders. The old code invented
    triggerStopLossPrice and sent it to /api/v1/orders, which has neither."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        captured.setdefault("paths", []).append(path)
        if path == "/api/v1/contracts/XBTUSDTM":
            return json_response({"code": "200000", "data": {"multiplier": "0.001",
                                                             "lotSize": "1", "tickSize": "0.1",
                                                             "maxLeverage": "50"}})
        if path.startswith("/api/v1/orders/"):
            # 10 contracts x 0.001 = 0.01 BTC for 1 USDT of value -> 100/BTC.
            return json_response({"code": "200000",
                                  "data": {"dealSize": "10", "dealValue": "1"}})
        captured["body"] = json.loads(request.content.decode())
        return json_response({"code": "200000", "data": {"orderId": "abc"}})

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.010"),
        order_type=OrderType.MARKET,
        stop_loss=D("90"),
        take_profit=D("110"),
    )

    assert "/api/v1/st-orders" in captured["paths"]
    assert "/api/v1/orders" not in captured["paths"]
    body = captured["body"]
    assert "triggerStopLossPrice" not in body
    # Long: take profit is the *up* trigger, stop loss the *down* one.
    assert body["triggerStopUpPrice"] == "110"
    assert body["triggerStopDownPrice"] == "90"


async def test_kucoin_swaps_the_trigger_directions_for_a_short():
    """Up and down are price directions, not TP and SL."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        if path == "/api/v1/contracts/XBTUSDTM":
            return json_response({"code": "200000", "data": {"multiplier": "0.001",
                                                             "lotSize": "1", "tickSize": "0.1"}})
        if path.startswith("/api/v1/orders/"):
            return json_response({"code": "200000", "data": {"dealSize": "0"}})
        if path == "/api/v1/mark-price/XBTUSDTM/current":
            return json_response({"code": "200000", "data": {"value": "100"}})
        captured["body"] = json.loads(request.content.decode())
        return json_response({"code": "200000", "data": {"orderId": "abc"}})

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.SHORT,
        qty=D("0.010"),
        order_type=OrderType.MARKET,
        stop_loss=D("110"),
        take_profit=D("90"),
    )

    body = captured["body"]
    assert body["triggerStopUpPrice"] == "110"  # short: stop loss is above
    assert body["triggerStopDownPrice"] == "90"  # short: target is below


async def test_kucoin_plain_order_when_there_is_no_protection_to_attach():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        captured.setdefault("paths", []).append(path)
        if path == "/api/v1/contracts/XBTUSDTM":
            return json_response({"code": "200000", "data": {"multiplier": "0.001",
                                                             "lotSize": "1", "tickSize": "0.1"}})
        if path.startswith("/api/v1/orders/"):
            # 10 contracts x 0.001 = 0.01 BTC for 1 USDT of value -> 100/BTC.
            return json_response({"code": "200000",
                                  "data": {"dealSize": "10", "dealValue": "1"}})
        return json_response({"code": "200000", "data": {"orderId": "abc"}})

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    result = await adapter.place_order(
        symbol="BTCUSDT",
        market=MarketType.FUTURES,
        side=Side.LONG,
        qty=D("0.010"),
        order_type=OrderType.MARKET,
    )

    assert "/api/v1/orders" in captured["paths"]
    assert "/api/v1/st-orders" not in captured["paths"]
    # Fill read back from the order rather than guessed from the mark price.
    assert result.avg_price == D("100")


async def test_kucoin_set_leverage_actually_calls_the_exchange():
    """It previously assigned an instance attribute and called nothing."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = urlparse(str(request.url)).path
        captured.setdefault("paths", []).append(path)
        captured[path] = json.loads(request.content.decode())
        return json_response({"code": "200000", "data": {}})

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.set_leverage("BTCUSDT", 7)

    assert "/api/v2/changeCrossUserLeverage" in captured["paths"]
    assert captured["/api/v2/changeCrossUserLeverage"]["leverage"] == "7"


async def test_kucoin_signs_delete_query_strings_like_get():
    """base_request.py signs GET and DELETE identically; only GET did here."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["sign"] = request.headers["KC-API-SIGN"]
        captured["ts"] = request.headers["KC-API-TIMESTAMP"]
        return json_response({"code": "200000", "data": {}})

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    await adapter.request("DELETE", "/api/v1/orders", params={"symbol": "XBTUSDTM"})

    expected = base64.b64encode(
        hmac.new(
            SECRET.encode(),
            f"{captured['ts']}DELETE/api/v1/orders?symbol=XBTUSDTM".encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    assert captured["sign"] == expected


async def test_kucoin_refuses_an_inverse_contract():
    """Inverse contracts are margined in the base asset; §5 sizes in USDT."""
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"code": "200000", "data": {"multiplier": "1", "isInverse": True}}
        )

    adapter = KucoinAdapter(
        api_key=KEY, api_secret=SECRET, passphrase=PASSPHRASE, client=mock(handler)
    )
    with pytest.raises(NotSupported):
        await adapter.get_symbol_rules("XBTUSDM", MarketType.FUTURES)
