"""Position sizing from risk config."""
from __future__ import annotations

from .config import RiskConfig


def size_from_risk(
    config: RiskConfig,
    *,
    equity: float,
    entry_price: float,
    stop_distance: float | None = None,
    leverage: float = 1.0,
) -> float:
    """Return position size (units) based on % risk or fixed USD risk."""
    if config.fixed_risk_usd and stop_distance and stop_distance > 0:
        return config.fixed_risk_usd / stop_distance

    if config.risk_per_trade_pct and equity > 0 and entry_price > 0:
        risk_usd = equity * (config.risk_per_trade_pct / 100.0)
        if stop_distance and stop_distance > 0:
            return risk_usd / stop_distance
        # No stop: use notional cap as fraction of equity * leverage
        notional = risk_usd * leverage
        return notional / entry_price

    return 1.0
