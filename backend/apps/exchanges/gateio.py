"""Gate.io APIv4 futures.

Signing (from ``reference/exchanges/gateio/python-sdk`` ``gen_sign``):
``METHOD\\nurl\\nquery\\nSHA512(body)\\ntimestamp``, HMAC-SHA512 hex.
Headers ``KEY``, ``Timestamp``, ``SIGN``.

Gate sizes futures in contracts and encodes direction in the *sign* of the
size — a negative size is a short. There is no separate side field.
"""

from __future__ import annotations

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

SETTLE = "usdt"


class GateioAdapter(RestAdapter):
    name = "gateio"
    base_url = "https://api.gateio.ws"
    testnet_url = "https://fx-api-testnet.gateio.ws"
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT, MarketType.FUTURES}),
        has_testnet=True,
        native_sltp_on_entry=False,
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._quanto: dict[str, Decimal] = {}

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        method = method.upper()
        timestamp = str(int(time.time()))
        query = urlencode(params or {})
        payload = json.dumps(body, separators=(",", ":")) if body is not None else ""
        hashed_body = hashlib.sha512(payload.encode()).hexdigest()
        message = f"{method}\n{path}\n{query}\n{hashed_body}\n{timestamp}"
        signature = hmac.new(
            self.api_secret.encode(), message.encode(), hashlib.sha512
        ).hexdigest()
        headers = {
            "KEY": self.api_key,
            "Timestamp": timestamp,
            "SIGN": signature,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        return headers, (params or None), (payload.encode() if body is not None else None)

    def unwrap(self, payload: Any) -> Any:
        if isinstance(payload, dict) and payload.get("label"):
            label = payload["label"]
            message = payload.get("message", label)
            if label in {"INVALID_KEY", "INVALID_SIGNATURE", "FORBIDDEN", "READ_ONLY"}:
                raise AuthError(f"gateio: {message} ({label})")
            raise AdapterError(f"gateio: {message} ({label})")
        return payload

    # --- interface ---------------------------------------------------------

    async def verify_credentials(self) -> None:
        # Gate does not expose key permissions via APIv4, so spec §7 cannot be
        # proven here — the admin confirms it when creating the key.
        await self.request("GET", f"/api/v4/futures/{SETTLE}/accounts")

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request("GET", f"/api/v4/futures/{SETTLE}/accounts")
        return Balance(
            asset=asset,
            available=D(str(data.get("available", "0"))),
            total=D(str(data.get("total", "0"))),
        )

    def _contract(self, symbol: str) -> str:
        """BTCUSDT -> BTC_USDT."""
        if "_" in symbol:
            return symbol
        for quote in ("USDT", "USDC", "USD"):
            if symbol.upper().endswith(quote):
                return f"{symbol[: -len(quote)].upper()}_{quote}"
        raise AdapterError(f"gateio: cannot map symbol {symbol}")

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        if market is MarketType.SPOT:
            raise NotSupported("gateio: this adapter covers futures only")
        contract = self._contract(symbol)
        data = await self.request(
            "GET", f"/api/v4/futures/{SETTLE}/contracts/{contract}", signed=False
        )
        # quanto_multiplier is the base-asset size of one contract.
        multiplier = D(str(data.get("quanto_multiplier") or "1"))
        self._quanto[contract] = multiplier
        return SymbolRules(
            symbol=symbol,
            price_tick=D(str(data.get("order_price_round") or "0.01")),
            qty_step=multiplier,
            min_qty=multiplier,
            min_notional=D("5"),
            max_leverage=int(D(str(data.get("leverage_max") or "10"))),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        contract = self._contract(symbol)
        data = await self.request(
            "GET",
            f"/api/v4/futures/{SETTLE}/tickers",
            params={"contract": contract},
            signed=False,
        )
        rows = data if isinstance(data, list) else [data]
        if not rows:
            raise AdapterError(f"gateio: no ticker for {contract}")
        return D(str(rows[0].get("mark_price") or rows[0].get("last") or "0"))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        contract = self._contract(symbol)
        await self.request(
            "POST",
            f"/api/v4/futures/{SETTLE}/positions/{contract}/leverage",
            params={"leverage": str(leverage)},
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
        contract = self._contract(symbol)
        if contract not in self._quanto:
            await self.get_symbol_rules(symbol, market)
        multiplier = self._quanto.get(contract, D("1"))
        size = int(floor_to_step(qty / multiplier, D("1")))
        if size < 1:
            raise AdapterError(f"gateio: size {qty} is under one contract ({multiplier})")
        # Direction is the sign of size; there is no side parameter.
        signed_size = size if side is Side.LONG else -size

        body: dict[str, Any] = {"contract": contract, "size": signed_size}
        if order_type is OrderType.MARKET:
            # Gate expresses market orders as price "0" with IOC.
            body["price"] = "0"
            body["tif"] = "ioc"
        else:
            if limit_price is None:
                raise AdapterError("gateio: limit order needs a price")
            body["price"] = f"{limit_price:f}"
            body["tif"] = "gtc"
        if reduce_only:
            body["reduce_only"] = True
        if client_order_id:
            body["text"] = f"t-{''.join(c for c in client_order_id if c.isalnum())[:28]}"

        data = await self.request("POST", f"/api/v4/futures/{SETTLE}/orders", body=body)
        fill = D(str(data.get("fill_price") or "0"))
        if fill == 0:
            fill = await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("id", "")),
            filled_qty=abs(D(str(data.get("size", signed_size)))) * multiplier,
            avg_price=fill,
            raw=data,
        )

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        """Open price-triggered orders on this contract (Q5d snapshot)."""
        data = await self.request(
            "GET",
            f"/api/v4/futures/{SETTLE}/price_orders",
            params={"status": "open", "contract": self._contract(symbol)},
        )
        rows = data if isinstance(data, list) else []
        return [str(row["id"]) for row in rows if row.get("id") is not None]

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        for order_id in order_ids:
            try:
                await self.request(
                    "DELETE", f"/api/v4/futures/{SETTLE}/price_orders/{order_id}"
                )
            except AdapterError as exc:
                # Already triggered or cancelled between snapshot and cancel.
                if "not found" not in str(exc).lower():
                    raise

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        """Places new price-triggered orders. Cancelling what they replace is
        the Q5d strategy's job (``executor.apply_sltp``), not this method's."""
        contract = self._contract(symbol)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"gateio: no open position on {symbol}")
        long = position.side is Side.LONG
        # rule 1 = trigger when price >= value, 2 = when price <= value.
        triggers = (
            (stop_loss, 2 if long else 1),
            (take_profit, 1 if long else 2),
        )
        for price, rule in triggers:
            if price is None:
                continue
            await self.request(
                "POST",
                f"/api/v4/futures/{SETTLE}/price_orders",
                body={
                    "initial": {
                        "contract": contract,
                        "size": 0,  # 0 with close=true means the whole position
                        "price": "0",
                        "close": True,
                        "tif": "ioc",
                        "reduce_only": True,
                    },
                    "trigger": {
                        "strategy_type": 0,
                        "price_type": 1,  # mark price
                        "price": f"{price:f}",
                        "rule": rule,
                    },
                },
            )

    async def get_position(self, symbol: str) -> Position | None:
        contract = self._contract(symbol)
        data = await self.request(
            "GET", f"/api/v4/futures/{SETTLE}/positions/{contract}"
        )
        size = D(str(data.get("size", "0")))
        if size == 0:
            return None
        multiplier = self._quanto.get(contract, D("1"))
        return Position(
            symbol=symbol,
            side=Side.LONG if size > 0 else Side.SHORT,
            size=abs(size) * multiplier,
            entry_price=D(str(data.get("entry_price") or "0")),
            liquidation_price=D(str(data.get("liq_price") or "0")) or None,
            unrealized_pnl=D(str(data.get("unrealised_pnl") or "0")),
            leverage=int(D(str(data.get("leverage") or "1"))),
        )

    async def close_position(self, symbol: str) -> OrderResult:
        contract = self._contract(symbol)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"gateio: no open position to close on {symbol}")
        data = await self.request(
            "POST",
            f"/api/v4/futures/{SETTLE}/orders",
            body={"contract": contract, "size": 0, "close": True, "price": "0", "tif": "ioc"},
        )
        fill = D(str(data.get("fill_price") or "0")) or await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("id", "")),
            filled_qty=position.size,
            avg_price=fill,
            raw=data,
        )
