"""Public (credential-free) market data, one source per exchange.

Every connected exchange can answer three questions without a key: what pairs
do you list, what are they worth, and what did they do. That is exactly what
the panel needs, so the price behind the chart comes from the venue the orders
actually go to rather than from a stranger's API.

These are **not** adapters. They sign nothing, hold nothing, and are shared
between requests; the isolation rules in spec §2 are about credentialed calls
and do not apply here. Endpoint shapes come from ``reference/`` and the
Hyperliquid docs server, never from memory.
"""

from __future__ import annotations

import time
from decimal import Decimal

from django.core.cache import cache

from apps.core.money import D
from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import (
    INTERVALS,
    Candle,
    HttpSource,
    MarketDataError,
    SymbolInfo,
    Ticker,
    split_pair,
)


def _now_s() -> int:
    return int(time.time())


def _window(interval: str, limit: int, end: int | None) -> tuple[int, int]:
    """(start, end) in UNIX seconds for ``limit`` bars ending at ``end``."""
    step = INTERVALS[interval]
    finish = end or _now_s()
    return finish - step * limit, finish


class BinancePublicSource(HttpSource):
    """Binance public endpoints. No key, no signature, no account context."""

    name = "binance"
    exchange = "binance"
    page_limit = 1000
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def _host(self, market: MarketType) -> str:
        return (
            "https://fapi.binance.com"
            if market is MarketType.FUTURES
            else "https://api.binance.com"
        )

    def _prefix(self, market: MarketType) -> str:
        return "/fapi/v1" if market is MarketType.FUTURES else "/api/v3"

    def candles(self, *, symbol, interval, market, limit, end=None):
        params = {
            "symbol": symbol.upper(),
            "interval": self._INTERVALS[interval],
            "limit": min(limit, self.page_limit),
        }
        if end is not None:
            params["endTime"] = end * 1000
        rows = self._get(f"{self._host(market)}{self._prefix(market)}/klines", params)
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

    def ticker(self, *, symbol, market):
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
            at=_now_s(),
        )

    def _volumes(self, market: MarketType) -> dict[str, Decimal]:
        rows = self._get(f"{self._host(market)}{self._prefix(market)}/ticker/24hr", {})
        if not isinstance(rows, list):
            return {}
        return {
            str(row.get("symbol", "")): D(row.get("quoteVolume") or "0")
            for row in rows
            if isinstance(row, dict)
        }

    def symbols(self, *, market):
        payload = self._get(f"{self._host(market)}{self._prefix(market)}/exchangeInfo", {})
        if not isinstance(payload, dict):
            raise MarketDataError("binance: unexpected exchangeInfo shape")
        volumes = self._volumes(market)
        out: list[SymbolInfo] = []
        for entry in payload.get("symbols", []):
            if entry.get("status") not in ("TRADING", None):
                continue
            if market is MarketType.FUTURES and entry.get("contractType") != "PERPETUAL":
                continue
            symbol = str(entry.get("symbol", "")).upper()
            filters = {f.get("filterType"): f for f in entry.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            notional = filters.get("MIN_NOTIONAL", filters.get("NOTIONAL", {}))
            out.append(
                SymbolInfo(
                    symbol=symbol,
                    base=str(entry.get("baseAsset", "")).upper(),
                    quote=str(entry.get("quoteAsset", "")).upper(),
                    native=symbol,
                    price_tick=D(filters.get("PRICE_FILTER", {}).get("tickSize") or "0") or None,
                    qty_step=D(lot.get("stepSize") or "0") or None,
                    min_qty=D(lot.get("minQty") or "0") or None,
                    min_notional=D(
                        notional.get("notional") or notional.get("minNotional") or "0"
                    )
                    or None,
                    volume_24h=volumes.get(symbol),
                )
            )
        return out


class BybitPublicSource(HttpSource):
    """Bybit v5 public market endpoints — the fallback when Binance is blocked."""

    name = "bybit"
    exchange = "bybit"
    page_limit = 1000
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

    def candles(self, *, symbol, interval, market, limit, end=None):
        params = {
            "category": self._category(market),
            "symbol": symbol.upper(),
            "interval": self._INTERVALS[interval],
            "limit": min(limit, self.page_limit),
        }
        if end is not None:
            start, finish = _window(interval, min(limit, self.page_limit), end)
            params["start"], params["end"] = start * 1000, finish * 1000
        result = self._result(self._get(f"{self._BASE}/v5/market/kline", params))
        candles = [
            Candle(
                time=int(row[0]) // 1000,
                open=D(row[1]),
                high=D(row[2]),
                low=D(row[3]),
                close=D(row[4]),
                volume=D(row[5]),
            )
            for row in result.get("list") or []
        ]
        # Bybit returns newest first; the chart needs oldest first.
        candles.reverse()
        return candles

    def ticker(self, *, symbol, market):
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
            at=_now_s(),
        )

    def _volumes(self, market: MarketType) -> dict[str, Decimal]:
        result = self._result(
            self._get(
                f"{self._BASE}/v5/market/tickers", {"category": self._category(market)}
            )
        )
        return {
            str(row.get("symbol", "")): D(row.get("turnover24h") or "0")
            for row in result.get("list") or []
        }

    def symbols(self, *, market):
        result = self._result(
            self._get(
                f"{self._BASE}/v5/market/instruments-info",
                {"category": self._category(market), "limit": 1000},
            )
        )
        volumes = self._volumes(market)
        out: list[SymbolInfo] = []
        for row in result.get("list") or []:
            if row.get("status") not in ("Trading", None):
                continue
            symbol = str(row.get("symbol", "")).upper()
            lot = row.get("lotSizeFilter") or {}
            out.append(
                SymbolInfo(
                    symbol=symbol,
                    base=str(row.get("baseCoin", "")).upper(),
                    quote=str(row.get("quoteCoin", "")).upper(),
                    native=symbol,
                    price_tick=D((row.get("priceFilter") or {}).get("tickSize") or "0") or None,
                    qty_step=D(lot.get("qtyStep") or lot.get("basePrecision") or "0") or None,
                    min_qty=D(lot.get("minOrderQty") or "0") or None,
                    min_notional=D(lot.get("minNotionalValue") or "0") or None,
                    max_leverage=int(
                        D((row.get("leverageFilter") or {}).get("maxLeverage") or "0")
                    ),
                    volume_24h=volumes.get(symbol),
                )
            )
        return out


class OkxPublicSource(HttpSource):
    """OKX v5 public endpoints. Instruments are ``BTC-USDT-SWAP`` / ``BTC-USDT``."""

    name = "okx"
    exchange = "okx"
    #: OKX caps a candle page at 300 (100 on some bars); 100 is always accepted.
    page_limit = 100
    _BASE = "https://www.okx.com"
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}

    def _inst_type(self, market: MarketType) -> str:
        return "SWAP" if market is MarketType.FUTURES else "SPOT"

    def _inst_id(self, symbol: str, market: MarketType) -> str:
        pair = split_pair(symbol)
        if pair is None:
            raise MarketDataError(f"okx: cannot map symbol {symbol}")
        base, quote = pair
        return f"{base}-{quote}-SWAP" if market is MarketType.FUTURES else f"{base}-{quote}"

    def _rows(self, payload) -> list:
        if not isinstance(payload, dict):
            raise MarketDataError("okx: unexpected response shape")
        if str(payload.get("code", "0")) not in ("0", ""):
            raise MarketDataError(f"okx: {payload.get('msg') or payload.get('code')}")
        data = payload.get("data")
        return data if isinstance(data, list) else []

    def candles(self, *, symbol, interval, market, limit, end=None):
        params = {
            "instId": self._inst_id(symbol, market),
            "bar": self._INTERVALS[interval],
            "limit": min(limit, self.page_limit),
        }
        # `after` means "older than this timestamp" — OKX pages backwards, which
        # is the direction the backfill walks.
        path = "/api/v5/market/candles"
        if end is not None:
            params["after"] = end * 1000
            path = "/api/v5/market/history-candles"
        rows = self._rows(self._get(f"{self._BASE}{path}", params))
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
        candles.reverse()  # newest first on the wire
        return candles

    def ticker(self, *, symbol, market):
        rows = self._rows(
            self._get(
                f"{self._BASE}/api/v5/market/ticker",
                {"instId": self._inst_id(symbol, market)},
            )
        )
        if not rows:
            raise MarketDataError(f"okx: no ticker for {symbol}")
        row = rows[0]
        last, open24h = D(row.get("last") or "0"), D(row.get("open24h") or "0")
        return Ticker(
            symbol=symbol.upper(),
            price=last,
            change_pct=(
                (last - open24h) / open24h * Decimal("100") if open24h else None
            ),
            at=_now_s(),
        )

    def symbols(self, *, market):
        inst_type = self._inst_type(market)
        rows = self._rows(
            self._get(f"{self._BASE}/api/v5/public/instruments", {"instType": inst_type})
        )
        volumes = {
            str(row.get("instId", "")): D(row.get("volCcy24h") or "0")
            for row in self._rows(
                self._get(f"{self._BASE}/api/v5/market/tickers", {"instType": inst_type})
            )
        }
        out: list[SymbolInfo] = []
        for row in rows:
            if row.get("state") not in ("live", None):
                continue
            # Inverse contracts are margined in the base asset, so spec §5's
            # 99%-of-USDT rule cannot size them. They are not listed.
            if market is MarketType.FUTURES and row.get("ctType") not in ("linear", None):
                continue
            inst_id = str(row.get("instId", ""))
            base = str(row.get("ctValCcy") or row.get("baseCcy") or "").upper()
            quote = str(row.get("settleCcy") or row.get("quoteCcy") or "").upper()
            if not base or not quote:
                continue
            # ctVal is the base-asset size of one contract; steps are expressed
            # in base units so sizing stays exchange-agnostic.
            contract = D(row.get("ctVal") or "1")
            out.append(
                SymbolInfo(
                    symbol=f"{base}{quote}",
                    base=base,
                    quote=quote,
                    native=inst_id,
                    price_tick=D(row.get("tickSz") or "0") or None,
                    qty_step=D(row.get("lotSz") or "1") * contract,
                    min_qty=D(row.get("minSz") or "1") * contract,
                    max_leverage=int(D(row.get("lever") or "0")),
                    volume_24h=volumes.get(inst_id),
                )
            )
        return out


class GateioPublicSource(HttpSource):
    """Gate.io v4 USDT-settled futures. Contracts are ``BTC_USDT``."""

    name = "gateio"
    exchange = "gateio"
    page_limit = 1000
    _BASE = "https://api.gateio.ws"
    _SETTLE = "usdt"
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def _contract(self, symbol: str) -> str:
        pair = split_pair(symbol)
        if pair is None:
            raise MarketDataError(f"gateio: cannot map symbol {symbol}")
        return f"{pair[0]}_{pair[1]}"

    def _path(self, market: MarketType, tail: str) -> str:
        if market is MarketType.SPOT:
            raise MarketDataError("gateio: this feed covers USDT futures only")
        return f"{self._BASE}/api/v4/futures/{self._SETTLE}/{tail}"

    def candles(self, *, symbol, interval, market, limit, end=None):
        limit = min(limit, self.page_limit)
        params = {
            "contract": self._contract(symbol),
            "interval": self._INTERVALS[interval],
            "limit": limit,
        }
        if end is not None:
            params["to"] = end
        rows = self._get(self._path(market, "candlesticks"), params)
        if not isinstance(rows, list):
            raise MarketDataError("gateio: unexpected candlestick shape")
        return [
            Candle(
                time=int(D(str(row.get("t", 0)))),
                open=D(str(row.get("o", "0"))),
                high=D(str(row.get("h", "0"))),
                low=D(str(row.get("l", "0"))),
                close=D(str(row.get("c", "0"))),
                volume=D(str(row.get("v", "0"))),
            )
            for row in rows
            if isinstance(row, dict)
        ]

    def _tickers(self, market: MarketType, contract: str = "") -> list[dict]:
        params = {"contract": contract} if contract else {}
        rows = self._get(self._path(market, "tickers"), params)
        listed = rows if isinstance(rows, list) else [rows]
        return [row for row in listed if isinstance(row, dict)]

    def ticker(self, *, symbol, market):
        rows = self._tickers(market, self._contract(symbol))
        if not rows:
            raise MarketDataError(f"gateio: no ticker for {symbol}")
        row = rows[0]
        change = row.get("change_percentage")
        return Ticker(
            symbol=symbol.upper(),
            price=D(str(row.get("last") or row.get("mark_price") or "0")),
            change_pct=None if change is None else D(str(change)),
            at=_now_s(),
        )

    def symbols(self, *, market):
        rows = self._get(self._path(market, "contracts"), {})
        if not isinstance(rows, list):
            raise MarketDataError("gateio: unexpected contracts shape")
        volumes = {
            str(row.get("contract", "")): D(str(row.get("volume_24h_quote") or "0"))
            for row in self._tickers(market)
        }
        out: list[SymbolInfo] = []
        for row in rows:
            name = str(row.get("name", ""))
            pair = name.split("_")
            if row.get("in_delisting") or len(pair) != 2:
                continue
            multiplier = D(str(row.get("quanto_multiplier") or "1")) or D("1")
            out.append(
                SymbolInfo(
                    symbol=f"{pair[0]}{pair[1]}".upper(),
                    base=pair[0].upper(),
                    quote=pair[1].upper(),
                    native=name,
                    price_tick=D(str(row.get("order_price_round") or "0")) or None,
                    qty_step=multiplier,
                    min_qty=multiplier,
                    max_leverage=int(D(str(row.get("leverage_max") or "0"))),
                    volume_24h=volumes.get(name),
                )
            )
        return out


class KucoinPublicSource(HttpSource):
    """KuCoin futures public endpoints. Contracts are ``XBTUSDTM``."""

    name = "kucoin"
    exchange = "kucoin"
    #: KuCoin serves at most 1500 bars per kline query.
    page_limit = 500
    _BASE = "https://api-futures.kucoin.com"
    #: Granularity is in minutes.
    _INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}

    def _contract(self, symbol: str) -> str:
        upper = symbol.upper()
        if upper.endswith("M"):
            return upper
        mapped = upper.replace("BTC", "XBT", 1) if upper.startswith("BTC") else upper
        return f"{mapped}M"

    def _canonical(self, contract: str) -> str:
        stripped = contract[:-1] if contract.endswith("M") else contract
        return stripped.replace("XBT", "BTC", 1) if stripped.startswith("XBT") else stripped

    def _data(self, payload):
        if not isinstance(payload, dict):
            raise MarketDataError("kucoin: unexpected response shape")
        if str(payload.get("code", "200000")) != "200000":
            raise MarketDataError(f"kucoin: {payload.get('msg') or payload.get('code')}")
        return payload.get("data")

    def candles(self, *, symbol, interval, market, limit, end=None):
        if market is MarketType.SPOT:
            raise MarketDataError("kucoin: this feed covers futures only")
        limit = min(limit, self.page_limit)
        start, finish = _window(interval, limit, end)
        rows = self._data(
            self._get(
                f"{self._BASE}/api/v1/kline/query",
                {
                    "symbol": self._contract(symbol),
                    "granularity": self._INTERVALS[interval],
                    "from": start * 1000,
                    "to": finish * 1000,
                },
            )
        )
        return [
            Candle(
                time=int(row[0]) // 1000,
                open=D(str(row[1])),
                high=D(str(row[2])),
                low=D(str(row[3])),
                close=D(str(row[4])),
                volume=D(str(row[5])),
            )
            for row in rows or []
        ]

    def ticker(self, *, symbol, market):
        row = self._data(
            self._get(f"{self._BASE}/api/v1/contracts/{self._contract(symbol)}", {})
        )
        if not isinstance(row, dict) or not row.get("lastTradePrice"):
            raise MarketDataError(f"kucoin: no ticker for {symbol}")
        change = row.get("priceChgPct")
        return Ticker(
            symbol=symbol.upper(),
            price=D(str(row["lastTradePrice"])),
            # priceChgPct is a fraction, like Bybit's.
            change_pct=None if change is None else D(str(change)) * Decimal("100"),
            at=_now_s(),
        )

    def symbols(self, *, market):
        if market is MarketType.SPOT:
            raise MarketDataError("kucoin: this feed covers futures only")
        rows = self._data(self._get(f"{self._BASE}/api/v1/contracts/active", {})) or []
        out: list[SymbolInfo] = []
        for row in rows:
            if row.get("isInverse") or row.get("status") not in ("Open", None):
                continue
            contract = str(row.get("symbol", ""))
            multiplier = abs(D(str(row.get("multiplier") or "1"))) or D("1")
            lot_step = abs(D(str(row.get("lotSize") or "1"))) or D("1")
            out.append(
                SymbolInfo(
                    symbol=self._canonical(contract),
                    base=str(row.get("baseCurrency", "")).upper(),
                    quote=str(row.get("quoteCurrency", "")).upper(),
                    native=contract,
                    price_tick=D(str(row.get("tickSize") or "0")) or None,
                    qty_step=multiplier * lot_step,
                    min_qty=multiplier * lot_step,
                    max_leverage=int(D(str(row.get("maxLeverage") or "0"))),
                    volume_24h=D(str(row.get("turnoverOf24h") or "0")) or None,
                )
            )
        return out


class ToobitPublicSource(HttpSource):
    """Toobit's quote service. Binance-shaped klines, its own instrument names."""

    name = "toobit"
    exchange = "toobit"
    page_limit = 1000
    _BASE = "https://api.toobit.com"
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def _native(self, symbol: str, market: MarketType) -> str:
        if market is MarketType.SPOT:
            return symbol.upper()
        pair = split_pair(symbol)
        if pair is None:
            raise MarketDataError(f"toobit: cannot map symbol {symbol}")
        # Toobit perpetuals are named BTC-SWAP-USDT.
        return f"{pair[0]}-SWAP-{pair[1]}"

    def candles(self, *, symbol, interval, market, limit, end=None):
        params = {
            "symbol": self._native(symbol, market),
            "interval": self._INTERVALS[interval],
            "limit": min(limit, self.page_limit),
        }
        if end is not None:
            start, finish = _window(interval, min(limit, self.page_limit), end)
            params["startTime"], params["endTime"] = start * 1000, finish * 1000
        rows = self._get(f"{self._BASE}/quote/v1/klines", params)
        if not isinstance(rows, list):
            raise MarketDataError("toobit: unexpected klines shape")
        return [
            Candle(
                time=int(row[0]) // 1000,
                open=D(str(row[1])),
                high=D(str(row[2])),
                low=D(str(row[3])),
                close=D(str(row[4])),
                volume=D(str(row[5])),
            )
            for row in rows
        ]

    def _ticker_path(self, market: MarketType) -> str:
        return (
            "/quote/v1/contract/ticker/24hr"
            if market is MarketType.FUTURES
            else "/quote/v1/ticker/24hr"
        )

    def ticker(self, *, symbol, market):
        payload = self._get(
            f"{self._BASE}{self._ticker_path(market)}",
            {"symbol": self._native(symbol, market)},
        )
        rows = payload if isinstance(payload, list) else [payload]
        row = next((r for r in rows if isinstance(r, dict) and r.get("c")), None)
        if row is None:
            raise MarketDataError(f"toobit: no ticker for {symbol}")
        open_price = D(str(row.get("o") or "0"))
        last = D(str(row.get("c") or row.get("lastPrice") or "0"))
        return Ticker(
            symbol=symbol.upper(),
            price=last,
            change_pct=(
                (last - open_price) / open_price * Decimal("100") if open_price else None
            ),
            at=_now_s(),
        )

    def symbols(self, *, market):
        payload = self._get(f"{self._BASE}/api/v1/exchangeInfo", {})
        if not isinstance(payload, dict):
            raise MarketDataError("toobit: unexpected exchangeInfo shape")
        key = "contracts" if market is MarketType.FUTURES else "symbols"
        entries = payload.get(key) or payload.get("symbols") or []
        out: list[SymbolInfo] = []
        for entry in entries:
            native = str(entry.get("symbol", ""))
            base = str(entry.get("baseAsset") or entry.get("baseTokenName") or "").upper()
            quote = str(entry.get("quoteAsset") or entry.get("quoteTokenName") or "").upper()
            if not base or not quote:
                continue
            filters = {f.get("filterType"): f for f in entry.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            notional = filters.get("MIN_NOTIONAL", filters.get("NOTIONAL", {}))
            out.append(
                SymbolInfo(
                    symbol=f"{base}{quote}",
                    base=base,
                    quote=quote,
                    native=native,
                    price_tick=D(filters.get("PRICE_FILTER", {}).get("tickSize") or "0") or None,
                    qty_step=D(lot.get("stepSize") or "0") or None,
                    min_qty=D(lot.get("minQty") or "0") or None,
                    min_notional=D(notional.get("minNotional") or "0") or None,
                )
            )
        return out


class LbankPublicSource(HttpSource):
    """LBank **spot** public data. Futures is unreachable at all (questions.md Q10)."""

    name = "lbank"
    exchange = "lbank"
    page_limit = 500
    _BASE = "https://api.lbkex.com"
    _INTERVALS = {
        "1m": "minute1",
        "5m": "minute5",
        "15m": "minute15",
        "1h": "hour1",
        "4h": "hour4",
        "1d": "day1",
    }

    def _pair(self, symbol: str) -> str:
        split = split_pair(symbol)
        if split is None:
            raise MarketDataError(f"lbank: cannot map symbol {symbol}")
        return f"{split[0]}_{split[1]}".lower()

    def _guard(self, market: MarketType) -> None:
        if market is MarketType.FUTURES:
            raise MarketDataError(
                "lbank: no public futures market data — see questions.md Q10"
            )

    def _rows(self, payload) -> list:
        if not isinstance(payload, dict):
            raise MarketDataError("lbank: unexpected response shape")
        if payload.get("result") in ("false", False):
            raise MarketDataError(f"lbank: {payload.get('error_code') or 'request rejected'}")
        data = payload.get("data")
        return data if isinstance(data, list) else []

    def candles(self, *, symbol, interval, market, limit, end=None):
        self._guard(market)
        limit = min(limit, self.page_limit)
        start, _finish = _window(interval, limit, end)
        rows = self._rows(
            self._get(
                f"{self._BASE}/v2/kline.do",
                {
                    "symbol": self._pair(symbol),
                    "size": limit,
                    "type": self._INTERVALS[interval],
                    "time": start,
                },
            )
        )
        return [
            Candle(
                time=int(row[0]),
                open=D(str(row[1])),
                high=D(str(row[2])),
                low=D(str(row[3])),
                close=D(str(row[4])),
                volume=D(str(row[5])),
            )
            for row in rows
        ]

    def ticker(self, *, symbol, market):
        self._guard(market)
        rows = self._rows(
            self._get(f"{self._BASE}/v2/ticker/24hr.do", {"symbol": self._pair(symbol)})
        )
        if not rows:
            raise MarketDataError(f"lbank: no ticker for {symbol}")
        quote = rows[0].get("ticker") or {}
        change = quote.get("change")
        return Ticker(
            symbol=symbol.upper(),
            price=D(str(quote.get("latest") or "0")),
            change_pct=None if change is None else D(str(change)),
            at=_now_s(),
        )

    def symbols(self, *, market):
        self._guard(market)
        rows = self._rows(self._get(f"{self._BASE}/v2/accuracy.do", {}))
        out: list[SymbolInfo] = []
        for row in rows:
            native = str(row.get("symbol", ""))
            parts = native.split("_")
            if len(parts) != 2:
                continue
            quantity_dp = int(D(str(row.get("quantityAccuracy") or "0")))
            price_dp = int(D(str(row.get("priceAccuracy") or "0")))
            out.append(
                SymbolInfo(
                    symbol=f"{parts[0]}{parts[1]}".upper(),
                    base=parts[0].upper(),
                    quote=parts[1].upper(),
                    native=native,
                    price_tick=Decimal(1).scaleb(-price_dp),
                    qty_step=Decimal(1).scaleb(-quantity_dp),
                    min_qty=D(str(row.get("minTranQua") or "0")) or None,
                )
            )
        return out


class HyperliquidPublicSource(HttpSource):
    """Hyperliquid's ``/info`` endpoint — POST, unsigned, no account context.

    Perps are named by base asset alone (``BTC``), and only the most recent
    5000 candles per interval exist at all, so a year of 1m bars is not
    something this venue can serve. The backfill records what there is.
    """

    name = "hyperliquid"
    exchange = "hyperliquid"
    page_limit = 500
    limited_history = True
    _BASE = "https://api.hyperliquid.xyz"
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
    #: The venue quotes perps in USD but every account here is USDT-denominated;
    #: the canonical symbol keeps the platform's naming.
    _QUOTE = "USDT"
    #: One quote costs the *whole* perp universe here (~70 KB, 1.3–2.7s): this
    #: venue has no per-symbol ticker endpoint. A ten-pair watchlist therefore
    #: downloaded it ten times per refresh and spent twenty seconds doing it,
    #: which is how a working feed ends up looking like a dead one. The payload
    #: is shared across symbols for as long as a quote is considered fresh.
    _CTX_KEY = "md:hl:ctxs"
    _CTX_TTL = 3

    def _coin(self, symbol: str) -> str:
        pair = split_pair(symbol)
        return pair[0] if pair else symbol.upper()

    def _info(self, body: dict):
        return self._post(f"{self._BASE}/info", body)

    def candles(self, *, symbol, interval, market, limit, end=None):
        if market is MarketType.SPOT:
            raise MarketDataError("hyperliquid: this feed covers perpetuals only")
        limit = min(limit, self.page_limit)
        start, finish = _window(interval, limit, end)
        rows = self._info(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": self._coin(symbol),
                    "interval": self._INTERVALS[interval],
                    "startTime": start * 1000,
                    "endTime": finish * 1000,
                },
            }
        )
        if not isinstance(rows, list):
            raise MarketDataError("hyperliquid: unexpected candle shape")
        return [
            Candle(
                time=int(row["t"]) // 1000,
                open=D(str(row["o"])),
                high=D(str(row["h"])),
                low=D(str(row["l"])),
                close=D(str(row["c"])),
                volume=D(str(row.get("v", "0"))),
            )
            for row in rows
            if isinstance(row, dict) and "t" in row
        ]

    def _contexts(self) -> list[tuple[dict, dict]]:
        payload = cache.get(self._CTX_KEY)
        if payload is None:
            payload = self._info({"type": "metaAndAssetCtxs"})
            if isinstance(payload, list) and len(payload) >= 2:
                cache.set(self._CTX_KEY, payload[:2], self._CTX_TTL)
        if not isinstance(payload, list) or len(payload) < 2:
            raise MarketDataError("hyperliquid: unexpected meta shape")
        universe = (payload[0] or {}).get("universe") or []
        contexts = payload[1] or []
        return [
            (asset, contexts[i] if i < len(contexts) else {})
            for i, asset in enumerate(universe)
            if isinstance(asset, dict)
        ]

    def ticker(self, *, symbol, market):
        coin = self._coin(symbol)
        for asset, context in self._contexts():
            if str(asset.get("name", "")).upper() != coin:
                continue
            mark = D(str(context.get("markPx") or context.get("midPx") or "0"))
            previous = D(str(context.get("prevDayPx") or "0"))
            return Ticker(
                symbol=symbol.upper(),
                price=mark,
                change_pct=(
                    (mark - previous) / previous * Decimal("100") if previous else None
                ),
                at=_now_s(),
            )
        raise MarketDataError(f"hyperliquid: no market for {symbol}")

    def symbols(self, *, market):
        if market is MarketType.SPOT:
            raise MarketDataError("hyperliquid: this feed covers perpetuals only")
        out: list[SymbolInfo] = []
        for asset, context in self._contexts():
            if asset.get("isDelisted"):
                continue
            base = str(asset.get("name", "")).upper()
            if not base:
                continue
            # szDecimals is the size precision; there is no separate step.
            step = Decimal(1).scaleb(-int(D(str(asset.get("szDecimals") or "0"))))
            out.append(
                SymbolInfo(
                    symbol=f"{base}{self._QUOTE}",
                    base=base,
                    quote=self._QUOTE,
                    native=base,
                    qty_step=step,
                    min_qty=step,
                    # $10 is the documented minimum order value on Hyperliquid.
                    min_notional=Decimal("10"),
                    max_leverage=int(D(str(asset.get("maxLeverage") or "0"))),
                    volume_24h=D(str(context.get("dayNtlVlm") or "0")) or None,
                )
            )
        return out


#: Every public source, keyed by the name used in ``MARKET_DATA_PROVIDERS`` —
#: which is also the ``accounts.Exchange`` value, so a connected account's
#: exchange resolves straight to its feed.
SOURCES: dict[str, type[HttpSource]] = {
    "binance": BinancePublicSource,
    "bybit": BybitPublicSource,
    "okx": OkxPublicSource,
    "gateio": GateioPublicSource,
    "kucoin": KucoinPublicSource,
    "toobit": ToobitPublicSource,
    "lbank": LbankPublicSource,
    "hyperliquid": HyperliquidPublicSource,
}
