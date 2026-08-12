"""KuCoin Futures.

Signing (reference/exchanges/kucoin/api-docs): HMAC-SHA256 over
``timestamp + METHOD + endpoint + body``, base64. The passphrase is *also*
HMAC-signed and base64-encoded for key version 2+, which is the part people get
wrong — a plaintext passphrase silently fails with 400004.

KuCoin Futures runs on a different host from spot and sizes in contract lots.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
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
    SymbolRules,
)
from apps.exchanges.rest import RestAdapter


class KucoinAdapter(RestAdapter):
    name = "kucoin"
    base_url = "https://api-futures.kucoin.com"
    testnet_url = "https://api-sandbox-futures.kucoin.com"
    capabilities = Capabilities(
        markets=frozenset({MarketType.FUTURES}),
        has_testnet=True,
        native_sltp_on_entry=True,
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._lot: dict[str, Decimal] = {}

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        timestamp = str(int(time.time() * 1000))
        method = method.upper()
        if method == "GET":
            endpoint = f"{path}?{urlencode(params)}" if params else path
            payload = ""
            content = None
        else:
            endpoint = path
            payload = json.dumps(body or {}, separators=(",", ":"))
            content = payload.encode()

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
        return headers, (params if method == "GET" else None), content

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

    async def verify_credentials(self) -> None:
        # KuCoin exposes no key-permission endpoint on the futures host, so
        # spec §7 cannot be proven from the API. A successful authenticated call
        # only proves the key works, not that it is withdrawal-disabled.
        await self.request("GET", "/api/v1/account-overview", params={"currency": "USDT"})

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
        lot = D(str(data.get("multiplier", "1")))
        self._lot[contract] = lot
        return SymbolRules(
            symbol=symbol,
            price_tick=D(str(data.get("tickSize", "0.1"))),
            qty_step=abs(lot),
            min_qty=abs(lot),
            min_notional=D("5"),
            max_leverage=int(D(str(data.get("maxLeverage", "10")))),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        contract = self._contract(symbol)
        data = await self.request(
            "GET", f"/api/v1/mark-price/{contract}/current", signed=False
        )
        return D(str(data.get("value", "0")))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        # KuCoin takes leverage per order rather than per symbol, so this is
        # recorded and applied at placement time.
        self._leverage = leverage

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
        contract = self._contract(symbol)
        if contract not in self._lot:
            await self.get_symbol_rules(symbol, market)
        lot = abs(self._lot.get(contract, D("1")))
        lots = floor_to_step(qty / lot, D("1"))
        if lots < 1:
            raise AdapterError(f"kucoin: size {qty} is under one contract ({lot})")

        body: dict[str, Any] = {
            "clientOid": (client_order_id or str(time.time_ns()))[:40],
            "symbol": contract,
            "side": "buy" if side is Side.LONG else "sell",
            "type": "market" if order_type is OrderType.MARKET else "limit",
            "size": int(lots),
            "leverage": str(getattr(self, "_leverage", 1)),
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError("kucoin: limit order needs a price")
            body["price"] = f"{limit_price:f}"
        if reduce_only:
            body["reduceOnly"] = True
        if stop_loss is not None:
            body["triggerStopLossPrice"] = f"{stop_loss:f}"
        if take_profit is not None:
            body["triggerStopUpPrice"] = f"{take_profit:f}"

        data = await self.request("POST", "/api/v1/orders", body=body)
        avg = limit_price if order_type is OrderType.LIMIT else await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            filled_qty=lots * lot,
            avg_price=D(avg or 0),
            raw=data,
        )

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        contract = self._contract(symbol)
        position = await self.get_position(symbol)
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
        for price, direction in triggers:
            if price is None:
                continue
            await self.request(
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
                    "closeOrder": True,
                },
            )

    async def get_position(self, symbol: str) -> Position | None:
        contract = self._contract(symbol)
        data = await self.request("GET", "/api/v1/position", params={"symbol": contract})
        qty = D(str(data.get("currentQty", "0")))
        if qty == 0:
            return None
        lot = abs(self._lot.get(contract, D("1")))
        return Position(
            symbol=symbol,
            side=Side.LONG if qty > 0 else Side.SHORT,
            size=abs(qty) * lot,
            entry_price=D(str(data.get("avgEntryPrice", "0"))),
            liquidation_price=D(str(data.get("liquidationPrice") or "0")) or None,
            unrealized_pnl=D(str(data.get("unrealisedPnl", "0"))),
            leverage=int(D(str(data.get("realLeverage", "1")))),
        )

    async def close_position(self, symbol: str) -> OrderResult:
        contract = self._contract(symbol)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"kucoin: no open position to close on {symbol}")
        data = await self.request(
            "POST",
            "/api/v1/orders",
            body={
                "clientOid": str(time.time_ns()),
                "symbol": contract,
                "side": "sell" if position.side is Side.LONG else "buy",
                "type": "market",
                "closeOrder": True,
            },
        )
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            filled_qty=position.size,
            avg_price=await self.get_mark_price(symbol),
            raw=data,
        )
