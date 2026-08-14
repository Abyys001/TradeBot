"""WebSocket channel to the admin panel.

Carries live position/balance updates and — the one that matters for spec §4 —
per-leg failure notifications the moment a leg fails, rather than after the
whole fan-out settles.
"""

from __future__ import annotations

import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.trading import streamhub

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
    #: The market room this socket is watching, or "" for none. An instance
    #: attribute rather than a lazily-set one so `disconnect` can rely on it
    #: even when the socket is refused before ever subscribing.
    market_room = ""

    async def connect(self) -> None:
        # Same gate as the REST side (`IsAdminUser`, and login itself refuses a
        # non-staff account). This channel carries balances, open positions,
        # per-leg failures and the halt state, so an ungated socket would hand
        # out everything the staff-only endpoints withhold — and it used to,
        # accepting any connection that reached it. The origin check in
        # config.asgi is the other half; this one is what stops a *logged-out*
        # or non-staff session.
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not user.is_staff:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected"})

    async def disconnect(self, code: int) -> None:
        # Leave the market room first: a socket that goes away without dropping
        # its viewer count would hold an exchange subscription open forever.
        await self._leave_market()
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def _leave_market(self) -> None:
        key = getattr(self, "market_room", "")
        if not key:
            return
        self.market_room = ""
        await self.channel_layer.group_discard(key, self.channel_name)
        await streamhub.leave(key)

    async def _subscribe_market(self, content: dict) -> None:
        """Follow one pair live. One room at a time — the panel shows one chart.

        Re-subscribing is how the symbol picker and the timeframe buttons work,
        so the previous room is always left first; without that, switching
        timeframe five times would leave five exchange subscriptions running.
        """
        from apps.exchanges.marketdata import normalise_interval, normalise_market

        symbol = str(content.get("symbol") or "").upper()
        if not symbol:
            return
        try:
            interval = normalise_interval(content.get("interval"))
            market = normalise_market(content.get("market"))
        except ValueError:
            return

        await self._leave_market()
        key = await streamhub.join(symbol=symbol, interval=interval, market=market)
        self.market_room = key
        await self.channel_layer.group_add(key, self.channel_name)

    async def receive_json(self, content: dict, **kwargs) -> None:
        if content.get("type") == "subscribe_market":
            await self._subscribe_market(content)
            return
        if content.get("type") == "unsubscribe_market":
            await self._leave_market()
            return
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

    async def market_bar(self, event: dict) -> None:
        await self.send_json({"type": "market_bar", **event["payload"]})

    async def market_stream_down(self, event: dict) -> None:
        # Not an error to show the admin — the polled feed is still real. It
        # tells the panel to stop expecting pushes and go back to asking.
        await self.send_json({"type": "market_stream_down", **event["payload"]})

    async def market_stream_up(self, event: dict) -> None:
        await self.send_json({"type": "market_stream_up", **event["payload"]})

    @classmethod
    async def encode_json(cls, content) -> str:
        # Async because Channels awaits this hook (channels>=4). A sync override
        # here raised TypeError inside connect(), which closed the socket
        # immediately after accept — the panel flapped Live/Offline forever.
        return json.dumps(content, default=str)
