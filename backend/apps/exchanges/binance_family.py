"""Binance and Toobit.

Both use the same scheme — HMAC-SHA256 over the query string with a `timestamp`
parameter and a `signature` parameter — so they share an implementation and
differ only in host, API-key header, and path prefixes. Confirmed for Toobit in
``reference/exchanges/toobit/api/basic-information.md`` (``X-BB-APIKEY``,
lowercase hex, parameter order must match signature order).
"""

from __future__ import annotations

import hashlib
import hmac
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
    NotSupported,
    OrderResult,
    OrderType,
    Position,
    Side,
    SymbolRules,
    WithdrawalPermissionError,
)
from apps.exchanges.rest import RestAdapter


class BinanceStyleAdapter(RestAdapter):
    """Shared behaviour. Subclasses set hosts, header name and path prefixes."""

    api_key_header = "X-MBX-APIKEY"
    futures_prefix = "/fapi/v1"
    spot_prefix = "/api/v3"
    recv_window = 5000

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        payload = {**(params or {}), **(body or {})}
        payload["timestamp"] = int(time.time() * 1000)
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

    # --- interface ---------------------------------------------------------

    async def verify_credentials(self) -> None:
        try:
            info = await self._get_account_permissions()
        except AuthError:
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

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request("GET", f"{self.futures_prefix}/balance", weight=5)
        for row in data if isinstance(data, list) else []:
            if row.get("asset", "").upper() == asset.upper():
                return Balance(
                    asset=asset,
                    available=D(row.get("availableBalance", row.get("free", "0"))),
                    total=D(row.get("balance", row.get("free", "0"))),
                )
        return Balance(asset=asset, available=D("0"), total=D("0"))

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        path = f"{self._prefix(market)}/exchangeInfo"
        data = await self.request("GET", path, signed=False, weight=10)
        for entry in data.get("symbols", []):
            if entry.get("symbol") != symbol:
                continue
            filters = {f["filterType"]: f for f in entry.get("filters", [])}
            price_filter = filters.get("PRICE_FILTER", {})
            lot = filters.get("LOT_SIZE", filters.get("MARKET_LOT_SIZE", {}))
            notional = filters.get("MIN_NOTIONAL", filters.get("NOTIONAL", {}))
            return SymbolRules(
                symbol=symbol,
                price_tick=D(price_filter.get("tickSize", "0.01")),
                qty_step=D(lot.get("stepSize", "0.001")),
                min_qty=D(lot.get("minQty", "0.001")),
                min_notional=D(notional.get("minNotional", notional.get("notional", "5"))),
                max_leverage=self.capabilities.max_leverage,
            )
        raise AdapterError(f"{self.name}: unknown symbol {symbol}")

    async def get_mark_price(self, symbol: str) -> Decimal:
        data = await self.request(
            "GET", f"{self.futures_prefix}/ticker/price", params={"symbol": symbol}, signed=False
        )
        if isinstance(data, list):
            data = data[0] if data else {}
        return D(data.get("price", "0"))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self.request(
            "POST",
            f"{self.futures_prefix}/leverage",
            body={"symbol": symbol, "leverage": leverage},
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
        body: dict[str, Any] = {
            "symbol": symbol,
            "side": "BUY" if side is Side.LONG else "SELL",
            "type": "MARKET" if order_type is OrderType.MARKET else "LIMIT",
            "quantity": f"{qty:f}",
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError(f"{self.name}: limit order needs a price")
            body["price"] = f"{limit_price:f}"
            body["timeInForce"] = "GTC"
        if reduce_only and market is MarketType.FUTURES:
            body["reduceOnly"] = "true"
        if client_order_id:
            body["newClientOrderId"] = client_order_id
        if stop_loss is not None:
            body["stopLoss"] = f"{stop_loss:f}"
        if take_profit is not None:
            body["takeProfit"] = f"{take_profit:f}"

        data = await self.request("POST", f"{self._prefix(market)}/order", body=body, weight=2)
        filled = D(data.get("executedQty", data.get("origQty", qty)))
        avg = D(data.get("avgPrice", "0")) or D(data.get("price", "0"))
        if avg == 0:
            avg = await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("orderId", "")), filled_qty=filled, avg_price=avg, raw=data
        )

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        """Binance has no amend-in-place for position TP/SL: place reduce-only
        conditional orders. Q5d place-then-cancel is honoured by the caller."""
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"{self.name}: no open position on {symbol}")
        exit_side = "SELL" if position.side is Side.LONG else "BUY"

        for price, order_type in (
            (stop_loss, "STOP_MARKET"),
            (take_profit, "TAKE_PROFIT_MARKET"),
        ):
            if price is None:
                continue
            await self.request(
                "POST",
                f"{self.futures_prefix}/order",
                body={
                    "symbol": symbol,
                    "side": exit_side,
                    "type": order_type,
                    "stopPrice": f"{price:f}",
                    "closePosition": "true",
                    "workingType": "MARK_PRICE",
                },
                weight=2,
            )

    async def get_position(self, symbol: str) -> Position | None:
        data = await self.request(
            "GET", f"{self.futures_prefix}/positionRisk", params={"symbol": symbol}, weight=5
        )
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            amount = D(row.get("positionAmt", "0"))
            if amount == 0:
                continue
            return Position(
                symbol=symbol,
                side=Side.LONG if amount > 0 else Side.SHORT,
                size=abs(amount),
                entry_price=D(row.get("entryPrice", "0")),
                liquidation_price=D(row.get("liquidationPrice", "0")) or None,
                unrealized_pnl=D(row.get("unRealizedProfit", "0")),
                leverage=int(D(row.get("leverage", "1"))),
            )
        return None

    async def close_position(self, symbol: str) -> OrderResult:
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"{self.name}: no open position to close on {symbol}")
        data = await self.request(
            "POST",
            f"{self.futures_prefix}/order",
            body={
                "symbol": symbol,
                "side": "SELL" if position.side is Side.LONG else "BUY",
                "type": "MARKET",
                "quantity": f"{position.size:f}",
                "reduceOnly": "true",
            },
            weight=2,
        )
        avg = D(data.get("avgPrice", "0")) or await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            filled_qty=position.size,
            avg_price=avg,
            raw=data,
        )


class BinanceAdapter(BinanceStyleAdapter):
    name = "binance"
    base_url = "https://fapi.binance.com"
    testnet_url = "https://testnet.binancefuture.com"
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT, MarketType.FUTURES}),
        has_testnet=True,
        native_sltp_on_entry=False,  # conditional orders, placed after entry
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=False,  # Binance weights are per-IP as well as per-key
    )

    async def _get_account_permissions(self) -> dict:
        # Only exposed on the spot host; futures-only keys return an error, in
        # which case we cannot prove the key is non-withdrawable from the API.
        return await self.request("GET", "/sapi/v1/account/apiRestrictions")


class ToobitAdapter(BinanceStyleAdapter):
    name = "toobit"
    base_url = "https://api.toobit.com"
    testnet_url = ""  # Q9: no testnet documented — surfaced in the panel
    api_key_header = "X-BB-APIKEY"
    futures_prefix = "/api/v1/futures"
    spot_prefix = "/api/v1"
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT, MarketType.FUTURES}),
        has_testnet=False,
        testnet_note="Toobit publishes no test environment — cannot be used in test mode.",
        native_sltp_on_entry=True,  # takeProfit/stopLoss accepted at entry
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,
    )

    async def _get_account_permissions(self) -> dict:
        # Toobit's docs expose no key-permission endpoint. Spec §7 cannot be
        # verified programmatically here, so the admin must confirm at connect
        # time and the account is flagged until they do.
        raise NotSupported(
            "Toobit does not expose an API-key permission endpoint. Confirm the "
            "key is trade-only in the Toobit dashboard before connecting."
        )

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request("GET", "/api/v1/futures/balance", weight=5)
        rows = data if isinstance(data, list) else data.get("balances", [])
        for row in rows:
            if row.get("asset", row.get("tokenId", "")).upper() == asset.upper():
                return Balance(
                    asset=asset,
                    available=D(row.get("availableBalance", row.get("free", "0"))),
                    total=D(row.get("balance", row.get("total", "0"))),
                )
        return Balance(asset=asset, available=D("0"), total=D("0"))
