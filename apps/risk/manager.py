"""Central risk manager for backtest, paper, and live trading.

State is persisted to Redis so that worker restarts do not reset risk gates
(daily loss limits, drawdown halts, etc.).
"""
from __future__ import annotations

import json
import logging

from django.core.cache import cache

from .config import RiskConfig
from . import gates

logger = logging.getLogger(__name__)

RISK_STATE_TTL = 90000  # ~25 hours — auto-expire at end of day


class RiskManager:
    def __init__(self, config: RiskConfig | None = None, initial_balance: float = 10_000.0, strategy_id: int | None = None):
        self.config = config or RiskConfig()
        self.initial_balance = initial_balance
        self.peak_equity = initial_balance
        self.daily_start_equity = initial_balance
        self.daily_pnl = 0.0
        self.halted = False
        self.halt_reason = ""
        self._strategy_id = strategy_id
        self._redis_key = f"risk:state:{strategy_id}" if strategy_id else None
        if self._redis_key:
            self._load_from_redis()

    # ----- Redis persistence -----

    def _load_from_redis(self) -> None:
        if not self._redis_key:
            return
        raw = cache.get(self._redis_key)
        if raw is None:
            return
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            self.peak_equity = data.get("peak_equity", self.peak_equity)
            self.daily_start_equity = data.get("daily_start_equity", self.daily_start_equity)
            self.daily_pnl = data.get("daily_pnl", self.daily_pnl)
            self.halted = data.get("halted", False)
            self.halt_reason = data.get("halt_reason", "")
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("failed to load risk state from redis for %s", self._redis_key)

    def _save_to_redis(self) -> None:
        if not self._redis_key:
            return
        data = {
            "peak_equity": self.peak_equity,
            "daily_start_equity": self.daily_start_equity,
            "daily_pnl": self.daily_pnl,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }
        cache.set(self._redis_key, json.dumps(data), RISK_STATE_TTL)

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
                self._save_to_redis()
                return

        self._save_to_redis()

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
