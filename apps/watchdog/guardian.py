"""Position guardian — §6.6: polls exchange for actual position state.

Compares actual position to expected state. If mismatch → corrective action.
Runs as part of the watchdog loop.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    """Current position state from the exchange."""
    symbol: str
    side: str           # "LONG", "SHORT", or "NONE"
    size: float         # absolute position size
    entry_price: float
    has_sl: bool
    has_tp: bool
    pnl: float
    updated_at: float   # timestamp


@dataclass
class GuardianCheck:
    """Result of a position guardian check."""
    ok: bool
    mismatch: str | None = None
    action_needed: str | None = None
    position: PositionState | None = None


def check_position(
    *,
    exchange_client,
    symbol: str,
    expected_has_sl: bool,
    sl_confirmed: bool,
) -> GuardianCheck:
    """§6.6: Compare actual position to expected state.

    Args:
        exchange_client: TabdealFuturesClient instance
        symbol: trading pair
        expected_has_sl: whether we expect SL to be attached
        sl_confirmed: whether SL was confirmed by the order book

    Returns:
        GuardianCheck with mismatch details if position state is wrong.
    """
    try:
        pos = exchange_client.get_position(symbol)
    except Exception as exc:
        logger.error("guardian: failed to read position for %s: %s", symbol, exc)
        return GuardianCheck(
            ok=False,
            mismatch=f"position_read_failed: {exc}",
            action_needed="retry",
        )

    # No position — check if we expected one
    if pos is None:
        if sl_confirmed:
            return GuardianCheck(
                ok=False,
                mismatch="position_gone_but_sl_confirmed",
                action_needed="reconcile",
            )
        return GuardianCheck(ok=True, position=PositionState(
            symbol=symbol, side="NONE", size=0, entry_price=0,
            has_sl=False, has_tp=False, pnl=0, updated_at=time.time(),
        ))

    # Position exists — check SL state
    try:
        amt = float(pos.get("positionAmt", 0))
        entry = float(pos.get("entryPrice", 0))
    except (TypeError, ValueError):
        return GuardianCheck(ok=False, mismatch="position_parse_error", action_needed="retry")

    side = "LONG" if amt > 0 else "SHORT" if amt < 0 else "NONE"
    has_sl = bool(pos.get("stopLossPrice") or pos.get("slPrice"))

    if expected_has_sl and not has_sl:
        return GuardianCheck(
            ok=False,
            mismatch=f"sl_missing_expected_side={side}",
            action_needed="attach_sl",
            position=PositionState(
                symbol=symbol, side=side, size=abs(amt), entry_price=entry,
                has_sl=False, has_tp=False, pnl=0, updated_at=time.time(),
            ),
        )

    return GuardianCheck(ok=True, position=PositionState(
        symbol=symbol, side=side, size=abs(amt), entry_price=entry,
        has_sl=has_sl, has_tp=bool(pos.get("takeProfitPrice") or pos.get("tpPrice")),
        pnl=float(pos.get("unRealizedProfit", 0)),
        updated_at=time.time(),
    ))
