"""Watchdog models — §6.2: configuration and action log."""
from __future__ import annotations

from django.db import models


class WatchdogConfig(models.Model):
    """Per-strategy watchdog configuration.

    sensible defaults match §6.2:
    - T_self = 5000ms (5s): heartbeat gap before Tier 1.
    - T_dead = 15000ms (15s): heartbeat gap before Tier 2.
    - max_blind_hold = 3 bars: max bars to hold with SL before forced flatten.
    - poll_interval = 5s: how often watchdog checks position state.
    """
    strategy_id = models.PositiveIntegerField(unique=True, db_index=True)
    t_self_ms = models.PositiveIntegerField(default=5000, help_text="Tier 1 threshold (ms)")
    t_dead_ms = models.PositiveIntegerField(default=15000, help_text="Tier 2 threshold (ms)")
    max_blind_hold = models.PositiveIntegerField(default=3, help_text="Max bars to hold blind")
    poll_interval_s = models.PositiveIntegerField(default=5, help_text="Position poll interval (s)")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "watchdog"

    def __str__(self):
        return f"WatchdogConfig(strategy={self.strategy_id}, enabled={self.enabled})"


class WatchdogAction(models.Model):
    """Append-only log of watchdog actions (§6.2 — audit trail)."""

    class Tier(models.IntegerChoices):
        TIER_1 = 1, "Tier 1 — SL attach"
        TIER_2 = 2, "Tier 2 — Position protection"
        TIER_3 = 3, "Tier 3 — Kill switch"

    class ActionType(models.TextChoices):
        SL_ATTACHED = "sl_attached", "SL Attached"
        POSITION_FLAT = "position_flat", "Position Flattened"
        KILL_SWITCH = "kill_switch", "Kill Switch Activated"
        HEARTBEAT_MISS = "heartbeat_miss", "Heartbeat Miss"
        HEARTBEAT_RECOVER = "heartbeat_recover", "Heartbeat Recovered"
        POSITION_GUARDIAN = "position_guardian", "Position Guardian Check"

    strategy_id = models.PositiveIntegerField(db_index=True)
    tier = models.PositiveSmallIntegerField(choices=Tier.choices)
    action_type = models.CharField(max_length=32, choices=ActionType.choices)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "watchdog"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[T{self.tier}] {self.action_type} strategy={self.strategy_id}"
