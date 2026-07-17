from django.db import models


class OrderRecord(models.Model):
    """Persisted record of an order sent to / reported by the exchange."""

    class Side(models.TextChoices):
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"

    strategy = models.ForeignKey(
        "strategies.Strategy", on_delete=models.CASCADE, related_name="orders"
    )
    exchange_order_id = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    client_order_id = models.CharField(max_length=64, blank=True, default="")
    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=8, choices=Side.choices)
    order_type = models.CharField(max_length=16, help_text="market, limit, ...")
    size = models.DecimalField(max_digits=24, decimal_places=8)
    price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    status = models.CharField(max_length=24, default="pending")
    filled_size = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    avg_fill_price = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    raw = models.JSONField(default=dict, blank=True, help_text="Raw exchange payload.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["strategy", "created_at"])]

    def __str__(self):
        return f"{self.side} {self.size} {self.symbol} [{self.status}]"


class ExecutionLog(models.Model):
    """Append-only audit trail of execution events."""

    class Level(models.TextChoices):
        DEBUG = "debug", "Debug"
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    strategy = models.ForeignKey(
        "strategies.Strategy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    event = models.CharField(max_length=128)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["strategy", "created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.level}] {self.event}"
