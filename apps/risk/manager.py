"""Central risk manager for backtest, paper, and live trading."""
from __future__ import annotations

from .config import RiskConfig
from . import gates


class RiskManager:
    def __init__(self, config: RiskConfig | None = None, initial_balance: float = 10_000.0):
        self.config = config or RiskConfig()
        self.initial_balance = initial_balance
        self.peak_equity = initial_balance
        self.daily_start_equity = initial_balance
        self.daily_pnl = 0.0
        self.halted = False
        self.halt_reason = ""

    def update_equity(self, equity: float, *, new_day: bool = False) -> None:
        if new_day:
            self.daily_start_equity = equity
            self.daily_pnl = 0.0
        self.daily_pnl = equity - self.daily_start_equity
        self.peak_equity = max(self.peak_equity, equity)
        dd_pct = 0.0
        if self.peak_equity > 0:
            dd_pct = (self.peak_equity - equity) / self.peak_equity * 100.0
        daily_pct = (self.daily_pnl / self.daily_start_equity * 100.0) if self.daily_start_equity else 0.0

        for decision in (
            gates.check_daily_loss(daily_pct, self.config.max_daily_loss_pct),
            gates.check_drawdown(dd_pct, self.config.max_drawdown_pct),
        ):
            if not decision.ok:
                self.halted = True
                self.halt_reason = decision.reason
                return

    def pre_trade(
        self,
        *,
        equity: float,
        open_trades: int,
        exposure_pct: float,
        leverage: float = 1.0,
    ) -> gates.GateDecision:
        if self.halted:
            return gates.GateDecision(False, self.halt_reason or "risk_halted")

        checks = [
            gates.check_max_open_trades(open_trades, self.config.max_open_trades),
            gates.check_max_exposure(exposure_pct, self.config.max_exposure_pct),
            gates.check_leverage(leverage, self.config.max_leverage),
        ]
        for decision in checks:
            if not decision.ok:
                return decision
        self.update_equity(equity)
        if self.halted:
            return gates.GateDecision(False, self.halt_reason)
        return gates.GateDecision(True)
