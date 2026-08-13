"""The live channel itself.

A consumer that raises inside connect() still completes the handshake, so the
panel reads "Live" for a moment and then flaps to "Offline" a second later —
and the latency readout stays blank because no pong ever arrives. That is what
these tests pin down: the socket must survive its own greeting, answer a ping,
and encode a payload holding non-JSON-native values (Decimal, datetime).

They also pin *who* may open it. This channel carries balances, positions and
per-leg failures, so it is staff-only like the REST side, and cross-origin
handshakes are refused — a WebSocket is exempt from CORS, so without that check
any page the admin visits could open one with their cookie attached.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.security.websocket import AllowedHostsOriginValidator
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.test import override_settings

from apps.trading.consumers import GROUP, TradingConsumer


@database_sync_to_async
def make_user(username: str, *, staff: bool) -> User:
    return User.objects.create_user(username, password="pw12345!", is_staff=staff)


async def open_socket(user=None) -> WebsocketCommunicator:
    """A connected socket as `user`, defaulting to a staff account."""
    if user is None:
        user = await make_user("boss", staff=True)
    communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
    communicator.scope["user"] = user
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


# --- who may open it --------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "who",
    ["anonymous", "no user in scope", "signed in but not staff"],
)
async def test_the_channel_is_staff_only(who):
    """Everything this socket pushes is behind IsAdminUser over REST.

    It used to accept every connection that reached it, which only stayed
    harmless while the /ws route was broken and nothing could connect at all.
    """
    if who == "anonymous":
        user = AnonymousUser()
    elif who == "no user in scope":
        user = None
    else:
        user = await make_user("peon", staff=False)

    communicator = WebsocketCommunicator(TradingConsumer.as_asgi(), "/ws/trading/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()

    assert not connected
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["maxbot.cybercina.co.uk"])
@pytest.mark.parametrize(
    "origin,allowed",
    [
        (b"https://maxbot.cybercina.co.uk", True),
        # The panel's own origin behind Caddy, explicit port form.
        (b"https://maxbot.cybercina.co.uk:443", True),
        (b"https://evil.example", False),
        # Suffix trick: a host that merely *starts* with the real one.
        (b"https://maxbot.cybercina.co.uk.evil.example", False),
    ],
)
async def test_only_the_panels_own_origin_may_open_the_channel(origin, allowed):
    """A WebSocket handshake is not subject to CORS, so this is the only guard.

    Without it, any page the admin has open could connect with their session
    cookie attached and read the live channel.
    """
    application = AllowedHostsOriginValidator(TradingConsumer.as_asgi())
    communicator = WebsocketCommunicator(
        application, "/ws/trading/", headers=[(b"origin", origin)]
    )
    communicator.scope["user"] = await make_user("boss", staff=True)
    connected, _ = await communicator.connect()

    assert connected is allowed
    await communicator.disconnect()
