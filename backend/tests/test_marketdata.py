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

import time
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
from apps.exchanges.catalogue import HistoryRequest, HistoryRequestStatus
from apps.exchanges.marketdata import (
    BinancePublicSource,
    BybitPublicSource,
    MarketDataError,
    SymbolNotListed,
    get_candles,
    get_ticker,
    provider_latency,
)
from apps.trading.models import StoredCandle, Trade, TradeLeg, TradeStatus

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


def history_feed(monkeypatch, *, days: int = 1):
    """A stub whose klines are *recent* and page back past the download span.

    ``stub_feed`` is pinned to November 2023, but ``backfill_series`` filters to
    the last ``days`` and would store nothing from it. This one is anchored to
    now and honours the ``end`` page cursor, so a 1-day walk actually reaches
    its floor and stops.
    """

    def fake_get(self, url, params):
        marketdata.record_rtt(self.name, 10.0)
        if "klines" in url:
            limit = int(params.get("limit") or 1000)
            step = 60000
            end_ms = int(params.get("endTime") or 0) or int(time.time()) * 1000
            # Real exchanges align bars to the epoch grid and never serve one
            # *after* endTime. Without the alignment the paged walk misses the
            # floor by up to a step and a covered pair keeps re-downloading.
            newest = (end_ms // step) * step
            base = newest - step * (limit - 1)
            return [
                [base + i * step, "100", "100", "100", "100", "1"] for i in range(limit)
            ]
        return {"lastPrice": "100", "priceChangePercent": "1.25"}

    monkeypatch.setattr(marketdata.HttpSource, "_get", fake_get)
    return override_settings(
        MARKET_DATA={
            "ENABLED": True,
            "PROVIDERS": ["binance"],
            "BACKFILL_INTERVALS": ["1m", "5m", "15m", "1h", "4h", "1d"],
            "CHART_BACKFILL_DAYS": days,
        }
    )


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


@pytest.mark.django_db
def test_an_unlisted_pair_does_not_take_the_provider_down(monkeypatch):
    """One pair the venue does not list must not cost every other pair its feed.

    This is the BMBUSDC case from the live log: a watchlist entry Hyperliquid
    has no market for made the *provider* cool off, and with MARKET_DATA_PIN
    there is nothing behind it — so /market/ticker/ answered 503 for BTCUSDT
    too, and the log filled with one WARNING per poll.
    """
    calls = []

    def answer(self, url, params):
        symbol = str(params.get("symbol") or "")
        calls.append(symbol or url)
        if "NOSUCH" in symbol:
            raise SymbolNotListed("binance: no market for NOSUCHUSDT")
        base = 1700000000000
        return [[base + i * 60000, "100", "100", "100", "100", "1"] for i in range(20)]

    monkeypatch.setattr(marketdata.HttpSource, "_get", answer)
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"]}):
        with pytest.raises(MarketDataError):
            get_candles(
                symbol="NOSUCHUSDT", interval="1m", market=MarketType.FUTURES, limit=20
            )
        # The very next request, for a pair the venue *does* list, still works.
        payload = get_candles(
            symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20
        )

    assert payload["candles"]
    assert len(calls) == 2


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


# --- the pinned venue -------------------------------------------------------
# A pin exists so the chart cannot change exchange behind the admin's back. The
# default arrangement quotes whichever venue the accounts sit on, which means
# connecting one Bybit key silently re-prices every chart — and a Bybit mark
# compared against a Hyperliquid fill is a different number that sizing reads.


@pytest.mark.django_db
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_pinned_venue_outranks_a_connected_exchange():
    ConnectedAccount.objects.create(
        label="bybit-1",
        exchange=Exchange.BYBIT,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
    )
    with override_settings(
        MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"], "PIN": "hyperliquid"}
    ):
        assert marketdata._configured_providers() == ["hyperliquid"]


@pytest.mark.django_db
def test_a_pin_has_no_fallback_behind_it():
    """That is the point of it: one venue answers, or the panel says so."""
    with override_settings(
        MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance", "bybit"], "PIN": "bybit"}
    ):
        assert marketdata._configured_providers() == ["bybit"]


@pytest.mark.django_db
def test_a_pin_naming_an_unknown_venue_is_ignored_not_fatal():
    """A typo in `.env` must not take every price down."""
    with override_settings(
        MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"], "PIN": "hyperliqiud"}
    ):
        assert marketdata._configured_providers() == ["binance"]


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
def test_positions_endpoint_names_the_leg_an_amend_did_not_reach():
    """An amend is a fan-out, so it can miss one account.

    The trade carries the new percentages the moment the amend is saved; a leg
    whose own amend failed keeps the prices it actually holds. Without a flag
    the panel draws the new line over an exchange resting on the old one — the
    exact desync the per-leg read-back exists to expose.
    """
    moved, missed = (
        ConnectedAccount.objects.create(
            label=label,
            exchange=Exchange.PAPER,
            status=AccountStatus.ACTIVE,
            withdrawal_check_passed=True,
        )
        for label in ("moved", "missed")
    )
    trade = Trade.objects.create(
        symbol="BTCUSDT",
        side="long",
        market="futures",
        leverage=10,
        status=TradeStatus.OPEN,
        sl_pct=D("2"),
        tp_pct=D("4"),
        sltp_basis="price",
        admin_entry_price=D("100"),
    )
    # Both filled at 100, so a 2% price stop is 98 and a 4% target is 104.
    for account, stop in ((moved, D("98")), (missed, D("99"))):
        TradeLeg.objects.create(
            trade=trade,
            account=account,
            ok=True,
            qty=D("0.1"),
            entry_price=D("100"),
            margin=D("1"),
            sltp_attached=True,
            sltp_verified=True,
            stop_loss=stop,
            take_profit=D("104"),
        )

    legs = {
        leg["account_label"]: leg
        for leg in user_client().get("/api/trading/positions/").json()["legs"]
    }

    assert legs["moved"]["sltp_stale"] is False
    assert legs["missed"]["sltp_stale"] is True


@pytest.mark.django_db
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_a_leg_with_no_protection_read_back_is_not_called_stale():
    """Unknown is not stale — ``sltp_verified`` already says it was never confirmed."""
    account = ConnectedAccount.objects.create(
        label="silent",
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
    )
    trade = Trade.objects.create(
        symbol="BTCUSDT",
        side="long",
        market="futures",
        leverage=10,
        status=TradeStatus.OPEN,
        sl_pct=D("2"),
        tp_pct=D("4"),
        admin_entry_price=D("100"),
    )
    TradeLeg.objects.create(
        trade=trade,
        account=account,
        ok=True,
        qty=D("0.1"),
        entry_price=D("100"),
        margin=D("1"),
        sltp_attached=False,
    )

    leg = user_client().get("/api/trading/positions/").json()["legs"][0]

    assert leg["sltp_stale"] is False


@pytest.mark.django_db
@override_settings(CREDENTIAL_ENCRYPTION_KEYS=[KEY])
def test_positions_endpoint_reports_a_leg_that_never_filled():
    account = ConnectedAccount.objects.create(
        label="too-small",
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
    )
    # A second account that did fill, so the trade is a real open trade. With
    # only the sized-out leg there is no position anywhere, and the poll
    # retires the trade rather than showing one — see
    # test_a_trade_nothing_can_be_holding_is_retired_on_the_positions_poll.
    filled = ConnectedAccount.objects.create(
        label="filled",
        exchange=Exchange.PAPER,
        status=AccountStatus.ACTIVE,
        withdrawal_check_passed=True,
    )
    trade = Trade.objects.create(
        symbol="BTCUSDT", side="long", market="futures", leverage=10, status=TradeStatus.OPEN
    )
    TradeLeg.objects.create(
        trade=trade,
        account=account,
        ok=False,
        error="below minimum notional",
        # A sized-out leg is *provably* flat, so the endpoint's re-check leaves
        # it alone. Without the code it would read as unconfirmed and be asked
        # about — see test_an_unconfirmed_leg_is_re_checked_on_the_positions_poll.
        error_code="below_min_notional",
    )
    TradeLeg.objects.create(
        trade=trade,
        account=filled,
        ok=True,
        qty=Decimal("0.01"),
        entry_price=Decimal("100"),
        margin=Decimal("99"),
    )

    body = user_client().get("/api/trading/positions/").json()
    assert body["totals"]["failed"] == 1
    sized_out = next(row for row in body["legs"] if row["account"] == account.id)
    assert sized_out["pnl"] is None
    assert sized_out["error"] == "below minimum notional"


# --- on-demand chart history -------------------------------------------------
# Opening a chart on a pair the bulk backfill never reached queues that pair's
# own download (at least a day across every timeframe, chart timeframe first),
# and the candles endpoint answers 202 until the worker has stored something.
# These never touch a real exchange and never start a real thread: the worker
# is stubbed out and ``run_history_request`` is driven by hand, which is also
# how the race-free assertions below stay deterministic.

CHART_SETTINGS = {
    "ENABLED": True,
    "PROVIDERS": ["binance"],
    "BACKFILL_INTERVALS": ["1m", "5m", "15m", "1h", "4h", "1d"],
    "CHART_BACKFILL_DAYS": 1,
}
ALL_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


@pytest.mark.django_db
def test_chart_history_is_downloaded_on_demand(monkeypatch):
    from apps.exchanges import catalogue

    monkeypatch.setattr(catalogue, "_ensure_worker", lambda: None)

    with history_feed(monkeypatch):
        status = catalogue.ensure_history("futures", "SHIBUSDT", "1m")
        assert status["state"] == "downloading"

        job = HistoryRequest.objects.get(symbol="SHIBUSDT")
        assert job.priority_interval == "1m"

        catalogue.run_history_request(job.pk)
        job.refresh_from_db()

    assert job.status == HistoryRequestStatus.DONE
    assert job.series_done == job.series_total == len(ALL_INTERVALS)
    assert job.bars_written > 0
    stored = set(
        StoredCandle.objects.filter(symbol="SHIBUSDT").values_list("interval", flat=True)
    )
    assert stored == ALL_INTERVALS


@pytest.mark.django_db
def test_candles_endpoint_answers_202_while_history_downloads(monkeypatch):
    from apps.exchanges import catalogue

    monkeypatch.setattr(catalogue, "_ensure_worker", lambda: None)
    client = user_client()

    def explode(self, url, params):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(marketdata.HttpSource, "_get", explode)
    with override_settings(MARKET_DATA=CHART_SETTINGS):
        response = client.get("/api/trading/market/candles/?symbol=SHIBUSDT")

    assert response.status_code == 202
    body = response.json()
    assert body["live"] is False
    assert body["candles"] == []
    assert body["history"]["state"] == "downloading"
    assert HistoryRequest.objects.filter(symbol="SHIBUSDT").count() == 1


@pytest.mark.django_db
def test_candles_endpoint_serves_downloaded_history_once_ready(monkeypatch):
    from apps.exchanges import catalogue

    monkeypatch.setattr(catalogue, "_ensure_worker", lambda: None)
    client = user_client()

    with history_feed(monkeypatch):
        catalogue.ensure_history("futures", "SHIBUSDT", "1m")
        job = HistoryRequest.objects.get(symbol="SHIBUSDT")
        catalogue.run_history_request(job.pk)
        job.refresh_from_db()
        assert job.status == HistoryRequestStatus.DONE

    def explode(self, url, params):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(marketdata.HttpSource, "_get", explode)
    with override_settings(MARKET_DATA=CHART_SETTINGS):
        response = client.get("/api/trading/market/candles/?symbol=SHIBUSDT")

    assert response.status_code == 200
    body = response.json()
    assert body["live"] is False
    assert body["stored"] is True
    assert len(body["candles"]) > 0
    assert body["history"]["state"] == "ready"


@pytest.mark.django_db
def test_a_pair_already_covered_by_stored_history_is_ready_not_redownloaded(monkeypatch):
    from apps.exchanges import catalogue

    now = int(time.time())
    StoredCandle.objects.create(
        exchange="binance",
        market="futures",
        symbol="SHIBUSDT",
        interval="1m",
        open_time=now - 2 * 86400,
        open=D("0.1"),
        high=D("0.1"),
        low=D("0.1"),
        close=D("0.1"),
        volume=D("1"),
    )

    with history_feed(monkeypatch):
        status = catalogue.ensure_history("futures", "SHIBUSDT", "1m")

    assert status["state"] == "ready"
    assert not HistoryRequest.objects.filter(symbol="SHIBUSDT").exists()


@pytest.mark.django_db
def test_a_failed_download_is_not_re_requested_on_every_poll(monkeypatch):
    from apps.exchanges import catalogue

    monkeypatch.setattr(catalogue, "_ensure_worker", lambda: None)
    client = user_client()

    def explode(self, url, params):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(marketdata.HttpSource, "_get", explode)
    with override_settings(MARKET_DATA=CHART_SETTINGS):
        assert client.get("/api/trading/market/candles/?symbol=SHIBUSDT").status_code == 202

        job = HistoryRequest.objects.get(symbol="SHIBUSDT")
        catalogue._finish_request(job, HistoryRequestStatus.FAILED, error="boom")

        response = client.get("/api/trading/market/candles/?symbol=SHIBUSDT")

    assert response.status_code == 503
    assert HistoryRequest.objects.filter(symbol="SHIBUSDT").count() == 1


@pytest.mark.django_db
def test_a_finished_download_is_not_queued_again_however_short_the_history(monkeypatch):
    """The stuck "Downloading history…" banner, pinned.

    ``_series_covered`` asks whether the archive reaches back
    CHART_BACKFILL_DAYS. For a pair the venue simply does not have that much
    history for — a recent listing, or Hyperliquid, which keeps 5000 bars per
    interval and no more — the answer is no however many times it is
    downloaded. So every chart poll queued the same job again, forever, and the
    panel showed a download that never ended over a chart that was already
    complete and quoting correctly.
    """
    from apps.exchanges import catalogue

    monkeypatch.setattr(catalogue, "_ensure_worker", lambda: None)

    # A venue with three bars and nothing older, against a 365-day backfill: the
    # coverage test can never pass, and that is a fact about the pair.
    def short_history(self, url, params):
        marketdata.record_rtt(self.name, 5.0)
        if "klines" in url:
            newest = (int(time.time()) // 60) * 60 * 1000
            return [[newest - i * 60000, "1", "1", "1", "1", "1"] for i in (2, 1, 0)]
        return {"lastPrice": "1", "priceChangePercent": "0"}

    monkeypatch.setattr(marketdata.HttpSource, "_get", short_history)
    settings = override_settings(
        MARKET_DATA={
            "ENABLED": True,
            "PROVIDERS": ["binance"],
            "BACKFILL_INTERVALS": ["1m"],
            "CHART_BACKFILL_DAYS": 365,
        }
    )
    with settings:
        catalogue.ensure_history("futures", "SHIBUSDT", "1m")
        job = HistoryRequest.objects.get(symbol="SHIBUSDT")
        catalogue.run_history_request(job.pk)
        job.refresh_from_db()
        assert job.status == HistoryRequestStatus.DONE

        # The next poll, and the one after it.
        first = catalogue.ensure_history("futures", "SHIBUSDT", "1m")
        second = catalogue.ensure_history("futures", "SHIBUSDT", "1m")

    assert first["state"] == "ready", "a finished download must stop reading as downloading"
    assert second["state"] == "ready"
    assert HistoryRequest.objects.filter(symbol="SHIBUSDT").count() == 1


@pytest.mark.django_db
def test_the_timeframe_the_chart_is_on_is_downloaded_even_when_it_is_derived(monkeypatch):
    """Opening a 30m chart used to queue a job that stored every interval but
    that one, so its coverage test could never pass either."""
    from apps.exchanges import catalogue

    monkeypatch.setattr(catalogue, "_ensure_worker", lambda: None)
    with history_feed(monkeypatch):
        catalogue.ensure_history("futures", "SHIBUSDT", "30m")

    job = HistoryRequest.objects.get(symbol="SHIBUSDT")
    assert "30m" in job.intervals.split(",")
    assert job.priority_interval == "30m"
    assert job.series_total == len(job.intervals.split(","))


@pytest.mark.django_db
def test_the_chart_timeframe_takes_priority(monkeypatch):
    from apps.exchanges import catalogue

    monkeypatch.setattr(catalogue, "_ensure_worker", lambda: None)

    with history_feed(monkeypatch):
        catalogue.ensure_history("futures", "SHIBUSDT", "1m")
        job = HistoryRequest.objects.get(symbol="SHIBUSDT")
        assert job.priority_interval == "1m"

        status = catalogue.ensure_history("futures", "SHIBUSDT", "4h")
        job.refresh_from_db()

    assert job.priority_interval == "4h"
    assert status["state"] == "downloading"
    assert HistoryRequest.objects.filter(symbol="SHIBUSDT").count() == 1


# --- a pinned venue is the only venue ---------------------------------------
#
# What froze the chart in production: one slow call put the pinned provider in
# cooldown, and with no second provider the panel spent the next minute on
# stored history while the ticker kept quoting a live price. These pin the two
# halves of that fix.


def _cooldowns(monkeypatch) -> dict[str, int | None]:
    """Record how long each provider is held off for, per `_mark_down`."""
    seen: dict[str, int | None] = {}
    original = marketdata.cache.set

    def spy(key, value, timeout=None, *args, **kwargs):
        if str(key).startswith("md:down:"):
            seen[str(key)] = timeout
        return original(key, value, timeout, *args, **kwargs)

    monkeypatch.setattr(marketdata.cache, "set", spy)
    return seen


@pytest.mark.django_db
def test_the_only_provider_is_held_off_briefly_not_for_a_minute(monkeypatch):
    """A pin leaves one venue, and it is the one we have to keep asking.

    A minute here is longer than four candle polls, so a single slow call cost
    the chart a minute of live bars while the ticker went on quoting — the panel
    then drew an old series under a current price.
    """
    seen = _cooldowns(monkeypatch)

    def explode(self, url, params):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(marketdata.HttpSource, "_get", explode)
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"]}):
        with pytest.raises(MarketDataError):
            get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)

    assert seen["md:down:binance"] == marketdata.SOLE_COOLDOWN
    assert marketdata.SOLE_COOLDOWN < 15  # shorter than the panel's candle poll


@pytest.mark.django_db
def test_a_provider_with_a_fallback_behind_it_keeps_the_full_cooldown(monkeypatch):
    """Where there *is* something to fall back to, the long hold-off still earns its keep."""
    seen = _cooldowns(monkeypatch)

    def only_bybit_answers(self, url, params):
        if self.name == "binance":
            raise httpx.ConnectError("no route to host")
        marketdata.record_rtt(self.name, 10.0)
        return {"result": {"list": [{"lastPrice": "100", "prevPrice24h": "99"}]}}

    monkeypatch.setattr(marketdata.HttpSource, "_get", only_bybit_answers)
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance", "bybit"]}):
        assert get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)["source"] == "bybit"

    assert seen["md:down:binance"] == marketdata.COOLDOWN


@pytest.mark.django_db
def test_stored_history_from_another_venue_is_not_served_under_a_pin(monkeypatch):
    """A pin names who may answer for this pair — downloads included.

    Binance history behind a chart badged Hyperliquid is the substitution the
    pin exists to prevent, and sizing reads that number.
    """
    now = int(time.time())
    for i in range(5):
        StoredCandle.objects.create(
            exchange="binance",
            market="futures",
            symbol="BTCUSDT",
            interval="1m",
            open_time=now - (5 - i) * 60,
            open=D("100"),
            high=D("100"),
            low=D("100"),
            close=D("100"),
            volume=D("1"),
        )

    def explode(self, *args, **kwargs):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(marketdata.HttpSource, "_get", explode)
    monkeypatch.setattr(marketdata.HttpSource, "_post", explode)

    with override_settings(
        MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"], "PIN": "hyperliquid"}
    ):
        with pytest.raises(MarketDataError):
            get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=50)

    # Unpinned, the same stored bars are the honest degraded answer.
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["binance"]}):
        payload = get_candles(
            symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=50
        )
    assert payload["stored"] is True
    assert payload["source"] == "binance"


@pytest.mark.django_db
def test_a_watchlist_refresh_downloads_the_hyperliquid_universe_once(monkeypatch):
    """One quote costs the whole perp universe on this venue; N must not cost N.

    A ten-pair watchlist made ten 70 KB round trips per refresh, each of them
    over a second, which is enough on its own to look like a dead feed.
    """
    posts = []

    def fake_post(self, url, body):
        posts.append(body["type"])
        marketdata.record_rtt(self.name, 10.0)
        if body["type"] == "meta":
            return {"universe": [{"name": "BTC"}, {"name": "ETH"}]}
        return [
            {"universe": [{"name": "BTC"}, {"name": "ETH"}]},
            [{"markPx": "100", "prevDayPx": "99"}, {"markPx": "10", "prevDayPx": "9"}],
        ]

    monkeypatch.setattr(marketdata.HttpSource, "_post", fake_post)
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["hyperliquid"]}):
        btc = get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
        eth = get_ticker(symbol="ETHUSDT", market=MarketType.FUTURES)

    assert btc["price"] == "100"
    assert eth["price"] == "10"
    # `meta` is the name map (which spelling of the coin this venue answers to),
    # cached for ten minutes; the universe itself is the quote. Both are shared
    # across symbols, which is the point: two quotes, not four downloads.
    assert posts == ["meta", "metaAndAssetCtxs"]


@pytest.mark.django_db
def test_hyperliquid_is_asked_for_the_coin_name_it_actually_answers_to(monkeypatch):
    """``KSHIBUSDT`` is not a coin on this venue; ``kSHIB`` is.

    Hyperliquid names its 1000x perps with a lowercase ``k`` and is
    case-sensitive about it, while everything else here uppercases symbols —
    including this platform's own catalogue, which stored the pair as
    ``KSHIBUSDT``. Asking for ``KSHIB`` is an **HTTP 500**, which reads as the
    venue being down, and under MARKET_DATA_PIN there is nothing behind it.
    """
    asked = []

    def fake_post(self, url, body):
        marketdata.record_rtt(self.name, 10.0)
        if body["type"] == "meta":
            return {"universe": [{"name": "BTC"}, {"name": "kSHIB"}]}
        asked.append(body["req"]["coin"])
        base = 1700000000000
        return [
            {"t": base + i * 60000, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}
            for i in range(5)
        ]

    monkeypatch.setattr(marketdata.HttpSource, "_post", fake_post)
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["hyperliquid"]}):
        get_candles(symbol="KSHIBUSDT", interval="1m", market=MarketType.FUTURES, limit=5)
        # And the way *other* venues write the same 1000x perp, which is what
        # the picker offers whenever a Binance or Bybit catalogue is downloaded.
        get_candles(symbol="1000SHIBUSDT", interval="1m", market=MarketType.FUTURES, limit=5)

    assert asked == ["kSHIB", "kSHIB"]


@pytest.mark.django_db
def test_a_pair_the_pinned_venue_does_not_list_is_not_an_outage(monkeypatch):
    """404, not 503 — and the venue is not marked down over it.

    "No exchange is reachable" and "this venue has no such market" are
    different facts and only the first is a fault. Answering 503 to the second
    logged an ERROR per poll from two loggers, so a panel doing exactly what it
    should reported a system error every two seconds; and marking the provider
    down over it took every *other* pair's price with it.
    """

    def fake_post(self, url, body):
        marketdata.record_rtt(self.name, 10.0)
        if body["type"] == "meta":
            return {"universe": [{"name": "BTC"}]}
        return [
            {"universe": [{"name": "BTC"}]},
            [{"markPx": "100", "prevDayPx": "99"}],
        ]

    monkeypatch.setattr(marketdata.HttpSource, "_post", fake_post)
    client = user_client()
    with override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["hyperliquid"]}):
        response = client.get("/api/trading/market/ticker/?symbol=1000CATUSDT")
        assert response.status_code == 404
        assert response.json()["listed"] is False
        assert "price" not in response.json()

        candles = client.get("/api/trading/market/candles/?symbol=1000CATUSDT")
        assert candles.status_code == 404

        # The pair nobody lists did not cost the pair everybody does.
        assert client.get("/api/trading/market/ticker/?symbol=BTCUSDT").status_code == 200


# --- a venue that flaps is not a fault of this platform ----------------------
#
# Hyperliquid answered HTTP 502, then timed out, for about two minutes. The
# pinned feed has no fallback by design, so every ticker poll became a 503 —
# and every 503 wrote two ERROR rows, one from the access middleware and one
# from ``django.request``, each of which Telegram sends as "System error". One
# upstream blip, forty alerts, a blank price, and a `_mark_down` WARNING per
# attempt underneath it. These pin all four halves of the answer.


def flapping_feed(monkeypatch, *, fail: list[bool], price: str = "100"):
    """A Hyperliquid stub whose calls fail while ``fail[0]`` is True."""

    def fake_post(self, url, body):
        if fail[0]:
            raise MarketDataError("hyperliquid: HTTP 502")
        marketdata.record_rtt(self.name, 10.0)
        if body["type"] == "meta":
            return {"universe": [{"name": "BTC"}]}
        return [
            {"universe": [{"name": "BTC"}]},
            [{"markPx": price, "prevDayPx": "99"}],
        ]

    monkeypatch.setattr(marketdata.HttpSource, "_post", fake_post)
    return override_settings(MARKET_DATA={"ENABLED": True, "PROVIDERS": ["hyperliquid"]})


def next_poll(symbol: str = "BTCUSDT") -> None:
    """What three seconds passing looks like.

    Two caches sit in front of a quote: the quote itself, and the whole-universe
    payload one Hyperliquid call shares across every symbol on the watchlist.
    Both have to expire for the next poll to reach the venue at all.
    """
    marketdata.cache.delete(f"md:ticker:{symbol}:futures")
    marketdata.cache.delete(marketdata.SOURCES["hyperliquid"]._CTX_KEY)


@pytest.mark.django_db
def test_the_last_real_quote_covers_a_venue_that_stops_answering(monkeypatch):
    """The chart has always had this; the price had nothing.

    Downloaded history is served when the live feed is down, labelled
    ``live: false``, because a stored bar is old rather than invented. A quote
    is the same kind of thing. Inside the grace it is served with its age; it
    never claims to be live.
    """
    fail = [False]
    with flapping_feed(monkeypatch, fail=fail):
        fresh = get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
        assert fresh["live"] is True and fresh["price"] == "100"

        # Past the three-second quote cache, with the venue now dead.
        next_poll()
        fail[0] = True
        stale = get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)

    assert stale["price"] == "100"
    assert stale["live"] is False and stale["stale"] is True
    assert stale["age_s"] < marketdata.TICKER_GRACE
    assert "502" in stale["feed_error"]


@pytest.mark.django_db
def test_past_the_grace_there_is_no_price_at_all(monkeypatch):
    """The grace is a window, not a memory. Old enough, and it is an outage."""
    fail = [False]
    with flapping_feed(monkeypatch, fail=fail):
        get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
        next_poll()
        # Age the stored quote past the window rather than sleeping a minute.
        key = marketdata._last_ticker_key("BTCUSDT", MarketType.FUTURES)
        aged = dict(marketdata.cache.get(key))
        aged["at"] = int(time.time()) - marketdata.TICKER_GRACE - 1
        marketdata.cache.set(key, aged, marketdata.TICKER_GRACE)
        fail[0] = True
        with pytest.raises(MarketDataError):
            get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)


@pytest.mark.django_db
def test_a_stale_quote_is_never_used_to_size_or_to_measure_drift(monkeypatch):
    """Good enough to look at, never good enough to trade on.

    Both callers already refuse anything that is not ``live`` — that flag is
    what makes serving the last quote safe at all, so it is pinned here rather
    than left to be re-derived.
    """
    from apps.bots.riskgate import _ticker_price
    from apps.trading.services import _reference_price

    fail = [False]
    with flapping_feed(monkeypatch, fail=fail):
        get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
        next_poll()
        fail[0] = True

        assert get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)["stale"] is True
        assert _ticker_price("BTCUSDT", MarketType.FUTURES.value) is None
        assert _reference_price.func("BTCUSDT", MarketType.FUTURES) is None


@pytest.mark.django_db
def test_an_outage_is_reported_once_not_once_per_poll(monkeypatch, caplog):
    """One line when it goes, one when it comes back.

    The cooldown key cannot double as the throttle: it expires every few
    seconds so the next poll retries, which is the whole point of it.
    """
    fail = [True]
    with flapping_feed(monkeypatch, fail=fail):
        with caplog.at_level("WARNING", logger="apps.exchanges.marketdata"):
            for _ in range(5):
                next_poll()
                marketdata.cache.delete("md:down:hyperliquid")
                with pytest.raises(MarketDataError):
                    get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
        down = [r for r in caplog.records if "unavailable" in r.getMessage()]
        assert len(down) == 1

        caplog.clear()
        fail[0] = False
        # What the cooldown expiring looks like: the next poll reaches the venue.
        marketdata.cache.delete("md:down:hyperliquid")
        with caplog.at_level("INFO", logger="apps.exchanges.marketdata"):
            get_ticker(symbol="BTCUSDT", market=MarketType.FUTURES)
        assert any("answering again" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
def test_no_feed_is_logged_as_an_answer_not_as_a_system_error(monkeypatch):
    """503 stays 503 — the panel needs it — and stops being an ERROR row.

    Two loggers wrote one ERROR each per poll, and every ERROR row is a
    Telegram "System error". The fact is still recorded, at WARNING, every
    time; what stops is calling a venue's outage a fault of this platform.
    """
    from apps.logging.middleware import EXPECTED_ATTR

    fail = [True]
    with flapping_feed(monkeypatch, fail=fail):
        response = user_client().get("/api/trading/market/ticker/?symbol=BTCUSDT")

    assert response.status_code == 503
    assert getattr(response, EXPECTED_ATTR, False) is True
    # Django's own escape hatch: `django.request` will not log it a second time.
    assert response._has_been_logged is True


# --- the candle archive ------------------------------------------------------
#
# Every closed bar the platform sees is written to StoredCandle. The two tests
# above that construct StoredCandle rows directly (@:610, @:743) are
# unaffected because MARKET_DATA.ARCHIVE is off under pytest by default; these
# opt in and exercise the real archiving path.


ARCHIVE_SETTINGS = {
    "ENABLED": True,
    "ARCHIVE": True,
    "PROVIDERS": ["binance"],
}


@pytest.mark.django_db
def test_a_successful_live_fetch_archives_its_closed_bars(monkeypatch):
    with stub_feed(monkeypatch):
        with override_settings(MARKET_DATA=ARCHIVE_SETTINGS):
            get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)

    stored = StoredCandle.objects.filter(symbol="BTCUSDT", interval="1m")
    # stub_feed's base is Nov 2023 — every bar is closed.  The last bar
    # (index 19) may or may not be written depending on whether it falls
    # exactly on the boundary, but at least 19 should be there.
    assert stored.count() >= 19


@pytest.mark.django_db
def test_a_second_identical_fetch_writes_nothing(monkeypatch):
    with stub_feed(monkeypatch):
        with override_settings(MARKET_DATA=ARCHIVE_SETTINGS):
            get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)
            count_after_first = StoredCandle.objects.filter(symbol="BTCUSDT").count()

            get_candles(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=20)
            count_after_second = StoredCandle.objects.filter(symbol="BTCUSDT").count()

    assert count_after_second == count_after_first


@pytest.mark.django_db
def test_a_deeper_limit_than_the_venue_returns_is_served_from_the_archive(monkeypatch):
    """The venue page is 20 bars; the archive fills the rest."""
    # Seed the archive with 50 closed bars from "binance".
    now = int(time.time())
    bars = [
        StoredCandle(
            exchange="binance", market="futures", symbol="BTCUSDT", interval="1m",
            open_time=now - (50 - i) * 60,
            open=D("100"), high=D("101"), low=D("99"), close=D("100"), volume=D("1"),
        )
        for i in range(50)
    ]
    StoredCandle.objects.bulk_create(bars)

    def fake_get(self, url, params):
        marketdata.record_rtt(self.name, 10.0)
        if "klines" in url:
            limit = int(params.get("limit") or 20)
            base = 1700000000000
            return [
                [base + i * 60000, "100", "100", "100", "100", "1"] for i in range(min(limit, 20))
            ]
        return {"lastPrice": "100", "priceChangePercent": "1.25"}

    monkeypatch.setattr(marketdata.HttpSource, "_get", fake_get)
    with override_settings(MARKET_DATA=ARCHIVE_SETTINGS):
        payload = get_candles(
            symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=60
        )

    # The venue only returned 20; the archive should supply the other 40.
    assert len(payload["candles"]) >= 50
    assert payload["stored_bars"] > 0


@pytest.mark.django_db
def test_the_end_cursor_returns_bars_before_that_moment(monkeypatch):
    now = int(time.time())
    for i in range(10):
        StoredCandle.objects.create(
            exchange="binance", market="futures", symbol="BTCUSDT", interval="1m",
            open_time=now - (10 - i) * 60,
            open=D("100"), high=D("100"), low=D("100"), close=D("100"), volume=D("1"),
        )

    def explode(self, *args, **kwargs):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(marketdata.HttpSource, "_get", explode)
    with override_settings(MARKET_DATA=ARCHIVE_SETTINGS):
        end = now - 3 * 60
        payload = get_candles(
            symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, limit=100, end=end
        )

    assert payload["live"] is False
    assert payload["stored"] is True
    assert all(c["t"] <= end for c in payload["candles"])
