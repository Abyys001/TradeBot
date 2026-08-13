"""WebSocket channel to the admin panel.

Carries live position/balance updates and — the one that matters for spec §4 —
per-leg failure notifications the moment a leg fails, rather than after the
whole fan-out settles.
"""

from __future__ import annotations

import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

GROUP = "trading"


@sync_to_async
def _exchange_latency() -> dict:
    """Last measured engine→exchange round trip, from the market-data cache.

    Read here rather than probed: the keepalive must not fire an outbound HTTP
    request every eight seconds. The number is whatever the real price polls
    last measured, and null when nothing was measured recently.
    """
    from apps.exchanges.marketdata import provider_latency

    return provider_latency()


class TradingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected"})

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def receive_json(self, content: dict, **kwargs) -> None:
        if content.get("type") == "ping":
            # The pong carries both halves of the real path: the browser times
            # its own round trip to the engine, and the engine reports the last
            # measured round trip to the exchange. Neither is a constant.
            latency = await _exchange_latency()
            await self.send_json(
                {
                    "type": "pong",
                    "exchange_ms": latency["ms"],
                    "exchange": latency["provider"],
                }
            )

    # --- group event handlers ---------------------------------------------

    async def leg_result(self, event: dict) -> None:
        await self.send_json({"type": "leg_result", **event["payload"]})

    async def notification(self, event: dict) -> None:
        # Spec §4: persistent until dismissed — the client must not auto-expire it.
        await self.send_json({"type": "notification", "persistent": True, **event["payload"]})

    async def balances(self, event: dict) -> None:
        await self.send_json({"type": "balances", "accounts": event["payload"]})

    async def stop_all(self, event: dict) -> None:
        # Spec §7: a halt flipped in one tab must show in every open panel.
        await self.send_json({"type": "stop_all", **event["payload"]})

    @classmethod
    async def encode_json(cls, content) -> str:
        # Async because Channels awaits this hook (channels>=4). A sync override
        # here raised TypeError inside connect(), which closed the socket
        # immediately after accept — the panel flapped Live/Offline forever.
        return json.dumps(content, default=str)
