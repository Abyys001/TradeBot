"""LBank — spot only.

Futures is **not implemented and cannot be** from published documentation.
LBank's contract API (``reference/exchanges/lbank/api/contract.md``, downloaded
in full) documents only the public namespace ``/cfd/openApi/v1/pub``. There are
no published private endpoints for placing orders, reading positions, or
querying balances, so every futures method here raises ``NotSupported`` rather
than guessing at an undocumented request shape and silently mis-trading.

Tracked as questions.md Q10. Spot is fully documented and works.

Signing (spot): MD5 of the sorted parameter string, uppercased, then
HMAC-SHA256 with the secret. ``echostr`` is a random 30–40 character
alphanumeric string, per the docs.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
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
)
from apps.exchanges.rest import RestAdapter

FUTURES_UNAVAILABLE = (
    "LBank publishes no private futures API. Only public market data is "
    "documented, so orders, positions and balances cannot be implemented. "
    "See questions.md Q10 — request the private contract docs from LBank."
)


class LbankAdapter(RestAdapter):
    name = "lbank"
    base_url = "https://api.lbkex.com"
    testnet_url = ""
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT}),  # futures deliberately absent
        has_testnet=False,
        testnet_note="LBank publishes no test environment.",
        native_sltp_on_entry=False,
        native_sltp_amend=False,
        supports_reduce_only=False,
        max_leverage=1,  # spot only
        per_key_rate_limits=True,
    )

    @staticmethod
    def _echostr() -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(35))

    def _sign(
        self, method: str, path: str, params: dict | None, body: dict | None
    ) -> tuple[dict[str, str], dict | None, Any]:
        payload = {**(params or {}), **(body or {})}
        payload["api_key"] = self.api_key
        payload["timestamp"] = str(int(time.time() * 1000))
        payload["signature_method"] = "HmacSHA256"
        echostr = self._echostr()
        payload["echostr"] = echostr

        ordered = urlencode(sorted(payload.items()))
        digest = hashlib.md5(ordered.encode()).hexdigest().upper()
        signature = hmac.new(
            self.api_secret.encode(), digest.encode(), hashlib.sha256
        ).hexdigest()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "timestamp": payload["timestamp"],
            "signature_method": "HmacSHA256",
            "echostr": echostr,
        }
        content = f"{urlencode(payload)}&sign={signature}".encode()
        return headers, None, content

    def unwrap(self, payload: Any) -> Any:
        if isinstance(payload, dict) and payload.get("result") in (False, "false"):
            code = payload.get("error_code")
            message = payload.get("msg", f"error_code {code}")
            if str(code) in {"10007", "10008", "10009"}:
                raise AuthError(f"lbank: {message}")
            raise AdapterError(f"lbank: {message}")
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def _pair(self, symbol: str) -> str:
        """BTCUSDT -> btc_usdt."""
        if "_" in symbol:
            return symbol.lower()
        upper = symbol.upper()
        for quote in ("USDT", "USDC", "USD"):
            if upper.endswith(quote):
                return f"{upper[: -len(quote)].lower()}_{quote.lower()}"
        raise AdapterError(f"lbank: cannot map symbol {symbol}")

    def _reject_futures(self, market: MarketType) -> None:
        if market is MarketType.FUTURES:
            raise NotSupported(FUTURES_UNAVAILABLE)

    # --- interface ---------------------------------------------------------

    async def verify_credentials(self) -> None:
        # LBank exposes no key-permission endpoint, so spec §7 cannot be proven
        # from the API — the admin confirms it when creating the key.
        await self.request("POST", "/v2/supplement/user_info.do")

    async def get_balance(self, asset: str = "USDT") -> Balance:
        data = await self.request("POST", "/v2/supplement/user_info.do")
        rows = data if isinstance(data, list) else data.get("balances", [])
        for row in rows:
            if str(row.get("asset", row.get("coin", ""))).upper() == asset.upper():
                free = D(str(row.get("free", row.get("usableAmt", "0"))))
                locked = D(str(row.get("locked", "0")))
                return Balance(asset=asset, available=free, total=free + locked)
        return Balance(asset=asset, available=D("0"), total=D("0"))

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        self._reject_futures(market)
        data = await self.request(
            "GET", "/v2/accuracy.do", params={"symbol": self._pair(symbol)}, signed=False
        )
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if row.get("symbol") != self._pair(symbol):
                continue
            qty_decimals = int(row.get("quantityAccuracy", 4))
            price_decimals = int(row.get("priceAccuracy", 2))
            return SymbolRules(
                symbol=symbol,
                price_tick=D(1).scaleb(-price_decimals),
                qty_step=D(1).scaleb(-qty_decimals),
                min_qty=D(str(row.get("minTranQua", "0.001"))),
                min_notional=D("5"),
                max_leverage=1,
            )
        raise AdapterError(f"lbank: unknown symbol {symbol}")

    async def get_mark_price(self, symbol: str) -> Decimal:
        data = await self.request(
            "GET",
            "/v2/supplement/ticker/price.do",
            params={"symbol": self._pair(symbol)},
            signed=False,
        )
        rows = data if isinstance(data, list) else [data]
        if not rows:
            raise AdapterError(f"lbank: no price for {symbol}")
        return D(str(rows[0].get("price", "0")))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        if leverage != 1:
            raise NotSupported(FUTURES_UNAVAILABLE)

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
        self._reject_futures(market)
        if side is Side.SHORT:
            raise NotSupported("lbank: spot cannot be shorted, and futures is unavailable")

        body: dict[str, Any] = {
            "symbol": self._pair(symbol),
            "type": "buy_market" if order_type is OrderType.MARKET else "buy",
            "amount": f"{qty:f}",
        }
        if order_type is OrderType.LIMIT:
            if limit_price is None:
                raise AdapterError("lbank: limit order needs a price")
            body["price"] = f"{limit_price:f}"
        if client_order_id:
            body["custom_id"] = client_order_id[:50]

        data = await self.request("POST", "/v2/supplement/create_order.do", body=body)
        price = limit_price or await self.get_mark_price(symbol)
        return OrderResult(
            order_id=str(data.get("order_id", "")),
            filled_qty=qty,
            avg_price=D(price),
            raw=data,
        )

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        raise NotSupported(
            "lbank: no SL/TP on spot via the documented API, and futures is unavailable. "
            "See questions.md Q10."
        )

    async def get_position(self, symbol: str) -> Position | None:
        # Spot has no positions; futures positions are undocumented.
        return None

    async def close_position(self, symbol: str) -> OrderResult:
        raise NotSupported(FUTURES_UNAVAILABLE)
