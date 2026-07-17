"""Copy-trading domain: subscriptions, signals, mirrored positions, fees, and order tracking.

An admin publishes a master ``Strategy``; investors create a ``Subscription``
pointing at their own exchange ``ExchangeCredential``. When the master's live
runner emits an entry/close, a ``CopySignal`` is recorded and fanned out to
each active subscription, sized from the investor's own balance and risk.
Realized profit on closes accrues a platform fee into ``FeeLedger`` using a
per-subscription high-water mark.

Also supports Tabdeal-based copy trading with CopyOrder, CopyTrade,
EquitySnapshot, and FeeLedgerEntry models.
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
    """A signal source broadcast to N investors.

    For Hyperliquid: a directional event emitted by a master strategy's live runner.
    For Tabdeal: bound to an admin ``Strategy`` (the internal Pine engine is the
    source). The optional ``secret_token`` also allows an inbound-webhook trigger later.
    """

    class Action(models.TextChoices):
        ENTRY = "entry", "Entry"
        CLOSE = "close", "Close"

    class Direction(models.TextChoices):
        LONG = "long", "Long"
        SHORT = "short", "Short"
        NONE = "", "None"

    # Hyperliquid fields
    master_strategy = models.ForeignKey(
        "strategies.Strategy", on_delete=models.CASCADE, related_name="copy_signals",
        null=True, blank=True,
    )
    action = models.CharField(max_length=8, choices=Action.choices, blank=True, default="")
    direction = models.CharField(
        max_length=8, choices=Direction.choices, blank=True, default=""
    )
    coin = models.CharField(max_length=32, blank=True, default="")
    price = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    ts = models.BigIntegerField(help_text="Bar timestamp (ms).", null=True, blank=True)

    # Tabdeal fields
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_signals"
    )
    strategy = models.OneToOneField(
        "strategies.Strategy",
        on_delete=models.CASCADE,
        related_name="copy_signal",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=64)
    secret_token = models.CharField(max_length=64, unique=True, db_index=True)
    default_position_size_pct = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    platform_share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or f"{self.action} {self.direction} {self.coin}@{self.price}"


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


class CopySubscription(models.Model):
    """Links one investor's ExchangeCredential to a CopySignal."""

    signal = models.ForeignKey(CopySignal, on_delete=models.CASCADE, related_name="subscriptions")
    credential = models.ForeignKey(
        "credentials.ExchangeCredential", on_delete=models.CASCADE, related_name="copy_subscriptions"
    )
    position_size_pct_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    risk_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    high_water_mark = models.DecimalField(
        max_digits=24,
        decimal_places=8,
        default=0,
        help_text="Cumulative realized profit peak; performance fee is charged only above this.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["signal", "credential"], name="uniq_signal_credential"
            )
        ]
        indexes = [models.Index(fields=["signal", "is_active"])]

    def __str__(self):
        return f"{self.credential} -> {self.signal}"


class CopyOrder(models.Model):
    """Order lifecycle record for copy-trading, parallel to execution.OrderRecord."""

    class Side(models.TextChoices):
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"

    subscription = models.ForeignKey(
        CopySubscription, on_delete=models.CASCADE, related_name="orders"
    )
    exchange_order_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    client_order_id = models.CharField(max_length=64, blank=True, default="")
    pair = models.CharField(max_length=32)
    side = models.CharField(max_length=8, choices=Side.choices)
    order_type = models.CharField(max_length=16, default="market")
    size = models.DecimalField(max_digits=24, decimal_places=8)
    price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    status = models.CharField(max_length=24, default="pending")
    filled_size = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    avg_fill_price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["subscription", "created_at"])]

    def __str__(self):
        return f"{self.side} {self.size} {self.pair} [{self.status}]"


class CopyTrade(models.Model):
    """One round-trip trade (entry -> exit) for a subscription, with the platform's PnL share."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    subscription = models.ForeignKey(CopySubscription, on_delete=models.CASCADE, related_name="trades")
    entry_order = models.ForeignKey(CopyOrder, on_delete=models.CASCADE, related_name="+")
    exit_order = models.ForeignKey(
        CopyOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    gross_pnl = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    platform_share_amount = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["subscription", "status"])]

    def __str__(self):
        return f"CopyTrade #{self.pk} [{self.status}]"


class EquitySnapshot(models.Model):
    """Point-in-time balance/equity reading for a subscription, for equity-curve charts."""

    subscription = models.ForeignKey(
        CopySubscription, on_delete=models.CASCADE, related_name="equity_snapshots"
    )
    balance = models.DecimalField(max_digits=24, decimal_places=8)
    equity = models.DecimalField(max_digits=24, decimal_places=8)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["subscription", "captured_at"])]

    def __str__(self):
        return f"{self.subscription} @ {self.captured_at}"


class PlatformFeeConfig(models.Model):
    """Admin-configured destination + rate for collected performance fees.

    "20% of the profit should come to the account I enter in my panel."
    Collection is ledger/accrual (trade-only keys can't move funds on-chain).
    """

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fee_config"
    )
    share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    destination_exchange = models.CharField(max_length=16, default="tabdeal")
    destination_account = models.CharField(
        max_length=128, blank=True, default="", help_text="Wallet/account the platform's share is owed to."
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FeeConfig({self.owner} @ {self.share_pct}%)"


class FeeLedgerEntry(models.Model):
    """One accrual of the platform's performance-fee share for a closed trade."""

    class Status(models.TextChoices):
        ACCRUED = "accrued", "Accrued"
        SETTLED = "settled", "Settled"

    subscription = models.ForeignKey(
        CopySubscription, on_delete=models.CASCADE, related_name="fee_entries"
    )
    trade = models.ForeignKey(
        CopyTrade, on_delete=models.CASCADE, related_name="fee_entries", null=True, blank=True
    )
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACCRUED)
    accrued_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["subscription", "status"])]

    def __str__(self):
        return f"Fee {self.amount} [{self.status}]"
