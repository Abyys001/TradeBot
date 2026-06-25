"""Risk gate decisions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GateDecision:
    ok: bool
    reason: str = ""
    details: dict | None = None


def check_max_open_trades(open_count: int, limit: int | None) -> GateDecision:
    if limit is not None and open_count >= limit:
        return GateDecision(False, "max_open_trades", {"open": open_count, "limit": limit})
    return GateDecision(True)


def check_max_exposure(exposure_pct: float, limit: float | None) -> GateDecision:
    if limit is not None and exposure_pct > limit:
        return GateDecision(False, "max_exposure", {"exposure_pct": exposure_pct, "limit": limit})
    return GateDecision(True)


def check_daily_loss(daily_pnl_pct: float, limit: float | None) -> GateDecision:
    if limit is not None and daily_pnl_pct <= -abs(limit):
        return GateDecision(False, "max_daily_loss", {"daily_pnl_pct": daily_pnl_pct, "limit": limit})
    return GateDecision(True)


def check_drawdown(current_dd_pct: float, limit: float | None) -> GateDecision:
    if limit is not None and current_dd_pct >= abs(limit):
        return GateDecision(False, "max_drawdown", {"drawdown_pct": current_dd_pct, "limit": limit})
    return GateDecision(True)


def check_leverage(requested: float, limit: float | None) -> GateDecision:
    if limit is not None and requested > limit:
        return GateDecision(False, "max_leverage", {"requested": requested, "limit": limit})
    return GateDecision(True)
