"""One upstream socket per pair, however many panels are watching.

The reference counting is the whole point of the hub, and it is the part that
fails quietly: a leaked room keeps an exchange subscription open forever, and
switching timeframe a few times would leave a trail of them. These drive the
hub with a stubbed pump so nothing here touches the network.
"""

from __future__ import annotations

import asyncio

import pytest

from apps.exchanges.base import MarketType
from apps.trading import streamhub


@pytest.fixture(autouse=True)
async def _no_rooms_left():
    yield
    await streamhub.shutdown()


@pytest.fixture
def quiet_pump(monkeypatch):
    """Replace the relay with a task that just parks, and count the starts."""
    started = []

    async def fake_pump(key, *, symbol, interval, market):
        started.append(key)
        await asyncio.Event().wait()

    monkeypatch.setattr(streamhub, "_pump", fake_pump)
    return started


async def settle() -> None:
    """Let the freshly created pump tasks reach their first await."""
    await asyncio.sleep(0.01)


def test_the_room_key_is_a_legal_channels_group_name():
    key = streamhub.room_key(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)
    assert key == "md.futures.BTCUSDT.1m"
    # Channels rejects anything outside this set, and rejects it at send time —
    # long after the subscription looked like it had worked.
    assert all(c.isalnum() or c in "-_." for c in key)
    assert len(key) < 100


@pytest.mark.asyncio
async def test_two_viewers_share_one_upstream_socket(quiet_pump):
    first = await streamhub.join(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)
    second = await streamhub.join(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)

    await settle()

    assert first == second
    assert quiet_pump == [first], "the second viewer must not open its own socket"


@pytest.mark.asyncio
async def test_the_socket_closes_only_when_the_last_viewer_leaves(quiet_pump):
    key = await streamhub.join(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)
    await streamhub.join(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)

    await streamhub.leave(key)
    assert key in streamhub._rooms, "one viewer left, the stream is still wanted"

    await streamhub.leave(key)
    assert key not in streamhub._rooms


@pytest.mark.asyncio
async def test_different_pairs_get_their_own_rooms(quiet_pump):
    btc = await streamhub.join(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)
    eth = await streamhub.join(symbol="ETHUSDT", interval="1m", market=MarketType.FUTURES)
    slow = await streamhub.join(symbol="BTCUSDT", interval="1h", market=MarketType.FUTURES)

    await settle()

    assert len({btc, eth, slow}) == 3
    assert sorted(quiet_pump) == sorted([btc, eth, slow])


@pytest.mark.asyncio
async def test_leaving_an_unknown_room_is_not_an_error(quiet_pump):
    """Disconnect runs on sockets that never subscribed; it must not raise."""
    await streamhub.leave("md.futures.NOPE.1m")


@pytest.mark.asyncio
async def test_the_upstream_task_is_actually_cancelled(quiet_pump):
    key = await streamhub.join(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)
    task, _ = streamhub._rooms[key]

    await streamhub.leave(key)

    assert task.cancelled() or task.done(), "the exchange socket would stay open"
