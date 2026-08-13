"""Public market data — candles and last price (spec §3).

Deliberately **not** part of the adapter seam. Adapters hold credentials, are
built one per account, and live inside the 1-second fan-out budget. This module
holds no credentials, is shared by every request, and never signs anything, so:

  - a market-data outage cannot touch order routing;
  - a chart refresh can never accidentally be signed with a partner's key;
  - the data can be cached across accounts, which per-account adapters must not.

Providers are tried in order and the first that answers wins. When none does,
this module **raises**. There is no synthetic fallback: a trading panel that
draws invented candles is how someone reads a number that was never real, and
no badge makes that safe. Callers turn the failure into an explicit "no feed"
state — never into a price.

Every real provider call is timed and the round trip is cached per provider, so
the panel can show the engine's actual latency to the exchange rather than only
the browser's latency to the engine.
"""

from __future__ import annotations

import logging
import os
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


# --- latency ----------------------------------------------------------------
#: How long a measured round trip is still worth showing. Past this the panel
#: shows nothing rather than a number from a link that may since have died.
RTT_TTL = 60


def record_rtt(provider: str, ms: float) -> None:
    """Remember the last real round trip to ``provider``, in milliseconds."""
    if not provider:
        return
    cache.set(f"md:rtt:{provider}", round(ms, 1), RTT_TTL)


def last_rtt(provider: str) -> float | None:
    """The last measured round trip, or None when nothing recent was measured."""
    return cache.get(f"md:rtt:{provider}") if provider else None


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


class MarketDataSource(Protocol):
    name: str

    def candles(
        self, *, symbol: str, interval: str, market: MarketType, limit: int
    ) -> list[Candle]: ...

    def ticker(self, *, symbol: str, market: MarketType) -> Ticker: ...


# --- providers --------------------------------------------------------------


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


class _HttpSource:
    """Shared transport. One short-lived client per call — this is not hot path."""

    name = ""

    def _get(self, url: str, params: dict) -> dict | list:
        started = time.perf_counter()
        with httpx.Client(
            timeout=httpx.Timeout(HTTP_TIMEOUT),
            headers={"User-Agent": "WalletManager-CopyTrader/1.0"},
            # Explicit rather than ambient: see resolve_proxy.
            trust_env=False,
            proxy=resolve_proxy(),
        ) as client:
            response = client.get(url, params=params)
        # Timed here rather than around the whole provider call: this is the
        # wire round trip to the exchange and nothing else. It is the number the
        # panel shows next to the browser's own round trip to the engine.
        record_rtt(self.name, (time.perf_counter() - started) * 1000)
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
) -> dict:
    """Real candles plus provenance, or ``MarketDataError``. Never invented data."""
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
    if not candles:
        raise MarketDataError(f"{provider}: no candles for {symbol}")

    payload = {
        "symbol": symbol,
        "interval": interval,
        "market": market.value,
        "source": provider,
        # Kept on the wire and always true: every payload that reaches a client
        # came from an exchange. Nothing else can produce one any more.
        "live": True,
        "provider_ms": last_rtt(provider),
        "candles": [candle.as_dict() for candle in candles],
    }
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
    payload = {
        **ticker.as_dict(),
        "market": market.value,
        "source": provider,
        "live": True,
        "provider_ms": last_rtt(provider),
    }
    cache.set(key, payload, TICKER_TTL)
    return payload
