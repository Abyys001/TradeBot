"""The Adapter seam.

Every exchange implements ``ExchangeAdapter``. The execution engine talks only
to this interface — there is no ``if exchange == "binance"`` anywhere above it.
Differences between exchanges (native vs emulated SL/TP, per-symbol vs
per-account leverage, testnet or not) are declared in ``Capabilities`` and
handled *inside* the adapter.

Everything here is async. A blocking call in an adapter stalls the whole
fan-out and blows the 1-second budget in spec §4.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
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
class OrderResult:
    order_id: str
    filled_qty: Decimal
    avg_price: Decimal
    raw: dict = field(default_factory=dict)


# --- Errors -----------------------------------------------------------------


class AdapterError(Exception):
    """Base class. Every adapter failure must surface as one of these."""

    retryable = False


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
        """Attach or replace SL/TP on the open position.

        Adapters where ``capabilities.native_sltp_amend`` is False must honour
        the configured amend strategy (Q5d) rather than blindly cancelling
        first — a gap here means an unprotected leveraged position.
        """

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

    @abc.abstractmethod
    async def close_position(self, symbol: str) -> OrderResult:
        """Market-close the whole position (spec §3)."""

    async def stream_events(self) -> AsyncIterator[dict]:
        """Private order/position stream. Optional; default is no stream."""
        return
        yield {}  # pragma: no cover - makes this an async generator
