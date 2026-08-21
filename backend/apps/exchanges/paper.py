"""In-memory paper adapter.

Two jobs:
  1. Spec §9's demo mode — the whole platform runs end to end with no real
     credentials and no real money.
  2. The test fixture for the fan-out engine, including its failure modes.
     Latency and failures are injectable, so "one account fails, the rest
     continue" (spec §4) is a test, not a hope.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

from apps.core.money import D, floor_to_step
from apps.exchanges.base import (
    AdapterError,
    Balance,
    BelowMinimumNotional,
    Capabilities,
    ClosedFill,
    ExchangeAdapter,
    MarketType,
    OrderResult,
    OrderType,
    Position,
    Side,
    SLTPState,
    SymbolRules,
)

_ids = itertools.count(1)

#: Demo-mode position state, keyed per account.
#:
#: A real exchange keeps positions server-side, so the service layer builds a
#: fresh adapter for every action and that is correct. The paper adapter has no
#: server, so without this its position would vanish between opening a trade and
#: closing it — spec §9's demo mode would not survive a round trip. Adapters
#: built without a ``state_key`` keep private state, which is what tests want.
_SHARED_STATE: dict[str, dict] = {}


def reset_paper_state() -> None:
    """Wipe demo state. Used when switching out of demo mode."""
    _SHARED_STATE.clear()


DEFAULT_RULES = SymbolRules(
    symbol="BTCUSDT",
    price_tick=D("0.1"),
    qty_step=D("0.001"),
    min_qty=D("0.001"),
    min_notional=D("5"),
    max_leverage=10,
)


class PaperAdapter(ExchangeAdapter):
    name = "paper"
    capabilities = Capabilities(
        markets=frozenset({MarketType.SPOT, MarketType.FUTURES}),
        has_testnet=True,
        native_sltp_on_entry=True,
        native_sltp_amend=True,
        supports_reduce_only=True,
        max_leverage=10,
        per_key_rate_limits=True,
    )

    def __init__(
        self,
        *,
        balance: Decimal = D("1000"),
        asset: str = "USDT",
        mark_price: Decimal = D("100000"),
        rules: SymbolRules = DEFAULT_RULES,
        latency: float = 0.0,
        fail_on: set[str] | None = None,
        failure: type[AdapterError] | None = None,
        state_key: str | None = None,
    ) -> None:
        self._balance = D(balance)
        self._asset = asset
        self._mark = D(mark_price)
        self._rules = rules
        self._latency = latency
        # Method names that should raise, e.g. {"place_order"}. Drives the
        # independent-failure tests in spec §4.
        self._fail_on = fail_on or set()
        self._failure = failure or AdapterError
        # With a state_key the position survives between adapter instances, so
        # demo mode can open a trade and later close it. Without one the state
        # is private to this instance, which keeps tests isolated.
        self._state = _SHARED_STATE.setdefault(state_key, {}) if state_key else {}
        self._state.setdefault("leverage", 1)
        self._state.setdefault("position", None)
        self._state.setdefault("sltp", (None, None))
        self.calls: list[str] = []
        self.closed = False

    @property
    def _leverage(self) -> int:
        return self._state["leverage"]

    @_leverage.setter
    def _leverage(self, value: int) -> None:
        self._state["leverage"] = value

    @property
    def _position(self) -> Position | None:
        return self._state["position"]

    @_position.setter
    def _position(self, value: Position | None) -> None:
        self._state["position"] = value

    # -- helpers ------------------------------------------------------------

    async def _tick(self, method: str) -> None:
        self.calls.append(method)
        if self._latency:
            await asyncio.sleep(self._latency)
        if method in self._fail_on:
            raise self._failure(f"paper adapter: injected failure in {method}")

    @property
    def sltp(self) -> tuple[Decimal | None, Decimal | None]:
        return self._state["sltp"]

    def set_mark_price(self, price: Decimal) -> None:
        self._mark = D(price)

    async def get_mark_price(self, symbol: str) -> Decimal | None:
        """Demo mode prices itself, so a market order needs no external feed."""
        return self._mark

    # -- interface ----------------------------------------------------------

    async def close(self) -> None:
        self.closed = True

    async def verify_credentials(self) -> None:
        await self._tick("verify_credentials")

    async def get_balance(self, asset: str = "USDT") -> Balance:
        await self._tick("get_balance")
        return Balance(asset=self._asset, available=self._balance, total=self._balance)

    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules:
        await self._tick("get_symbol_rules")
        return self._rules

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._tick("set_leverage")
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
        await self._tick("place_order")
        qty = floor_to_step(D(qty), self._rules.qty_step)
        price = D(limit_price) if order_type is OrderType.LIMIT and limit_price else self._mark
        if qty < self._rules.min_qty or qty * price < self._rules.min_notional:
            raise BelowMinimumNotional(
                f"qty {qty} @ {price} is below the minimum for {symbol}"
            )
        self._position = Position(
            symbol=symbol,
            side=side,
            size=qty,
            entry_price=price,
            liquidation_price=self._liquidation(side, price),
            unrealized_pnl=D("0"),
            leverage=self._leverage,
        )
        self._state["sltp"] = (stop_loss, take_profit)
        return OrderResult(order_id=str(next(_ids)), filled_qty=qty, avg_price=price)

    def _liquidation(self, side: Side, entry: Decimal) -> Decimal:
        # Simplified: ignores maintenance margin and fees. Enough to exercise
        # the liquidation guard in the risk calculator; a real adapter reports
        # the exchange's own number.
        move = entry / D(self._leverage)
        return entry - move if side is Side.LONG else entry + move

    async def set_sltp(
        self,
        *,
        symbol: str,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
        position: Position | None = None,
    ) -> None:
        await self._tick("set_sltp")
        self._state["sltp"] = (stop_loss, take_profit)

    async def get_sltp(self, symbol: str) -> SLTPState:
        """Demo mode has a server-side state, so it can answer truthfully."""
        await self._tick("get_sltp")
        stop_loss, take_profit = self._state["sltp"]
        return SLTPState(stop_loss=stop_loss, take_profit=take_profit)

    async def get_position(self, symbol: str) -> Position | None:
        await self._tick("get_position")
        return self._position

    async def close_position(self, symbol: str) -> OrderResult:
        await self._tick("close_position")
        pos = self._position
        if pos is None:
            raise AdapterError("no open position to close", code="no_position")
        self._settle(pos, self._mark)
        return OrderResult(order_id=str(next(_ids)), filled_qty=pos.size, avg_price=self._mark)

    def _settle(self, pos: Position, price: Decimal) -> None:
        """Flatten and keep the fill, the way a real venue keeps its trade log."""
        direction = D("1") if pos.side is Side.LONG else D("-1")
        self._state["last_close"] = ClosedFill(
            exit_price=price,
            qty=pos.size,
            realised_pnl=(price - pos.entry_price) * pos.size * direction,
            fees=D("0"),
            closed_at=datetime.now(UTC),
        )
        self._position = None
        self._state["sltp"] = (None, None)

    def settle_on_exchange(self, price: Decimal) -> None:
        """Demo stand-in for a stop firing: the venue closes, nothing is sent."""
        pos = self._position
        if pos is not None:
            self._settle(pos, D(price))

    async def get_closed_pnl(self, symbol: str, since: datetime) -> ClosedFill | None:
        await self._tick("get_closed_pnl")
        fill = self._state.get("last_close")
        if fill is None or (fill.closed_at is not None and fill.closed_at < since):
            return None
        return fill

    async def stream_events(self) -> AsyncIterator[dict]:
        return
        yield {}  # pragma: no cover
