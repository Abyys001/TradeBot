"""Channels consumer pushing exchange updates to authenticated clients."""
import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.dashboard.publish import dashboard_group_name
from .ws_manager import group_name


class ExchangeConsumer(AsyncWebsocketConsumer):
    """Client WS endpoint: /ws/exchange/<credential_id>/

    Joins the credential's group and relays exchange.update events. Only the
    owner of the credential may subscribe.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.credential_id = int(self.scope["url_route"]["kwargs"]["credential_id"])
        if not await self._owns_credential(user, self.credential_id):
            await self.close(code=4403)
            return

        self.group = group_name(self.credential_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, "group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def exchange_update(self, event):
        """Handler for {"type": "exchange.update"} group messages."""
        await self.send(text_data=json.dumps(event["payload"]))

    @staticmethod
    async def _owns_credential(user, credential_id):
        from channels.db import database_sync_to_async

        from apps.credentials.models import ExchangeCredential

        @database_sync_to_async
        def _check():
            return ExchangeCredential.objects.filter(
                pk=credential_id, user=user
            ).exists()

        return await _check()


class DashboardConsumer(AsyncWebsocketConsumer):
    """Client WS endpoint: /ws/dashboard/

    Joins the user's dashboard group and relays health, log, candle, and PnL events.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.user_id = user.pk
        self.group = dashboard_group_name(self.user_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, "group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def dashboard_update(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
