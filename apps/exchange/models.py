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


class RecordedSymbol(models.Model):
    """A market the ingest nodes should be recording.

    Source of truth for what gets recorded. ``TABDEAL_INGEST_SYMBOLS`` only seeds
    this table on first run, so symbols can be added from the dashboard without a
    container restart — which matters because recording is the long pole: history
    only exists from the moment a symbol is switched on.
    """

    symbol = models.CharField(
        max_length=32, unique=True, help_text="Ledger symbol, e.g. BTC_USDT."
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether ingest should currently record this market."
    )
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]

    def __str__(self):
        return f"{self.symbol}{'' if self.is_active else ' (paused)'}"

    @classmethod
    def active_symbols(cls) -> list[str]:
        """Symbols to record, seeding from settings the first time."""
        from django.conf import settings

        try:
            rows = list(cls.objects.filter(is_active=True).values_list("symbol", flat=True))
            if rows:
                return rows
            if cls.objects.exists():
                return []  # deliberately all paused — not an empty-table seed
        except Exception:  # noqa: BLE001 — no DB yet (migrate, collectstatic)
            pass
        return list(getattr(settings, "TABDEAL_INGEST_SYMBOLS", ["BTC_USDT"]))


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
    # Provenance (§3.2 invariant 1): a bar built from partial ingest coverage must
    # stay identifiable after the fact, or a backtest silently trusts bad data.
    quality = models.CharField(
        max_length=8,
        default="CLEAN",
        help_text="CLEAN | FLAT | SUSPECT | MISSING — see apps.exchange.data_quality.",
    )
    trade_count = models.PositiveIntegerField(
        default=0, help_text="Raw trades folded into this bar (0 == FLAT)."
    )

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
