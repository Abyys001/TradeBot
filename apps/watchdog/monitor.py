"""Watchdog monitor — §6.2: heartbeat monitor + tiered response.

Reads heartbeat from Redis, evaluates tier, executes actions.
Runs as a loop in the watchdog process.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from django.core.cache import cache

from .models import WatchdogConfig, WatchdogAction
from .tiers import evaluate_tier, log_action
from .guardian import check_position

logger = logging.getLogger(__name__)


@dataclass
class MonitorState:
    """Per-strategy monitoring state."""
    strategy_id: int
    last_heartbeat_ts: float
    bars_since_halt: int
    sl_confirmed: bool
    current_tier: int
    daily_loss_breached: bool


class WatchdogMonitor:
    """Monitors Node B health and enforces position protection.

    Reads heartbeat from Redis key ``health:hot_compute:{strategy_id}``.
    Evaluates tier and executes actions via the exchange client.
    """

    HEARTBEAT_KEY = "health:hot_compute:{strategy_id}"
    DAILY_LOSS_KEY = "risk:halted:{strategy_id}"

    def __init__(self, strategy_id: int, exchange_client):
        self.strategy_id = strategy_id
        self.client = exchange_client
        self.state = MonitorState(
            strategy_id=strategy_id,
            last_heartbeat_ts=0.0,
            bars_since_halt=0,
            sl_confirmed=False,
            current_tier=0,
            daily_loss_breached=False,
        )
        self._config: WatchdogConfig | None = None

    def _get_config(self) -> WatchdogConfig:
        if self._config is None:
            self._config, _ = WatchdogConfig.objects.get_or_create(
                strategy_id=self.strategy_id,
                defaults={"enabled": True},
            )
        return self._config

    def _read_heartbeat(self) -> float:
        """Read the last heartbeat timestamp from Redis."""
        key = self.HEARTBEAT_KEY.format(strategy_id=self.strategy_id)
        data = cache.get(key)
        if data is None:
            return 0.0
        if isinstance(data, dict):
            return float(data.get("ts", 0))
        return float(data) if data else 0.0

    def _check_daily_loss(self) -> bool:
        """Check if daily loss limit is breached."""
        key = self.DAILY_LOSS_KEY.format(strategy_id=self.strategy_id)
        data = cache.get(key)
        if data is None:
            return False
        if isinstance(data, dict):
            return bool(data.get("halted", False))
        return bool(data)

    def _check_sl_status(self) -> bool:
        """Check if SL is confirmed attached to the position."""
        from apps.strategies.models import StrategyState
        try:
            state = StrategyState.objects.get(strategy_id=self.strategy_id)
            return bool(state.sl_confirmed)
        except StrategyState.DoesNotExist:
            return False

    def check(self) -> tuple[int, dict]:
        """Single check cycle: read state, evaluate tier, return decision.

        Returns (tier, detail_dict).
        """
        config = self._get_config()
        if not config.enabled:
            return 0, {"action": "disabled"}

        now = time.time()
        heartbeat_ts = self._read_heartbeat()
        heartbeat_gap_ms = int((now - heartbeat_ts) * 1000) if heartbeat_ts > 0 else 999999

        sl_confirmed = self._check_sl_status()
        daily_loss = self._check_daily_loss()

        decision = evaluate_tier(
            heartbeat_gap_ms=heartbeat_gap_ms,
            t_self_ms=config.t_self_ms,
            t_dead_ms=config.t_dead_ms,
            sl_confirmed=sl_confirmed,
            bars_since_halt=self.state.bars_since_halt,
            max_blind_hold=config.max_blind_hold,
            daily_loss_breached=daily_loss,
        )

        detail = {
            "heartbeat_gap_ms": heartbeat_gap_ms,
            "sl_confirmed": sl_confirmed,
            "daily_loss_breached": daily_loss,
            "bars_since_halt": self.state.bars_since_halt,
            "action": decision.action,
            "reason": decision.reason,
        }

        # Update state
        if decision.tier > 0:
            self.state.bars_since_halt += 1
        else:
            self.state.bars_since_halt = 0
        self.state.current_tier = decision.tier
        self.state.sl_confirmed = sl_confirmed
        self.state.daily_loss_breached = daily_loss

        return decision.tier, detail

    def execute(self, tier: int, detail: dict) -> None:
        """Execute the tier decision actions."""
        if detail.get("action") == "disabled":
            return

        if detail.get("action") == "healthy":
            if self.state.current_tier > 0:
                log_action(self.strategy_id, 0, WatchdogAction.ActionType.HEARTBEAT_RECOVER, detail)
                logger.info("watchdog %s: heartbeat recovered", self.strategy_id)
            return

        if detail.get("should_attach_sl"):
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED, detail)
            logger.warning("watchdog %s: T%d attaching SL", self.strategy_id, tier)

        if detail.get("should_flatten"):
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.POSITION_FLAT, detail)
            logger.warning("watchdog %s: T%d flattening position", self.strategy_id, tier)

        if detail.get("should_kill_switch"):
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.KILL_SWITCH, detail)
            logger.critical("watchdog %s: T%d KILL SWITCH activated", self.strategy_id, tier)


async def run_watchdog(interval_s: float = 5.0) -> None:
    """Main watchdog loop — monitors all enabled strategies."""
    import asyncio

    from apps.strategies.models import StrategyState
    from apps.credentials.models import Exchange
    from apps.exchange.tabdeal_futures import TabdealFuturesClient

    logger.info("watchdog starting: interval=%.1fs", interval_s)

    while True:
        try:
            # Find all live strategies on Tabdeal
            states = (
                StrategyState.objects.select_related("strategy", "strategy__credential")
                .filter(live_started_at__isnull=False)
            )
            for st in states:
                strat = st.strategy
                if not strat.credential or strat.credential.exchange != Exchange.TABDEAL:
                    continue
                try:
                    client = TabdealFuturesClient(strat.credential)
                    monitor = WatchdogMonitor(strat.pk, client)
                    tier, detail = monitor.check()
                    monitor.execute(tier, detail)
                except Exception:
                    logger.exception("watchdog check failed for strategy %s", strat.pk)
        except Exception:
            logger.exception("watchdog loop error")

        await asyncio.sleep(interval_s)
