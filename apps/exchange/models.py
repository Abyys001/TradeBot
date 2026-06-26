from django.conf import settings
from django.db import models


class HistoryDownload(models.Model):
    """Async job downloading market history from Hyperliquid."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="history_downloads",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    network = models.CharField(max_length=16, default="mainnet")
    coins = models.JSONField(default=list)
    intervals = models.JSONField(default=list)
    data_types = models.JSONField(default=list)
    start_ms = models.BigIntegerField()
    end_ms = models.BigIntegerField()
    progress = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"HistoryDownload<{self.pk}> {self.status}"


class Candle(models.Model):
    """OHLCV candle stored in PostgreSQL (canonical source for queries)."""

    network = models.CharField(max_length=16, default="mainnet")
    asset = models.CharField(max_length=32)
    timeframe = models.CharField(max_length=8)
    timestamp = models.BigIntegerField()
    open = models.DecimalField(max_digits=24, decimal_places=8)
    high = models.DecimalField(max_digits=24, decimal_places=8)
    low = models.DecimalField(max_digits=24, decimal_places=8)
    close = models.DecimalField(max_digits=24, decimal_places=8)
    volume = models.DecimalField(max_digits=24, decimal_places=8)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["network", "asset", "timeframe", "timestamp"],
                name="uniq_candle_ntf_ts",
            )
        ]
        indexes = [
            models.Index(fields=["network", "asset", "timeframe", "timestamp"]),
        ]

    def __str__(self):
        return f"Candle<{self.asset}/{self.timeframe}@{self.timestamp}>"


class FundingRate(models.Model):
    """Funding-rate history."""

    network = models.CharField(max_length=16, default="mainnet")
    asset = models.CharField(max_length=32)
    timestamp = models.BigIntegerField()
    funding_rate = models.DecimalField(max_digits=24, decimal_places=12)
    premium = models.DecimalField(max_digits=24, decimal_places=12, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["network", "asset", "timestamp"],
                name="uniq_funding_nt_ts",
            )
        ]
        indexes = [
            models.Index(fields=["network", "asset", "timestamp"]),
        ]


class OpenInterest(models.Model):
    """Open-interest snapshots (built forward via scheduled polling)."""

    network = models.CharField(max_length=16, default="mainnet")
    asset = models.CharField(max_length=32)
    timestamp = models.BigIntegerField()
    value = models.DecimalField(max_digits=24, decimal_places=8)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["network", "asset", "timestamp"],
                name="uniq_oi_nt_ts",
            )
        ]
        indexes = [
            models.Index(fields=["network", "asset", "timestamp"]),
        ]
