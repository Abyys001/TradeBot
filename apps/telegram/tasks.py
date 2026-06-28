import logging

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.telegram.telegram import build_trade_alert, send_message

logger = logging.getLogger(__name__)


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
) -> None:
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
    )

    success_count = 0
    for chat_id in whitelist:
        ok = send_message(bot_token, chat_id, text)
        if ok:
            success_count += 1
        else:
            logger.warning(
                "telegram dispatch failed for user %s chat %s", user_id, chat_id
            )

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"dashboard_{user_id}",
        {
            "type": "dashboard.update",
            "payload": {
                "source": "telegram_alert",
                "dispatch_count": success_count,
                "total_targets": len(whitelist),
                "strategy_name": strategy_name,
                "action": action,
            },
        },
    )
    logger.info(
        "telegram dispatch: user=%s sent=%d/%d",
        user_id,
        success_count,
        len(whitelist),
    )
