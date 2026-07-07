from django.db import models


class Backtest(models.Model):
    """A backtest run of a strategy's Pine source over historical data."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    strategy = models.ForeignKey(
        "strategies.Strategy", on_delete=models.CASCADE, related_name="backtests"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    symbol = models.CharField(max_length=32)
    timeframe = models.CharField(max_length=16, blank=True, default="")
    network = models.CharField(max_length=16, default="mainnet")
    range_start = models.DateTimeField(null=True, blank=True)
    range_end = models.DateTimeField(null=True, blank=True)
    initial_balance = models.FloatField(default=10_000.0)
    metrics = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Backtest<{self.strategy_id}> {self.status}"


class BacktestTrade(models.Model):
    backtest = models.ForeignKey(
        Backtest, on_delete=models.CASCADE, related_name="trades"
    )
    side = models.CharField(max_length=8)
    entry_price = models.DecimalField(max_digits=24, decimal_places=8)
    exit_price = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    size = models.DecimalField(max_digits=24, decimal_places=8)
    pnl = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    gross_pnl = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    commission = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    entry_bar = models.IntegerField()
    exit_bar = models.IntegerField(null=True, blank=True)
    stop_px = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    limit_px = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True
    )
    exit_reason = models.CharField(max_length=16, blank=True, default="")
    entry_time = models.DateTimeField(null=True, blank=True)
    exit_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.side} pnl={self.pnl}"
