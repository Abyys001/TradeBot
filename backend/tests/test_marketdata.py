"""Market data (spec §3) — the chart feed and the marked-to-market position.

The suite never reaches a real exchange (``MARKET_DATA.ENABLED`` is False under
pytest), so these tests pin the two things that must hold regardless of who is
serving the data: fake data is always *labelled* as fake, and PnL arithmetic
stays in Decimal.
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
    get_candles,
    get_ticker,
)
from apps.trading.models import Trade, TradeLeg, TradeStatus

KEY = Fernet.generate_key().decode()


def user_client() -> Client:
    User.objects.create_user("boss", password="pw12345!", is_staff=True)
    client = Client()
    assert client.login(username="boss", password="pw12345!")
    return client


# --- fallback labelling -----------------------------------------------------


def test_offline_candles_are_labelled_not_live():
    payload = get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=50)
    assert payload["live"] is False
    assert payload["source"] == "synthetic"
    assert len(payload["candles"]) == 50


def test_offline_ticker_is_labelled_not_live():
    assert get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)["live"] is False


def test_synthetic_series_is_stable_for_a_symbol():
    """Two polls a second apart must not redraw the whole chart."""
    first = get_candles(symbol="ETHUSDT", interval="1m", market=MarketType.FUTURES, limit=30)
    marketdata.cache.clear()
    second = get_candles(symbol="ETHUSDT", interval="1m", market=MarketType.FUTURES, limit=30)
    assert [c["c"] for c in first["candles"]] == [c["c"] for c in second["candles"]]


def test_different_symbols_do_not_draw_the_same_chart():
    a = get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)
    b = get_candles(symbol="LINKUSDT", interval="1m", market=MarketType.FUTURES, limit=20)
    assert [c["c"] for c in a["candles"]] != [c["c"] for c in b["candles"]]


def test_synthetic_ticker_agrees_with_the_last_candle():
    """PnL marks against the ticker; a chart that disagrees invents a profit."""
    feed = get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=100)
    quote = get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
    assert D(feed["candles"][-1]["c"]) == D(quote["price"])


def test_candles_are_oldest_first():
    payload = get_candles(symbol="BTCUSDT", interval="5m", market=MarketType.FUTURES, limit=20)
    times = [c["t"] for c in payload["candles"]]
    assert times == sorted(times)


def test_a_dead_provider_is_not_retried_on_every_request(monkeypatch):
    calls = []

    def explode(self, url, params):
        calls.append(url)
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(marketdata._HttpSource, "_get", explode)
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"]}):
        first = get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)
        marketdata.cache.delete("md:candles:BTCUSDT:1m:futures:20")
        second = get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)

    assert first["live"] is False and second["live"] is False
    # One attempt, then the cooldown holds it off — not one per request.
    assert len(calls) == 1


# --- provider parsing (no network) ------------------------------------------


def test_binance_parses_klines(monkeypatch):
    rows = [[1700000000000, "100.5", "101", "99", "100.75", "12.5", 1700000059999]]
    monkeypatch.setattr(marketdata._HttpSource, "_get", lambda self, url, params: rows)

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
    monkeypatch.setattr(marketdata._HttpSource, "_get", lambda self, url, params: payload)

    candles = BybitPublicSource().candles(
        symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=2
    )
    assert [c.time for c in candles] == [1700000000, 1700000060]


def test_bybit_converts_the_24h_fraction_to_a_percentage(monkeypatch):
    payload = {"retCode": 0, "result": {"list": [{"lastPrice": "100", "price24hPcnt": "0.0125"}]}}
    monkeypatch.setattr(marketdata._HttpSource, "_get", lambda self, url, params: payload)

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
def test_tickers_endpoint_batches_the_watchlist():
    body = user_client().get("/api/trading/market/tickers/?symbols=BTCUSDT,ETHUSDT").json()
    assert [row["symbol"] for row in body["tickers"]] == ["BTCUSDT", "ETHUSDT"]
    assert all(row["live"] is False for row in body["tickers"])


@pytest.mark.django_db
def test_tickers_endpoint_caps_the_symbol_count():
    """A hand-written URL must not turn into a hundred outbound calls."""
    symbols = ",".join(f"SYM{i}USDT" for i in range(60))
    body = user_client().get(f"/api/trading/market/tickers/?symbols={symbols}").json()
    assert len(body["tickers"]) == 30


@pytest.mark.django_db
def test_tickers_endpoint_handles_an_empty_list():
    assert user_client().get("/api/trading/market/tickers/?symbols=").json() == {"tickers": []}


@pytest.mark.django_db
def test_positions_endpoint_is_empty_when_flat():
    body = user_client().get("/api/trading/positions/").json()
    assert body["trade"] is None and body["legs"] == []


@pytest.mark.django_db
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_positions_endpoint_marks_each_leg_to_market():
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

    body = user_client().get("/api/trading/positions/").json()
    mark = D(body["mark"]["price"])
    leg = body["legs"][0]

    assert body["trade"]["id"] == trade.id
    assert D(leg["pnl"]) == (mark - D("100")) * D("0.1")
    assert D(body["totals"]["pnl"]) == D(leg["pnl"])
    assert body["totals"]["accounts"] == 1


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
