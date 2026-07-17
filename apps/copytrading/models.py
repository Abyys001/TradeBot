"""Copy-trading domain: subscriptions, signals, mirrored positions, fees.

An admin publishes a master ``Strategy``; investors create a ``Subscription``
pointing at their own exchange ``ExchangeCredential``. When the master's live
runner emits an entry/close, a ``CopySignal`` is recorded and fanned out to
each active subscription, sized from the investor's own balance and risk.
Realized profit on closes accrues a platform fee into ``FeeLedger`` using a
per-subscription high-water mark.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class FeeConfig(models.Model):
    """Global platform fee configuration (single row)."""

    fee_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.20"),
        help_text="Fraction of new profit taken as platform fee (0.20 = 20%).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls) -> "FeeConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"FeeConfig(rate={self.fee_rate})"


class Subscription(models.Model):
    """An investor mirroring a master strategy onto their own account."""

    class Sizing(models.TextChoices):
        RISK_PCT = "risk_pct", "Percent of balance"
        FIXED_NOTIONAL = "fixed_notional", "Fixed notional"

    investor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    master_strategy = models.ForeignKey(
        "strategies.Strategy",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    credential = models.ForeignKey(
        "credentials.ExchangeCredential",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    sizing_mode = models.CharField(
        max_length=16, choices=Sizing.choices, default=Sizing.RISK_PCT
    )
    risk_pct = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("1.0"),
        help_text="Percent of account balance per trade (risk_pct mode).",
    )
    fixed_notional = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal("0"),
        help_text="Quote-currency notional per trade (fixed_notional mode).",
    )
    leverage = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["investor", "master_strategy"],
                name="uniq_investor_master",
            )
        ]

    def __str__(self):
        return f"{self.investor} → {self.master_strategy_id}"


class CopySignal(models.Model):
    """A directional event emitted by a master strategy's live runner."""

    class Action(models.TextChoices):
        ENTRY = "entry", "Entry"
        CLOSE = "close", "Close"

    class Direction(models.TextChoices):
        LONG = "long", "Long"
        SHORT = "short", "Short"
        NONE = "", "None"

    master_strategy = models.ForeignKey(
        "strategies.Strategy", on_delete=models.CASCADE, related_name="copy_signals"
    )
    action = models.CharField(max_length=8, choices=Action.choices)
    direction = models.CharField(
        max_length=8, choices=Direction.choices, blank=True, default=""
    )
    coin = models.CharField(max_length=32)
    price = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    ts = models.BigIntegerField(help_text="Bar timestamp (ms).")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} {self.direction} {self.coin}@{self.price}"


class InvestorPosition(models.Model):
    """One open mirrored position per (subscription, coin)."""

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="positions"
    )
    coin = models.CharField(max_length=32)
    size = models.DecimalField(
        max_digits=24, decimal_places=8, help_text="Signed: + long, - short."
    )
    entry_price = models.DecimalField(max_digits=24, decimal_places=8)
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "coin"], name="uniq_subscription_coin"
            )
        ]

    def __str__(self):
        return f"{self.subscription_id} {self.coin} {self.size}"


class FeeLedger(models.Model):
    """Per-subscription cumulative realized PnL, high-water mark, accrued fee."""

    subscription = models.OneToOneField(
        Subscription, on_delete=models.CASCADE, related_name="fee_ledger"
    )
    realized_pnl = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    high_water_mark = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    fee_accrued = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    fee_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.20")
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ledger<{self.subscription_id}> hwm={self.high_water_mark}"
