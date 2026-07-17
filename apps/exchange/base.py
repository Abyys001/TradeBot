"""Exchange-agnostic client interface + factory.

Copy-trading and live execution route orders through this interface so the
same signal can be mirrored onto any supported exchange (Hyperliquid, Tabdeal)
using each investor's own credentials. Concrete clients live in
``hl_client``/``tabdeal_client``; ``get_client`` picks one by
``credential.exchange``.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

# Normalized order/verify result shape used across clients:
#   {"ok": bool, ..., "error": str}  (error only when ok is False)
Result = dict


@runtime_checkable
class ExchangeClient(Protocol):
    """Uniform surface every exchange client implements.

    All methods are best-effort and return a ``Result`` dict rather than
    raising, so fan-out over many investor accounts never aborts midway.
    """

    def verify(self) -> tuple[bool, str]:
        """Confirm credentials authenticate and can trade. Returns (ok, msg)."""

    def place_order(
        self,
        coin: str,
        is_buy: bool,
        size: float,
        *,
        price: float | None = None,
        reduce_only: bool = False,
    ) -> Result:
        """Place an order. ``price=None`` means market/aggressive."""

    def close_position(self, coin: str) -> Result:
        """Market-close a single position for ``coin``."""

    def positions(self) -> list[dict]:
        """Return open positions: [{coin, size, entry, ...}]."""

    def set_leverage(self, coin: str, leverage: int, *, is_cross: bool = True) -> Result:
        """Set per-asset leverage before trading."""

    def cancel_all(self) -> Result:
        """Cancel all open orders for the account."""

    def balance(self) -> float:
        """Account equity in quote currency (USD/USDT). 0.0 if unavailable."""


def get_client(credential) -> ExchangeClient:
    """Return the exchange client bound to ``credential``.

    Keyed on ``credential.exchange``; import concrete clients lazily to avoid
    pulling heavy SDKs (hyperliquid, requests) at module import time.
    """
    from apps.credentials.models import Exchange

    exchange = credential.exchange
    if exchange == Exchange.HYPERLIQUID:
        from .hl_client import HyperliquidClient

        return HyperliquidClient(credential)
    if exchange == Exchange.TABDEAL:
        from .tabdeal_client import TabdealClient

        return TabdealClient(credential)
    raise ValueError(f"unsupported exchange: {exchange!r}")
