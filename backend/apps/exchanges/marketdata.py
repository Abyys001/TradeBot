"""Public market data — candles and last price (spec §3).

Deliberately **not** part of the adapter seam. Adapters hold credentials, are
built one per account, and live inside the 1-second fan-out budget. This module
holds no credentials, is shared by every request, and never signs anything, so:

  - a market-data outage cannot touch order routing;
  - a chart refresh can never accidentally be signed with a partner's key;
  - the data can be cached across accounts, which per-account adapters must not.

**Where a price comes from** is now decided by what is connected: the exchanges
with active accounts are tried first, in order of how many accounts sit on
them, and only then the configured public fallbacks. The panel therefore marks
against the venue the orders actually go to. Providers are tried in order and
the first that answers wins.

When none does, this module **raises**. There is no synthetic fallback: a
trading panel that draws invented candles is how someone reads a number that
was never real, and no badge makes that safe. Callers turn the failure into an
explicit "no feed" state — never into a price. Downloaded history (see
``apps.exchanges.catalogue``) is the one thing served when the live feed is
down, and it is labelled ``live: false`` with the exchange that produced it,
because a stored bar is old rather than invented.

Every real provider call is timed and the round trip is cached per provider, so
the panel can show the engine's actual latency to the exchange rather than only
the browser's latency to the engine.
"""

from __future__ import annotations

import logging

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import (
    DEFAULT_LIMIT,
    INTERVALS,
    MAX_LIMIT,
    RTT_TTL,
    Candle,
    HttpSource,
    MarketDataError,
    SymbolInfo,
    Ticker,
    last_rtt,
    record_rtt,
    resolve_proxy,
    split_pair,
)
from apps.exchanges.public_sources import (
    SOURCES,
    BinancePublicSource,
    BybitPublicSource,
)

logger = logging.getLogger(__name__)

CANDLE_TTL = 10
TICKER_TTL = 3
#: How long a provider that just failed is skipped for. Without this, one dead
#: provider costs every request its full timeout before the fallback runs.
COOLDOWN = 60
#: How long the "which exchanges are connected" lookup is reused. The routing
#: path must not pay a query per chart tick, and this changes at human speed.
CONNECTED_TTL = 30

__all__ = [
    "BinancePublicSource",
    "BybitPublicSource",
    "Candle",
    "DEFAULT_LIMIT",
    "HttpSource",
    "INTERVALS",
    "MAX_LIMIT",
    "MarketDataError",
    "RTT_TTL",
    "SOURCES",
    "SymbolInfo",
    "Ticker",
    "get_candles",
    "get_ticker",
    "last_rtt",
    "normalise_interval",
    "normalise_market",
    "pinned_provider",
    "probe_latency",
    "provider_latency",
    "record_rtt",
    "resolve_proxy",
    "source_for",
    "split_pair",
]


def provider_latency() -> dict:
    """Measured engine→exchange round trips, in provider preference order.

    Null rather than a guess when nothing has been measured inside ``RTT_TTL``:
    an old number from a link that has since died is worse than no number.
    """
    rows = [
        {"provider": name, "ms": last_rtt(name)}
        for name in _configured_providers()
        if last_rtt(name) is not None
    ]
    return {
        "providers": rows,
        "provider": rows[0]["provider"] if rows else "",
        "ms": rows[0]["ms"] if rows else None,
    }


#: A probe runs at most this often, however many panels ask. The reading only
#: has to be fresher than ``RTT_TTL`` for the top bar to stay populated.
PROBE_EVERY = 25
#: What the probe asks for: the pair every venue here lists, and the smallest
#: window the feed will serve.
#:
#: Small on purpose. The reading is presented as the hop an order travels, so
#: it has to be a round trip and not a download — Hyperliquid's ticker call
#: returns the whole perp universe and timed at 1.25s against a venue whose
#: actual round trip is a fraction of that, which would have read as blowing
#: the spec §4 budget on a link that meets it comfortably.
PROBE_SYMBOL = "BTCUSDT"
PROBE_LIMIT = 10


def probe_latency() -> dict:
    """Measure the engine→exchange round trip if nothing recent exists.

    The readout used to be a by-product of whatever the panel happened to be
    polling. That broke in exactly the case it mattered: once bars stream over
    a WebSocket the REST polls drop to one every two minutes, ``RTT_TTL``
    expires, and "Exchange latency" goes blank on a deployment where everything
    is working. A settings page that never opens the chart never measured
    anything at all.

    So the engine measures it itself — one real ticker call, debounced across
    every connected panel, and only when the cached reading has gone stale.
    Still a real round trip to a real venue; never a synthesised number.
    """
    current = provider_latency()
    if current["ms"] is not None:
        return current
    # `add` is atomic on both cache backends: whichever panel wins runs the one
    # probe and the rest fall through to whatever is cached.
    if not cache.add("md:rtt:probe", 1, PROBE_EVERY):
        return current
    try:
        get_candles(symbol=PROBE_SYMBOL, interval="1m", limit=PROBE_LIMIT)
    except MarketDataError as exc:
        logger.info("latency probe found no provider: %s", exc)
    return provider_latency()


# --- resolution -------------------------------------------------------------


def connected_exchanges() -> list[str]:
    """Exchanges with an active account, most-used first.

    This is what makes the feed follow the accounts: connect Bybit keys and the
    chart starts quoting Bybit, with no configuration change anywhere.
    """
    cached = cache.get("md:connected")
    if cached is not None:
        return cached

    from django.db.models import Count

    from apps.accounts.models import AccountStatus, ConnectedAccount

    rows = (
        ConnectedAccount.objects.filter(status=AccountStatus.ACTIVE)
        .values("exchange")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    names = [row["exchange"] for row in rows if row["exchange"] in SOURCES]
    cache.set("md:connected", names, CONNECTED_TTL)
    return names


def pinned_provider() -> str:
    """The one venue the feed is pinned to, or "" when it follows the accounts.

    Returns "" for a pin naming an exchange with no public source rather than
    failing every price call — a typo in `.env` must not take the chart down.
    """
    name = settings.MARKET_DATA.get("PIN", "").strip()
    if not name:
        return ""
    if name not in SOURCES:
        logger.warning("MARKET_DATA_PIN=%r has no public source; ignoring", name)
        return ""
    return name


def _configured_providers() -> list[str]:
    """Connected exchanges first, then the configured public fallbacks.

    Unless the feed is pinned, in which case that venue is the whole list. A
    pin with a fallback behind it would still let the chart change venue, which
    is the thing the pin exists to prevent.
    """
    pin = pinned_provider()
    if pin:
        return [pin]

    ordered = list(connected_exchanges())
    for name in settings.MARKET_DATA["PROVIDERS"]:
        name = name.strip()
        if name in SOURCES and name not in ordered:
            ordered.append(name)
    return ordered


def source_for(exchange: str, *, timeout: float | None = None) -> HttpSource:
    """The public feed for one exchange. Raises for an exchange without one."""
    try:
        cls = SOURCES[exchange]
    except KeyError as exc:
        raise MarketDataError(f"no public market data source for {exchange!r}") from exc
    return cls(timeout=timeout) if timeout else cls()


def _cooling_off(name: str) -> bool:
    return cache.get(f"md:down:{name}") is not None


def _mark_down(name: str, exc: Exception) -> None:
    cache.set(f"md:down:{name}", str(exc), COOLDOWN)
    logger.warning("market data provider %s unavailable: %s", name, exc)


def _try_providers(call, *, what: str):
    """Run ``call(source)`` against each live provider; return (value, name).

    Raises ``MarketDataError`` when nothing answers. There is no fallback value:
    the only honest answer to "what is BTC worth" with every provider down is
    "we do not know".
    """
    if not settings.MARKET_DATA["ENABLED"]:
        raise MarketDataError("market data is disabled")

    configured = _configured_providers()
    if not configured:
        raise MarketDataError("no market data provider is configured")

    reasons: list[str] = []
    for name in configured:
        if _cooling_off(name):
            reasons.append(f"{name}: cooling off ({cache.get(f'md:down:{name}')})")
            continue
        try:
            return call(SOURCES[name]()), name
        except (MarketDataError, httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            _mark_down(name, exc)
            reasons.append(f"{name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - one bad provider is not a 500
            _mark_down(name, exc)
            reasons.append(f"{name}: {exc}")
            logger.exception("unexpected market data failure fetching %s", what)
    raise MarketDataError(f"no provider could serve {what} — " + "; ".join(reasons))


def normalise_interval(value: str | None) -> str:
    interval = (value or "1m").lower()
    if interval not in INTERVALS:
        raise ValueError(f"unsupported interval {value!r}")
    return interval


def normalise_market(value: str | None) -> MarketType:
    try:
        return MarketType(value or "futures")
    except ValueError as exc:
        raise ValueError(f"unsupported market {value!r}") from exc


def get_candles(
    *,
    symbol: str,
    interval: str = "1m",
    market: MarketType = MarketType.FUTURES,
    limit: int = DEFAULT_LIMIT,
    end: int | None = None,
) -> dict:
    """Real candles plus provenance, or ``MarketDataError``. Never invented data.

    ``end`` (UNIX seconds) asks for the window *before* that moment, which is
    how the chart pans back into downloaded history.
    """
    symbol = symbol.upper()
    limit = max(10, min(limit, MAX_LIMIT))
    key = f"md:candles:{symbol}:{interval}:{market.value}:{limit}:{end or 0}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        candles, provider = _try_providers(
            lambda source: source.candles(
                symbol=symbol, interval=interval, market=market, limit=limit, end=end
            ),
            what="candles",
        )
        if not candles:
            raise MarketDataError(f"{provider}: no candles for {symbol}")
    except MarketDataError as exc:
        # Downloaded history is real exchange data that is merely old. Serving
        # it beats a blank chart, but it is never presented as live.
        stored = stored_candles(
            symbol=symbol, interval=interval, market=market, limit=limit, end=end
        )
        if not stored:
            raise
        payload = {
            "symbol": symbol,
            "interval": interval,
            "market": market.value,
            "source": stored[1],
            "live": False,
            "stored": True,
            "feed_error": str(exc),
            "provider_ms": None,
            "candles": [candle.as_dict() for candle in stored[0]],
        }
        cache.set(key, payload, CANDLE_TTL)
        return payload

    payload = {
        "symbol": symbol,
        "interval": interval,
        "market": market.value,
        "source": provider,
        # Kept on the wire and always true: every payload that reaches a client
        # came from an exchange. Nothing else can produce one any more.
        "live": True,
        "stored": False,
        "provider_ms": last_rtt(provider),
        "candles": [candle.as_dict() for candle in candles],
    }
    cache.set(key, payload, CANDLE_TTL)
    return payload


def stored_candles(
    *,
    symbol: str,
    interval: str,
    market: MarketType,
    limit: int,
    end: int | None = None,
) -> tuple[list[Candle], str] | None:
    """The newest ``limit`` downloaded bars at or before ``end``, oldest first."""
    from apps.trading.models import StoredCandle

    rows = StoredCandle.objects.filter(
        symbol=symbol, interval=interval, market=market.value
    )
    if end is not None:
        rows = rows.filter(open_time__lte=end)
    rows = list(rows.order_by("-open_time")[:limit])
    if not rows:
        return None
    rows.reverse()
    candles = [
        Candle(
            time=row.open_time,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    ]
    return candles, rows[0].exchange


def get_ticker(*, symbol: str, market: MarketType = MarketType.FUTURES) -> dict:
    symbol = symbol.upper()
    key = f"md:ticker:{symbol}:{market.value}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    ticker, provider = _try_providers(
        lambda source: source.ticker(symbol=symbol, market=market), what="ticker"
    )
    payload = {
        **ticker.as_dict(),
        "market": market.value,
        "source": provider,
        "live": True,
        "provider_ms": last_rtt(provider),
    }
    cache.set(key, payload, TICKER_TTL)
    return payload
