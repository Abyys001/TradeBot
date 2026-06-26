"""Risk configuration schema."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    risk_per_trade_pct: float | None = 1.0
    fixed_risk_usd: float | None = None
    max_daily_loss_pct: float | None = 5.0
    max_drawdown_pct: float | None = 15.0
    max_open_trades: int | None = 3
    max_exposure_pct: float | None = 50.0
    max_leverage: float | None = 10.0

    @classmethod
    def from_dict(cls, data: dict | None) -> RiskConfig:
        if not data:
            return cls()
        return cls(
            risk_per_trade_pct=data.get("risk_per_trade_pct", 1.0),
            fixed_risk_usd=data.get("fixed_risk_usd"),
            max_daily_loss_pct=data.get("max_daily_loss_pct", 5.0),
            max_drawdown_pct=data.get("max_drawdown_pct", 15.0),
            max_open_trades=data.get("max_open_trades", 3),
            max_exposure_pct=data.get("max_exposure_pct", 50.0),
            max_leverage=data.get("max_leverage", 10.0),
        )


def parse_risk_config(live_config: dict | None) -> RiskConfig:
    risk = (live_config or {}).get("risk") or {}
    return RiskConfig.from_dict(risk)
