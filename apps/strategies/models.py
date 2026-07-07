from django.conf import settings
from django.db import models


class Strategy(models.Model):
    """A user's trading strategy configuration.

    Phase 1 defines the schema only — the execution engine that reads `params`
    and drives orders is a later phase.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        STOPPED = "stopped", "Stopped"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="strategies"
    )
    credential = models.ForeignKey(
        "credentials.ExchangeCredential",
        on_delete=models.PROTECT,
        related_name="strategies",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=128)
    type = models.CharField(max_length=64, help_text="Strategy type identifier.")
    symbol = models.CharField(max_length=32, help_text="HL coin e.g. BTC, ETH")

    class MarketType(models.TextChoices):
        PERP = "perp", "Perpetual"
        SPOT = "spot", "Spot"

    market_type = models.CharField(
        max_length=8,
        choices=MarketType.choices,
        default=MarketType.PERP,
    )
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    # Pine Script v5 source + last compile result (Phase 2 transpiler).
    source = models.TextField(blank=True, default="")
    validation_status = models.CharField(
        max_length=16, blank=True, default="", help_text="ok | error"
    )
    validation_error = models.TextField(blank=True, default="")
    timeframe = models.CharField(max_length=16, default="1m")
    warmup_bars = models.PositiveIntegerField(default=200)
    live_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Operational config: symbols[], timeframes[], risk{}.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "strategies"

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class StrategyState(models.Model):
    """Mutable runtime state for a strategy. One-to-one with Strategy."""

    strategy = models.OneToOneField(
        Strategy, on_delete=models.CASCADE, related_name="state"
    )
    position = models.JSONField(default=dict, blank=True)
    last_signal = models.CharField(max_length=64, blank=True, default="")
    pnl = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    live_started_at = models.DateTimeField(null=True, blank=True)
    last_bar_ts = models.BigIntegerField(null=True, blank=True)
    live_error = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"state<{self.strategy_id}>"
