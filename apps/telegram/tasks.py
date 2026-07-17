import logging

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.telegram.telegram import build_trade_alert, send_message

logger = logging.getLogger(__name__)


class AlertSeverity:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


def _build_system_alert(severity: str, title: str, details: str, timestamp: str | None = None) -> str:
    """Build a formatted system alert message for Telegram."""
    ts = timestamp or timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    icon = {"info": "ℹ", "warning": "⚠", "critical": "🚨"}.get(severity, "ℹ")
    return (
        f"<b>{icon} {title}</b>\n"
        f"<pre>{details}</pre>\n"
        f"<i>{ts}</i>"
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def dispatch_telegram_alert(
    self,
    user_id: int,
    strategy_name: str,
    symbol: str,
    action: str,
    price: str = "",
    leverage: str = "",
    qty: str = "",
    pnl: str = "",
    exit_reason: str = "",
    position_side: str = "",
) -> None:
    from django.conf import settings

    if not getattr(settings, "TELEGRAM_ALERT_ENABLED", True):
        return

    from .models import AlertWhitelist, TelegramConfig

    try:
        config = TelegramConfig.objects.get(user_id=user_id, enabled=True)
    except TelegramConfig.DoesNotExist:
        return
    bot_token = config.bot_token
    if not bot_token:
        return

    whitelist = AlertWhitelist.objects.filter(
        user_id=user_id, enabled=True
    ).values_list("chat_id", flat=True)
    if not whitelist:
        return

    time_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    text = build_trade_alert(
        strategy_name=strategy_name,
        symbol=symbol,
        action=action,
        price=price,
        leverage=leverage,
        qty=qty,
        pnl=pnl,
        time_str=time_str,
        exit_reason=exit_reason,
        position_side=position_side,
    )

    _send_to_whitelist(bot_token, whitelist, user_id, text)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def dispatch_system_alert(
    self,
    user_id: int,
    severity: str,
    title: str,
    details: str,
) -> None:
    """Send a system alert (errors, kill-switch, reconciliation, etc.) to Telegram."""
    from django.conf import settings

    if not getattr(settings, "TELEGRAM_ALERT_ENABLED", False):
        return

    from .models import AlertWhitelist, TelegramConfig

    try:
        config = TelegramConfig.objects.get(user_id=user_id, enabled=True)
    except TelegramConfig.DoesNotExist:
        return
    bot_token = config.bot_token
    if not bot_token:
        return

    whitelist = AlertWhitelist.objects.filter(
        user_id=user_id, enabled=True
    ).values_list("chat_id", flat=True)
    if not whitelist:
        return

    text = _build_system_alert(severity, title, details)
    _send_to_whitelist(bot_token, whitelist, user_id, text)


def _send_to_whitelist(bot_token: str, whitelist, user_id: int, text: str) -> None:
    """Send a message to all whitelisted chats and publish to channel layer."""
    success_count = 0
    for chat_id in whitelist:
        ok = send_message(bot_token, chat_id, text)
        if ok:
            success_count += 1
        else:
            logger.warning(
                "telegram dispatch failed for user %s chat %s", user_id, chat_id
            )

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"dashboard_{user_id}",
            {
                "type": "dashboard.update",
                "payload": {
                    "source": "telegram_alert",
                    "dispatch_count": success_count,
                    "total_targets": len(whitelist),
                },
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning("channel layer publish failed for user %s", user_id, exc_info=True)

    logger.info(
        "telegram dispatch: user=%s sent=%d/%d",
        user_id,
        success_count,
        len(whitelist),
    )
