from django.conf import settings
from django.db import models


class PaperAccount(models.Model):
  user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="paper_accounts")
  strategy = models.ForeignKey("strategies.Strategy", on_delete=models.CASCADE, related_name="paper_accounts")
  balance = models.DecimalField(max_digits=24, decimal_places=8, default=10_000)
  equity = models.DecimalField(max_digits=24, decimal_places=8, default=10_000)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)


class PaperTrade(models.Model):
  account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE, related_name="trades")
  side = models.CharField(max_length=8)
  entry_price = models.DecimalField(max_digits=24, decimal_places=8)
  exit_price = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
  size = models.DecimalField(max_digits=24, decimal_places=8)
  pnl = models.DecimalField(max_digits=24, decimal_places=8, default=0)
  entry_bar = models.IntegerField(default=0)
  exit_bar = models.IntegerField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
