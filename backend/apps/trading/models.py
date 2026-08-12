"""Trades and per-account legs (spec §8 trade history)."""

from __future__ import annotations

from django.db import models

from apps.accounts.models import ConnectedAccount


class KillSwitch(models.Model):
    """Spec §7: the platform-wide emergency halt, as a row rather than a redeploy.

    ``STOP_ALL=true`` in the environment pins it on and the API cannot turn it
    off — a deployment-level halt must not be clearable from a browser. This row
    is the runtime half: the admin flips it from the panel and new routing stops
    on the next order. Closing and amending open positions keep working, which
    is the point (see ``apps.trading.killswitch``).
    """

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1)
    stop_all = models.BooleanField(default=False)
    reason = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    #: Username, not a FK: this row outlives the account that set it and is read
    #: on the routing path, where a join is pure cost.
    updated_by = models.CharField(max_length=150, blank=True)

    def __str__(self) -> str:
        return f"stop_all={self.stop_all}"


class TradeStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class Trade(models.Model):
    """One admin action, fanned out to many accounts."""

    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=8)
    market = models.CharField(max_length=10, default="futures")
    leverage = models.PositiveSmallIntegerField(default=1)
    sl_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    tp_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    # The basis in force when this trade was opened (Q5a). Recorded per trade so
    # history stays interpretable if the setting is ever changed.
    sltp_basis = models.CharField(max_length=10, default="price")
    admin_entry_price = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    status = models.CharField(max_length=8, choices=TradeStatus.choices, default=TradeStatus.OPEN)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    fanout_ms = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"{self.symbol} {self.side} x{self.leverage} ({self.status})"


class TradeLeg(models.Model):
    """One account's participation. Spec §8 wants pair, time and PnL per account."""

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="legs")
    account = models.ForeignKey(
        ConnectedAccount, on_delete=models.CASCADE, related_name="trade_legs"
    )

    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    dispatch_ms = models.FloatField(null=True, blank=True)

    qty = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    entry_price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    exit_price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    margin = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    # False means the entry filled but SL/TP did not attach (Q5e).
    sltp_attached = models.BooleanField(default=False)
    pnl = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)

    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["trade", "account"], name="one_leg_per_account")
        ]

    def __str__(self) -> str:
        return f"{self.account.label}: {self.trade.symbol}"
