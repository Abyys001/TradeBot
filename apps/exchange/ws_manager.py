"""Exchange update fan-out to Django Channels (UI notifications)."""
from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def group_name(credential_id: int) -> str:
    """Channels group that receives this credential's exchange updates."""
    return f"exchange.cred.{credential_id}"


def publish_update(credential_id: int, payload: dict) -> None:
    """Push one exchange update to the credential's Channels group."""
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        group_name(credential_id),
        {"type": "exchange.update", "payload": payload},
    )
