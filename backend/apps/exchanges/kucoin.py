"""KuCoin Futures.

Checked against material vendored in ``reference/exchanges/kucoin/``: the
generated models of ``kucoin-universal-sdk`` for exact JSON field names, and the
official ``kucoin-futures-python-sdk`` for signing and endpoint paths. The Slate
repo in ``api-docs/`` covers spot only and contains no futures material at all —
which is why this adapter was previously written from memory and sent parameters
that do not exist.

Signing: HMAC-SHA256 over ``timestamp + METHOD + endpoint + body``, base64, where
``endpoint`` includes the **sorted** query string for GET *and* DELETE. The
passphrase is itself HMAC-signed and base64-encoded for key version 2+, which is
the part people get wrong — a plaintext passphrase fails with 400004.

Two things that differ from every other exchange here:

* **There are two order endpoints.** ``POST /api/v1/orders`` takes
  ``stop``/``stopPrice``/``stopPriceType``. ``POST /api/v1/st-orders`` takes
  ``triggerStopUpPrice``/``triggerStopDownPrice`` and is the only way to attach
  TP/SL at entry. Neither accepts the other's parameters. The old code sent
  ``triggerStopLossPrice`` — a name that appears in neither — to the first one.
* **Up and down are price directions, not TP and SL.** For a long, TP is Up and
  SL is Down; for a short they swap. Getting this backwards puts the stop where
  the target should be.

Sizes are in **contracts**: ``size`` is an integer count of lots, and one lot is
``multiplier`` units of the base asset.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from apps.core.money import D, floor_to_step
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
    SLTPState,
    SymbolRules,
    WithdrawalPermissionError,
    place_both,
)
from apps.exchanges.rest import RestAdapter

logger = logging.getLogger(__name__)

#: KuCoin answers a cancel for an order that already triggered with an error
#: rather than a no-op. Between the Q5d snapshot and the cancel that is a race,
#: not a failure (see base.cancel_orders).
_GONE = ("does not exist", "300009", "order not exist")


def _already_gone(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _GONE)


class KucoinAdapter(RestAdapter):
    name = "kucoin"
    base_url = "https://api-futures.kucoin.com"
    testnet_url = "https://api-sandbox-futures.kucoin.com"
    capabilities = Capabilities(
        markets=frozenset({MarketType.FUTURES}),
        has_testnet=True,
        # True via POST /api/v1/st-orders, which carries the triggers on the
        # entry order itself. This is worth having: it removes the unprotected
        # window between fill and stop placement that Q5e exists to cover.
        native_sltp_on_entry=True,
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,
    )

    #: Margin mode used for every position. Cross matches
    #: ``/api/v2/changeCrossUserLeverage`` below, so the leverage the platform
    #: sets is the leverage the position actually runs at.
    margin_mode = "CROSS"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        #: Base-asset units per contract, per symbol.
        self._lot: dict[str, Decimal] = {}
        #: Contract-size increment, per symbol. Usually 1.
        self._lot_step: dict[str, Decimal] = {}
        self._leverage = 1

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        timestamp = str(int(time.time() * 1000))
        method = method.upper()
        if method in {"GET", "DELETE"}:
            # DELETE signs its query string exactly like GET. Sorted, because
            # the signature covers this exact string and the transmitted order
            # has to match it (reference/exchanges/kucoin/futures-sdk-python
            # base_request.py:56-63).
            ordered = dict(sorted((params or {}).items()))
            endpoint = f"{path}?{urlencode(ordered)}" if ordered else path
            payload = ""
            content = None
            query: dict | None = ordered or None
        else:
            endpoint = path
            payload = json.dumps(body or {}, separators=(",", ":"))
            content = payload.encode()
            query = None

        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode(),
                f"{timestamp}{method}{endpoint}{payload}".encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        # Key version 2+: the passphrase is signed, not sent in the clear.
        signed_passphrase = base64.b64encode(
            hmac.new(self.api_secret.encode(), self.passphrase.encode(), hashlib.sha256).digest()
        ).decode()

        headers = {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-PASSPHRASE": signed_passphrase,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json",
        }
        return headers, query, content

    def unwrap(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        code = str(payload.get("code", "200000"))
        if code != "200000":
            message = payload.get("msg", "")
            if code.startswith("4000"):
                raise AuthError(f"kucoin: {message} (code {code})")
            raise AdapterError(f"kucoin: {message} (code {code})")
        return payload.get("data", payload)

    # --- interface ---------------------------------------------------------

    #: Key permissions are published — but on the **spot** host, not the
    #: futures one this adapter otherwise talks to
    #: (`GET /api/v1/user/api-key`, see reference/exchanges/kucoin/universal-sdk
    #: `account/account/api_account_test.py`). Same credential, same signing.
    spot_url = "https://api.kucoin.com"

    #: KuCoin's permission strings. "Transfer" is the one that moves funds out
    #: of the account; "InnerTransfer" only moves between the user's own
    #: sub-accounts and is not a withdrawal right.
    WITHDRAWAL_PERMISSIONS = ("transfer",)

    async def verify_credentials(self) -> None:
        if self.testnet:
            # The sandbox has no spot host to ask.
            await self.request(
                "GET", "/api/v1/account-overview", params={"currency": "USDT"}
            )
            raise NotSupported(
                "kucoin: the sandbox exposes no key-permission endpoint. Confirm in "
                "the KuCoin dashboard that the key is trade-only."
            )

        data = await self.request(
            "GET", "/api/v1/user/api-key", client=self.host_client(self.spot_url)
        )
        granted = [
            perm.strip().lower()
            for perm in str((data or {}).get("permission", "")).split(",")
            if perm.strip()
        ]
        if not granted:
            raise NotSupported(
                "kucoin: the key-permission endpoint returned no permission list, so "
                "withdrawal rights could not be checked. Confirm in the KuCoin "
                "dashboard that the key is trade-only."
            )
        # Spec §7: a withdrawable key is a hard refusal.
        if any(perm in self.WITHDRAWAL_PERMISSIONS for perm in granted):
            raise WithdrawalPermissionError(
                "kucoin: this API key carries the Transfer permission, which can move "
                "funds out of the account. Recreate it with trade-only rights before "
                "connecting the account."
            )

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request(
            "GET", "/api/v1/account-overview", params={"currency": asset}
        )
        return Balance(
            asset=asset,
            available=D(data.get("availableBalance", "0")),
            total=D(data.get("accountEquity", "0")),
        )

    def _contract(self, symbol: str) -> str:
        """BTCUSDT -> XBTUSDTM. KuCoin uses XBT for bitcoin and an M suffix."""
        if symbol.endswith("M"):
            return symbol
        mapped = symbol.replace("BTC", "XBT", 1) if symbol.startswith("BTC") else symbol
        return f"{mapped}M"

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        if market is MarketType.SPOT:
            raise NotSupported("kucoin: this adapter covers futures only")
        contract = self._contract(symbol)
        data = await self.request(
            "GET", f"/api/v1/contracts/{contract}", signed=False
        )
        if data.get("isInverse"):
            # An inverse contract is margined in the base asset, so the whole
            # 99%-of-USDT sizing rule in spec §5 does not apply to it.
            raise NotSupported(
                f"kucoin: {contract} is an inverse contract, not USDT-margined; "
                "this platform sizes in USDT only"
            )

        # multiplier = base-asset units in one contract.
        # lotSize     = how many contracts an order size must be a multiple of.
        multiplier = abs(D(str(data.get("multiplier", "1"))))
        lot_step = abs(D(str(data.get("lotSize", "1")))) or D("1")
        self._lot[contract] = multiplier
        self._lot_step[contract] = lot_step

        step = multiplier * lot_step
        return SymbolRules(
            symbol=symbol,
            price_tick=D(str(data.get("tickSize", "0.1"))),
            qty_step=step,
            min_qty=step,
            # KuCoin publishes no minimum order *value*; the real floor is one
            # lot, which min_qty above already expresses. A hardcoded 5 here
            # would skip accounts the exchange would have accepted.
            min_notional=D("0"),
            max_leverage=int(D(str(data.get("maxLeverage", "10")))),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        contract = self._contract(symbol)
        data = await self.request(
            "GET", f"/api/v1/mark-price/{contract}/current", signed=False
        )
        return D(str(data.get("value", "0")))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """``POST /api/v2/changeCrossUserLeverage``, plus the per-order value.

        KuCoin takes leverage on the order *and* keeps a cross-margin setting
        per symbol. Setting only the first leaves the position running at
        whatever the account was last configured with, so both are set. The
        previous implementation called no API at all — it assigned an
        undeclared instance attribute and returned.
        """
        self._leverage = leverage
        contract = self._contract(symbol)
        try:
            await self.request(
                "POST",
                "/api/v2/changeCrossUserLeverage",
                body={"symbol": contract, "leverage": str(leverage)},
            )
        except AdapterError as exc:
            # Isolated-margin accounts reject it; the per-order leverage below
            # still applies, so this is not fatal to the trade.
            logger.info("kucoin: cross leverage not set for %s: %s", contract, exc)

    async def _lots(self, symbol: str, qty: Decimal) -> tuple[str, int, Decimal]:
        """(contract, integer lot count, base units per contract)."""
        contract = self._contract(symbol)
        if contract not in self._lot:
            await self.get_symbol_rules(symbol, MarketType.FUTURES)
        multiplier = self._lot.get(contract, D("1"))
        step = self._lot_step.get(contract, D("1"))
        lots = floor_to_step(qty / multiplier, step)
        if lots < step:
            raise AdapterError(
                f"kucoin: size {qty} is under one contract ({multiplier} per lot)"
            )
        return contract, int(lots), multiplier

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
        contract, lots, multiplier = await self._lots(symbol, qty)

        body: dict[str, Any] = {
            "clientOid": (client_order_id or str(time.time_ns()))[:40],
            "symbol": contract,
            "side": "buy" if side is Side.LONG else "sell",
            "type": "market" if order_type is OrderType.MARKET else "limit",
            "size": lots,
            "leverage": str(self._leverage),
            "marginMode": self.margin_mode,
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError("kucoin: limit order needs a price")
            body["price"] = f"{limit_price:f}"
        if reduce_only:
            body["reduceOnly"] = True

        # TP/SL at entry is a *different endpoint* with different parameter
        # names, and Up/Down are price directions rather than TP/SL.
        path = "/api/v1/orders"
        if stop_loss is not None or take_profit is not None:
            path = "/api/v1/st-orders"
            body["stopPriceType"] = "MP"  # trigger on mark price
            long = side is Side.LONG
            up, down = (take_profit, stop_loss) if long else (stop_loss, take_profit)
            if up is not None:
                body["triggerStopUpPrice"] = f"{up:f}"
            if down is not None:
                body["triggerStopDownPrice"] = f"{down:f}"

        data = await self.request("POST", path, body=body)
        order_id = str(data.get("orderId", ""))
        filled, avg = await self._fill(order_id, symbol, lots, multiplier)
        return OrderResult(order_id=order_id, filled_qty=filled, avg_price=avg, raw=data)

    async def _fill(
        self, order_id: str, symbol: str, lots: int, multiplier: Decimal
    ) -> tuple[Decimal, Decimal]:
        """Real fill size and average price, or a flagged estimate.

        KuCoin's order response carries only an id, so the fill has to be read
        back. When it is not filled yet — a resting limit order, or a market
        order read a hair too early — the mark price is returned instead and
        said to be an estimate, rather than passed off as an execution price.
        """
        expected = D(lots) * multiplier
        if order_id:
            try:
                order = await self.request("GET", f"/api/v1/orders/{order_id}")
                deal_size = D(str(order.get("dealSize", "0")))
                deal_value = D(str(order.get("dealValue", "0")))
                if deal_size > 0 and deal_value > 0:
                    filled = deal_size * multiplier
                    return filled, deal_value / filled
            except AdapterError as exc:
                logger.info("kucoin: could not read back order %s: %s", order_id, exc)
        logger.info(
            "kucoin: order %s has no fill yet; entry price is a mark-price estimate",
            order_id or "?",
        )
        return expected, await self.get_mark_price(symbol)

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        """Untriggered stop orders on this contract (Q5d snapshot).

        Cancel-all (`DELETE /api/v1/stopOrders`) exists and is cheaper, but it
        cannot be used here: under place-then-cancel it would also kill the
        replacement placed a moment earlier. Ids it is.
        """
        data = await self.request(
            "GET", "/api/v1/stopOrders", params={"symbol": self._contract(symbol)}
        )
        rows = data.get("items", []) if isinstance(data, dict) else (data or [])
        return [str(row["id"]) for row in rows if row.get("id")]

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        for order_id in order_ids:
            try:
                await self.request("DELETE", f"/api/v1/orders/{order_id}")
            except AdapterError as exc:
                if not _already_gone(exc):
                    raise
                logger.info("kucoin: order %s was already gone", order_id)

    async def set_sltp(
        self,
        *,
        symbol: str,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
        position: Position | None = None,
    ) -> None:
        """Places new stop orders. The old ones are cancelled by the Q5d
        strategy in ``executor.apply_sltp``, never here.

        These go to ``/api/v1/orders`` with ``stop``/``stopPrice`` — the
        st-orders parameters are for attaching triggers to an *entry*, and are
        not accepted here.
        """
        contract = self._contract(symbol)
        position = position or await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"kucoin: no open position on {symbol}")
        exit_side = "sell" if position.side is Side.LONG else "buy"
        long = position.side is Side.LONG
        # A long is stopped out when price falls and takes profit when it rises;
        # a short is the mirror image.
        triggers = (
            (stop_loss, "down" if long else "up"),
            (take_profit, "up" if long else "down"),
        )
        calls = []
        for price, direction in triggers:
            if price is None:
                continue
            calls.append(
                self.request(
                    "POST",
                    "/api/v1/orders",
                    body={
                        "clientOid": str(time.time_ns()),
                        "symbol": contract,
                        "side": exit_side,
                        "type": "market",
                        "stop": direction,
                        "stopPrice": f"{price:f}",
                        "stopPriceType": "MP",
                        "marginMode": self.margin_mode,
                        "closeOrder": True,
                    },
                )
            )
        await place_both(*calls)

    async def get_sltp(self, symbol: str) -> SLTPState:
        """The untriggered stop orders, split into stop and take-profit.

        KuCoin's stop orders carry their direction in ``stop`` — ``down``
        triggers when price falls, ``up`` when it rises. For a long the stop
        is a ``down`` order and the take-profit an ``up`` order; a short is
        the mirror image — the same mapping ``set_sltp`` places by.
        """
        data = await self.request(
            "GET", "/api/v1/stopOrders", params={"symbol": self._contract(symbol)}
        )
        rows = data.get("items", []) if isinstance(data, dict) else (data or [])
        if not rows:
            return SLTPState(stop_loss=None, take_profit=None)
        position = await self.get_position(symbol)
        long = position is not None and position.side is Side.LONG
        stop_loss = take_profit = None
        for row in rows:
            price = D(str(row.get("stopPrice") or "")) or None
            if price is None:
                continue
            direction = row.get("stop")
            if direction == ("down" if long else "up"):
                stop_loss = price
            elif direction == ("up" if long else "down"):
                take_profit = price
        return SLTPState(stop_loss=stop_loss, take_profit=take_profit)

    async def get_position(self, symbol: str) -> Position | None:
        contract = self._contract(symbol)
        data = await self.request("GET", "/api/v1/position", params={"symbol": contract})
        qty = D(str(data.get("currentQty", "0")))
        if qty == 0:
            return None
        if contract not in self._lot:
            await self.get_symbol_rules(symbol, MarketType.FUTURES)
        multiplier = self._lot.get(contract, D("1"))
        return Position(
            symbol=symbol,
            side=Side.LONG if qty > 0 else Side.SHORT,
            size=abs(qty) * multiplier,
            entry_price=D(str(data.get("avgEntryPrice", "0"))),
            liquidation_price=D(str(data.get("liquidationPrice") or "0")) or None,
            unrealized_pnl=D(str(data.get("unrealisedPnl", "0"))),
            leverage=int(D(str(data.get("realLeverage", "1")))),
        )

    async def close_position(self, symbol: str) -> OrderResult:
        contract = self._contract(symbol)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(
                f"kucoin: no open position to close on {symbol}", code="no_position"
            )
        data = await self.request(
            "POST",
            "/api/v1/orders",
            body={
                "clientOid": str(time.time_ns()),
                "symbol": contract,
                "side": "sell" if position.side is Side.LONG else "buy",
                "type": "market",
                "marginMode": self.margin_mode,
                # closeOrder carries no size: it flattens whatever is open, so
                # it cannot race a partial fill into a reversal.
                "closeOrder": True,
            },
        )
        order_id = str(data.get("orderId", ""))
        multiplier = self._lot.get(contract, D("1"))
        lots = int(position.size / multiplier) if multiplier else 0
        filled, avg = await self._fill(order_id, symbol, lots, multiplier)
        return OrderResult(
            order_id=order_id,
            filled_qty=filled or position.size,
            avg_price=avg,
            raw=data,
        )

    # --- private stream -----------------------------------------------------

    async def stream_events(self) -> AsyncIterator[dict]:
        """Private order and position stream.

        ``POST /api/v1/bullet-private`` hands back a token and a server list;
        the socket then carries ``/contractMarket/tradeOrders`` (fills) and
        ``/contract/position:{symbol}`` (liquidation, margin). Nothing consumes
        this yet — positions are still polled — so it exists to satisfy the
        per-exchange checklist and to be the seam a fill-driven history hangs off.
        """
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise NotSupported(
                "kucoin: the private stream needs the 'websockets' package"
            ) from exc

        bullet = await self.request("POST", "/api/v1/bullet-private")
        servers = bullet.get("instanceServers") or []
        token = bullet.get("token")
        if not servers or not token:
            raise AdapterError("kucoin: bullet-private returned no server or token")
        endpoint = servers[0].get("endpoint")
        ping_ms = int(servers[0].get("pingInterval", 18000))

        async with websockets.connect(f"{endpoint}?token={token}") as socket:
            await socket.send(
                json.dumps(
                    {
                        "id": str(time.time_ns()),
                        "type": "subscribe",
                        "topic": "/contractMarket/tradeOrders",
                        "privateChannel": True,
                        "response": True,
                    }
                )
            )
            last_ping = time.monotonic()
            async for message in socket:
                now = time.monotonic()
                if (now - last_ping) * 1000 >= ping_ms:
                    await socket.send(
                        json.dumps({"id": str(time.time_ns()), "type": "ping"})
                    )
                    last_ping = now
                try:
                    frame = json.loads(message)
                except ValueError:
                    logger.warning("kucoin: unparseable stream frame")
                    continue
                if frame.get("type") == "message":
                    yield frame
