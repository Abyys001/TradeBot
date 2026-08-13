"""Market data (spec §3) — the chart feed and the marked-to-market position.

The suite never reaches a real exchange (``MARKET_DATA.ENABLED`` is False under
pytest); a test that wants prices stubs the HTTP transport with ``stub_feed``.

Anything that resolves a *provider* needs ``django_db`` even when it never
looks at a model: preference now starts from the exchanges with active
accounts, and a failed live fetch falls back to downloaded history before it
raises. Both read the database.

What these pin: no price ever reaches a client unless an exchange produced it,
a feed outage is an outage rather than a number, and PnL stays in Decimal.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.test import Client, override_settings

from apps.accounts.models import AccountStatus, ConnectedAccount, Exchange
from apps.core.money import D
from apps.exchanges import marketdata
from apps.exchanges.base import MarketType
from apps.exchanges.marketdata import (
    BinancePublicSource,
    BybitPublicSource,
    MarketDataError,
    get_candles,
    get_ticker,
    provider_latency,
)
from apps.trading.models import Trade, TradeLeg, TradeStatus

KEY = Fernet.generate_key().decode()


def user_client() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


def stub_feed(monkeypatch, *, price: str = "100.5", rtt_ms: float = 42.0):
    """Answer like Binance without a socket, and enable the provider.

    Returns the ``override_settings`` context manager, so a test reads:
    ``with stub_feed(monkeypatch): ...``
    """

    def fake_get(self, url, params):
        marketdata.record_rtt(self.name, rtt_ms)
        if "klines" in url:
            limit = int(params.get("limit") or 20)
            base = 1700000000000
            return [
                [base + i * 60000, price, price, price, price, "1"] for i in range(limit)
            ]
        return {"lastPrice": price, "priceChangePercent": "1.25"}

    monkeypatch.setattr(marketdata.HttpSource, "_get", fake_get)
    return override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"]})


# --- no feed means no price -------------------------------------------------


@pytest.mark.django_db
def test_candles_raise_when_no_provider_answers():
    """Nothing invents a series. The caller has to deal with the outage.

    Needs the database because the live feed failing is not the end of the
    story: ``get_candles`` falls back to downloaded history before giving up,
    and only raises once that is empty too.
    """
    with pytest.raises(MarketDataError):
        get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=50)


def test_ticker_raises_when_no_provider_answers():
    with pytest.raises(MarketDataError):
        get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)


@pytest.mark.django_db
def test_a_served_payload_is_always_real(monkeypatch):
    with stub_feed(monkeypatch):
        payload = get_candles(
            symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20
        )
    assert payload["live"] is True
    assert payload["source"] == "binance"
    assert len(payload["candles"]) == 20


@pytest.mark.django_db
def test_candles_are_oldest_first(monkeypatch):
    with stub_feed(monkeypatch):
        payload = get_candles(
            symbol="BTCUSDT", interval="5m", market=MarketType.FUTURES, limit=20
        )
    times = [c["t"] for c in payload["candles"]]
    assert times == sorted(times)


@pytest.mark.django_db
def test_a_dead_provider_is_not_retried_on_every_request(monkeypatch):
    calls = []

    def explode(self, url, params):
        calls.append(url)
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(marketdata.HttpSource, "_get", explode)
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"]}):
        with pytest.raises(MarketDataError):
            get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)
        with pytest.raises(MarketDataError):
            get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)

    # One attempt, then the cooldown holds it off — not one per request.
    assert len(calls) == 1


# --- measured latency -------------------------------------------------------


@pytest.mark.django_db
def test_provider_latency_is_measured_not_assumed(monkeypatch):
    with stub_feed(monkeypatch, rtt_ms=37.5):
        payload = get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
        assert payload["provider_ms"] == 37.5
        assert provider_latency() == {
            "providers": [{"provider": "binance", "ms": 37.5}],
            "provider": "binance",
            "ms": 37.5,
        }


@pytest.mark.django_db
def test_latency_is_null_when_nothing_was_measured():
    """An old number from a link that has since died is worse than none.

    Needs the database because provider preference now starts from the
    exchanges with active accounts, not just the configured fallbacks.
    """
    assert provider_latency()["ms"] is None


# --- outbound proxy ---------------------------------------------------------
# These exist because an unusable proxy URL is silent and total: httpx raises on
# every request, both providers are marked down, and the panel ends up with no
# prices on a machine that can reach the exchange perfectly well.


def test_a_shell_socks_proxy_is_normalised_to_one_httpx_can_speak(monkeypatch):
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:10808/")
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"], "PROXY": ""}):
        assert marketdata.resolve_proxy() == "socks5://127.0.0.1:10808/"


def test_an_unusable_proxy_is_dropped_rather_than_failing_every_call(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "not a url at all")
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"], "PROXY": ""}):
        assert marketdata.resolve_proxy() is None


def test_a_pinned_proxy_wins_over_the_shell(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1/")
    with override_settings(
        MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"], "PROXY": "http://10.0.0.1:8080"}
    ):
        assert marketdata.resolve_proxy() == "http://10.0.0.1:8080"


# --- provider parsing (no network) ------------------------------------------


def test_binance_parses_klines(monkeypatch):
    rows = [[1700000000000, "100.5", "101", "99", "100.75", "12.5", 1700000059999]]
    monkeypatch.setattr(marketdata.HttpSource, "_get", lambda self, url, params: rows)

    candles = BinancePublicSource().candles(
        symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=1
    )
    assert candles[0].time == 1700000000
    assert candles[0].close == Decimal("100.75")


def test_bybit_reverses_to_oldest_first(monkeypatch):
    payload = {
        "retCode": 0,
        "result": {
            "list": [
                ["1700000060000", "2", "2", "2", "2", "1", "2"],
                ["1700000000000", "1", "1", "1", "1", "1", "1"],
            ]
        },
    }
    monkeypatch.setattr(marketdata.HttpSource, "_get", lambda self, url, params: payload)

    candles = BybitPublicSource().candles(
        symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=2
    )
    assert [c.time for c in candles] == [1700000000, 1700000060]


def test_bybit_converts_the_24h_fraction_to_a_percentage(monkeypatch):
    payload = {"retCode": 0, "result": {"list": [{"lastPrice": "100", "price24hPcnt": "0.0125"}]}}
    monkeypatch.setattr(marketdata.HttpSource, "_get", lambda self, url, params: payload)

    ticker = BybitPublicSource().ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
    assert ticker.change_pct == Decimal("1.25")


# --- endpoints --------------------------------------------------------------


@pytest.mark.django_db
def test_market_endpoints_require_a_session():
    assert Client().get("/api/trading/market/candles/?symbol=BTCUSDT").status_code in (401, 403)


@pytest.mark.django_db
def test_candles_endpoint_rejects_an_unknown_interval():
    assert user_client().get("/api/trading/market/candles/?interval=7s").status_code == 400


@pytest.mark.django_db
def test_candles_endpoint_reports_an_outage_rather_than_inventing_a_chart():
    response = user_client().get("/api/trading/market/candles/?symbol=BTCUSDT")
    assert response.status_code == 503
    assert response.json()["live"] is False
    assert "candles" not in response.json()


@pytest.mark.django_db
def test_ticker_endpoint_reports_an_outage_rather_than_inventing_a_price():
    response = user_client().get("/api/trading/market/ticker/?symbol=BTCUSDT")
    assert response.status_code == 503
    assert "price" not in response.json()


@pytest.mark.django_db
def test_tickers_endpoint_batches_the_watchlist(monkeypatch):
    with stub_feed(monkeypatch):
        body = user_client().get("/api/trading/market/tickers/?symbols=BTCUSDT,ETHUSDT").json()
    assert [row["symbol"] for row in body["tickers"]] == ["BTCUSDT", "ETHUSDT"]
    assert all(row["live"] is True for row in body["tickers"])
    assert body["unavailable"] == []


@pytest.mark.django_db
def test_tickers_endpoint_omits_a_symbol_it_cannot_quote():
    """A row with no quote is named, never filled in with a made-up price."""
    body = user_client().get("/api/trading/market/tickers/?symbols=BTCUSDT,ETHUSDT").json()
    assert body["tickers"] == []
    assert body["unavailable"] == ["BTCUSDT", "ETHUSDT"]


@pytest.mark.django_db
def test_tickers_endpoint_caps_the_symbol_count(monkeypatch):
    """A hand-written URL must not turn into a hundred outbound calls."""
    symbols = ",".join(f"SYM{i}USDT" for i in range(60))
    with stub_feed(monkeypatch):
        body = user_client().get(f"/api/trading/market/tickers/?symbols={symbols}").json()
    assert len(body["tickers"]) == 30


@pytest.mark.django_db
def test_tickers_endpoint_handles_an_empty_list():
    body = user_client().get("/api/trading/market/tickers/?symbols=").json()
    assert body == {"tickers": [], "unavailable": []}


@pytest.mark.django_db
def test_positions_endpoint_is_empty_when_flat():
    body = user_client().get("/api/trading/positions/").json()
    assert body["trade"] is None and body["legs"] == []


@pytest.mark.django_db
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_positions_endpoint_marks_each_leg_to_market(monkeypatch):
    account = ConnectedAccount.objects.create(
        label="partner-a",
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
        last_balance=D("1000"),
        last_balance_asset="USDT",
    )
    trade = Trade.objects.create(
        symbol="BTCUSDT", side="long", market="futures", leverage=10, status=TradeStatus.OPEN
    )
    TradeLeg.objects.create(
        trade=trade,
        account=account,
        ok=True,
        qty=D("0.1"),
        entry_price=D("100"),
        margin=D("1"),
        sltp_attached=True,
    )

    with stub_feed(monkeypatch, price="120"):
        body = user_client().get("/api/trading/positions/").json()
    mark = D(body["mark"]["price"])
    leg = body["legs"][0]

    assert mark == D("120")
    assert body["trade"]["id"] == trade.id
    assert D(leg["pnl"]) == (mark - D("100")) * D("0.1")
    assert D(body["totals"]["pnl"]) == D(leg["pnl"])
    assert body["totals"]["accounts"] == 1


@pytest.mark.django_db
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_positions_endpoint_reports_the_position_but_no_pnl_with_no_feed():
    """The position is a fact; the PnL needs a price. Unknown reads as unknown."""
    account = ConnectedAccount.objects.create(
        label="partner-a",
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
    )
    trade = Trade.objects.create(
        symbol="BTCUSDT", side="long", market="futures", leverage=10, status=TradeStatus.OPEN
    )
    TradeLeg.objects.create(
        trade=trade, account=account, ok=True, qty=D("0.1"), entry_price=D("100"), margin=D("1")
    )

    body = user_client().get("/api/trading/positions/").json()

    assert body["mark"] is None
    assert body["feed_error"]
    assert body["legs"][0]["entry_price"] == "100"
    assert body["legs"][0]["pnl"] is None
    assert body["totals"]["pnl"] is None


@pytest.mark.django_db
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_positions_endpoint_reports_a_leg_that_never_filled():
    account = ConnectedAccount.objects.create(
        label="too-small",
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
    )
    trade = Trade.objects.create(
        symbol="BTCUSDT", side="long", market="futures", leverage=10, status=TradeStatus.OPEN
    )
    TradeLeg.objects.create(
        trade=trade, account=account, ok=False, error="below minimum notional"
    )

    body = user_client().get("/api/trading/positions/").json()
    assert body["totals"]["failed"] == 1
    assert body["legs"][0]["pnl"] is None
    assert body["legs"][0]["error"] == "below minimum notional"
