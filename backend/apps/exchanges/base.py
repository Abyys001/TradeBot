"""The Adapter seam.

Every exchange implements ``ExchangeAdapter``. The execution engine talks only
to this interface — there is no ``if exchange == "binance"`` anywhere above it.
Differences between exchanges (native vs emulated SL/TP, per-symbol vs
per-account leverage, testnet or not) are declared in ``Capabilities`` and
handled *inside* the adapter.

Everything here is async. A blocking call in an adapter stalls the whole
fan-out and blows the per-leg deadline in spec §4.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


class MarketType(StrEnum):
    SPOT = "spot"
    FUTURES = "futures"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


# --- Capability declaration -------------------------------------------------


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What an exchange can actually do. Filled in per adapter from its docs."""

    markets: frozenset[MarketType]
    has_testnet: bool
    # Spec §9: shown in the panel as "no test environment" when False.
    testnet_note: str = ""
    # True when SL/TP can be attached to the entry order itself.
    native_sltp_on_entry: bool = True
    # True when an existing SL/TP can be modified without cancel+replace (Q5d).
    native_sltp_amend: bool = False
    # True when stop orders accept reduce-only, which makes place-then-cancel safe.
    supports_reduce_only: bool = True
    max_leverage: int = 10
    # True when rate limits are scoped per API key/address rather than per IP.
    # Spec §2 isolation depends on this; False means accounts contend.
    per_key_rate_limits: bool = True
    # Exchanges where credentials are wallet keys rather than API key/secret.
    wallet_based_auth: bool = False


@dataclass(frozen=True, slots=True)
class SymbolRules:
    """Tick/step/minimum rules. Sizing must respect these before an order is sent."""

    symbol: str
    price_tick: Decimal
    qty_step: Decimal
    min_qty: Decimal
    min_notional: Decimal
    max_leverage: int


@dataclass(frozen=True, slots=True)
class Balance:
    asset: str
    available: Decimal
    total: Decimal

    @property
    def is_usdt(self) -> bool:
        # Spec §5 / Q4: non-USDT accounts are reported, not traded.
        return self.asset.upper() == "USDT"


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    side: Side
    size: Decimal
    entry_price: Decimal
    liquidation_price: Decimal | None
    unrealized_pnl: Decimal
    leverage: int


@dataclass(frozen=True, slots=True)
class ClosedFill:
    """What the venue says an exit was actually worth.

    Recovered from the exchange's own fill record, so it is the only honest
    answer for a position that left the platform's sight — a stop that fired, a
    liquidation, a close done in the venue's own app. ``realised_pnl`` is the
    exchange's number with fees already deducted; ``fees`` is carried
    separately so the panel can show where it differs from raw price maths.
    """

    exit_price: Decimal
    qty: Decimal
    realised_pnl: Decimal
    fees: Decimal
    closed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OrderResult:
    order_id: str
    filled_qty: Decimal
    avg_price: Decimal
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SLTPState:
    """What actually rests on the exchange: the verified trigger prices.

    ``None`` for a side means the exchange holds no trigger order for it. The
    whole state is only meaningful when it came from ``get_sltp`` — a read of
    the exchange, never what we asked it to place.
    """

    stop_loss: Decimal | None
    take_profit: Decimal | None


# --- Errors -----------------------------------------------------------------


class AdapterError(Exception):
    """Base class. Every adapter failure must surface as one of these."""

    retryable = False

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        # Optional machine-readable code, carried through the fan-out to the
        # notification ("below_min_qty" vs "timeout" vs "exchange broke"). When
        # absent the fan-out falls back to the exception's class name.
        self.code = code


class AuthError(AdapterError):
    """Credentials rejected, expired, or lacking permission."""


class WithdrawalPermissionError(AuthError):
    """Credential has withdrawal rights. Spec §7 forbids connecting it."""


class InsufficientBalance(AdapterError):
    pass


class BelowMinimumNotional(AdapterError):
    """99% of this account is too small to trade this symbol (spec §5 / Q4)."""


class RateLimited(AdapterError):
    retryable = True


class ExchangeUnavailable(AdapterError):
    retryable = True


class NotSupported(AdapterError):
    """The exchange cannot do this at all (e.g. LBank futures private endpoints)."""


# --- The interface ----------------------------------------------------------


class ExchangeAdapter(abc.ABC):
    """One instance per connected account. Never shared between accounts.

    Isolation (spec §2) is structural: separate instance, separate HTTP client,
    separate rate limiter, separate credentials.
    """

    name: str
    capabilities: Capabilities

    @abc.abstractmethod
    async def close(self) -> None:
        """Release the HTTP/WS client. Always called, even on failure paths."""

    async def warm(self) -> None:
        """Do whatever the first call would otherwise do, off the critical path.

        An adapter with lazy setup — a client to construct, asset metadata to
        download — pays for it inside the spec §4 deadline on the first action
        after a restart, where it is measured against a budget meant for one
        order round trip. Hyperliquid's build is ~2.5s on a link where a warm
        round trip is 0.6s, which is the whole deadline before the order is
        even signed.

        Default no-op: an adapter with nothing to set up is already warm.
        Never raises — a venue that cannot be reached now is a leg's problem
        later, not a reason to fail the panel's connection.
        """
        return None

    async def settle_inflight(self, timeout: float) -> bool:
        """Wait for requests this adapter started and stopped listening for.

        The fan-out deadline cancels a leg's coroutine, and for an adapter
        whose transport is genuinely async that also aborts the request. It
        does **not** for an adapter that drives a synchronous SDK through
        ``asyncio.to_thread``: cancelling the awaiting coroutine cannot kill
        the worker thread, which runs the signed order to completion long
        after the leg was written off.

        Returns True when nothing of this adapter's is still in the air, so a
        caller may trust what the exchange says about the account. False means
        a request is still executing and "no position" would be a read taken
        before the exchange was even asked — the mistake that reported a live
        Hyperliquid position as ``not_filled``.

        Default True: an adapter whose cancellations are real has nothing to
        wait for.
        """
        return True

    @abc.abstractmethod
    async def verify_credentials(self) -> None:
        """Raise AuthError if unusable, WithdrawalPermissionError if withdrawable.

        Called once at connect time. Spec §7 makes a withdrawable key a hard
        refusal, so adapters must check the permission scope wherever the
        exchange exposes it, and say so in the docstring when it does not.
        """

    @abc.abstractmethod
    async def get_balance(self, asset: str = "USDT") -> Balance: ...

    @abc.abstractmethod
    async def get_symbol_rules(self, symbol: str, market: MarketType) -> SymbolRules: ...

    @abc.abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> None: ...

    @abc.abstractmethod
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
    ) -> OrderResult: ...

    @abc.abstractmethod
    async def set_sltp(
        self,
        *,
        symbol: str,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
    ) -> None:
        """Place SL/TP for the open position.

        Adapters where ``capabilities.native_sltp_amend`` is True replace the
        existing protection in place, and this is the whole operation.

        Everywhere else SL/TP are ordinary reduce-only conditional orders and
        this call only *places* them — it must not cancel anything. Sequencing
        the old orders out is the Q5d amend strategy and lives in one place,
        ``apps.engine.executor.apply_sltp``, which drives the two methods
        below. Never call ``set_sltp`` directly on an amend path.
        """

    async def list_conditional_orders(self, symbol: str) -> list[str]:
        """Ids of the live reduce-only SL/TP orders on ``symbol``.

        Snapshotted before new protection is placed so the Q5d strategy can
        cancel exactly the orders that were already there. The default is
        empty, which makes the strategy a no-op: correct for adapters that
        amend in place, and honest for one that cannot enumerate its orders.
        """
        return []

    async def cancel_orders(self, symbol: str, order_ids: list[str]) -> None:
        """Cancel the given orders. Ids come from ``list_conditional_orders``.

        Must tolerate an id that has already triggered or been cancelled — a
        stop that fired between the snapshot and this call is a race, not an
        error, and raising here would fail an amend that actually succeeded.
        """
        return None

    async def get_sltp(self, symbol: str) -> SLTPState | None:
        """The SL/TP **actually resting on the exchange**, when the adapter can ask.

        Placing is not proof. A trigger order an exchange silently drops (a
        take-profit that never lands, say) looks identical to a working one from
        the caller's side, so after every ``set_sltp`` the executor reads back
        and only then calls the leg protected. Adapters that can enumerate their
        conditional orders (Binance, Bybit, OKX, KuCoin, Gate.io, Hyperliquid,
        paper) return the resting trigger prices.

        The default is ``None`` = "cannot answer". That is never a failure — an
        exchange that cannot be asked is honest about it, and the leg is
        recorded as placed-but-unconfirmed rather than verified.
        """
        return None

    @abc.abstractmethod
    async def get_position(self, symbol: str) -> Position | None: ...

    async def get_mark_price(self, symbol: str) -> Decimal | None:
        """The adapter's own view of the current price, if it has one.

        Optional. A **market** order cannot be sized without a reference price:
        qty is notional / price, and the notional comes from the balance. When
        an adapter cannot answer, the caller supplies the price from the public
        market-data feed instead (see ``apps.trading.services.route_open``).
        """
        return None

    async def get_closed_pnl(self, symbol: str, since: datetime) -> ClosedFill | None:
        """The venue's own record of how a position was closed, after ``since``.

        A position can end without this platform sending anything — a stop
        firing, a liquidation, a close made in the exchange's own app — and then
        the exit price and PnL exist only on the venue. ``possync`` asks here
        before it writes such a leg off, so the trade log carries real numbers
        instead of a dash.

        The default is ``None`` = "cannot answer", the same contract as
        ``get_sltp``. An adapter that cannot enumerate its fills leaves the exit
        unknown; nothing is estimated from a mark price, because a number the
        exchange did not say is not a fill.
        """
        return None

    @abc.abstractmethod
    async def close_position(self, symbol: str) -> OrderResult:
        """Market-close the whole position (spec §3)."""

    async def stream_events(self) -> AsyncIterator[dict]:
        """Private order/position stream. Optional; default is no stream."""
        return
        yield {}  # pragma: no cover - makes this an async generator
