"""Public market-data **streams** — the live half of `marketdata`.

`public_sources` answers "what is the price now" over HTTP; this answers "tell
me the moment it changes" over a WebSocket. Same rules as its sibling, for the
same reasons:

  - **not** part of the adapter seam. No credentials are involved, nothing is
    signed, and one socket is shared by every viewer, which per-account
    adapters must never be;
  - **real prices only.** A stream that drops does not emit a held value or an
    interpolated bar; it reconnects, and until it does the panel falls back to
    the polled REST feed and says where the number came from;
  - Decimal from the wire inwards, so no float artefact reaches sizing.

Only the providers that actually stream are implemented. Anything absent from
``STREAMS`` degrades to polling automatically rather than pretending: the
subscription layer walks the same provider preference as the REST feed and
takes the first that connects.

One deliberate limitation: `websockets` 14 cannot dial through a proxy, so
these connect directly even when ``MARKET_DATA_PROXY`` is set for the REST
calls. Where the stream provider is only reachable through that proxy the
socket simply never connects and the panel keeps polling — degraded, never
wrong. Bybit and Hyperliquid were verified to connect directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import websockets

from apps.core.money import D
from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import Candle, record_rtt, split_pair

logger = logging.getLogger(__name__)

#: Give up on a handshake that has not completed in this long and try the next
#: provider. The panel is already showing polled prices, so waiting longer buys
#: nothing.
CONNECT_TIMEOUT = 10.0

#: How long to wait for the *first* frame after subscribing. Every venue here
#: pushes a snapshot immediately, so silence means the socket is not really
#: working: a filtered route completes the TCP connect and the TLS handshake
#: and then simply delivers nothing. Measured against Binance from a network
#: that cannot reach it — it connected in 1.4s and went mute, and a long wait
#: here held up every provider queued behind it.
FIRST_FRAME_TIMEOUT = 15.0

#: Once bars are flowing, a quiet spell is ordinary — an illiquid pair on a 1d
#: candle updates rarely. This only catches a stream that has genuinely died
#: without closing, so it is far more patient than the first-frame wait.
IDLE_TIMEOUT = 90.0

#: How often an open stream re-times itself. The handshake measures the round
#: trip once, and `RTT_TTL` is 60s, so a socket that stays up all afternoon used
#: to leave the panel's exchange-latency readout blank while it was working
#: perfectly. A protocol-level ping is the honest measurement — the same frame
#: the venue already answers, timed against its pong — and costs nothing.
RTT_PING_EVERY = 20.0


@dataclass(frozen=True, slots=True)
class BarUpdate:
    """One candle, and whether the exchange considers it finished.

    The chart needs both: an unfinished bar replaces the last one in place and
    an finished bar starts a new one. Collapsing the two is what makes a live
    chart grow a spurious extra candle every tick.
    """

    candle: Candle
    closed: bool

    def as_dict(self) -> dict:
        return {**self.candle.as_dict(), "closed": self.closed}


class PublicStream:
    """One exchange's public candle stream."""

    name = ""
    url = ""

    def subscription(self, *, symbol: str, interval: str, market: MarketType) -> dict | None:
        """The subscribe frame, or None when the stream is addressed by URL."""
        raise NotImplementedError

    def endpoint(self, *, symbol: str, interval: str, market: MarketType) -> str:
        return self.url

    def parse(self, message: dict, *, symbol: str) -> BarUpdate | None:
        """A bar from one frame, or None for anything else (acks, heartbeats)."""
        raise NotImplementedError

    async def bars(
        self, *, symbol: str, interval: str, market: MarketType
    ) -> AsyncIterator[BarUpdate]:
        """Yield bars until cancelled. Raises if the socket cannot be opened."""
        url = self.endpoint(symbol=symbol, interval=interval, market=market)
        started = time.perf_counter()

        # `open_timeout` bounds the *handshake*, not the DNS lookup and TCP
        # connect underneath it. Against a venue that is blocked rather than
        # merely down — Binance, from a network that cannot route to it — the
        # socket sat in SYN retries for 101 seconds and stalled every provider
        # queued behind it, so the chart showed nothing for two minutes. This
        # outer timeout is what actually bounds "try the next one".
        socket = await asyncio.wait_for(
            websockets.connect(url, open_timeout=CONNECT_TIMEOUT), timeout=CONNECT_TIMEOUT
        )

        # The handshake is a real round trip to the exchange, so it feeds the
        # same latency readout the REST polls do.
        record_rtt(self.name, (time.perf_counter() - started) * 1000)

        keepalive = asyncio.ensure_future(self._time_round_trips(socket))

        try:
            frame = self.subscription(symbol=symbol, interval=interval, market=market)
            if frame is not None:
                await socket.send(json.dumps(frame))

            delivered = False
            while True:
                patience = IDLE_TIMEOUT if delivered else FIRST_FRAME_TIMEOUT
                raw = await asyncio.wait_for(socket.recv(), timeout=patience)
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                update = self.parse(message, symbol=symbol)
                if update is not None:
                    delivered = True
                    yield update
        finally:
            keepalive.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive
            await socket.close()

    async def _time_round_trips(self, socket) -> None:
        """Keep the engine→exchange latency readout live for as long as this is.

        A WebSocket ping is a real round trip to the venue over the same
        connection the bars arrive on, so it measures the hop an order travels
        rather than a separate HTTP path that might route differently. Failures
        are swallowed: this is a diagnostic, and the stream's own read timeouts
        are what decide whether the socket is alive.
        """
        while True:
            await asyncio.sleep(RTT_PING_EVERY)
            started = time.perf_counter()
            try:
                pong = await socket.ping()
                await asyncio.wait_for(pong, timeout=CONNECT_TIMEOUT)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the reader decides if it is dead
                return
            record_rtt(self.name, (time.perf_counter() - started) * 1000)


class BybitPublicStream(PublicStream):
    """v5 public stream. One socket per market type, topic per pair."""

    name = "bybit"
    _INTERVALS = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}

    def endpoint(self, *, symbol, interval, market):
        kind = "spot" if market is MarketType.SPOT else "linear"
        return f"wss://stream.bybit.com/v5/public/{kind}"

    def subscription(self, *, symbol, interval, market):
        return {"op": "subscribe", "args": [f"kline.{self._INTERVALS[interval]}.{symbol}"]}

    def parse(self, message, *, symbol):
        if not str(message.get("topic", "")).startswith("kline."):
            return None
        rows = message.get("data") or []
        if not rows:
            return None
        row = rows[-1]
        return BarUpdate(
            candle=Candle(
                time=int(row["start"]) // 1000,
                open=D(str(row["open"])),
                high=D(str(row["high"])),
                low=D(str(row["low"])),
                close=D(str(row["close"])),
                volume=D(str(row.get("volume", "0"))),
            ),
            closed=bool(row.get("confirm")),
        )


class HyperliquidPublicStream(PublicStream):
    """Perps are keyed by base asset alone (BTC), matching the REST source."""

    name = "hyperliquid"
    url = "wss://api.hyperliquid.xyz/ws"
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def _coin(self, symbol: str) -> str:
        pair = split_pair(symbol)
        return pair[0] if pair else symbol.upper()

    def subscription(self, *, symbol, interval, market):
        return {
            "method": "subscribe",
            "subscription": {
                "type": "candle",
                "coin": self._coin(symbol),
                "interval": self._INTERVALS[interval],
            },
        }

    def parse(self, message, *, symbol):
        if message.get("channel") != "candle":
            return None
        row = message.get("data") or {}
        if "t" not in row:
            return None
        # Hyperliquid marks the close by the bar's own end time passing, not by
        # a flag: `T` is the last millisecond the bar accepts trades.
        now_ms = time.time() * 1000
        return BarUpdate(
            candle=Candle(
                time=int(row["t"]) // 1000,
                open=D(str(row["o"])),
                high=D(str(row["h"])),
                low=D(str(row["l"])),
                close=D(str(row["c"])),
                volume=D(str(row.get("v", "0"))),
            ),
            closed=now_ms > float(row.get("T", 0)),
        )


class BinancePublicStream(PublicStream):
    """Addressed entirely by URL — no subscribe frame."""

    name = "binance"
    _INTERVALS = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    def endpoint(self, *, symbol, interval, market):
        host = "stream.binance.com:9443" if market is MarketType.SPOT else "fstream.binance.com"
        return f"wss://{host}/ws/{symbol.lower()}@kline_{self._INTERVALS[interval]}"

    def subscription(self, *, symbol, interval, market):
        return None

    def parse(self, message, *, symbol):
        if message.get("e") != "kline":
            return None
        k = message["k"]
        return BarUpdate(
            candle=Candle(
                time=int(k["t"]) // 1000,
                open=D(str(k["o"])),
                high=D(str(k["h"])),
                low=D(str(k["l"])),
                close=D(str(k["c"])),
                volume=D(str(k.get("v", "0"))),
            ),
            closed=bool(k.get("x")),
        )


#: Keyed exactly like ``public_sources.SOURCES`` so provider preference is one
#: order shared by both feeds. An exchange missing here polls instead.
STREAMS: dict[str, type[PublicStream]] = {
    "bybit": BybitPublicStream,
    "hyperliquid": HyperliquidPublicStream,
    "binance": BinancePublicStream,
}


def streamable(providers: list[str]) -> list[str]:
    """The subset of ``providers`` that can stream, order preserved."""
    return [name for name in providers if name in STREAMS]


@dataclass(frozen=True, slots=True)
class StreamDown:
    """Every provider failed a full pass. Poll until a bar arrives again."""

    reason: str


#: Backoff between full failed passes. A handshake that times out once is
#: routine — the first retry is immediate enough to be invisible, and the cap
#: keeps a genuinely unreachable venue from being hammered.
RETRY_BACKOFF = (1.0, 2.0, 5.0, 15.0, 30.0)


async def stream_bars(
    *, symbol: str, interval: str, market: MarketType, providers: list[str]
) -> AsyncIterator[tuple[str, BarUpdate] | StreamDown]:
    """Bars from whichever provider is currently up, forever.

    Walks the same preference order as the REST feed and keeps walking it. A
    provider that fails to connect or dies mid-stream hands over to the next;
    when a whole pass fails, this yields one ``StreamDown`` so the caller can
    fall back to polling, then backs off and starts the pass again.

    Retrying rather than returning is the point. A chart is open for hours, and
    a single timed-out handshake — which happens on any real network — must not
    leave it polling for the rest of the session.
    """
    order = streamable(providers)
    if not order:
        yield StreamDown("no configured provider can stream")
        return

    attempt = 0
    announced_down = False

    while True:
        connected = False
        reasons = []

        for name in order:
            stream = STREAMS[name]()
            try:
                bars = stream.bars(symbol=symbol, interval=interval, market=market)
                async with contextlib.aclosing(bars) as source:
                    async for update in source:
                        # Any bar means the venue is answering: reset the
                        # backoff so a later drop retries promptly again.
                        connected = True
                        attempt = 0
                        announced_down = False
                        yield name, update
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one dead venue is not an outage
                reasons.append(f"{name}: {exc}")
                logger.info("stream %s dropped for %s %s: %s", name, symbol, interval, exc)

        if not connected and not announced_down:
            announced_down = True
            yield StreamDown("; ".join(reasons) or "no provider connected")

        delay = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
        attempt += 1
        await asyncio.sleep(delay)
