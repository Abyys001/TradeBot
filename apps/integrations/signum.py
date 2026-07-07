"""Signum alert payload rendering and webhook delivery."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

DEFAULT_WEBHOOK = "https://signum.bot/api/webhook"


def get_signum_config(user):
    if user is None:
        return None
    from .models import SignumConfig

    return SignumConfig.objects.filter(user=user, enabled=True).first()


def render_alert_message(
    template: str,
    *,
    action: str,
    ticker: str,
    position_size: float,
    timestamp_ms: int,
    bot_id: str = "",
    order_size: str = "",
) -> str:
    """Substitute TradingView-style placeholders in a Pine alert_message template."""
    ts_iso = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
    out = template
    replacements = {
        "{{strategy.order.action}}": action,
        "{{ticker}}": ticker,
        "{{strategy.position_size}}": str(position_size),
        "{{time}}": ts_iso,
    }
    for key, val in replacements.items():
        out = out.replace(key, val)
    if bot_id:
        out = re.sub(r'"bot_id"\s*:\s*"[^"]*"', f'"bot_id": "{bot_id}"', out)
    if order_size:
        out = re.sub(r'"order_size"\s*:\s*"[^"]*"', f'"order_size": "{order_size}"', out)
    return out


def build_signum_payload(
    template: str,
    *,
    user,
    action: str,
    ticker: str,
    position_size: float,
    timestamp_ms: int,
) -> str:
    cfg = get_signum_config(user)
    bot_id = ""
    order_size = ""
    if cfg:
        if cfg.use_settings_bot_id:
            bot_id = cfg.get_bot_id()
        order_size = cfg.order_size_default or ""
    return render_alert_message(
        template,
        action=action,
        ticker=ticker,
        position_size=position_size,
        timestamp_ms=timestamp_ms,
        bot_id=bot_id,
        order_size=order_size,
    )


def send_signum_webhook(user, payload: str) -> dict:
    """POST JSON payload to the user's Signum webhook URL."""
    cfg = get_signum_config(user)
    if cfg is None:
        return {"ok": False, "skipped": True, "reason": "signum_disabled"}
    url = cfg.get_webhook_url() or DEFAULT_WEBHOOK
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = {"raw": payload}
    try:
        resp = requests.post(url, json=data, timeout=15)
        return {"ok": resp.ok, "status": resp.status_code, "body": resp.text[:500]}
    except requests.RequestException as exc:
        logger.warning("Signum webhook failed: %s", exc)
        return {"ok": False, "error": str(exc)}
