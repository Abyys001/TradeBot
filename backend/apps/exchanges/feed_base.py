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

# Short: this sits in front of the chart, not in front of an order.
HTTP_TIMEOUT = 2.5
#: Backfill requests are bulk downloads, not a chart refresh — a whole page of
#: bars over a long link is worth waiting for rather than retrying.
BACKFILL_TIMEOUT = 15.0

#: Chart intervals the panel offers, mapped per provider. Keys are the wire
#: values the frontend sends.
INTERVALS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

MAX_LIMIT = 1000
DEFAULT_LIMIT = 300

#: How long a measured round trip is still worth showing. Past this the panel
#: shows nothing rather than a number from a link that may since have died.
RTT_TTL = 60


class MarketDataError(Exception):
    """No provider could answer. There is no fallback — the caller says so."""


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
            headers={"User-Agent": "WalletManager-CopyTrader/1.0"},
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
        """Bars, oldest first. ``end`` (UNIX seconds) walks the history back."""
        raise NotImplementedError

    def ticker(self, *, symbol: str, market) -> Ticker:
        raise NotImplementedError

    def symbols(self, *, market) -> list[SymbolInfo]:
        """Every pair this exchange lists. Raises when it publishes no catalogue."""
        raise MarketDataError(f"{self.name}: no public symbol catalogue")


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
