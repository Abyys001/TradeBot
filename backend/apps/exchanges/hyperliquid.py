"""Hyperliquid.

The odd one out on this platform. No API key/secret: actions are signed with an
**agent (API) wallet** private key using EIP-712. See
``reference/exchanges/hyperliquid/README.md`` for the constraints that shaped
this adapter.

Two decisions worth stating:

1. **The official SDK does the signing.** EIP-712 action hashing is easy to get
   subtly wrong and a wrong signature is a rejected order, so correctness beats
   a hand-rolled implementation here. The SDK is synchronous, so every call is
   pushed to a worker thread — a blocking call on the event loop would stall
   every other account's leg and blow the spec §4 budget.

2. **Queries use the master address, actions use the agent key.** Querying the
   agent address returns empty results; that pitfall is called out in the docs
   and is why ``wallet_address`` is a separate stored field.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from apps.core.money import D, floor_to_step
from apps.exchanges.base import (
    AdapterError,
    AuthError,
    Balance,
    Capabilities,
    ExchangeAdapter,
    MarketType,
    NotSupported,
    OrderResult,
    OrderType,
    Position,
    Side,
    SymbolRules,
)

logger = logging.getLogger(__name__)

MAINNET = "https://api.hyperliquid.xyz"
TESTNET = "https://api.hyperliquid-testnet.xyz"


class HyperliquidAdapter(ExchangeAdapter):
    name = "hyperliquid"
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT, MarketType.FUTURES}),
        has_testnet=True,
        native_sltp_on_entry=False,  # TP/SL are separate trigger orders
        native_sltp_amend=False,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,  # address-based; sub-accounts count separately
        wallet_based_auth=True,
    )

    def __init__(
        self,
        *,
        agent_private_key: str,
        account_address: str,
        testnet: bool = False,
        **_: Any,
    ) -> None:
        if not agent_private_key:
            raise AuthError("hyperliquid: no agent wallet private key configured")
        if not account_address:
            raise AuthError(
                "hyperliquid: the master account address is required — querying the "
                "agent address returns empty results"
            )
        self.account_address = account_address
        self.testnet = testnet
        self._url = TESTNET if testnet else MAINNET
        self._key = agent_private_key
        self._exchange: Any = None
        self._info: Any = None
        self._meta: dict[str, dict] = {}

    # --- SDK plumbing -------------------------------------------------------

    def _build(self) -> None:
        from eth_account import Account
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info

        wallet = Account.from_key(self._key)
        self._info = Info(base_url=self._url, skip_ws=True, timeout=5)
        self._exchange = Exchange(
            wallet=wallet, base_url=self._url, account_address=self.account_address, timeout=5
        )

    async def _call(self, fn_name: str, *args, **kwargs) -> Any:
        """Run a synchronous SDK call off the event loop."""
        if self._exchange is None:
            await asyncio.to_thread(self._build)
        target = self._exchange if hasattr(self._exchange, fn_name) else self._info
        fn = getattr(target, fn_name)
        try:
            result = await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as exc:  # SDK raises bare exceptions
            raise AdapterError(f"hyperliquid: {exc}") from exc
        return self._check(result)

    def _check(self, result: Any) -> Any:
        if isinstance(result, dict) and result.get("status") == "err":
            raise AdapterError(f"hyperliquid: {result.get('response')}")
        if isinstance(result, dict):
            response = result.get("response", {})
            statuses = (response.get("data") or {}).get("statuses") or []
            for status in statuses:
                if isinstance(status, dict) and "error" in status:
                    raise AdapterError(f"hyperliquid: {status['error']}")
        return result

    async def close(self) -> None:
        self._exchange = None
        self._info = None

    def _coin(self, symbol: str) -> str:
        """BTCUSDT -> BTC. Hyperliquid perps are named by base asset alone."""
        upper = symbol.upper()
        for quote in ("USDT", "USDC", "USD"):
            if upper.endswith(quote):
                return upper[: -len(quote)]
        return upper

    # --- interface ---------------------------------------------------------

    async def verify_credentials(self) -> None:
        state = await self._call("user_state", self.account_address)
        if not isinstance(state, dict) or "marginSummary" not in state:
            raise AuthError(
                "hyperliquid: could not read the account state. Check that the "
                "master address is correct and the agent wallet is approved."
            )
        # Spec §7 cannot be enforced from the API here: the docs do not state
        # whether an agent wallet can sign withdrawals. questions.md Q11 tracks
        # verifying this on testnet before real funds are connected.
        logger.warning(
            "hyperliquid: agent-wallet withdrawal rights are unverified (questions.md Q11); "
            "account %s connected without a spec §7 permission check",
            self.account_address,
        )

    async def get_balance(self, asset: str = "USDT") -> Balance:
        # Hyperliquid perps are USDC-margined. It is reported as USDT to the
        # sizing layer because it is the account's dollar collateral, but the
        # real asset name is surfaced so the dashboard can show the truth.
        state = await self._call("user_state", self.account_address)
        summary = state.get("marginSummary", {})
        withdrawable = D(str(state.get("withdrawable", "0")))
        return Balance(
            asset="USDT",
            available=withdrawable,
            total=D(str(summary.get("accountValue", "0"))),
        )

    async def _load_meta(self) -> None:
        meta = await self._call("meta")
        for entry in meta.get("universe", []):
            self._meta[entry["name"]] = entry

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        if market is MarketType.SPOT:
            raise NotSupported("hyperliquid: this adapter covers perpetuals only")
        coin = self._coin(symbol)
        if not self._meta:
            await self._load_meta()
        entry = self._meta.get(coin)
        if entry is None:
            raise AdapterError(f"hyperliquid: unknown coin {coin}")
        # szDecimals fixes the size grid; prices carry at most 5 significant
        # figures and (6 - szDecimals) decimal places.
        size_decimals = int(entry.get("szDecimals", 3))
        return SymbolRules(
            symbol=symbol,
            price_tick=D(1).scaleb(-(6 - size_decimals)),
            qty_step=D(1).scaleb(-size_decimals),
            min_qty=D(1).scaleb(-size_decimals),
            # Documented minimum order value; orders below it are rejected with
            # minTradeNtlRejected.
            min_notional=D("10"),
            max_leverage=int(entry.get("maxLeverage", 10)),
        )

    async def get_mark_price(self, symbol: str) -> Decimal:
        mids = await self._call("all_mids")
        coin = self._coin(symbol)
        if coin not in mids:
            raise AdapterError(f"hyperliquid: no mid price for {coin}")
        return D(str(mids[coin]))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._call("update_leverage", leverage, self._coin(symbol), True)

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
        coin = self._coin(symbol)
        rules = await self.get_symbol_rules(symbol, market)
        size = floor_to_step(qty, rules.qty_step)
        if size <= 0:
            raise AdapterError(f"hyperliquid: size {qty} rounds to zero")

        is_buy = side is Side.LONG
        if order_type is OrderType.MARKET:
            # There is no market order type — an aggressive IOC limit is the
            # documented equivalent. 5% crossing matches the SDK default.
            mid = await self.get_mark_price(symbol)
            price = mid * (D("1.05") if is_buy else D("0.95"))
            hl_type = {"limit": {"tif": "Ioc"}}
        else:
            if limit_price is None:
                raise AdapterError("hyperliquid: limit order needs a price")
            price = limit_price
            hl_type = {"limit": {"tif": "Gtc"}}

        result = await self._call(
            "order",
            coin,
            is_buy,
            float(size),
            float(self._round_price(price, rules)),
            hl_type,
            reduce_only,
        )

        filled = size
        avg = price
        statuses = ((result.get("response") or {}).get("data") or {}).get("statuses") or []
        for status in statuses:
            if isinstance(status, dict) and "filled" in status:
                filled = D(str(status["filled"].get("totalSz", size)))
                avg = D(str(status["filled"].get("avgPx", price)))
        return OrderResult(order_id=str(statuses), filled_qty=filled, avg_price=avg, raw=result)

    def _round_price(self, price: Decimal, rules: SymbolRules) -> Decimal:
        """Hyperliquid rejects prices off the tick grid (tickRejected)."""
        return floor_to_step(price, rules.price_tick)

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        """Resting reduce-only trigger orders on this coin (Q5d snapshot).

        ``frontendOpenOrders`` rather than ``openOrders``: only the former
        carries ``isTrigger``/``reduceOnly``, and without those a plain resting
        limit order the partner placed would look like protection and be
        cancelled on the next SL/TP change.
        """
        coin = self._coin(symbol)
        orders = await self._call("frontend_open_orders", self.account_address)
        return [
            str(order["oid"])
            for order in orders or []
            if order.get("coin") == coin
            and order.get("isTrigger")
            and order.get("reduceOnly")
            and order.get("oid") is not None
        ]

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        coin = self._coin(symbol)
        for order_id in order_ids:
            try:
                await self._call("cancel", coin, int(order_id))
            except (AdapterError, ValueError) as exc:
                # "Order was never placed, already canceled, or filled" — the
                # trigger fired between the snapshot and this call.
                if "never placed" not in str(exc).lower():
                    raise

    async def set_sltp(
        self, *, symbol: str, stop_loss: Decimal | None, take_profit: Decimal | None
    ) -> None:
        """Places new trigger orders. Hyperliquid has no amend for these, so the
        previous pair is cancelled by ``executor.apply_sltp`` (Q5d)."""
        coin = self._coin(symbol)
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"hyperliquid: no open position on {symbol}")
        rules = await self.get_symbol_rules(symbol, MarketType.FUTURES)
        # Exit side is the opposite of the position.
        is_buy = position.side is Side.SHORT

        for price, kind in ((stop_loss, "sl"), (take_profit, "tp")):
            if price is None:
                continue
            await self._call(
                "order",
                coin,
                is_buy,
                float(position.size),
                float(self._round_price(price, rules)),
                {"trigger": {"triggerPx": float(self._round_price(price, rules)),
                             "isMarket": True, "tpsl": kind}},
                True,  # reduce_only
            )

    async def get_position(self, symbol: str) -> Position | None:
        coin = self._coin(symbol)
        state = await self._call("user_state", self.account_address)
        for entry in state.get("assetPositions", []):
            position = entry.get("position", {})
            if position.get("coin") != coin:
                continue
            size = D(str(position.get("szi", "0")))
            if size == 0:
                continue
            leverage = position.get("leverage", {})
            return Position(
                symbol=symbol,
                side=Side.LONG if size > 0 else Side.SHORT,
                size=abs(size),
                entry_price=D(str(position.get("entryPx") or "0")),
                liquidation_price=D(str(position.get("liquidationPx") or "0")) or None,
                unrealized_pnl=D(str(position.get("unrealizedPnl", "0"))),
                leverage=int(leverage.get("value", 1)) if isinstance(leverage, dict) else 1,
            )
        return None

    async def close_position(self, symbol: str) -> OrderResult:
        position = await self.get_position(symbol)
        if position is None:
            raise AdapterError(f"hyperliquid: no open position to close on {symbol}")
        result = await self._call("market_close", self._coin(symbol))
        return OrderResult(
            order_id="market_close",
            filled_qty=position.size,
            avg_price=await self.get_mark_price(symbol),
            raw=result,
        )
