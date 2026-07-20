"""Watchdog tiers — §6.2/6.3/6.4/6.5: response logic.

The watchdog cannot open a position — no code path exists (§6.7).
Only close/flatten. Own API key with close-only permissions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .models import WatchdogAction

logger = logging.getLogger(__name__)


@dataclass
class TierDecision:
    """What the watchdog should do at each tier."""
    tier: int
    action: str
    reason: str
    should_flatten: bool
    should_attach_sl: bool
    should_kill_switch: bool


def evaluate_tier(
    *,
    heartbeat_gap_ms: int,
    t_self_ms: int,
    t_dead_ms: int,
    sl_confirmed: bool,
    bars_since_halt: int,
    max_blind_hold: int,
    daily_loss_breached: bool,
) -> TierDecision:
    """§6.2: Determine the response tier based on heartbeat and position state.

    Args:
        heartbeat_gap_ms: ms since last heartbeat from Node B.
        t_self_ms: Tier 1 threshold (slow B).
        t_dead_ms: Tier 2 threshold (dead B).
        sl_confirmed: True if SL is confirmed attached.
        bars_since_halt: bars elapsed since first heartbeat miss.
        max_blind_hold: max bars to hold blind before forced flatten.
        daily_loss_breached: True if daily loss limit hit (§6.5).
    """
    # Tier 3: daily loss breach → flatten + kill switch (§6.5)
    if daily_loss_breached:
        return TierDecision(
            tier=3,
            action="kill_switch",
            reason="daily_loss_breach",
            should_flatten=True,
            should_attach_sl=False,
            should_kill_switch=True,
        )

    # Tier 2: B is dead (§6.4)
    if heartbeat_gap_ms >= t_dead_ms:
        if not sl_confirmed:
            # Naked position → flatten immediately
            return TierDecision(
                tier=2,
                action="flatten_naked",
                reason="dead_no_sl",
                should_flatten=True,
                should_attach_sl=False,
                should_kill_switch=False,
            )
        if bars_since_halt >= max_blind_hold:
            # Exceeded blind hold budget → flatten
            return TierDecision(
                tier=2,
                action="flatten_exceeded",
                reason="dead_exceeded_blind_hold",
                should_flatten=True,
                should_attach_sl=False,
                should_kill_switch=False,
            )
        # SL confirmed, within budget → hold
        return TierDecision(
            tier=2,
            action="hold_protected",
            reason="dead_sl_within_budget",
            should_flatten=False,
            should_attach_sl=False,
            should_kill_switch=False,
        )

    # Tier 1: B is slow (§6.3)
    if heartbeat_gap_ms >= t_self_ms:
        if not sl_confirmed:
            # Attach SL — do NOT close position
            return TierDecision(
                tier=1,
                action="attach_sl",
                reason="slow_no_sl",
                should_flatten=False,
                should_attach_sl=True,
                should_kill_switch=False,
            )
        # SL already attached → monitor
        return TierDecision(
            tier=1,
            action="monitor",
            reason="slow_sl_attached",
            should_flatten=False,
            should_attach_sl=False,
            should_kill_switch=False,
        )

    # Healthy
    return TierDecision(
        tier=0,
        action="healthy",
        reason="heartbeat_ok",
        should_flatten=False,
        should_attach_sl=False,
        should_kill_switch=False,
    )


def log_action(
    strategy_id: int,
    tier: int,
    action_type: str,
    detail: dict | None = None,
) -> WatchdogAction:
    """Append an action to the audit trail."""
    return WatchdogAction.objects.create(
        strategy_id=strategy_id,
        tier=tier,
        action_type=action_type,
        detail=detail or {},
    )
