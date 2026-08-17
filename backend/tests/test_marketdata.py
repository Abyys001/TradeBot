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
        trade=trade,
        account=account,
        ok=False,
        error="below minimum notional",
        # A sized-out leg is *provably* flat, so the endpoint's re-check leaves
        # it alone. Without the code it would read as unconfirmed and be asked
        # about — see test_an_unconfirmed_leg_is_re_checked_on_the_positions_poll.
        error_code="below_min_notional",
    )

    body = user_client().get("/api/trading/positions/").json()
    assert body["totals"]["failed"] == 1
    assert body["legs"][0]["pnl"] is None
    assert body["legs"][0]["error"] == "below minimum notional"


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
    assert posts == ["metaAndAssetCtxs"]
