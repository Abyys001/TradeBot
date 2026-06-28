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


class ReplaySession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="replay_sessions")
    coin = models.CharField(max_length=32)
    interval = models.CharField(max_length=16)
    network = models.CharField(max_length=16, default="mainnet")
    cursor_bar = models.IntegerField(default=0)
    speed = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)
