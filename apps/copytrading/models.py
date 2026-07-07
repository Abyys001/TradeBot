from django.conf import settings
from django.db import models


class CopySignal(models.Model):
    """A single inbound webhook source (one TradingView alert), broadcast to N investors."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_signals"
    )
    name = models.CharField(max_length=64)
    secret_token = models.CharField(max_length=64, unique=True, db_index=True)
    default_position_size_pct = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    platform_share_pct = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class CopySubscription(models.Model):
    """Links one investor's Tabdeal ExchangeCredential to a CopySignal."""

    signal = models.ForeignKey(CopySignal, on_delete=models.CASCADE, related_name="subscriptions")
    credential = models.ForeignKey(
        "credentials.ExchangeCredential", on_delete=models.CASCADE, related_name="copy_subscriptions"
    )
    position_size_pct_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    risk_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1)
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
