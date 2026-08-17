from django.db import models


class Level(models.TextChoices):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Category(models.TextChoices):
    TRADE = "TRADE"
    EXCHANGE = "EXCHANGE"
    SYSTEM = "SYSTEM"
    AUTH = "AUTH"
    MARKET_DATA = "MARKET_DATA"
    ENGINE = "ENGINE"
    ADMIN = "ADMIN"


class LogEntry(models.Model):
    id = models.BigAutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=8, choices=Level.choices)
    category = models.CharField(max_length=16, choices=Category.choices)
    source = models.CharField(max_length=200)
    message = models.TextField()
    account_id = models.IntegerField(null=True, blank=True)
    trade_id = models.IntegerField(null=True, blank=True)
    exchange = models.CharField(max_length=20, null=True, blank=True)
    error_code = models.CharField(max_length=60, null=True, blank=True)
    context = models.JSONField(null=True, blank=True)
    request_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["level", "timestamp"]),
            models.Index(fields=["category", "timestamp"]),
            models.Index(fields=["account_id", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"[{self.level}] {self.timestamp:%Y-%m-%d %H:%M:%S} {self.source}: {self.message[:80]}"
