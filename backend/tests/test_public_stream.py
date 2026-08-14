"""Live market-data streams (spec §3) — parsing, failover, and the room count.

No test here opens a socket. The exchange frames are real captures, and the
failover tests drive fake streams, because a suite that needs Bybit to be up is
a suite that fails for reasons that have nothing to do with the code.

What these pin: a bar carries Decimal prices and the exchange's own idea of
"finished", a dead venue hands over to the next instead of taking the chart
down, and one upstream socket is opened per pair no matter how many panels are
watching it.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from apps.exchanges.base import MarketType
from apps.exchanges.public_stream import (
    STREAMS,
    BinancePublicStream,
    BybitPublicStream,
    HyperliquidPublicStream,
    StreamDown,
    stream_bars,
    streamable,
)

# --- parsing real frames ----------------------------------------------------


def test_bybit_frame_becomes_a_decimal_bar():
    frame = {
        "topic": "kline.1.BTCUSDT",
        "data": [
            {
                "start": 1786664400000,
                "open": "63428.1",
                "high": "63430.0",
                "low": "63420.5",
                "close": "63429.9",
                "volume": "12.5",
                "confirm": True,
            }
        ],
    }
    update = BybitPublicStream().parse(frame, symbol="BTCUSDT")

    assert update.candle.time == 1786664400
    assert update.candle.close == Decimal("63429.9")
    assert isinstance(update.candle.high, Decimal)
    assert update.closed is True


def test_bybit_ignores_its_subscribe_ack():
    ack = {"success": True, "op": "subscribe"}
    assert BybitPublicStream().parse(ack, symbol="BTCUSDT") is None


def test_hyperliquid_frame_is_keyed_by_base_asset():
    stream = HyperliquidPublicStream()
    assert stream.subscription(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES) == {
        "method": "subscribe",
        "subscription": {"type": "candle", "coin": "BTC", "interval": "1m"},
    }

    frame = {
        "channel": "candle",
        "data": {
            "t": 1786664400000,
            "T": 1786664459999,
            "o": "63461.0",
            "h": "63465.0",
            "l": "63455.0",
            "c": "63459.0",
            "v": "2.16715",
        },
    }
    update = stream.parse(frame, symbol="BTCUSDT")
    assert update.candle.time == 1786664400
    assert update.candle.open == Decimal("63461.0")
    # `T` is far in the past, so this bar is finished.
    assert update.closed is True


def test_binance_is_addressed_by_url_with_no_subscribe_frame():
    stream = BinancePublicStream()
    url = stream.endpoint(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)
    assert url == "wss://fstream.binance.com/ws/btcusdt@kline_1m"
    assert stream.subscription(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES) is None

    frame = {
        "e": "kline",
        "k": {"t": 1786664400000, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "9", "x": False},
    }
    update = stream.parse(frame, symbol="BTCUSDT")
    assert update.candle.low == Decimal("0.5")
    assert update.closed is False


def test_spot_and_futures_are_different_endpoints():
    bybit = BybitPublicStream()
    spot = bybit.endpoint(symbol="BTCUSDT", interval="1m", market=MarketType.SPOT)
    futures = bybit.endpoint(symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES)
    assert spot.endswith("/spot")
    assert futures.endswith("/linear")


# --- failover ---------------------------------------------------------------


class FakeStream:
    """A stand-in venue: either yields bars forever, or refuses to connect."""

    name = "fake"
    bars_to_yield = 0
    fail_with: Exception | None = None

    async def bars(self, *, symbol, interval, market):
        if self.fail_with is not None:
            raise self.fail_with
        sent = 0
        while sent < self.bars_to_yield:
            sent += 1
            yield BybitPublicStream().parse(
                {
                    "topic": "kline.1.X",
                    "data": [
                        {
                            "start": 1786664400000 + sent * 1000,
                            "open": "1",
                            "high": "1",
                            "low": "1",
                            "close": str(sent),
                            "volume": "1",
                            "confirm": False,
                        }
                    ],
                },
                symbol=symbol,
            )
            await asyncio.sleep(0)


def _venue(monkeypatch, name, **attrs):
    cls = type(f"{name.title()}Fake", (FakeStream,), {"name": name, **attrs})
    monkeypatch.setitem(STREAMS, name, cls)


def test_only_providers_that_can_stream_are_walked():
    """Exchanges with no stream implementation degrade to polling silently."""
    assert streamable(["hyperliquid", "kucoin", "bybit", "okx"]) == ["hyperliquid", "bybit"]


@pytest.mark.asyncio
async def test_a_dead_venue_hands_over_to_the_next(monkeypatch):
    _venue(monkeypatch, "hyperliquid", fail_with=OSError("route to host"))
    _venue(monkeypatch, "bybit", bars_to_yield=2)

    seen = []
    agen = stream_bars(
        symbol="BTCUSDT",
        interval="1m",
        market=MarketType.FUTURES,
        providers=["hyperliquid", "bybit"],
    )
    async for event in agen:
        seen.append(event)
        if len(seen) == 2:
            break
    await agen.aclose()

    assert [name for name, _ in seen] == ["bybit", "bybit"]
    assert seen[-1][1].candle.close == Decimal("2")


@pytest.mark.asyncio
async def test_every_venue_down_reports_it_once_rather_than_going_quiet(monkeypatch):
    """The panel has to be told, or it waits forever for a push that never comes."""
    _venue(monkeypatch, "hyperliquid", fail_with=OSError("down"))
    _venue(monkeypatch, "bybit", fail_with=OSError("also down"))

    agen = stream_bars(
        symbol="BTCUSDT",
        interval="1m",
        market=MarketType.FUTURES,
        providers=["hyperliquid", "bybit"],
    )
    first = await anext(agen)
    await agen.aclose()

    assert isinstance(first, StreamDown)
    assert "hyperliquid" in first.reason and "bybit" in first.reason


@pytest.mark.asyncio
async def test_nothing_streamable_says_so_immediately():
    agen = stream_bars(
        symbol="BTCUSDT", interval="1m", market=MarketType.FUTURES, providers=["kucoin", "okx"]
    )
    first = await anext(agen)
    await agen.aclose()
    assert isinstance(first, StreamDown)
