"""The live channel itself.

A consumer that raises inside connect() still completes the handshake, so the
panel reads "Live" for a moment and then flaps to "Offline" a second later —
and the latency readout stays blank because no pong ever arrives. That is what
these tests pin down: the socket must survive its own greeting, answer a ping,
and encode a payload holding non-JSON-native values (Decimal, datetime).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from apps.trading.consumers import GROUP, TradingConsumer


async def open_socket() -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
    connected, _ = await communicator.connect()
    assert connected
    return communicator


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_greeting_arrives_and_socket_stays_open():
    communicator = await open_socket()
    assert await communicator.receive_json_from() == {"type": "connected"}
    # The regression: the greeting used to raise, closing the socket right after
    # the handshake. Nothing should be waiting to close it now.
    assert await communicator.receive_nothing(timeout=0.2)
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ping_is_answered():
    communicator = await open_socket()
    await communicator.receive_json_from()
    await communicator.send_json_to({"type": "ping"})
    pong = await communicator.receive_json_from()
    assert pong["type"] == "pong"
    # The pong carries the engine's own measured round trip to the exchange, so
    # the panel can show both halves of the path. Nothing has been measured in
    # this test, and an unmeasured link reports null rather than a number.
    assert pong["exchange_ms"] is None
    assert pong["exchange"] == ""
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_group_payload_with_decimals_is_encoded():
    """Balances and prices are Decimal on this side of the wire (money rule)."""
    communicator = await open_socket()
    await communicator.receive_json_from()

    await get_channel_layer().group_send(
        GROUP,
        {
            "type": "balances",
            "payload": [{"id": 1, "balance": Decimal("99.00"), "at": datetime(2026, 1, 1)}],
        },
    )

    message = await communicator.receive_json_from()
    assert message["type"] == "balances"
    assert message["accounts"][0]["balance"] == "99.00"
    await communicator.disconnect()
