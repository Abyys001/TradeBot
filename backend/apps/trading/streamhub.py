"""One upstream socket per pair, fanned out to every panel watching it.

The panel does not talk to an exchange. It asks this process for a symbol and
gets bars pushed down the channel it already has open, which buys three things
that a browser-to-exchange socket does not:

  - **one** connection per pair no matter how many tabs are open, so ten
    viewers are not ten subscriptions on the venue's rate limit;
  - the egress stays on the server, where the deployment's network sits — the
    admin's browser may not be able to reach the exchange at all;
  - the panel keeps its single origin, so no exchange host needs to be in the
    page's connect-src and nothing new is exposed to the browser.

Subscriptions are reference counted. The upstream socket opens when the first
viewer arrives and closes when the last one leaves; nothing streams into an
empty room. This lives in the ASGI process rather than a worker because it is
pure IO with no ordering requirement — and because a broker hop would add
latency to the one thing here that is supposed to be immediate.

When no provider can stream, the room is told once and the panel goes back to
polling. That is the honest degraded state: slower, still real, never invented.
"""

from __future__ import annotations

import asyncio
import logging

from channels.layers import get_channel_layer

from apps.exchanges.base import MarketType
from apps.exchanges.public_stream import StreamDown, stream_bars

logger = logging.getLogger(__name__)

#: Guards the table below. Every mutation happens in the ASGI event loop, but
#: two consumers can interleave at an await point inside subscribe/unsubscribe.
_lock = asyncio.Lock()

#: key -> (task, viewer count)
_rooms: dict[str, tuple[asyncio.Task, int]] = {}


def room_key(*, symbol: str, interval: str, market: MarketType) -> str:
    """A key that is also a legal Channels group name (alnum, dot, dash, _)."""
    return f"md.{market.value}.{symbol.upper()}.{interval}"


async def _providers_for(market: MarketType) -> list[str]:
    """Provider preference, resolved off the event loop (it reads the DB)."""
    from asgiref.sync import sync_to_async

    from apps.exchanges.marketdata import _configured_providers

    return await sync_to_async(_configured_providers)()


async def _pump(key: str, *, symbol: str, interval: str, market: MarketType) -> None:
    """Relay one pair's bars into its group until cancelled.

    `stream_bars` never returns on its own — it retries providers forever — so
    this only ends by cancellation, which is what `leave` does.
    """
    layer = get_channel_layer()
    providers = await _providers_for(market)
    where = {"symbol": symbol, "interval": interval, "market": market.value}
    live = False

    try:
        async for event in stream_bars(
            symbol=symbol, interval=interval, market=market, providers=providers
        ):
            if isinstance(event, StreamDown):
                # Not an outage of the *data* — the polled REST feed is still
                # real. It tells the panel to stop waiting for pushes.
                live = False
                logger.info("stream down for %s: %s", key, event.reason)
                await layer.group_send(
                    key,
                    {
                        "type": "market_stream_down",
                        "payload": {**where, "reason": event.reason},
                    },
                )
                continue

            provider, update = event
            if not live:
                # First bar after a drop: the panel can stop polling again.
                live = True
                await layer.group_send(
                    key, {"type": "market_stream_up", "payload": {**where, "source": provider}}
                )

            await layer.group_send(
                key,
                {
                    "type": "market_bar",
                    "payload": {**where, "source": provider, "bar": update.as_dict()},
                },
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("stream pump failed for %s", key)
        await layer.group_send(
            key, {"type": "market_stream_down", "payload": {**where, "reason": "stream failed"}}
        )


async def join(*, symbol: str, interval: str, market: MarketType) -> str:
    """Register one viewer and return the group to add the channel to."""
    key = room_key(symbol=symbol, interval=interval, market=market)
    async with _lock:
        existing = _rooms.get(key)
        if existing is None:
            task = asyncio.create_task(
                _pump(key, symbol=symbol, interval=interval, market=market), name=key
            )
            _rooms[key] = (task, 1)
        else:
            task, viewers = existing
            _rooms[key] = (task, viewers + 1)
    return key


async def leave(key: str) -> None:
    """Drop one viewer, closing the upstream socket when it was the last."""
    async with _lock:
        existing = _rooms.get(key)
        if existing is None:
            return
        task, viewers = existing
        if viewers > 1:
            _rooms[key] = (task, viewers - 1)
            return
        del _rooms[key]

    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001 - teardown is best effort
        pass


async def shutdown() -> None:
    """Cancel every room. Used by tests so no task outlives its event loop."""
    async with _lock:
        rooms = list(_rooms.values())
        _rooms.clear()
    for task, _ in rooms:
        task.cancel()
    for task, _ in rooms:
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
