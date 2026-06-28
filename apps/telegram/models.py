from django.conf import settings
from django.db import models


class TelegramConfig(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_config",
    )
    bot_token = models.CharField(
        max_length=128, blank=True, default="", help_text="Telegram Bot API token"
    )
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"telegram<{self.user_id}>"


class AlertWhitelist(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_whitelist",
    )
    chat_id = models.BigIntegerField(help_text="Telegram Chat ID (user or group)")
    label = models.CharField(
        max_length=64, blank=True, default="", help_text="Friendly label for this chat"
    )
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "chat_id")]
        verbose_name = "Alert Whitelist Entry"
        verbose_name_plural = "Alert Whitelist Entries"

    def __str__(self):
        return f"whitelist<{self.chat_id}>"
