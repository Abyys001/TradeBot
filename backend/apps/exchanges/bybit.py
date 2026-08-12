"""Bybit V5.

Signing (reference/exchanges/bybit/v5-docs guide): sign
``timestamp + apiKey + recvWindow + (queryString | jsonBody)`` with HMAC-SHA256,
lowercase hex.

Bybit is the best-behaved exchange on the list for this platform: it can attach
TP/SL at entry *and* amend them in place on an open position, so the Q5d
cancel/replace dance is never needed here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from apps.core.money import D
from apps.exchanges.base import (
    AdapterError,
    AuthError,
    Balance,
    Capabilities,
    MarketType,
    OrderResult,
    OrderType,
    Position,
    Side,
    SymbolRules,
    WithdrawalPermissionError,
)
from apps.exchanges.rest import RestAdapter

RECV_WINDOW = "5000"


class BybitAdapter(RestAdapter):
    name = "bybit"
    base_url = "https://api.bybit.com"
    testnet_url = "https://api-testnet.bybit.com"
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT, MarketType.FUTURES}),
        has_testnet=True,
        native_sltp_on_entry=True,
        native_sltp_amend=True,  # POST /v5/position/trading-stop
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,
    )

    def _category(self, market: MarketType) -> str:
        return "linear" if market is MarketType.FUTURES else "spot"

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        timestamp = str(int(time.time() * 1000))
        if method.upper() == "GET":
            query = urlencode(params or {})
            payload = query
            content = None
        else:
            payload = json.dumps(body or {}, separators=(",", ":"))
            content = payload.encode()

        signature = hmac.new(
            self.api_secret.encode(),
            f"{timestamp}{self.api_key}{RECV_WINDOW}{payload}".encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            "Content-Type": "application/json",
        }
        return headers, (params if method.upper() == "GET" else None), content

    def unwrap(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        code = payload.get("retCode")
        if code not in (0, None):
            message = payload.get("retMsg", "")
            if code in (10003, 10004, 10005, 33004):
                raise AuthError(f"bybit: {message} (retCode {code})")
            raise AdapterError(f"bybit: {message} (retCode {code})")
        return payload.get("result", payload)

    # --- interface ---------------------------------------------------------

    async def verify_credentials(self) -> None:
        info = await self.request("GET", "/v5/user/query-api")
        permissions = info.get("permissions", {}) or {}
        # Spec §7: any withdrawal permission is a hard refusal.
        if permissions.get("Withdraw"):
            raise WithdrawalPermissionError(
                "bybit: this API key has withdrawal permission. Recreate it with "
                "trade-only rights before connecting the account."
            )

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request(
            "GET",
            "/v5/account/wallet-balance",
            params={"accountType": "UNIFIED", "coin": asset},
        )
        for account in data.get("list", []):
            for coin in account.get("coin", []):
                if coin.get("coin", "").upper() == asset.upper():
                    available = coin.get("availableToWithdraw") or coin.get("walletBalance", "0")
                    return Balance(
                        asset=asset,
                        available=D(available or "0"),
                        total=D(coin.get("walletBalance", "0")),
                    )
        return Balance(asset=asset, available=D("0"), total=D("0"))

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        data = await self.request(
            "GET",
            "/v5/market/instruments-info",
            params={"category": self._category(market), "symbol": symbol},
            signed=False,
        )
        entries = data.get("list", [])
        if not entries:
            raise AdapterError(f"bybit: unknown symbol {symbol}")
        entry = entries[0]
        price_filter = entry.get("priceFilter", {})
        lot = entry.get("lotSizeFilter", {})
        leverage_filter = entry.get("leverageFilter", {})
        return SymbolRules(
            symbol=symbol,
            price_tick=D(price_filter.get("tickSize", "0.01")),
            qty_step=D(lot.get("qtyStep", lot.get("basePrecision", "0.001"))),
            min_qty=D(lot.get("minOrderQty", "0.001")),
            min_notional=D(lot.get("minNotionalValue", "5")),
            max_leverage=int(D(leverage_filter.get("maxLeverage", "10"))),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        data = await self.request(
            "GET",
            "/v5/market/tickers",
            params={"category": "linear", "symbol": symbol},
            signed=False,
        )
        entries = data.get("list", [])
        if not entries:
            raise AdapterError(f"bybit: no ticker for {symbol}")
        return D(entries[0].get("markPrice") or entries[0].get("lastPrice", "0"))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            await self.request(
                "POST",
                "/v5/position/set-leverage",
                body={
                    "category": "linear",
                    "symbol": symbol,
                    "buyLeverage": str(leverage),
                    "sellLeverage": str(leverage),
                },
            )
        except AdapterError as exc:
            # 110043 = leverage not modified. Already correct, so not an error.
            if "110043" not in str(exc):
                raise

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
        body: dict[str, Any] = {
            "category": self._category(market),
            "symbol": symbol,
            "side": "Buy" if side is Side.LONG else "Sell",
            "orderType": "Market" if order_type is OrderType.MARKET else "Limit",
            "qty": f"{qty:f}",
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError("bybit: limit order needs a price")
            body["price"] = f"{limit_price:f}"
            body["timeInForce"] = "GTC"
        if reduce_only:
            body["reduceOnly"] = True
        if client_order_id:
            body["orderLinkId"] = client_order_id[:36]
        # Attached at entry, sized to the whole position.
        if stop_loss is not None:
            body["stopLoss"] = f"{stop_loss:f}"
            body["slTriggerBy"] = "MarkPrice"
        if take_profit is not None:
            body["takeProfit"] = f"{take_profit:f}"
            body["tpTriggerBy"] = "MarkPrice"

        data = await self.request("POST", "/v5/order/create", body=body)
        order_id = data.get("orderId", "")
        avg = limit_price if order_type is OrderType.LIMIT else await self.get_mark_price(symbol)
        return OrderResult(order_id=order_id, filled_qty=qty, avg_price=D(avg or 0), raw=data)

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        """True amend in place — no cancel/replace, so no unprotected window."""
        body: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "positionIdx": 0,
            "tpslMode": "Full",
        }
        # "0" clears the leg on Bybit; None would leave it untouched.
        body["stopLoss"] = f"{stop_loss:f}" if stop_loss is not None else "0"
        body["takeProfit"] = f"{take_profit:f}" if take_profit is not None else "0"
        if stop_loss is not None:
            body["slTriggerBy"] = "MarkPrice"
        if take_profit is not None:
            body["tpTriggerBy"] = "MarkPrice"
        await self.request("POST", "/v5/position/trading-stop", body=body)

    async def get_position(self, symbol: str) -> Position | None:
        data = await self.request(
            "GET", "/v5/position/list", params={"category": "linear", "symbol": symbol}
        )
        for row in data.get("list", []):
            size = D(row.get("size", "0"))
            if size == 0:
                continue
            return Position(
                symbol=symbol,
                side=Side.LONG if row.get("side") == "Buy" else Side.SHORT,
                size=size,
                entry_price=D(row.get("avgPrice", "0")),
                liquidation_price=D(row.get("liqPrice") or "0") or None,
                unrealized_pnl=D(row.get("unrealisedPnl", "0")),
                leverage=int(D(row.get("leverage", "1"))),
            )
        return None

    async def close_position(self, symbol: str) -> OrderResult:
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"bybit: no open position to close on {symbol}")
        data = await self.request(
            "POST",
            "/v5/order/create",
            body={
                "category": "linear",
                "symbol": symbol,
                "side": "Sell" if position.side is Side.LONG else "Buy",
                "orderType": "Market",
                "qty": f"{position.size:f}",
                "reduceOnly": True,
            },
        )
        return OrderResult(
            order_id=data.get("orderId", ""),
            filled_qty=position.size,
            avg_price=await self.get_mark_price(symbol),
            raw=data,
        )
