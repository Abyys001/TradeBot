"""Publish dashboard WebSocket events to per-user Channels groups."""
from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def dashboard_group_name(user_id: int) -> str:
    return f"dashboard.user.{user_id}"


def publish_dashboard(user_id: int, payload: dict) -> None:
    """Push one event to the user's dashboard WebSocket group."""
    if not user_id:
        return
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        dashboard_group_name(user_id),
        {"type": "dashboard.update", "payload": payload},
    )
