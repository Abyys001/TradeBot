"""Shared primitives for the **public** market-data sources.

Split out of ``marketdata`` so that module can import the per-exchange sources
without a cycle: ``feed_base`` -> ``public_sources`` -> ``marketdata``.

Nothing here holds a credential or signs anything. That is the whole point of
the split from the adapter seam (see the note at the top of ``marketdata``): a
chart refresh must never be able to travel down a path that can sign an order.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# This sits in front of the chart, not in front of an order, so it is bounded
# by what a real venue actually takes rather than by the fan-out's budget.
#
# It was 2.5s, and that is what froze the chart. Measured against Hyperliquid
# over the deployment's egress: a 300-bar `candleSnapshot` takes 1.0–6.1s and
# `metaAndAssetCtxs` (71 KB, the ticker call) 1.3–2.7s. Every overrun raised,
# which put the provider in `COOLDOWN` — and with `MARKET_DATA_PIN` there is no
# second provider to fall back to, so one slow call cost the chart a minute of
# live bars while the ticker kept quoting. The panel then showed a moving price
# over a series hours old, which is the worst of both readings.
HTTP_TIMEOUT = 8.0
#: Backfill requests are bulk downloads, not a chart refresh — a whole page of
#: bars over a long link is worth waiting for rather than retrying.
BACKFILL_TIMEOUT = 15.0

#: Every interval the platform offers, in seconds. Keys are the wire values the
#: frontend sends, and this dict is the single answer to "is that a timeframe".
INTERVALS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
}

#: The intervals a venue is actually asked for. Every public source has been
#: written and tested against exactly these six wire values, and an exchange API
#: fact is not something to invent from memory — so the other eight are
#: **derived** rather than guessed at (see ``DERIVED_FROM``).
NATIVE_INTERVALS: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d")

#: ``derived interval -> the native one it is built from``. Each pair divides
#: exactly and by a small factor (3, 2, 2, 6, 2, 3, 3, 7), so one page of base
#: bars still covers a useful window: a 6h bar is six 1h bars, never three
#: hundred 1m ones.
DERIVED_FROM: dict[str, str] = {
    "3m": "1m",
    "30m": "15m",
    "2h": "1h",
    "6h": "1h",
    "8h": "4h",
    "12h": "4h",
    "3d": "1d",
    "1w": "1d",
}

#: Where a bucket boundary sits, as an offset from the UNIX epoch.
#:
#: Epoch second 0 is a **Thursday**, so a week bucket floored at ``t // 604800``
#: would start on Thursdays. Exchanges align weekly and multi-day bars to
#: Monday, and a chart whose weeks start on the wrong day is a different series
#: from the one the venue draws.
BUCKET_OFFSET: dict[str, int] = {"3d": 345600, "1w": 345600}


def is_native(interval: str) -> bool:
    return interval in NATIVE_INTERVALS


def native_for(source, interval: str) -> bool:
    """Whether *this* venue serves ``interval`` itself, rather than it being folded.

    A venue that lists the interval is asked for it directly. Folding 30m out of
    15m on Hyperliquid, which serves 30m natively and caps every interval at its
    latest 5000 bars, halved the history a backtest could reach — and a replay
    that starts months after TradingView's is a different set of trades.
    """
    own = getattr(source, "_INTERVALS", None)
    return interval in own if own else is_native(interval)


def base_interval(interval: str) -> str:
    """The interval a venue is asked for in order to serve ``interval``."""
    return DERIVED_FROM.get(interval, interval)


def base_ratio(interval: str) -> int:
    """How many base bars make one ``interval`` bar. 1 when it is native."""
    return INTERVALS[interval] // INTERVALS[base_interval(interval)]


def bucket_start(open_time: int, interval: str) -> int:
    """The open time of the ``interval`` bar that contains ``open_time``."""
    step = INTERVALS[interval]
    offset = BUCKET_OFFSET.get(interval, 0) % step
    return ((open_time - offset) // step) * step + offset


#: The most bars a *venue* is asked for in one call. A page of someone else's
#: HTTP API, on someone else's rate limit.
MAX_LIMIT = 1000
DEFAULT_LIMIT = 300
#: The most bars a request may return once the local archive is allowed to make
#: up the difference (`exchanges.candlestore`). Far higher than MAX_LIMIT because
#: this side is an indexed table rather than a rate-limited endpoint, and serving
#: depth from it is the reason bars are kept at all. Still bounded: the payload
#: is JSON over the wire and the chart has to paint it.
STORED_MAX_LIMIT = 5000

#: How long a measured round trip is still worth showing. Past this the panel
#: shows nothing rather than a number from a link that may since have died.
RTT_TTL = 60


class MarketDataError(Exception):
    """No provider could answer. There is no fallback — the caller says so."""


class SymbolNotListed(MarketDataError):
    """This venue does not list this pair. A fact about the pair, not an outage.

    The distinction is not cosmetic. ``marketdata._try_providers`` puts a
    provider that raises into a cooldown, on the assumption that a failure
    means the venue is unreachable. A pair the venue simply does not list is
    not that: Hyperliquid answering "no market for BMBUSDC" says nothing about
    whether it can quote BTC, and with ``MARKET_DATA_PIN`` there is only one
    provider — so one unlisted pair in the watchlist took the whole feed down
    for every pair, every poll, and wrote a WARNING each time.

    Raised by a source when it can prove the pair is absent from the venue's
    own instrument list. Never for a timeout, a 5xx, or an unparsable reply:
    those really are outages.
    """


@dataclass(frozen=True, slots=True)
class Candle:
    """One OHLCV bar. ``time`` is a UNIX second, which is what the chart wants."""

    time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def as_dict(self) -> dict:
        # Strings, not floats: prices cross this boundary as text so no float
        # artefact is introduced on the way out (the chart parses them back).
        return {
            "t": self.time,
            "o": str(self.open),
            "h": str(self.high),
            "l": str(self.low),
            "c": str(self.close),
            "v": str(self.volume),
        }


def aggregate(candles: list[Candle], interval: str) -> list[Candle]:
    """Roll base bars up into ``interval`` bars — oldest first in, oldest first out.

    Open is the first sub-bar's open, close the last one's, high/low the
    extremes and volume the sum: the definition every venue uses, so a derived
    bar matches the one the exchange would have served.

    A **leading partial bucket is dropped**. The first bar of a page almost
    never lands on a bucket boundary, and a half-built bar written to the
    archive as though it were closed is wrong forever. The *trailing* bucket is
    kept and left to ``candlestore.is_closed``, which is already what
    distinguishes a forming bar from a settled one.
    """
    if not candles:
        return []
    out: list[Candle] = []
    bucket: list[Candle] = []
    start = bucket_start(candles[0].time, interval)
    for candle in candles:
        at = bucket_start(candle.time, interval)
        if at != start:
            if bucket:
                out.append(_fold(bucket, start))
            bucket = []
            start = at
        bucket.append(candle)
    if bucket:
        out.append(_fold(bucket, start))
    # The first bucket is only whole when the page began exactly on its edge.
    if out and candles[0].time != out[0].time:
        out.pop(0)
    return out


def _fold(bucket: list[Candle], start: int) -> Candle:
    return Candle(
        time=start,
        open=bucket[0].open,
        high=max(c.high for c in bucket),
        low=min(c.low for c in bucket),
        close=bucket[-1].close,
        volume=sum((c.volume for c in bucket), Decimal("0")),
    )


@dataclass(frozen=True, slots=True)
class Ticker:
    symbol: str
    price: Decimal
    change_pct: Decimal | None
    at: int

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": str(self.price),
            "change_pct": None if self.change_pct is None else str(self.change_pct),
            "at": self.at,
        }


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    """One pair as the exchange lists it, in this platform's canonical naming.

    ``symbol`` is always BASE+QUOTE (BTCUSDT); ``native`` is what that exchange
    calls it (BTC-USDT-SWAP, XBTUSDTM, BTC_USDT, BTC). Both are kept: the panel
    and the sizing rules speak the first, every request speaks the second.
    """

    symbol: str
    base: str
    quote: str
    native: str
    price_tick: Decimal | None = None
    qty_step: Decimal | None = None
    min_qty: Decimal | None = None
    min_notional: Decimal | None = None
    max_leverage: int = 0
    volume_24h: Decimal | None = None


# --- latency ----------------------------------------------------------------


def record_rtt(provider: str, ms: float) -> None:
    """Remember the last real round trip to ``provider``, in milliseconds."""
    if not provider:
        return
    cache.set(f"md:rtt:{provider}", round(ms, 1), RTT_TTL)


def last_rtt(provider: str) -> float | None:
    """The last measured round trip, or None when nothing recent was measured."""
    return cache.get(f"md:rtt:{provider}") if provider else None


# --- transport --------------------------------------------------------------


def resolve_proxy() -> str | None:
    """The proxy these calls should use, or None for a direct connection.

    ``MARKET_DATA_PROXY`` pins one explicitly. Otherwise the ambient shell proxy
    is used **only if httpx can actually speak it**, with one normalisation:
    shells commonly export ``socks://…`` while httpx wants ``socks5://…``.

    Anything left unusable is dropped and the call goes direct. This is not
    tidiness — httpx raises on an unparseable proxy URL, and with a fallback
    that meant every price call failing on a machine that could reach the
    exchange perfectly well, which is the whole reason a panel ends up showing
    numbers no exchange ever quoted.
    """
    pinned = settings.MARKET_DATA.get("PROXY") or ""
    candidate = pinned or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or ""
    candidate = candidate or os.getenv("ALL_PROXY") or os.getenv("all_proxy") or ""
    candidate = candidate.strip()
    if not candidate:
        return None
    if candidate.startswith("socks://"):
        candidate = "socks5://" + candidate[len("socks://") :]
    try:
        httpx.Proxy(candidate)
    except Exception as exc:  # noqa: BLE001 - an unusable proxy must not kill the feed
        logger.warning("ignoring unusable market data proxy %r: %s", candidate, exc)
        return None
    return candidate


class HttpSource:
    """Shared transport. One short-lived client per call — this is not hot path."""

    name = ""
    #: Exchange key in ``accounts.Exchange``; ties a source to the venue whose
    #: accounts are connected, so prices come from where the orders go.
    exchange = ""
    #: Bars a single request may return. Paging in the backfill uses it.
    page_limit = MAX_LIMIT
    #: True when the exchange only serves a short window of history at all
    #: (Hyperliquid keeps 5000 bars), so a short backfill is not a failure.
    limited_history = False

    def __init__(self, *, timeout: float = HTTP_TIMEOUT) -> None:
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(self._timeout),
            headers={"User-Agent": "TradeBot/1.0"},
            # Explicit rather than ambient: see resolve_proxy.
            trust_env=False,
            proxy=resolve_proxy(),
        )

    def _get(self, url: str, params: dict) -> dict | list:
        started = time.perf_counter()
        with self._client() as client:
            response = client.get(url, params=params)
        # Timed here rather than around the whole provider call: this is the
        # wire round trip to the exchange and nothing else. It is the number the
        # panel shows next to the browser's own round trip to the engine.
        record_rtt(self.name, (time.perf_counter() - started) * 1000)
        return self._payload(response)

    def _post(self, url: str, body: dict) -> dict | list:
        started = time.perf_counter()
        with self._client() as client:
            response = client.post(url, json=body)
        record_rtt(self.name, (time.perf_counter() - started) * 1000)
        return self._payload(response)

    def _payload(self, response: httpx.Response) -> dict | list:
        if response.status_code >= 400:
            raise MarketDataError(f"{self.name}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise MarketDataError(f"{self.name}: non-JSON response") from exc

    # --- interface ---------------------------------------------------------

    def candles(
        self,
        *,
        symbol: str,
        interval: str,
        market,
        limit: int,
        end: int | None = None,
    ) -> list[Candle]:
        """Bars, oldest first, at a **native** interval. ``end`` walks back."""
        raise NotImplementedError

    def ticker(self, *, symbol: str, market) -> Ticker:
        raise NotImplementedError

    def symbols(self, *, market) -> list[SymbolInfo]:
        """Every pair this exchange lists. Raises when it publishes no catalogue."""
        raise MarketDataError(f"{self.name}: no public symbol catalogue")


def fetch_candles(
    source: HttpSource,
    *,
    symbol: str,
    interval: str,
    market,
    limit: int,
    end: int | None = None,
) -> list[Candle]:
    """Bars at any offered interval — **the one entry point callers use**.

    Deliberately a function over a source rather than a method on it: deriving
    30m from 15m is a fact about arithmetic, not about Binance, and eight
    sources each carrying their own copy of it is eight places for the fold to
    drift. A native interval is a straight pass to ``source.candles``.

    ``limit`` is in bars **of the interval asked for**, so the base request is
    scaled up by the ratio — plus one bucket, because ``aggregate`` drops the
    leading partial one. A venue's own page limit still caps it: a short page
    is a shorter window, never a wrong bar.
    """
    if native_for(source, interval):
        return source.candles(
            symbol=symbol, interval=interval, market=market, limit=limit, end=end
        )
    rows = source.candles(
        symbol=symbol,
        interval=base_interval(interval),
        market=market,
        limit=min(source.page_limit, (limit + 1) * base_ratio(interval)),
        end=end,
    )
    folded = aggregate(rows, interval)
    return folded[-limit:] if limit else folded


# --- canonical naming -------------------------------------------------------

#: Quote assets recognised when splitting an exchange's own symbol into
#: base/quote. Order matters: USDT before USD, or BTCUSDT splits as BTCUS+DT.
QUOTES = ("USDT", "USDC", "USD", "BTC", "ETH")


def split_pair(symbol: str) -> tuple[str, str] | None:
    """``BTCUSDT`` -> ``("BTC", "USDT")``; None when no known quote is on the end."""
    upper = symbol.upper()
    for quote in QUOTES:
        if upper.endswith(quote) and len(upper) > len(quote):
            return upper[: -len(quote)], quote
    return None
