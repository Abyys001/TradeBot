"""Confirmed bars, exactly once each, in order — or the bot stops.

This is a thin, strict layer over machinery that already exists rather than a
new data stack: ``public_sources`` fetches candles, ``public_stream`` streams
them, ``catalogue.ensure_history`` downloads history and ``candlestore``
archives it. What Phase 3 adds is the strictness the chart does not need and a
bot does.

The rules, and why each one is not negotiable:

  **Only closed bars (Q23).** A bar is confirmed when
  ``now >= open_time + interval + BAR_CONFIRM_LAG_MS``. Exchanges emit the
  closing update slightly late; reading a bar the instant the clock rolls over
  gets one that is still moving, and a decision made on a moving bar can reverse
  before it stops.

  **Never synthesise, hold, or interpolate.** ``public_stream`` already makes
  that promise for the chart and the bot inherits it. A gap that cannot be
  repaired from the exchange **stops the bot** (Q25) rather than being skipped:
  the strategy's state machine now disagrees with the market, and carrying on is
  trading a position it thinks it understands.

  **Warm-up trades nothing.** History is replayed with ``barstate.ishistory``
  and every intent it produces is discarded. An unconverged EMA never trades:
  too little history and the bot refuses to start, saying how many bars it has
  against how many it needs.

  **The clock is checked.** A bot whose clock runs a minute fast confirms bars
  that have not closed. Checked at start and hourly against the exchange.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from django.conf import settings

from apps.bots.config import bot_settings
from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import INTERVALS, Candle
from apps.pine.bar import Bar

logger = logging.getLogger(__name__)


class FeedGap(Exception):
    """A bar the exchange cannot supply. Q25 stops the bot on the first one."""

    def __init__(self, message: str, *, missing: list[int]) -> None:
        super().__init__(message)
        self.missing = missing


class NotEnoughHistory(Exception):
    """Too little history to converge the indicators. The bot refuses to start."""

    def __init__(self, have: int, need: int) -> None:
        super().__init__(
            f"this symbol has {have} stored bars and the strategy needs {need} to "
            f"converge its indicators — it will not start on an unconverged average"
        )
        self.have = have
        self.need = need


class ClockSkew(Exception):
    """Local time is too far from the exchange's. The bot refuses to start."""


@dataclass(frozen=True, slots=True)
class FeedBar:
    """A confirmed bar plus where it came from — the panel names the source."""

    bar: Bar
    source: str
    #: "stream" or "poll". Both are real exchange data and the panel says which,
    #: rather than blurring them the way a single "live" badge would.
    transport: str
    #: True when this bar was fetched to repair a gap rather than arriving live.
    repaired: bool = False


def to_bar(candle: Candle) -> Bar:
    """``apps.exchanges`` Candle → the pure runtime's Bar. The one conversion."""
    return Bar(
        time=candle.time,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )


def interval_seconds(interval: str) -> int:
    step = INTERVALS.get(interval)
    if step is None:
        raise ValueError(f"unsupported interval {interval!r}")
    return step


def is_confirmed(open_time: int, interval: str, *, now: float | None = None) -> bool:
    """Whether this bar has finished *and* the exchange has had time to say so."""
    lag = bot_settings()["BAR_CONFIRM_LAG_MS"] / 1000
    moment = time.time() if now is None else now
    return moment >= open_time + interval_seconds(interval) + lag


def warmup_bars_needed(lookback: int) -> int:
    """``max(indicator lookback) × multiplier``, floored at the minimum.

    Three times the longest lookback rather than exactly it, because a seeded
    ``rma`` is *arithmetically* defined after ``length`` bars and not yet
    converged; an RSI seeded and then run for two more periods matches
    TradingView's, one seeded and read immediately does not.
    """
    values = bot_settings()
    return max(values["WARMUP_MIN_BARS"], lookback * values["WARMUP_MULTIPLIER"])


class BarFeed:
    """``async for bar in BarFeed(...)`` — closed bars, once each, in order.

    Prefers the WebSocket stream and falls back to polling exactly as the chart
    does. Every reconnect re-fetches the window since the last bar seen and
    replays whatever closed while the socket was away, so a dropped connection
    costs latency and never a bar.
    """

    def __init__(
        self,
        *,
        symbol: str,
        interval: str,
        market: MarketType,
        poll_seconds: float | None = None,
    ) -> None:
        self.symbol = symbol.upper()
        self.interval = interval
        self.market = market
        self.step = interval_seconds(interval)
        # Poll well inside the bar so a confirmed bar is picked up promptly
        # without hammering a venue: a quarter of the bar, capped at 15s.
        self.poll_seconds = poll_seconds or min(15.0, max(2.0, self.step / 4))
        self.last_bar_time: int | None = None
        self.transport = "poll"
        self.source = ""
        self.gaps = 0
        self.gaps_repaired = 0

    # --- history ------------------------------------------------------------

    async def warmup(self, *, lookback: int) -> list[Bar]:
        """Bars to converge the indicators on, oldest first. Never trades."""
        need = warmup_bars_needed(lookback)
        candles, source = await sync_to_async(self._read_history)(need)
        if len(candles) < need:
            raise NotEnoughHistory(len(candles), need)
        self.source = source
        bars = [to_bar(candle) for candle in candles]
        # The last of these is the bar the live loop must not repeat.
        self.last_bar_time = bars[-1].time if bars else None
        logger.info(
            "bot feed warm-up %s %s: %d bars from %s, %s → %s",
            self.symbol,
            self.interval,
            len(bars),
            source,
            bars[0].time if bars else "-",
            bars[-1].time if bars else "-",
            extra={"category": "BOT"},
        )
        return bars

    def _read_history(self, need: int) -> tuple[list[Candle], str]:
        """Stored archive first, then whatever the venue will still serve.

        The archive is the deeper source by design — it is a local table with an
        index on exactly this query — so it answers first and the venue only
        fills the head.
        """
        from apps.exchanges import candlestore, marketdata

        stored = candlestore.read_window(
            symbol=self.symbol,
            interval=self.interval,
            market=self.market,
            limit=need + 5,
            exchange=marketdata.pinned_provider(),
        )
        archived, source = (stored or ([], ""))

        live: list[Candle] = []
        try:
            payload = marketdata.get_candles(
                symbol=self.symbol, interval=self.interval, market=self.market, limit=need + 5
            )
            source = payload.get("source") or source
            live = [_candle_from(row) for row in payload.get("candles", [])]
        except Exception as exc:  # noqa: BLE001 - the archive may still be enough
            logger.info("bot feed warm-up: live history unavailable (%s)", exc)

        merged = candlestore.merge(list(archived), live)
        # An unfinished bar at the head is exactly what Q23 excludes.
        closed = [c for c in merged if is_confirmed(c.time, self.interval)]
        return closed[-need:] if len(closed) > need else closed, source or "archive"

    # --- the clock ----------------------------------------------------------

    async def check_clock(self) -> None:
        """Refuse to run on a clock too far from the exchange's.

        Uses the round trip the market-data layer already measures rather than
        adding another signed call: the check is about *drift*, and a venue that
        answers a public request answers it with a timestamp.
        """
        allowed = bot_settings()["MAX_CLOCK_SKEW_MS"]
        skew = await sync_to_async(_measure_skew_ms)(self.symbol, self.interval, self.market)
        if skew is None:
            # Nothing to compare against is not proof of a good clock, but it is
            # also not proof of a bad one, and refusing to start every bot
            # because a public endpoint is briefly down is its own outage.
            logger.warning("bot feed: clock skew unmeasurable", extra={"category": "BOT"})
            return
        if abs(skew) > allowed:
            raise ClockSkew(
                f"this host's clock is {skew:.0f}ms from the exchange's, over the "
                f"{allowed}ms limit — a fast clock confirms bars that have not closed"
            )

    # --- the live stream ----------------------------------------------------

    async def __aiter__(self) -> AsyncIterator[FeedBar]:
        """Confirmed bars from now on. Streamed where the venue can, polled otherwise."""
        from apps.exchanges import marketdata
        from apps.exchanges.public_stream import StreamDown, stream_bars, streamable

        # Same accessor `streamhub` uses, and off the event loop for the same
        # reason: it reads the connected-exchange list from the database.
        providers = await sync_to_async(marketdata._configured_providers)()
        if streamable(providers):
            async for item in self._stream(providers, stream_bars, StreamDown):
                yield item
        else:
            async for item in self._poll():
                yield item

    async def _stream(self, providers, stream_bars, StreamDown) -> AsyncIterator[FeedBar]:
        self.transport = "stream"
        stream = stream_bars(
            symbol=self.symbol, interval=self.interval, market=self.market, providers=providers
        )
        async with contextlib.aclosing(stream) as source:
            async for update in source:
                if isinstance(update, StreamDown):
                    # Not an error to report: the polled feed is real data too.
                    # It tells the bot to stop expecting pushes and go back to
                    # asking, and the panel says which it is on.
                    logger.info(
                        "bot feed %s: stream down (%s) — polling",
                        self.symbol,
                        update.reason,
                        extra={"category": "BOT"},
                    )
                    self.transport = "poll"
                    async for item in self._poll(until_stream_returns=True):
                        yield item
                    self.transport = "stream"
                    continue

                provider, bar_update = update
                self.source = provider
                if not bar_update.closed:
                    continue
                for item in await self._accept(bar_update.candle, provider):
                    yield item

    async def _poll(self, *, until_stream_returns: bool = False) -> AsyncIterator[FeedBar]:
        from apps.exchanges import marketdata

        while True:
            await asyncio.sleep(self.poll_seconds)
            try:
                payload = await sync_to_async(marketdata.get_candles)(
                    symbol=self.symbol, interval=self.interval, market=self.market, limit=10
                )
            except Exception as exc:  # noqa: BLE001 - one failed poll is not a gap
                logger.info("bot feed %s: poll failed (%s)", self.symbol, exc)
                continue
            provider = payload.get("source", "")
            self.source = provider
            candles = [_candle_from(row) for row in payload.get("candles", [])]
            for candle in candles:
                if not is_confirmed(candle.time, self.interval):
                    continue
                for item in await self._accept(candle, provider):
                    yield item
            if until_stream_returns:
                return

    # --- ordering and gaps --------------------------------------------------

    async def _accept(self, candle: Candle, provider: str) -> list[FeedBar]:
        """Admit one bar, repairing anything missing before it.

        The order matters: a repaired bar is yielded *before* the bar that
        exposed the gap, so the runtime never sees the future before the past.
        """
        if self.last_bar_time is not None and candle.time <= self.last_bar_time:
            return []  # already delivered, or still forming
        if not is_confirmed(candle.time, self.interval):
            return []

        out: list[FeedBar] = []
        if self.last_bar_time is not None:
            expected = self.last_bar_time + self.step
            if candle.time > expected:
                self.gaps += 1
                repaired = await self._repair(expected, candle.time)
                self.gaps_repaired += 1
                out.extend(
                    FeedBar(
                        bar=to_bar(item),
                        source=provider,
                        transport=self.transport,
                        repaired=True,
                    )
                    for item in repaired
                )
                self.last_bar_time = repaired[-1].time if repaired else self.last_bar_time

        self.last_bar_time = candle.time
        out.append(FeedBar(bar=to_bar(candle), source=provider, transport=self.transport))
        return out

    async def _repair(self, first_missing: int, up_to: int) -> list[Candle]:
        """Re-fetch the window a reconnect or a stall skipped.

        Raises ``FeedGap`` when the exchange has no data for it. That stops the
        bot, and stopping is the right answer: skipping leaves the strategy's
        state machine describing a market that did not happen, and a strategy
        that is wrong about the past is wrong about the position it holds now.
        """
        from apps.exchanges import marketdata

        wanted = list(range(first_missing, up_to, self.step))
        if not wanted:
            return []
        logger.warning(
            "bot feed %s %s: %d bar(s) missing from %s — refetching",
            self.symbol,
            self.interval,
            len(wanted),
            first_missing,
            extra={"category": "BOT"},
        )
        try:
            payload = await sync_to_async(marketdata.get_candles)(
                symbol=self.symbol,
                interval=self.interval,
                market=self.market,
                limit=min(1000, len(wanted) + 10),
                end=up_to,
            )
        except Exception as exc:  # noqa: BLE001 - reported as the gap it is
            raise FeedGap(
                f"{len(wanted)} bar(s) are missing from {first_missing} and the exchange "
                f"could not be reached to refetch them ({exc})",
                missing=wanted,
            ) from exc

        by_time = {c.time: c for c in (_candle_from(row) for row in payload.get("candles", []))}
        recovered = [by_time[t] for t in wanted if t in by_time]
        still_missing = [t for t in wanted if t not in by_time]
        if still_missing:
            raise FeedGap(
                f"the exchange has no data for {len(still_missing)} bar(s) starting at "
                f"{still_missing[0]} — the strategy's state machine no longer matches "
                f"the market",
                missing=still_missing,
            )
        return recovered


def _candle_from(row: dict) -> Candle:
    from decimal import Decimal

    return Candle(
        time=int(row["t"]),
        open=Decimal(row["o"]),
        high=Decimal(row["h"]),
        low=Decimal(row["l"]),
        close=Decimal(row["c"]),
        volume=Decimal(row.get("v", "0")),
    )


def _measure_skew_ms(symbol: str, interval: str, market: MarketType) -> float | None:
    """Local clock minus the newest confirmed bar's expected close, in ms.

    A public candle endpoint is the cheapest exchange-side clock available, and
    it is the *same* clock that decides when a bar closes — which is the only
    clock this check is about.
    """
    from apps.exchanges import marketdata

    try:
        payload = marketdata.get_candles(symbol=symbol, interval=interval, market=market, limit=3)
    except Exception:  # noqa: BLE001 - unmeasurable, not wrong
        return None
    rows = payload.get("candles") or []
    if not rows:
        return None
    step = interval_seconds(interval)
    newest_open = max(int(row["t"]) for row in rows)
    # The newest bar the venue has opened cannot be in the future, and it cannot
    # be more than one full bar in the past on a live feed. Anything outside
    # that band is our clock, not theirs.
    now = time.time()
    if newest_open <= now < newest_open + 2 * step:
        return 0.0
    if now < newest_open:
        return (now - newest_open) * 1000
    return (now - (newest_open + 2 * step)) * 1000


def supervisor_enabled() -> bool:
    return bool(settings.BOT["SUPERVISOR_IN_ASGI"])
