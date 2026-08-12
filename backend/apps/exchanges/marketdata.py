"""Public market data — candles and last price (spec §3).

Deliberately **not** part of the adapter seam. Adapters hold credentials, are
built one per account, and live inside the 1-second fan-out budget. This module
holds no credentials, is shared by every request, and never signs anything, so:

  - a market-data outage cannot touch order routing;
  - a chart refresh can never accidentally be signed with a partner's key;
  - the data can be cached across accounts, which per-account adapters must not.

Providers are tried in order and the first that answers wins. When none does,
``SyntheticSource`` returns a labelled random walk — the response says
``live: false`` and the panel renders a "placeholder data" badge from that flag.
An unlabelled fake price series on a trading screen is how someone reads a
number that was never real, so the flag travels with the data rather than being
a frontend decision.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.core.money import D
from apps.exchanges.base import MarketType

logger = logging.getLogger(__name__)

# Short: this sits in front of the chart, not in front of an order.
HTTP_TIMEOUT = 2.5
CANDLE_TTL = 10
TICKER_TTL = 3
#: How long a provider that just failed is skipped for. Without this, one dead
#: provider costs every request its full timeout before the fallback runs.
COOLDOWN = 60

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


class MarketDataError(Exception):
    """No provider could answer. Callers fall back to synthetic data."""


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


class MarketDataSource(Protocol):
    name: str

    def candles(
        self, *, symbol: str, interval: str, market: MarketType, limit: int
    ) -> list[Candle]: ...

    def ticker(self, *, symbol: str, market: MarketType) -> Ticker: ...


# --- providers --------------------------------------------------------------


class _HttpSource:
    """Shared transport. One short-lived client per call — this is not hot path."""

    name = ""

    def _get(self, url: str, params: dict) -> dict | list:
        with httpx.Client(
            timeout=httpx.Timeout(HTTP_TIMEOUT),
            headers={"User-Agent": "WalletManager-CopyTrader/1.0"},
        ) as client:
            response = client.get(url, params=params)
        if response.status_code >= 400:
            raise MarketDataError(f"{self.name}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise MarketDataError(f"{self.name}: non-JSON response") from exc


class BinancePublicSource(_HttpSource):
    """Binance public endpoints. No key, no signature, no account context."""

    name = "binance"
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def _host(self, market: MarketType) -> str:
        return "https://fapi.binance.com" if market is MarketType.FUTURES else "https://api.binance.com"

    def _prefix(self, market: MarketType) -> str:
        return "/fapi/v1" if market is MarketType.FUTURES else "/api/v3"

    def candles(self, *, symbol: str, interval: str, market: MarketType, limit: int):
        rows = self._get(
            f"{self._host(market)}{self._prefix(market)}/klines",
            {
                "symbol": symbol.upper(),
                "interval": self._INTERVALS[interval],
                "limit": min(limit, MAX_LIMIT),
            },
        )
        if not isinstance(rows, list):
            raise MarketDataError("binance: unexpected klines shape")
        return [
            Candle(
                time=int(row[0]) // 1000,
                open=D(row[1]),
                high=D(row[2]),
                low=D(row[3]),
                close=D(row[4]),
                volume=D(row[5]),
            )
            for row in rows
        ]

    def ticker(self, *, symbol: str, market: MarketType):
        payload = self._get(
            f"{self._host(market)}{self._prefix(market)}/ticker/24hr",
            {"symbol": symbol.upper()},
        )
        if not isinstance(payload, dict) or "lastPrice" not in payload:
            raise MarketDataError("binance: unexpected ticker shape")
        return Ticker(
            symbol=symbol.upper(),
            price=D(payload["lastPrice"]),
            change_pct=D(payload.get("priceChangePercent", "0")),
            at=int(time.time()),
        )


class BybitPublicSource(_HttpSource):
    """Bybit v5 public market endpoints — the fallback when Binance is blocked."""

    name = "bybit"
    _BASE = "https://api.bybit.com"
    _INTERVALS = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}

    def _category(self, market: MarketType) -> str:
        return "linear" if market is MarketType.FUTURES else "spot"

    def _result(self, payload) -> dict:
        if not isinstance(payload, dict) or payload.get("retCode") not in (0, None):
            detail = payload.get("retMsg") if isinstance(payload, dict) else payload
            raise MarketDataError(f"bybit: {detail}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise MarketDataError("bybit: unexpected response shape")
        return result

    def candles(self, *, symbol: str, interval: str, market: MarketType, limit: int):
        result = self._result(
            self._get(
                f"{self._BASE}/v5/market/kline",
                {
                    "category": self._category(market),
                    "symbol": symbol.upper(),
                    "interval": self._INTERVALS[interval],
                    "limit": min(limit, 1000),
                },
            )
        )
        rows = result.get("list") or []
        candles = [
            Candle(
                time=int(row[0]) // 1000,
                open=D(row[1]),
                high=D(row[2]),
                low=D(row[3]),
                close=D(row[4]),
                volume=D(row[5]),
            )
            for row in rows
        ]
        # Bybit returns newest first; the chart needs oldest first.
        candles.reverse()
        return candles

    def ticker(self, *, symbol: str, market: MarketType):
        result = self._result(
            self._get(
                f"{self._BASE}/v5/market/tickers",
                {"category": self._category(market), "symbol": symbol.upper()},
            )
        )
        rows = result.get("list") or []
        if not rows:
            raise MarketDataError("bybit: no ticker for that symbol")
        row = rows[0]
        change = row.get("price24hPcnt")
        return Ticker(
            symbol=symbol.upper(),
            price=D(row["lastPrice"]),
            # Bybit gives a fraction (0.0123); the panel shows a percentage.
            change_pct=None if change is None else D(change) * Decimal("100"),
            at=int(time.time()),
        )


class SyntheticSource:
    """A deterministic random walk, used only when every real provider is down.

    Deterministic on purpose: the same symbol and minute give the same series,
    so the chart does not reshuffle itself on every poll. Callers must pass the
    ``live: False`` flag on to the client — see the module docstring.
    """

    name = "synthetic"

    _ANCHORS = {"BTC": Decimal("100000"), "ETH": Decimal("3500"), "SOL": Decimal("180")}

    def _anchor(self, symbol: str) -> Decimal:
        for prefix, price in self._ANCHORS.items():
            if symbol.upper().startswith(prefix):
                return price
        # Anything else gets a stable pseudo-price derived from its name, so two
        # different symbols do not draw the identical chart.
        digest = hashlib.sha256(symbol.upper().encode()).digest()
        return Decimal(int.from_bytes(digest[:2], "big") % 900 + 100)

    #: The walk is always this long and callers take the tail they need, so the
    #: last value is the same whoever asks. Without that the ticker and the last
    #: candle disagree — and PnL is marked against the ticker, so an open
    #: position would show an instant profit or loss that never happened.
    _LENGTH = 500

    def _walk(self, symbol: str) -> list[Decimal]:
        price = self._anchor(symbol)
        seed = int.from_bytes(hashlib.sha256(symbol.upper().encode()).digest()[:4], "big")
        prices = []
        for _ in range(self._LENGTH):
            seed = (seed * 1103515245 + 12345) % (2**31)
            step = (Decimal(seed % 2000) - Decimal("1000")) / Decimal("100000")
            price = price * (Decimal("1") + step)
            prices.append(price)
        return prices

    def candles(self, *, symbol: str, interval: str, market: MarketType, limit: int):
        seconds = INTERVALS[interval]
        count = min(limit, self._LENGTH)
        # Snap to the interval grid so successive polls agree on bar boundaries.
        last_open = (int(time.time()) // seconds) * seconds
        closes = self._walk(symbol)[-count:]
        candles = []
        for i, close in enumerate(closes):
            open_price = closes[i - 1] if i else close
            high = max(open_price, close) * Decimal("1.001")
            low = min(open_price, close) * Decimal("0.999")
            candles.append(
                Candle(
                    time=last_open - (count - 1 - i) * seconds,
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=Decimal("0"),
                )
            )
        return candles

    def ticker(self, *, symbol: str, market: MarketType):
        return Ticker(
            symbol=symbol.upper(),
            price=round(self._walk(symbol)[-1], 2),
            change_pct=None,
            at=int(time.time()),
        )


SOURCES: dict[str, type] = {
    "binance": BinancePublicSource,
    "bybit": BybitPublicSource,
}


# --- resolution -------------------------------------------------------------


def _configured_providers() -> list[str]:
    return [p.strip() for p in settings.MARKET_DATA["PROVIDERS"] if p.strip() in SOURCES]


def _cooling_off(name: str) -> bool:
    return cache.get(f"md:down:{name}") is not None


def _mark_down(name: str, exc: Exception) -> None:
    cache.set(f"md:down:{name}", str(exc), COOLDOWN)
    logger.warning("market data provider %s unavailable: %s", name, exc)


def _try_providers(call, *, what: str):
    """Run ``call(source)`` against each live provider; return (value, name)."""
    if not settings.MARKET_DATA["ENABLED"]:
        return None, ""

    for name in _configured_providers():
        if _cooling_off(name):
            continue
        try:
            return call(SOURCES[name]()), name
        except (MarketDataError, httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            _mark_down(name, exc)
        except Exception as exc:  # noqa: BLE001 - the chart must never 500
            _mark_down(name, exc)
            logger.exception("unexpected market data failure fetching %s", what)
    return None, ""


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
) -> dict:
    """Candles plus provenance. Always returns data; ``live`` says whether it is real."""
    symbol = symbol.upper()
    limit = max(10, min(limit, MAX_LIMIT))
    key = f"md:candles:{symbol}:{interval}:{market.value}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    candles, provider = _try_providers(
        lambda source: source.candles(
            symbol=symbol, interval=interval, market=market, limit=limit
        ),
        what="candles",
    )
    live = bool(candles)
    if not live:
        candles = SyntheticSource().candles(
            symbol=symbol, interval=interval, market=market, limit=limit
        )
        provider = SyntheticSource.name

    payload = {
        "symbol": symbol,
        "interval": interval,
        "market": market.value,
        "source": provider,
        "live": live,
        "candles": [candle.as_dict() for candle in candles],
    }
    # Synthetic data is cached briefly too, so a provider outage does not turn
    # into a burst of pointless retries from an open chart.
    cache.set(key, payload, CANDLE_TTL)
    return payload


def get_ticker(*, symbol: str, market: MarketType = MarketType.FUTURES) -> dict:
    symbol = symbol.upper()
    key = f"md:ticker:{symbol}:{market.value}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    ticker, provider = _try_providers(
        lambda source: source.ticker(symbol=symbol, market=market), what="ticker"
    )
    live = ticker is not None
    if ticker is None:
        ticker = SyntheticSource().ticker(symbol=symbol, market=market)
        provider = SyntheticSource.name

    payload = {**ticker.as_dict(), "market": market.value, "source": provider, "live": live}
    cache.set(key, payload, TICKER_TTL)
    return payload
