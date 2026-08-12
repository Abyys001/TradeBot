"""OKX V5.

Signing: HMAC-SHA256 over ``ISO8601-timestamp + METHOD + requestPath + body``,
base64-encoded. Headers ``OK-ACCESS-KEY/SIGN/TIMESTAMP/PASSPHRASE``.
(Confirmed against ``reference/exchanges/okx/ts-sdk/src/util/BaseRestClient.ts``:
``const message = tsISO + method + endpoint + serializedParams``.)

OKX sizes contracts in *lots*, not base units — see ``_to_contracts``. Getting
that wrong is how a position ends up 100x too large, so it is converted
explicitly rather than inferred.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
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
    OrderResult,
    OrderType,
    Position,
    Side,
    SymbolRules,
    WithdrawalPermissionError,
)
from apps.exchanges.rest import RestAdapter


class OkxAdapter(RestAdapter):
    name = "okx"
    base_url = "https://www.okx.com"
    testnet_url = "https://www.okx.com"  # demo mode is a header, not a host
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT, MarketType.FUTURES}),
        has_testnet=True,
        testnet_note="OKX demo trading is enabled with the x-simulated-trading header.",
        native_sltp_on_entry=True,
        native_sltp_amend=True,  # /api/v5/trade/amend-algos
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._contract_size: dict[str, Decimal] = {}

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        timestamp = (
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )
        method = method.upper()
        if method == "GET":
            query = f"?{urlencode(params)}" if params else ""
            message = f"{timestamp}{method}{path}{query}"
            content = None
        else:
            payload = json.dumps(body or {}, separators=(",", ":"))
            message = f"{timestamp}{method}{path}{payload}"
            content = payload.encode()

        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), message.encode(), hashlib.sha256).digest()
        ).decode()

        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }
        if self.testnet:
            headers["x-simulated-trading"] = "1"
        return headers, (params if method == "GET" else None), content

    def unwrap(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        code = str(payload.get("code", "0"))
        if code not in ("0", ""):
            message = payload.get("msg") or ""
            data = payload.get("data") or []
            if data and isinstance(data, list) and isinstance(data[0], dict):
                message = data[0].get("sMsg") or message
            if code in ("50111", "50113", "50114", "50102"):
                raise AuthError(f"okx: {message} (code {code})")
            raise AdapterError(f"okx: {message} (code {code})")
        return payload.get("data", payload)

    def _inst_id(self, symbol: str, market: MarketType) -> str:
        """BTCUSDT -> BTC-USDT-SWAP (futures) or BTC-USDT (spot)."""
        if "-" in symbol:
            return symbol
        for quote in ("USDT", "USDC", "USD"):
            if symbol.upper().endswith(quote):
                base = symbol[: -len(quote)]
                pair = f"{base.upper()}-{quote}"
                return f"{pair}-SWAP" if market is MarketType.FUTURES else pair
        raise AdapterError(f"okx: cannot map symbol {symbol}")

    # --- interface ---------------------------------------------------------

    async def verify_credentials(self) -> None:
        data = await self.request("GET", "/api/v5/account/config")
        rows = data if isinstance(data, list) else [data]
        if not rows:
            raise AuthError("okx: credentials rejected")
        # OKX exposes key permissions as a comma list, e.g. "read_only,trade".
        perms = str(rows[0].get("perm", ""))
        if "withdraw" in perms.lower():
            raise WithdrawalPermissionError(
                "okx: this API key has withdrawal permission. Recreate it with "
                "trade-only rights before connecting the account."
            )

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request("GET", "/api/v5/account/balance", params={"ccy": asset})
        for account in data if isinstance(data, list) else []:
            for detail in account.get("details", []):
                if detail.get("ccy", "").upper() == asset.upper():
                    return Balance(
                        asset=asset,
                        available=D(detail.get("availBal") or detail.get("availEq") or "0"),
                        total=D(detail.get("eq") or detail.get("cashBal") or "0"),
                    )
        return Balance(asset=asset, available=D("0"), total=D("0"))

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        inst_id = self._inst_id(symbol, market)
        inst_type = "SWAP" if market is MarketType.FUTURES else "SPOT"
        data = await self.request(
            "GET",
            "/api/v5/public/instruments",
            params={"instType": inst_type, "instId": inst_id},
            signed=False,
        )
        rows = data if isinstance(data, list) else []
        if not rows:
            raise AdapterError(f"okx: unknown instrument {inst_id}")
        row = rows[0]
        # ctVal is the base-asset size of one contract; spot has no contracts.
        self._contract_size[inst_id] = D(row.get("ctVal") or "1")
        lot = D(row.get("lotSz") or "1")
        contract = self._contract_size[inst_id]
        return SymbolRules(
            symbol=symbol,
            price_tick=D(row.get("tickSz") or "0.01"),
            # Expressed in base units so sizing stays exchange-agnostic.
            qty_step=lot * contract,
            min_qty=D(row.get("minSz") or "1") * contract,
            min_notional=D("5"),
            max_leverage=int(D(row.get("lever") or "10")),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        inst_id = self._inst_id(symbol, MarketType.FUTURES)
        data = await self.request(
            "GET", "/api/v5/public/mark-price", params={"instId": inst_id}, signed=False
        )
        rows = data if isinstance(data, list) else []
        if not rows:
            raise AdapterError(f"okx: no mark price for {inst_id}")
        return D(rows[0].get("markPx", "0"))

    def _to_contracts(self, inst_id: str, qty: Decimal) -> str:
        """Base units -> contract lots. OKX rejects fractional contracts."""
        size = self._contract_size.get(inst_id, D("1"))
        return f"{floor_to_step(qty / size, D('1')):f}"

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self.request(
            "POST",
            "/api/v5/account/set-leverage",
            body={
                "instId": self._inst_id(symbol, MarketType.FUTURES),
                "lever": str(leverage),
                "mgnMode": "cross",
            },
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
        inst_id = self._inst_id(symbol, market)
        if inst_id not in self._contract_size:
            await self.get_symbol_rules(symbol, market)

        body: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cross" if market is MarketType.FUTURES else "cash",
            "side": "buy" if side is Side.LONG else "sell",
            "ordType": "market" if order_type is OrderType.MARKET else "limit",
            "sz": self._to_contracts(inst_id, qty)
            if market is MarketType.FUTURES
            else f"{qty:f}",
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError("okx: limit order needs a price")
            body["px"] = f"{limit_price:f}"
        if reduce_only:
            body["reduceOnly"] = True
        if client_order_id:
            body["clOrdId"] = "".join(c for c in client_order_id if c.isalnum())[:32]
        if stop_loss is not None:
            body["slTriggerPx"] = f"{stop_loss:f}"
            body["slOrdPx"] = "-1"  # market on trigger
        if take_profit is not None:
            body["tpTriggerPx"] = f"{take_profit:f}"
            body["tpOrdPx"] = "-1"

        data = await self.request("POST", "/api/v5/trade/order", body=body)
        rows = data if isinstance(data, list) else [data]
        order_id = rows[0].get("ordId", "") if rows else ""
        avg = limit_price if order_type is OrderType.LIMIT else await self.get_mark_price(symbol)
        return OrderResult(order_id=order_id, filled_qty=qty, avg_price=D(avg or 0), raw=rows)

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        inst_id = self._inst_id(symbol, MarketType.FUTURES)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"okx: no open position on {symbol}")
        body: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": "cross",
            "side": "sell" if position.side is Side.LONG else "buy",
            "ordType": "oco",
            "closeFraction": "1",  # whole position, tracks resizes
        }
        if stop_loss is not None:
            body["slTriggerPx"] = f"{stop_loss:f}"
            body["slOrdPx"] = "-1"
        if take_profit is not None:
            body["tpTriggerPx"] = f"{take_profit:f}"
            body["tpOrdPx"] = "-1"
        await self.request("POST", "/api/v5/trade/order-algo", body=body)

    async def get_position(self, symbol: str) -> Position | None:
        inst_id = self._inst_id(symbol, MarketType.FUTURES)
        data = await self.request(
            "GET", "/api/v5/account/positions", params={"instId": inst_id}
        )
        for row in data if isinstance(data, list) else []:
            contracts = D(row.get("pos") or "0")
            if contracts == 0:
                continue
            size = abs(contracts) * self._contract_size.get(inst_id, D("1"))
            return Position(
                symbol=symbol,
                side=Side.LONG if contracts > 0 else Side.SHORT,
                size=size,
                entry_price=D(row.get("avgPx") or "0"),
                liquidation_price=D(row.get("liqPx") or "0") or None,
                unrealized_pnl=D(row.get("upl") or "0"),
                leverage=int(D(row.get("lever") or "1")),
            )
        return None

    async def close_position(self, symbol: str) -> OrderResult:
        inst_id = self._inst_id(symbol, MarketType.FUTURES)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"okx: no open position to close on {symbol}")
        data = await self.request(
            "POST",
            "/api/v5/trade/close-position",
            body={"instId": inst_id, "mgnMode": "cross", "autoCxl": True},
        )
        return OrderResult(
            order_id=str(data[0].get("clOrdId", "")) if isinstance(data, list) and data else "",
            filled_qty=position.size,
            avg_price=await self.get_mark_price(symbol),
            raw=data,
        )
