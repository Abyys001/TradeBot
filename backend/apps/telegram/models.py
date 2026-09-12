"""The Telegram notifier's one row.

A singleton for the same reason ``SecurityPolicy`` and ``KillSwitch`` are: there
is exactly one bot and one recipient (Q36), so a table with one row is the whole
model. Two writers touch it — the Settings card and the ``run_telegram``
service — and they own disjoint fields: the card writes settings with
``save(update_fields=...)`` and the service writes its cursor, offset and health
with queryset ``update()``, so neither can overwrite the other's change with a
stale copy.

The bot token is a credential like an exchange key: Fernet ciphertext at rest,
never logged, never returned over HTTP — only its fingerprint and the bot's
public username are.
"""

from __future__ import annotations

from django.db import models

from apps.core import crypto
from apps.telegram.events import GROUPS


class Language(models.TextChoices):
    EN = "en", "English"
    FA = "fa", "Persian"


def _all_groups() -> list[str]:
    return list(GROUPS)


class TelegramBot(models.Model):
    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1)

    #: The master switch. Only true while a token is stored and a chat linked.
    enabled = models.BooleanField(default=False)

    token_encrypted = models.TextField(blank=True)
    token_fingerprint = models.CharField(max_length=16, blank=True)
    #: The bot's own @name, from ``getMe`` — public, and what the deep link needs.
    bot_username = models.CharField(max_length=64, blank=True)

    #: Who may link, without the ``@``. The Bot API cannot message a username,
    #: only a chat id, so this is checked against the ``/start`` that links.
    recipient_username = models.CharField(max_length=64, blank=True)
    chat_id = models.BigIntegerField(null=True, blank=True)
    #: SHA-256 of the one-time deep-link code. Never the code itself.
    link_code_hash = models.CharField(max_length=64, blank=True)
    link_code_expires_at = models.DateTimeField(null=True, blank=True)

    language = models.CharField(max_length=2, choices=Language.choices, default=Language.EN)
    groups = models.JSONField(default=_all_groups)

    # --- the service's fields ------------------------------------------------
    #: Last ``LogEntry.id`` delivered or passed over. Null means "start at the
    #: head", which is what enabling sets, so switching on never replays history.
    log_cursor = models.BigIntegerField(null=True, blank=True)
    #: ``getUpdates`` offset: the next update id to ask for.
    update_offset = models.BigIntegerField(default=0)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    #: Username, not a FK — this row outlives the account that wrote it.
    updated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name_plural = "telegram bot"

    def __str__(self) -> str:
        return "telegram bot"

    @classmethod
    def load(cls) -> TelegramBot:
        return cls.objects.get_or_create(singleton=1)[0]

    @property
    def token(self) -> str:
        return crypto.decrypt(self.token_encrypted)

    @property
    def configured(self) -> bool:
        return bool(self.token_encrypted)

    @property
    def linked(self) -> bool:
        return self.chat_id is not None

    def set_token(self, plaintext: str) -> None:
        self.token_encrypted = crypto.encrypt(plaintext)
        self.token_fingerprint = crypto.fingerprint(plaintext)
