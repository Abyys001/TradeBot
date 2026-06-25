from django.conf import settings
from django.db import models


class StrategyVersion(models.Model):
    strategy = models.ForeignKey("strategies.Strategy", on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    source = models.TextField()
    params = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("strategy", "version")
        ordering = ["-version"]


class TradeJournal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal_entries")
    strategy = models.ForeignKey("strategies.Strategy", on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=128)
    body = models.TextField(blank=True, default="")
    tags = models.JSONField(default=list, blank=True)
    screenshot_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class MarketplacePackage(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="packages")
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    source = models.TextField()
    params = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ReplaySession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="replay_sessions")
    coin = models.CharField(max_length=32)
    interval = models.CharField(max_length=16)
    network = models.CharField(max_length=16, default="mainnet")
    cursor_bar = models.IntegerField(default=0)
    speed = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)
