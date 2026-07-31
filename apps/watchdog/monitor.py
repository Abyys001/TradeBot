"""Watchdog monitor — §6.2: heartbeat monitor + tiered response.

Reads heartbeat from Redis, evaluates tier, executes actions via the
exchange client.  Runs as a loop in the watchdog process.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from django.core.cache import cache

from .models import WatchdogConfig, WatchdogAction
from .tiers import evaluate_tier, log_action
from .guardian import check_position, GuardianCheck

logger = logging.getLogger(__name__)

_DEFAULT_SL_PCT = 10.0


@dataclass
class MonitorState:
    """Per-strategy monitoring state."""
    strategy_id: int
    last_heartbeat_ts: float
    bars_since_halt: int
    sl_confirmed: bool
    current_tier: int
    daily_loss_breached: bool
    guardian: GuardianCheck | None = None
    symbol: str = ""


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
        self._strategy = None

    # ----- helpers -----

    def _get_strategy(self):
        if self._strategy is None:
            from apps.strategies.models import Strategy
            self._strategy = Strategy.objects.get(pk=self.strategy_id)
        return self._strategy

    def _get_symbol(self) -> str:
        if not self.state.symbol:
            self.state.symbol = self._get_strategy().symbol
        return self.state.symbol

    def _get_risk_config(self) -> dict:
        try:
            return self._get_strategy().live_config.get("risk", {})
        except Exception:
            return {}

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

    # ----- guardian integration -----

    def _run_guardian(self) -> GuardianCheck:
        """Poll the exchange for actual position state."""
        symbol = self._get_symbol()
        risk = self._get_risk_config()
        has_sl_configured = bool(risk.get("global_stop_loss_pct"))
        return check_position(
            exchange_client=self.client,
            symbol=symbol,
            expected_has_sl=has_sl_configured,
            sl_confirmed=self.state.sl_confirmed,
        )

    # ----- check -----

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

        # Guardian: poll exchange for actual SL status (§6.6).
        guardian_result = None
        sl_confirmed = False
        try:
            guardian_result = self._run_guardian()
            self.state.guardian = guardian_result
            if guardian_result.ok and guardian_result.position:
                sl_confirmed = guardian_result.position.has_sl
        except Exception:
            logger.exception("guardian check failed for strategy %s", self.strategy_id)

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

    # ----- execution (exchange calls) -----

    def execute(self, tier: int, detail: dict) -> None:
        """Execute the tier decision actions — calls the exchange."""
        if detail.get("action") == "disabled":
            return

        if detail.get("action") == "healthy":
            if self.state.current_tier > 0:
                log_action(self.strategy_id, 0, WatchdogAction.ActionType.HEARTBEAT_RECOVER, detail)
                logger.info("watchdog %s: heartbeat recovered", self.strategy_id)
            return

        if detail.get("should_attach_sl"):
            self._execute_attach_sl(tier, detail)

        # Kill switch includes flatten internally — skip separate flatten call.
        if detail.get("should_kill_switch"):
            self._execute_kill_switch(tier, detail)
        elif detail.get("should_flatten"):
            self._execute_flatten(tier, detail)

    def _execute_attach_sl(self, tier: int, detail: dict) -> None:
        """Attach SL to the current position (§6.3)."""
        symbol = self._get_symbol()
        risk = self._get_risk_config()
        sl_pct = risk.get("global_stop_loss_pct", _DEFAULT_SL_PCT)

        # Read actual position from exchange.
        position = self.state.guardian.position if self.state.guardian and self.state.guardian.ok else None
        if position is None:
            try:
                pos_raw = self.client.get_position(symbol)
                if pos_raw is None:
                    log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED,
                               {**detail, "error": "no_position"})
                    logger.warning("watchdog %s: T%d no position to attach SL to", self.strategy_id, tier)
                    return
                amt = float(pos_raw.get("positionAmt", 0))
                entry = float(pos_raw.get("entryPrice", 0))
            except Exception as exc:
                log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED,
                           {**detail, "error": str(exc)})
                logger.error("watchdog %s: T%d failed to read position: %s", self.strategy_id, tier, exc)
                return
        else:
            amt = position.size if position.side != "NONE" else 0
            if position.side == "SHORT":
                amt = -amt
            entry = position.entry_price

        if amt == 0:
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED,
                       {**detail, "error": "zero_position"})
            logger.warning("watchdog %s: T%d zero position, skipping SL", self.strategy_id, tier)
            return

        # Compute SL price.
        is_long = amt > 0
        if is_long:
            sl_price = round(entry * (1 - sl_pct / 100), 8)
        else:
            sl_price = round(entry * (1 + sl_pct / 100), 8)

        # Get internal position ID for SL endpoint.
        try:
            position_id = self.client.get_open_position_id(symbol)
            if position_id is None:
                log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED,
                           {**detail, "error": "no_position_id"})
                logger.error("watchdog %s: T%d no position ID for SL", self.strategy_id, tier)
                return
        except Exception as exc:
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED,
                       {**detail, "error": str(exc)})
            logger.error("watchdog %s: T%d failed to get position ID: %s", self.strategy_id, tier, exc)
            return

        # Attach SL.
        try:
            self.client.set_position_sl_tp(position_id=position_id, sl_price=sl_price, symbol=symbol)
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED,
                       {**detail, "sl_price": sl_price, "position_id": position_id, "side": "long" if is_long else "short"})
            logger.warning("watchdog %s: T%d SL attached at %.8f (%s)", self.strategy_id, tier, sl_price, symbol)
            self.state.sl_confirmed = True
        except Exception as exc:
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.SL_ATTACHED,
                       {**detail, "error": str(exc), "sl_price": sl_price})
            logger.error("watchdog %s: T%d failed to attach SL: %s", self.strategy_id, tier, exc)

    def _execute_flatten(self, tier: int, detail: dict) -> None:
        """Market-close the entire position (§6.4)."""
        symbol = self._get_symbol()
        try:
            result = self.client.close_position(symbol)
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.POSITION_FLAT,
                       {**detail, "result": result})
            logger.warning("watchdog %s: T%d position flattened on %s", self.strategy_id, tier, symbol)
        except Exception as exc:
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.POSITION_FLAT,
                       {**detail, "error": str(exc)})
            logger.error("watchdog %s: T%d failed to flatten: %s", self.strategy_id, tier, exc)

    def _execute_kill_switch(self, tier: int, detail: dict) -> None:
        """Flatten position + disable user trading (§6.5)."""
        # Flatten first.
        self._execute_flatten(tier, detail)

        # Disable the user's trading.
        try:
            strategy = self._get_strategy()
            user = strategy.user
            if user.is_trading_enabled:
                user.is_trading_enabled = False
                user.save(update_fields=["is_trading_enabled"])
                log_action(self.strategy_id, tier, WatchdogAction.ActionType.KILL_SWITCH,
                           {**detail, "user_id": user.pk, "trading_disabled": True})
                logger.critical("watchdog %s: T%d kill switch — user %s trading disabled",
                                self.strategy_id, tier, user.pk)
            else:
                log_action(self.strategy_id, tier, WatchdogAction.ActionType.KILL_SWITCH,
                           {**detail, "user_id": user.pk, "trading_disabled": True})
        except Exception as exc:
            log_action(self.strategy_id, tier, WatchdogAction.ActionType.KILL_SWITCH,
                       {**detail, "error": str(exc)})
            logger.error("watchdog %s: T%d failed to disable user trading: %s", self.strategy_id, tier, exc)


async def run_watchdog(interval_s: float = 5.0) -> None:
    """Main watchdog loop — monitors all enabled strategies."""
    import asyncio

    from apps.strategies.models import StrategyState
    from apps.credentials.models import Exchange
    from apps.exchange.tabdeal_futures import TabdealFuturesClient

    from asgiref.sync import sync_to_async

    logger.info("watchdog starting: interval=%.1fs", interval_s)

    def _tick() -> None:
        """One sweep. Sync: the ORM and the exchange client both block."""
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

    while True:
        try:
            await sync_to_async(_tick, thread_sensitive=True)()
        except Exception:
            logger.exception("watchdog loop error")

        await asyncio.sleep(interval_s)
