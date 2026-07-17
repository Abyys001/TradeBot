"""Telegram Bot API delivery for trade/fill/error notifications."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def get_telegram_config(user, *, require_enabled: bool = True):
    if user is None:
        return None
    from .models import TelegramConfig

    qs = TelegramConfig.objects.filter(user=user)
    if require_enabled:
        qs = qs.filter(enabled=True)
    return qs.first()


def send_telegram_message(user, text: str, *, event: str = "", force: bool = False) -> dict:
    """Send a message to the user's configured Telegram chat.

    Skips silently when Telegram is disabled/unconfigured or the event type is
    not subscribed (unless ``force`` — used by the "send test message" action).
    """
    cfg = get_telegram_config(user, require_enabled=not force)
    if cfg is None:
        return {"ok": False, "skipped": True, "reason": "telegram_disabled"}
    if event and not force and not cfg.wants(event):
        return {"ok": False, "skipped": True, "reason": "event_unsubscribed"}

    token = cfg.get_bot_token()
    if not token or not cfg.chat_id:
        return {"ok": False, "skipped": True, "reason": "missing_token_or_chat"}

    try:
        resp = requests.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={"chat_id": cfg.chat_id, "text": text},
            timeout=15,
        )
        return {"ok": resp.ok, "status": resp.status_code, "body": resp.text[:500]}
    except requests.RequestException as exc:
        logger.warning("Telegram send failed: %s", exc)
        return {"ok": False, "error": str(exc)}
