"""Signum webhook integration models."""
from django.conf import settings
from django.db import models

from apps.credentials.crypto import decrypt, encrypt


class SignumConfig(models.Model):
    """Per-user Signum bot credentials (encrypted at rest)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signum_config",
    )
    bot_id_enc = models.BinaryField(blank=True, default=b"")
    webhook_url_enc = models.BinaryField(blank=True, default=b"")
    order_size_default = models.CharField(max_length=32, default="80%")
    enabled = models.BooleanField(default=False)
    use_settings_bot_id = models.BooleanField(
        default=True,
        help_text="When true, override Pine input bot_id with stored secret.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_bot_id(self, bot_id: str) -> None:
        self.bot_id_enc = encrypt(bot_id.strip()) if bot_id else b""

    def get_bot_id(self) -> str:
        if not self.bot_id_enc:
            return ""
        return decrypt(bytes(self.bot_id_enc))

    def set_webhook_url(self, url: str) -> None:
        self.webhook_url_enc = encrypt(url.strip()) if url else b""

    def get_webhook_url(self) -> str:
        if not self.webhook_url_enc:
            return ""
        return decrypt(bytes(self.webhook_url_enc))

    def __str__(self):
        return f"SignumConfig<{self.user_id}>"


class TelegramConfig(models.Model):
    """Per-user Telegram bot credentials (encrypted at rest).

    Sends trade/fill/error notifications via the Telegram Bot API
    (``sendMessage``). Complements Signum; both can be enabled independently.
    """

    class Event(models.TextChoices):
        TRADE = "trade", "Trade signals"
        FILL = "fill", "Order fills"
        ERROR = "error", "Errors"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_config",
    )
    bot_token_enc = models.BinaryField(blank=True, default=b"")
    chat_id = models.CharField(
        max_length=64, blank=True, default="", help_text="Target chat/channel id."
    )
    events = models.JSONField(
        default=list,
        blank=True,
        help_text="Subscribed event types (subset of Event choices).",
    )
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_bot_token(self, token: str) -> None:
        self.bot_token_enc = encrypt(token.strip()) if token else b""

    def get_bot_token(self) -> str:
        if not self.bot_token_enc:
            return ""
        return decrypt(bytes(self.bot_token_enc))

    def wants(self, event: str) -> bool:
        """True if this event should be delivered (empty events = all)."""
        return not self.events or event in self.events

    def __str__(self):
        return f"TelegramConfig<{self.user_id}>"
