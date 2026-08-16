"""Binance USDⓈ-M futures, and Toobit.

The two share **only a signing scheme** — HMAC-SHA256 over the query string with
`timestamp` and `signature` parameters. They shared far more than that until
2026-08-13, and that was the bug: Toobit's request shapes were being sent to
Binance. See ``reference/exchanges/binance/README.md`` for the full list of what
that broke and ``docs/exchanges/coverage.md`` for the audit trail.

Everything Binance does here is checked against material vendored in
``reference/exchanges/binance/`` — the official ``binance-futures-connector-python``
for endpoint paths and parameter names, and the USDⓈ-M documentation snapshot for
response shapes and filters. Toobit's half is checked against
``reference/exchanges/toobit/api/`` (``X-BB-APIKEY``, lowercase hex, parameter
order must match signature order).

Three Binance facts that are easy to get wrong from memory, all of them load-bearing:

* Balance is ``/fapi/v3/balance``. ``/fapi/v1/balance`` **does not exist**.
* ``/fapi/v3/positionRisk`` **dropped the ``leverage`` field**; per-symbol
  configuration moved to ``/fapi/v1/symbolConfig``.
* ``POST /fapi/v1/order`` has **no ``stopLoss`` or ``takeProfit`` parameters**.
  Protection is separate ``STOP_MARKET`` / ``TAKE_PROFIT_MARKET`` orders.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from collections.abc import AsyncIterator
from decimal import ROUND_DOWN, Decimal
from typing import Any
from urllib.parse import urlencode

from apps.core.money import D
from apps.exchanges.base import (
    AdapterError,
    AuthError,
    Balance,
    Capabilities,
    MarketType,
    NotSupported,
    OrderResult,
    OrderType,
    Position,
    Side,
    SymbolRules,
    WithdrawalPermissionError,
)
from apps.exchanges.rest import RestAdapter

logger = logging.getLogger(__name__)

#: -2011 "Unknown order sent" / -2013 "No such order" / -1143 "Order not found
#: on order book" — the order triggered or was cancelled between the snapshot
#: and the cancel. That is a race, not a failure (see base.cancel_orders).
_GONE = ("-2011", "-2013", "-1143", "unknown order", "does not exist")


def _already_gone(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _GONE)


#: -2015 "Invalid API-key, IP, or permissions for action" is what a futures-only
#: key gets from /sapi. It cannot be told apart from a genuinely dead key, so the
#: account ends up paused and flagged either way — but the note says which.
_NO_SPOT_ACCESS = ("-2015", "permission", "not authorized", "unauthorized")


def _no_spot_access(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _NO_SPOT_ACCESS)


#: -1021 "Timestamp for this request is outside of the recvWindow". A drifting
#: local clock rejects every signed call with no other symptom, so it is worth
#: recovering from rather than failing every leg of every trade.
def _clock_drift(exc: Exception) -> bool:
    text = str(exc).lower()
    return "-1021" in text or "recvwindow" in text


class BinanceStyleAdapter(RestAdapter):
    """Signing and the Q5d order-cancel contract. **No request shapes.**

    Deliberately holds nothing that differs between the two exchanges. Every
    verb lives on the concrete adapter, because the previous arrangement — one
    shared set of verbs — is precisely how Toobit's endpoints ended up being
    sent to Binance.
    """

    api_key_header = "X-MBX-APIKEY"
    futures_prefix = "/fapi/v1"
    spot_prefix = "/api/v3"
    recv_window = 5000

    #: Server-time minus local-time, in ms, learned only after a clock-drift
    #: rejection. Class-level so it survives the per-request adapter rebuild;
    #: it is public timing data, not credentials, so sharing it across accounts
    #: carries nothing and costs one fewer round trip per leg.
    _time_offset_ms: int = 0

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        payload = {**(params or {}), **(body or {})}
        payload["timestamp"] = int(time.time() * 1000) + type(self)._time_offset_ms
        payload["recvWindow"] = self.recv_window
        # The signature covers this exact string, and the docs require the
        # transmitted parameter order to match it. dict preserves insertion
        # order and httpx encodes params in that order, so the two agree.
        query = urlencode(payload)
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        headers = {self.api_key_header: self.api_key}

        if method.upper() in {"GET", "DELETE"}:
            return headers, {**payload, "signature": signature}, None

        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return headers, None, f"{query}&signature={signature}".encode()

    def unwrap(self, payload: Any) -> Any:
        if isinstance(payload, dict) and payload.get("code") not in (None, 200, "200", 0):
            raise AdapterError(f"{self.name}: {payload.get('msg', payload)}")
        return payload

    def _prefix(self, market: MarketType) -> str:
        return self.futures_prefix if market is MarketType.FUTURES else self.spot_prefix

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Signed request with one retry after a clock-drift rejection.

        A local clock a few seconds off rejects *every* signed call with -1021
        and nothing else to go on. One resync and one retry turns a total outage
        into a single slow request.
        """
        try:
            return await super().request(method, path, **kwargs)
        except AdapterError as exc:
            if not kwargs.get("signed", True) or not _clock_drift(exc):
                raise
            await self._sync_clock()
            return await super().request(method, path, **kwargs)

    async def _sync_clock(self) -> None:
        data = await super().request(
            "GET", f"{self.futures_prefix}/time", signed=False
        )
        server_ms = int(data.get("serverTime", 0))
        if server_ms:
            type(self)._time_offset_ms = server_ms - int(time.time() * 1000)
            logger.warning(
                "%s: local clock is %sms off the exchange; signed requests corrected",
                self.name,
                type(self)._time_offset_ms,
            )

    # --- spec §7 ------------------------------------------------------------

    async def verify_credentials(self) -> None:
        try:
            info = await self._get_account_permissions()
        except (AuthError, NotSupported):
            # NotSupported means "this exchange will not tell us" — a different
            # thing from a rejected credential, and verify_account flags the
            # account on it rather than reporting a broken key.
            raise
        except AdapterError as exc:
            raise AuthError(f"{self.name}: could not verify credentials — {exc}") from exc

        # Spec §7: a withdrawable key is a hard refusal.
        if info.get("enableWithdrawals"):
            raise WithdrawalPermissionError(
                f"{self.name}: this API key has withdrawal rights. Recreate it as "
                "trade-only before connecting the account."
            )

    async def _get_account_permissions(self) -> dict:
        """Key permissions. Overridden where the exchange exposes them differently."""
        return await self.request("GET", "/sapi/v1/account/apiRestrictions")

    # --- Q5d ----------------------------------------------------------------

    #: Order types this platform places as SL/TP protection. Only these are
    #: ever cancelled by the Q5d strategy — an unrelated working order the
    #: partner placed by hand must survive an SL/TP change untouched.
    #: STOP/STOP_PROFIT_LOSS are Toobit's names for the same thing
    #: (reference/exchanges/toobit/api/usdt-m-account-and-trading.md openOrders).
    conditional_types = frozenset(
        {"STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT", "STOP_PROFIT_LOSS"}
    )

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        data = await self.request(
            "GET", f"{self.futures_prefix}/openOrders", params={"symbol": symbol}, weight=3
        )
        rows = data if isinstance(data, list) else []
        return [
            str(row["orderId"])
            for row in rows
            if row.get("type") in self.conditional_types and row.get("orderId") is not None
        ]

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        for order_id in order_ids:
            try:
                await self.request(
                    "DELETE",
                    f"{self.futures_prefix}/order",
                    params={"symbol": symbol, "orderId": order_id},
                )
            except AdapterError as exc:
                if not _already_gone(exc):
                    raise
                logger.info("%s: order %s was already gone", self.name, order_id)

    async def _exchange_info(self) -> dict[str, dict]:
        # An injected client means a mocked transport. Caching across mocks
        # would leak one test's fixture into the next, and the cache is a
        # latency optimisation, not behaviour — so tests skip it entirely.
        if self._injected:
            return await self._fetch_exchange_info()

        host = self._url
        cached = _EXCHANGE_INFO.get(host)
        now = time.monotonic()
        if cached and now - cached[0] < _EXCHANGE_INFO_TTL:
            return cached[1]

        lock = _EXCHANGE_INFO_LOCKS.setdefault(host, asyncio.Lock())
        async with lock:
            # Another leg of the same fan-out may have filled it while we waited.
            cached = _EXCHANGE_INFO.get(host)
            if cached and time.monotonic() - cached[0] < _EXCHANGE_INFO_TTL:
                return cached[1]
            symbols = await self._fetch_exchange_info()
            _EXCHANGE_INFO[host] = (time.monotonic(), symbols)
            return symbols


# --- Binance ----------------------------------------------------------------


#: Parsed ``/fapi/v1/exchangeInfo`` per host: ``{host: (fetched_at, {symbol: filters})}``.
#: That endpoint takes no symbol filter and answers with the *whole* exchange —
#: megabytes — which does not fit the 0.8s per-request budget on every leg of
#: every fan-out. It is public, unsigned, identical for every account, so
#: caching the parsed result across adapters carries no credential and cannot
#: couple two accounts' failures. The HTTP clients stay per-account regardless,
#: which is what spec §2 isolation actually requires.
_EXCHANGE_INFO: dict[str, tuple[float, dict[str, dict]]] = {}
_EXCHANGE_INFO_TTL = 900.0
_EXCHANGE_INFO_LOCKS: dict[str, asyncio.Lock] = {}

#: Hedge mode per credential, keyed by a digest of the key so the key itself is
#: never a dict key anywhere. Position mode is an account setting that changes
#: about never, and reading it costs a signed round trip we cannot afford on
#: every entry.
_HEDGE_MODE: dict[str, tuple[float, bool]] = {}
_HEDGE_MODE_TTL = 300.0


class BinanceAdapter(BinanceStyleAdapter):
    """USDⓈ-M futures.

    Every path below is from the official connector vendored at
    ``reference/exchanges/binance/futures-connector-python/binance/um_futures/``.
    """

    name = "binance"
    base_url = "https://fapi.binance.com"
    testnet_url = "https://testnet.binancefuture.com"

    #: Binance bills USDⓈ-M in *weight*, 2400/minute per IP — 40/s. The base
    #: class's 8/20 default is a guess that predates any documentation, and it
    #: is smaller than a single ``positionSide/dual`` call (weight 30), so that
    #: request could never be issued at all. Half the documented budget, because
    #: the limit is per-IP and every account on this host shares it.
    rate = 20.0
    burst = 100
    capabilities = Capabilities(
        markets=frozenset({MarketType.FUTURES}),
        has_testnet=True,
        # Binance has no way to attach SL/TP to the entry order — the parameters
        # simply do not exist on POST /fapi/v1/order. Protection is placed after
        # the fill, which is the dangerous window Q5e's policy covers.
        native_sltp_on_entry=False,
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=False,  # Binance weights are per-IP as well as per-key
    )

    #: `/sapi/v1` lives on the **spot** host while `base_url` here is the
    #: futures host, so this one call goes out on a second client for that host
    #: (``RestAdapter.host_client``). Before that the request went to
    #: fapi.binance.com/sapi/... and 4xx'd every single time, which meant the
    #: spec §7 refusal below could never fire for Binance.
    spot_url = "https://api.binance.com"
    spot_testnet_url = ""  # the futures testnet has no /sapi namespace

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        #: /fapi/v3/positionRisk no longer reports leverage, so it is carried
        #: from whatever last set or read it for this adapter instance.
        self._leverage: dict[str, int] = {}

    async def _get_account_permissions(self) -> dict:
        host = self.spot_testnet_url if self.testnet else self.spot_url
        if not host:
            raise NotSupported(
                "binance: the futures testnet exposes no key-permission endpoint, so "
                "withdrawal rights cannot be checked there. Confirm in the Binance "
                "dashboard that the key is trade-only."
            )
        try:
            return await self.request(
                "GET", "/sapi/v1/account/apiRestrictions", client=self.host_client(host)
            )
        except AdapterError as exc:
            # A futures-only key cannot reach /sapi at all. That proves nothing
            # about withdrawal rights either way, so say so instead of reporting
            # it as a broken credential — the account connects flagged, not
            # refused, exactly like the exchanges with no permission endpoint.
            if _no_spot_access(exc):
                raise NotSupported(
                    "binance: this key has no spot API access, so Binance will not "
                    "report its withdrawal permission. Confirm in the Binance "
                    f"dashboard that the key is trade-only ({exc})."
                ) from exc
            raise

    # --- account ------------------------------------------------------------

    async def get_balance(self, asset: str = "USDT") -> Balance:
        """``GET /fapi/v3/balance``.

        v1 does not exist and v2 is the previous generation; the connector uses
        v3. ``availableBalance`` is what spec §5 takes 99% of — ``balance``
        includes margin already committed to open positions.
        """
        data = await self.request("GET", "/fapi/v3/balance", weight=5)
        for row in data if isinstance(data, list) else []:
            if row.get("asset", "").upper() == asset.upper():
                return Balance(
                    asset=asset,
                    available=D(row.get("availableBalance", "0")),
                    total=D(row.get("balance", "0")),
                )
        return Balance(asset=asset, available=D("0"), total=D("0"))

    async def _hedge_mode(self) -> bool:
        """True when the account is in Hedge (dual-side) position mode.

        It changes what a valid order looks like: hedge mode *requires*
        ``positionSide`` and *forbids* ``reduceOnly``. Getting it wrong is
        rejection -4061, on every order.
        """
        digest = hashlib.sha256(self.api_key.encode()).hexdigest()[:16]
        now = time.monotonic()
        # As with exchange info: an injected client is a mock, and a cache that
        # outlives the mock would answer the next test with the last one's fixture.
        if not self._injected:
            cached = _HEDGE_MODE.get(digest)
            if cached and now - cached[0] < _HEDGE_MODE_TTL:
                return cached[1]
        data = await self.request("GET", "/fapi/v1/positionSide/dual", weight=30)
        dual = bool(data.get("dualSidePosition", False))
        if not self._injected:
            _HEDGE_MODE[digest] = (now, dual)
        return dual

    def _position_side(self, side: Side) -> str:
        return "LONG" if side is Side.LONG else "SHORT"

    # --- market rules -------------------------------------------------------

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        if market is MarketType.SPOT:
            raise NotSupported(
                "binance: this adapter covers USDⓈ-M futures only. Spot would be a "
                "different host (api.binance.com) and a different order model."
            )
        entry = (await self._exchange_info()).get(symbol)
        if entry is None:
            raise AdapterError(f"binance: unknown symbol {symbol}")

        filters = {f["filterType"]: f for f in entry.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot = filters.get("LOT_SIZE", {})
        market_lot = filters.get("MARKET_LOT_SIZE", {})
        notional = filters.get("MIN_NOTIONAL", {})

        # LOT_SIZE governs limit orders and MARKET_LOT_SIZE market orders, and
        # they differ per symbol. Sizing happens before the order type is known
        # here, so take whichever is stricter and stay valid for both.
        steps = [D(f["stepSize"]) for f in (lot, market_lot) if f.get("stepSize")]
        mins = [D(f["minQty"]) for f in (lot, market_lot) if f.get("minQty")]

        return SymbolRules(
            symbol=symbol,
            price_tick=D(price_filter.get("tickSize", "0.01")),
            qty_step=max(steps) if steps else D("0.001"),
            min_qty=max(mins) if mins else D("0.001"),
            # The futures filter spells this "notional"; "minNotional" is spot.
            min_notional=D(notional.get("notional", "5")),
            # exchangeInfo carries no leverage cap — that is per-account and
            # lives in /fapi/v1/leverageBracket, a signed call this hot path
            # cannot afford. The platform ceiling applies instead, and
            # set_leverage below reports what the exchange actually granted.
            max_leverage=self.capabilities.max_leverage,
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        """``GET /fapi/v1/premiumIndex`` — the true mark price.

        Deliberately not ``/fapi/v2/ticker/price``: that is the last trade
        price, while every stop this adapter places triggers on
        ``workingType=MARK_PRICE``. Sizing and triggering off different prices
        is how a stop lands where nobody expected.
        """
        data = await self.request(
            "GET", "/fapi/v1/premiumIndex", params={"symbol": symbol}, signed=False
        )
        if isinstance(data, list):
            data = data[0] if data else {}
        return D(data.get("markPrice", "0"))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        data = await self.request(
            "POST",
            f"{self.futures_prefix}/leverage",
            body={"symbol": symbol, "leverage": leverage},
        )
        # Binance answers with the leverage it actually applied, which can be
        # lower than asked when the notional sits in a tighter bracket.
        granted = data.get("leverage") if isinstance(data, dict) else None
        self._leverage[symbol] = int(granted) if granted else leverage

    async def _symbol_leverage(self, symbol: str) -> int:
        """Leverage for a symbol. v3 positionRisk no longer reports it."""
        if symbol in self._leverage:
            return self._leverage[symbol]
        try:
            data = await self.request(
                "GET", f"{self.futures_prefix}/symbolConfig", params={"symbol": symbol}
            )
        except AdapterError:
            return 0
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if row.get("symbol") == symbol:
                self._leverage[symbol] = int(D(str(row.get("leverage", "0"))))
                return self._leverage[symbol]
        return 0

    # --- orders -------------------------------------------------------------

    async def place_order(
        self,
        *,
        symbol: str,
        market: MarketType,
        side: Side,
        qty: Decimal,
        order_type: OrderType,
        limit_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        reduce_only: bool = False,
        client_order_id: str | None = None,
    ) -> OrderResult:
        """``POST /fapi/v1/order``.

        ``stop_loss`` / ``take_profit`` are accepted and **ignored** — Binance
        has no parameter for either, which is what ``native_sltp_on_entry=False``
        declares. The executor reads that flag and calls ``set_sltp`` after the
        fill instead. Silently dropping them would be worse than the old code
        inventing parameters, so an attempt to use them is logged loudly.
        """
        if market is MarketType.SPOT:
            raise NotSupported("binance: this adapter covers USDⓈ-M futures only")
        if stop_loss is not None or take_profit is not None:
            logger.error(
                "binance: place_order was given SL/TP, which this exchange cannot "
                "attach at entry; they must go through set_sltp. Ignoring them."
            )

        body: dict[str, Any] = {
            "symbol": symbol,
            "side": "BUY" if side is Side.LONG else "SELL",
            "type": "MARKET" if order_type is OrderType.MARKET else "LIMIT",
            "quantity": f"{qty:f}",
            # ACK is the default and carries no fill. RESULT costs nothing extra
            # and returns avgPrice/executedQty, so the entry price recorded per
            # account is the real one rather than a mark price read afterwards.
            "newOrderRespType": "RESULT",
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError("binance: limit order needs a price")
            body["price"] = f"{limit_price:f}"
            body["timeInForce"] = "GTC"

        if await self._hedge_mode():
            # Hedge mode: positionSide is mandatory and reduceOnly is rejected.
            body["positionSide"] = self._position_side(side)
        elif reduce_only:
            body["reduceOnly"] = "true"

        if client_order_id:
            body["newClientOrderId"] = client_order_id[:36]

        data = await self.request("POST", f"{self.futures_prefix}/order", body=body, weight=2)
        filled = D(str(data.get("executedQty", "0")))
        avg = D(str(data.get("avgPrice", "0")))
        if filled == 0:
            # A resting limit order has no fill yet; report what was accepted.
            filled = D(str(data.get("origQty", qty)))
        if avg == 0:
            avg = D(str(data.get("price", "0"))) or await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("orderId", "")), filled_qty=filled, avg_price=avg, raw=data
        )

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        """Reduce-only conditional orders — Binance has no amend in place.

        Cancelling what this replaces is the caller's job (Q5d): see
        ``executor.apply_sltp``, which drives ``list_conditional_orders`` and
        ``cancel_orders`` around this call.

        ``closePosition=true`` is used rather than a quantity so the protection
        tracks the position if it is ever partially closed, and it is mutually
        exclusive with both ``quantity`` and ``reduceOnly``.
        """
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"binance: no open position on {symbol}")
        exit_side = "SELL" if position.side is Side.LONG else "BUY"
        hedge = await self._hedge_mode()

        for price, order_type in (
            (stop_loss, "STOP_MARKET"),
            (take_profit, "TAKE_PROFIT_MARKET"),
        ):
            if price is None:
                continue
            body: dict[str, Any] = {
                "symbol": symbol,
                "side": exit_side,
                "type": order_type,
                "stopPrice": f"{price:f}",
                "closePosition": "true",
                "workingType": "MARK_PRICE",
                # Rejects a trigger set the wrong side of the mark price rather
                # than accepting one that would fire the instant it is placed.
                "priceProtect": "TRUE",
            }
            if hedge:
                body["positionSide"] = self._position_side(position.side)
            await self.request("POST", f"{self.futures_prefix}/order", body=body, weight=2)

    async def get_sltp(self, symbol: str) -> SLTPState:
        """What is actually resting: the ``closePosition`` market triggers.

        ``STOP_MARKET`` is the stop, ``TAKE_PROFIT_MARKET`` the take-profit —
        both carry their trigger in ``stopPrice``. Only ``closePosition=true``
        orders count: those are the ones ``set_sltp`` places and the Q5d
        strategy cancels, so this is the same set the exchange will honour.
        """
        data = await self.request(
            "GET", f"{self.futures_prefix}/openOrders", params={"symbol": symbol}, weight=1
        )
        rows = data if isinstance(data, list) else []
        stop_loss = take_profit = None
        for row in rows:
            if not row.get("closePosition"):
                continue
            price = D(str(row.get("stopPrice") or "")) or None
            if price is None:
                continue
            if row.get("type") == "STOP_MARKET":
                stop_loss = price
            elif row.get("type") == "TAKE_PROFIT_MARKET":
                take_profit = price
        return SLTPState(stop_loss=stop_loss, take_profit=take_profit)

    async def get_position(self, symbol: str) -> Position | None:
        """``GET /fapi/v3/positionRisk``.

        v3 returns only symbols with a position or a working order, and it
        **dropped ``leverage``** — that now comes from ``/fapi/v1/symbolConfig``
        via ``_symbol_leverage``.
        """
        data = await self.request(
            "GET", "/fapi/v3/positionRisk", params={"symbol": symbol}, weight=5
        )
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            amount = D(str(row.get("positionAmt", "0")))
            if amount == 0:
                continue
            return Position(
                symbol=symbol,
                side=Side.LONG if amount > 0 else Side.SHORT,
                size=abs(amount),
                entry_price=D(str(row.get("entryPrice", "0"))),
                liquidation_price=D(str(row.get("liquidationPrice", "0"))) or None,
                unrealized_pnl=D(str(row.get("unRealizedProfit", "0"))),
                leverage=await self._symbol_leverage(symbol),
            )
        return None

    async def close_position(self, symbol: str) -> OrderResult:
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"binance: no open position to close on {symbol}")
        body: dict[str, Any] = {
            "symbol": symbol,
            "side": "SELL" if position.side is Side.LONG else "BUY",
            "type": "MARKET",
            "quantity": f"{position.size:f}",
            "newOrderRespType": "RESULT",
        }
        if await self._hedge_mode():
            body["positionSide"] = self._position_side(position.side)
        else:
            body["reduceOnly"] = "true"

        data = await self.request("POST", f"{self.futures_prefix}/order", body=body, weight=2)
        avg = D(str(data.get("avgPrice", "0"))) or await self.get_mark_price(symbol)
        filled = D(str(data.get("executedQty", "0"))) or position.size
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            filled_qty=filled,
            avg_price=avg,
            raw=data,
        )

    # --- private stream -----------------------------------------------------

    ws_url = "wss://fstream.binance.com"
    ws_testnet_url = "wss://stream.binancefuture.com"

    async def stream_events(self) -> AsyncIterator[dict]:
        """User data stream: fills, liquidations and position changes.

        ``POST /fapi/v1/listenKey`` opens it, ``PUT`` every 30 minutes keeps it
        alive (it expires after 60), and the socket carries ``ORDER_TRADE_UPDATE``
        and ``ACCOUNT_UPDATE``. Nothing in the platform consumes this yet —
        positions are still polled — so it is here to satisfy the per-exchange
        checklist and to be the seam a fill-driven history can hang off.
        """
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise NotSupported(
                "binance: the private stream needs the 'websockets' package"
            ) from exc

        data = await self.request("POST", f"{self.futures_prefix}/listenKey")
        listen_key = data.get("listenKey")
        if not listen_key:
            raise AdapterError("binance: the exchange returned no listenKey")

        host = self.ws_testnet_url if self.testnet else self.ws_url
        stop = asyncio.Event()

        async def keepalive() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1800)
                    return
                except TimeoutError:
                    try:
                        await self.request("PUT", f"{self.futures_prefix}/listenKey")
                    except AdapterError as exc:
                        logger.warning("binance: listenKey keepalive failed: %s", exc)

        pump = asyncio.create_task(keepalive())
        try:
            async with websockets.connect(f"{host}/ws/{listen_key}") as socket:
                async for message in socket:
                    try:
                        yield json.loads(message)
                    except ValueError:
                        logger.warning("binance: unparseable stream frame")
        finally:
            stop.set()
            pump.cancel()
            try:
                await self.request("DELETE", f"{self.futures_prefix}/listenKey")
            except AdapterError:
                pass


# --- Toobit -----------------------------------------------------------------


class ToobitAdapter(BinanceStyleAdapter):
    """Toobit USDT-M futures.

    Rebuilt 2026-08-16 against ``reference/exchanges/toobit/api/*`` after the
    2026-08-13 audit proved the previous shapes were Binance's, not Toobit's.
    The differences that matter, in one place:

    * **Signing** — parameters (``signature`` included) travel in the query
      string for every verb. Toobit signs ``totalParams`` = the query string,
      and the documented curl pattern puts ``signature`` in the query, so the
      form-body path is never taken here.
    * **Symbols** — the contract id is ``BTC-SWAP-USDT``, reached from the
      admin's ``BTCUSDT`` through ``exchangeInfo.contracts[].index``
      (USDT-margined, non-inverse only).
    * **Quantity is in contracts** — divide base size by ``contractMultiplier``.
      The ``LOT_SIZE`` / ``MIN_NOTIONAL`` filters are in base / quote units, so
      sizing never sees contract counts.
    * **Entry is the v2 endpoint** (``side`` + ``positionSide``, ``type``
      ``MARKET`` / ``LIMIT``); the response is wrapped in ``{code, msg, data}``.
    * **Closing is ``flashClose``** — it cancels working orders then
      market-closes. There is no ``reduceOnly`` parameter.
    * **SL/TP post-entry amend is native** — ``position/trading-stop`` replaces
      the position's protection in place, so ``native_sltp_amend`` is True and
      the Q5d cancel dance is never entered for this exchange.

    Spot is deliberately not declared: Toobit's spot order model differs
    (``POST /api/v1/spot/order``, ``BUY``/``SELL``, quote-quantity buys) and
    nothing in the platform needs it yet. Binance's adapter made the same call.

    Still doc-vs-code only — no testnet exists (Q9), so nothing here has been
    exercised against a live key. Tracked in ``docs/exchanges/coverage.md``.
    """

    name = "toobit"
    base_url = "https://api.toobit.com"
    testnet_url = ""  # Q9: no testnet documented — surfaced in the panel
    api_key_header = "X-BB-APIKEY"
    futures_prefix = "/api/v1/futures"
    spot_prefix = "/api/v1"
    ws_url = "wss://stream.toobit.com"
    capabilities = Capabilities(
        markets=frozenset({MarketType.FUTURES}),
        has_testnet=False,
        testnet_note="Toobit publishes no test environment — cannot be used in test mode.",
        native_sltp_on_entry=True,  # takeProfit/stopLoss accepted at entry (v2)
        native_sltp_amend=True,  # position/trading-stop replaces in place (Q5d)
        supports_reduce_only=True,  # closes via close-sides / flashClose
        max_leverage=10,
        per_key_rate_limits=True,
    )

    #: Toobit's names for the reduce-only SL/TP protection orders (Q5d). Only
    #: these are ever cancelled by the Q5d strategy — an unrelated working order
    #: the partner placed by hand must survive an SL/TP change untouched.
    conditional_types = frozenset({"STOP", "STOP_PROFIT_LOSS"})

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        # Toobit signs the query string and only the query string; params and
        # signature may all ride there for any verb. Sending them that way
        # sidesteps the "query string + body" signing rule entirely — the body
        # is always empty here.
        payload = {**(params or {}), **(body or {})}
        payload["timestamp"] = int(time.time() * 1000) + type(self)._time_offset_ms
        payload["recvWindow"] = self.recv_window
        query = urlencode(payload)
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return {self.api_key_header: self.api_key}, {**payload, "signature": signature}, None

    async def _sync_clock(self) -> None:
        # Toobit's server-time endpoint is /api/v1/time, not {futures_prefix}/time.
        data = await super().request("GET", "/api/v1/time", signed=False)
        server_ms = int(data.get("serverTime", 0))
        if server_ms:
            type(self)._time_offset_ms = server_ms - int(time.time() * 1000)
            logger.warning(
                "%s: local clock is %sms off the exchange; signed requests corrected",
                self.name,
                type(self)._time_offset_ms,
            )

    async def _get_account_permissions(self) -> dict:
        # Toobit's docs expose no key-permission endpoint. Spec §7 cannot be
        # verified programmatically here, so the admin must confirm at connect
        # time and the account is flagged until they do.
        raise NotSupported(
            "Toobit does not expose an API-key permission endpoint. Confirm the "
            "key is trade-only in the Toobit dashboard before connecting."
        )

    # --- contract id and exchange rules ---------------------------------------

    async def _fetch_exchange_info(self) -> dict[str, dict]:
        # Futures live under ``contracts`` (not ``symbols``), and only the
        # USDT-margined, non-inverse ones are reachable through this adapter.
        # Keyed by the plain ``index`` (``BTCUSDT``) so the admin's symbol maps
        # straight in.
        data = await self.request("GET", "/api/v1/exchangeInfo", signed=False, weight=1)
        return {
            entry["index"]: entry
            for entry in data.get("contracts", [])
            if entry.get("index")
            and entry.get("marginToken") == "USDT"
            and not entry.get("inverse")
        }

    async def _contract(self, symbol: str) -> tuple[str, Decimal]:
        entry = (await self._exchange_info()).get(symbol)
        if entry is None:
            raise AdapterError(f"{self.name}: unknown symbol {symbol}")
        return entry["symbol"], D(str(entry.get("contractMultiplier", "1")))

    @staticmethod
    def _v2_data(payload: Any) -> Any:
        # v2 responses wrap in {code, msg, data}; v1 do not. unwrap() has
        # already rejected non-200 codes, so just drop the envelope.
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict | list):
            return payload["data"]
        return payload

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        if market is MarketType.SPOT:
            raise NotSupported(
                "toobit: this adapter covers USDT-M futures only. Spot would be a "
                "different order model (POST /api/v1/spot/order)."
            )
        entry = (await self._exchange_info()).get(symbol)
        if entry is None:
            raise AdapterError(f"{self.name}: unknown symbol {symbol}")
        filters = {f["filterType"]: f for f in entry.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot = filters.get("LOT_SIZE", {})
        notional = filters.get("MIN_NOTIONAL", {})
        return SymbolRules(
            symbol=symbol,
            price_tick=D(str(price_filter.get("tickSize", "0.01"))),
            qty_step=D(str(lot.get("stepSize", "0.0001"))),
            min_qty=D(str(lot.get("minQty", "0.0001"))),
            min_notional=D(str(notional.get("minNotional", "5"))),
            max_leverage=self.capabilities.max_leverage,
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        contract, _ = await self._contract(symbol)
        data = await self.request(
            "GET", "/quote/v1/markPrice", params={"symbol": contract}, signed=False, weight=1
        )
        return D(str(data.get("price", "0")))

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request("GET", f"{self.futures_prefix}/balance", weight=5)
        rows = data if isinstance(data, list) else []
        for row in rows:
            if str(row.get("coin", "")).upper() == asset.upper():
                return Balance(
                    asset=asset,
                    available=D(str(row.get("availableBalance", "0"))),
                    total=D(str(row.get("balance", "0"))),
                )
        return Balance(asset=asset, available=D("0"), total=D("0"))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        contract, _ = await self._contract(symbol)
        await self.request(
            "POST",
            f"{self.futures_prefix}/leverage",
            body={"symbol": contract, "leverage": leverage},
        )

    async def place_order(
        self,
        *,
        symbol: str,
        market: MarketType,
        side: Side,
        qty: Decimal,
        order_type: OrderType,
        limit_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        reduce_only: bool = False,
        client_order_id: str | None = None,
    ) -> OrderResult:
        if market is MarketType.SPOT:
            raise NotSupported("toobit: this adapter covers USDT-M futures only")
        contract, multiplier = await self._contract(symbol)
        if multiplier <= 0:
            raise AdapterError(f"{self.name}: bad contractMultiplier for {symbol}")

        # Toobit sizes orders in whole contracts; the sizing layer works in base
        # units. The exchange's LOT_SIZE step equals the contract multiplier, so
        # the division is exact — round down defensively and refuse sub-contract
        # sizes rather than silently rounding up past the 99% margin cap.
        contracts = (qty / multiplier).to_integral_value(rounding=ROUND_DOWN)
        if contracts <= 0:
            raise AdapterError(
                f"{self.name}: size {qty} {symbol} is under one contract "
                f"({multiplier} {symbol} per contract)"
            )

        body: dict[str, Any] = {
            "symbol": contract,
            "side": "BUY" if side is Side.LONG else "SELL",
            "positionSide": "LONG" if side is Side.LONG else "SHORT",
            "type": "MARKET" if order_type is OrderType.MARKET else "LIMIT",
            "quantity": str(int(contracts)),
            # Mandatory on Toobit; the engine does not pass one.
            "newClientOrderId": (client_order_id or str(time.time_ns()))[:36],
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError("toobit: limit order needs a price")
            body["price"] = f"{limit_price:f}"
            body["timeInForce"] = "GTC"
        if stop_loss is not None:
            body["stopLoss"] = f"{stop_loss:f}"
        if take_profit is not None:
            body["takeProfit"] = f"{take_profit:f}"
        if stop_loss is not None or take_profit is not None:
            # Mark price is harder to manipulate than last-traded — the same
            # reason Binance sets workingType=MARK_PRICE on its stops.
            body["slTriggerBy"] = "MARK_PRICE"
            body["tpTriggerBy"] = "MARK_PRICE"

        data = self._v2_data(
            await self.request("POST", "/api/v2/futures/order", body=body, weight=1)
        )
        filled = D(str(data.get("executedQty", "0"))) * multiplier
        avg = D(str(data.get("avgPrice", "0")))
        if filled == 0:
            # A resting limit order has no fill yet; report what was accepted.
            filled = D(str(data.get("origQty", qty))) * multiplier
        if avg == 0:
            avg = D(str(data.get("price", "0"))) or await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("orderId", "")), filled_qty=filled, avg_price=avg, raw=data
        )

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        """Replace SL/TP in place via ``position/trading-stop`` (native amend).

        ``native_sltp_amend`` is True, so ``executor.apply_sltp`` calls this
        directly and never runs the Q5d cancel dance — the position's protection
        is overwritten as a whole and there is nothing to cancel.
        """
        contract, _ = await self._contract(symbol)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"{self.name}: no open position on {symbol}")
        await self.request(
            "POST",
            f"{self.futures_prefix}/position/trading-stop",
            body={
                "symbol": contract,
                "side": "LONG" if position.side is Side.LONG else "SHORT",
                "takeProfit": f"{take_profit:f}" if take_profit is not None else "",
                "stopLoss": f"{stop_loss:f}" if stop_loss is not None else "",
                "tpTriggerBy": "MARK_PRICE",
                "slTriggerBy": "MARK_PRICE",
            },
            weight=3,
        )

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        contract, _ = await self._contract(symbol)
        data = await self.request(
            "GET", f"{self.futures_prefix}/openOrders", params={"symbol": contract}, weight=1
        )
        rows = data if isinstance(data, list) else []
        return [
            str(row["orderId"])
            for row in rows
            if row.get("type") in self.conditional_types and row.get("orderId") is not None
        ]

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        contract, _ = await self._contract(symbol)
        for order_id in order_ids:
            try:
                # ``type=STOP`` covers both STOP and STOP_PROFIT_LOSS cancels.
                await self.request(
                    "DELETE",
                    f"{self.futures_prefix}/order",
                    params={"symbol": contract, "orderId": order_id, "type": "STOP"},
                )
            except AdapterError as exc:
                if not _already_gone(exc):
                    raise
                logger.info("%s: order %s was already gone", self.name, order_id)

    async def get_position(self, symbol: str) -> Position | None:
        contract, multiplier = await self._contract(symbol)
        data = await self.request(
            "GET", f"{self.futures_prefix}/positions", params={"symbol": contract}, weight=5
        )
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            contracts = D(str(row.get("position", "0")))
            if contracts == 0:
                continue
            return Position(
                symbol=symbol,
                side=Side.LONG if row.get("side") == "LONG" else Side.SHORT,
                size=contracts * multiplier,
                entry_price=D(str(row.get("avgPrice", "0"))),
                liquidation_price=D(str(row.get("flp", "0"))) or None,
                unrealized_pnl=D(str(row.get("unrealizedPnL", "0"))),
                leverage=int(D(str(row.get("leverage", "1")))),
            )
        return None

    async def close_position(self, symbol: str) -> OrderResult:
        contract, _ = await self._contract(symbol)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"{self.name}: no open position to close on {symbol}")
        data = await self.request(
            "POST",
            f"{self.futures_prefix}/flashClose",
            body={
                "symbol": contract,
                "side": "LONG" if position.side is Side.LONG else "SHORT",
                "clientOrderId": str(time.time_ns()),
            },
            weight=1,
        )
        avg = await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            filled_qty=position.size,
            avg_price=avg,
            raw=data,
        )

    # --- private stream -----------------------------------------------------

    async def stream_events(self) -> AsyncIterator[dict]:
        """User data stream: ``POST /api/v1/listenKey`` + ``stream.toobit.com``.

        Nothing in the platform consumes this yet — positions are polled — so it
        exists to satisfy the per-exchange checklist and to be the seam a
        fill-driven history can hang off. The listenKey endpoints take the same
        timestamp/signature as any signed call.
        """
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise NotSupported(
                "toobit: the private stream needs the 'websockets' package"
            ) from exc

        data = await self.request("POST", "/api/v1/listenKey")
        listen_key = data.get("listenKey")
        if not listen_key:
            raise AdapterError("toobit: the exchange returned no listenKey")

        stop = asyncio.Event()

        async def keepalive() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1800)
                    return
                except TimeoutError:
                    try:
                        await self.request(
                            "PUT", "/api/v1/listenKey", body={"listenKey": listen_key}
                        )
                    except AdapterError as exc:
                        logger.warning("toobit: listenKey keepalive failed: %s", exc)

        pump = asyncio.create_task(keepalive())
        try:
            async with websockets.connect(f"{self.ws_url}/api/v1/ws/{listen_key}") as socket:
                async for message in socket:
                    try:
                        yield json.loads(message)
                    except ValueError:
                        logger.warning("toobit: unparseable stream frame")
        finally:
            stop.set()
            pump.cancel()
            try:
                await self.request(
                    "DELETE", "/api/v1/listenKey", body={"listenKey": listen_key}
                )
            except AdapterError:
                pass
