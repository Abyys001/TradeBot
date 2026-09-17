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


def untraded(bar: Bar | Candle) -> bool:
    """A slot in which nothing traded — a venue's filler, not a bar.

    Hyperliquid answers a quiet 30 minutes on a thin pair with a flat,
    zero-volume candle at the last price; TradingView draws nothing there. Kept,
    one of them shifts every ``x[2]`` in the script by a bar and drags the ATR
    toward zero: on UZEC/USDC 30m it moved a reversal a bar early against the
    Strategy Tester. Both conditions, so a feed that simply omits volume does
    not lose every bar it serves.
    """
    return bar.volume == 0 and bar.open == bar.high == bar.low == bar.close


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


#: How long past a bar's own close the *next* bar may go undelivered before
#: the stream is treated as frozen and the REST feed is asked instead. A whole
#: further bar is already allowed on top of this, so on any timeframe this is
#: slack beyond slack — it exists so the catch-up can never race a stream that
#: is merely slow.
STREAM_CATCHUP_GRACE = 60.0


def warmup_bars_needed(lookback: int) -> int:
    """``max(indicator lookback) × multiplier``, floored at the minimum.

    Three times the longest lookback rather than exactly it, because a seeded
    ``rma`` is *arithmetically* defined after ``length`` bars and not yet
    converged; an RSI seeded and then run for two more periods matches
    TradingView's, one seeded and read immediately does not.
    """
    values = bot_settings()
    return max(values["WARMUP_MIN_BARS"], lookback * values["WARMUP_MULTIPLIER"])


#: A length past this many bars is a price, a percentage or a drawing budget
#: rather than an indicator period. Warm-up is floored at ``WARMUP_MIN_BARS``
#: anyway, so ignoring them costs nothing and reading them costs a month of
#: history on a venue that only keeps five thousand bars.
MAX_CREDIBLE_LOOKBACK = 500


def longest_lookback(result, inputs: dict | None = None) -> int:
    """The largest constant length any ``ta.*`` call in this script can ask for.

    **The single definition, read by the backtest and by the live loop.** It
    used to exist only in ``apps.bots.backtest``; the supervisor guessed
    instead, from the *number* of ``ta.*`` call sites rather than the lengths
    they were called with. The two answers were not close — a script whose
    longest period is ``ta.atr(200)`` warmed up on 600 bars in a backtest and
    on 300 live — and an indicator that has not converged is a different
    indicator, so the bot traded a strategy the report had never described. A
    live entry that the backtest exits two bars later, and a reversal that
    never fires at all, both come out of exactly that gap.

    An over-estimate is cheap (a few hundred extra warm-up bars) and an
    under-estimate is the above, so this leans high deliberately: it takes the
    largest literal in the script rather than trying to trace which argument is
    a length.

    ``inputs`` is the bot's configured input values. A length the operator
    *raised* — ``McGinley Length`` from 65 to 400 — never appears as a literal
    anywhere in the source, so a reading that only walked the AST would warm up
    for the default and converge nothing.
    """
    from apps.pine import ast_nodes as ast

    longest = 0
    program = getattr(result, "program", None)
    if program is None:
        return longest
    # `strategy(max_lines_count = 500)` is a drawing budget, not a lookback. Read
    # as one it tripled the warm-up to 1500 bars — a month of 30m history spent
    # before the first trade, on a venue that only keeps 5000 bars at all.
    declaration = {
        id(child)
        for node in ast.walk(program)
        if isinstance(node, ast.Call)
        and ast.dotted_name(node.func) in ("strategy", "indicator", "study")
        for child in ast.walk(node)
    }
    for node in ast.walk(program):
        if isinstance(node, ast.NumberLit) and id(node) not in declaration:
            longest = max(longest, _as_lookback(node.value))
    for value in (inputs or {}).values():
        longest = max(longest, _as_lookback(value))
    return longest


def _as_lookback(value) -> int:
    """A literal read as a period, or 0 when it cannot be one."""
    from decimal import Decimal

    try:
        number = int(Decimal(str(value)))
    except (ValueError, ArithmeticError, TypeError):
        return 0
    return number if 0 < number <= MAX_CREDIBLE_LOOKBACK else 0


def strategy_warmup(result, inputs: dict | None = None) -> int:
    """How many bars this script has to see before its first tradable bar.

    The backtest and the supervisor both call this and nothing else, which is
    the whole point: the two must not be able to disagree about it.
    """
    return warmup_bars_needed(longest_lookback(result, inputs))


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
        #: The latest state of the bar still forming, and the bars a later one
        #: has proved finished but ``BAR_CONFIRM_LAG_MS`` has not yet released.
        #: See ``_rollover`` for why a stream's own ``closed`` flag is not
        #: enough on its own.
        self._forming: Candle | None = None
        self._finished: list[Candle] = []
        #: When ``_catch_up`` last asked the REST feed, so a stream that has
        #: frozen behind the market is not one fetch per frame.
        self._catch_up_at = 0.0

    # --- history ------------------------------------------------------------

    async def warmup(self, *, lookback: int | None = None, bars: int | None = None) -> list[Bar]:
        """Bars to converge the indicators on, oldest first. Never trades.

        ``bars`` is an exact count — what ``strategy_warmup`` already worked
        out from the script — and is how the supervisor asks. ``lookback`` is
        the older shape, a period this multiplies out itself. Exactly one of
        the two, because "300" meaning a period on one call and a bar count on
        the next is how the live loop came to warm up on half the history its
        own backtest used.
        """
        if (bars is None) == (lookback is None):
            raise TypeError("warmup() takes exactly one of bars= or lookback=")
        need = bars if bars is not None else warmup_bars_needed(lookback)
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
        # Everything the venue just served that the archive did not already
        # hold. The platform's rule is that every closed bar it sees is kept
        # (`apps/exchanges/candlestore.py`), and until now the bot's own feed
        # was the one place that read bars and threw them away — which left
        # holes exactly where a bot had been running, since a panel nobody has
        # open is not archiving either.
        self._archive(live, source=source)
        # An unfinished bar at the head is exactly what Q23 excludes.
        closed = [
            c for c in merged if is_confirmed(c.time, self.interval) and not untraded(c)
        ]
        return closed[-need:] if len(closed) > need else closed, source or "archive"

    def _archive(self, candles: list[Candle], *, source: str = "") -> int:
        """Write bars this feed saw into the archive. Never raises, never blocks a bar.

        ``source`` is the venue the caller has in hand — during warm-up that is
        a local, because ``self.source`` is not set until the read returns. A
        pinned feed answers for everything else, and without either the bars are
        dropped rather than stored with no provenance: ``marketdata.get_candles``
        refuses another exchange's bars under a pinned badge, so a mislabelled
        row would be a bar that can never be read back.
        """
        if not candles:
            return 0
        from apps.exchanges import candlestore, marketdata

        exchange = marketdata.pinned_provider() or source or self.source
        if not exchange:
            return 0
        return candlestore.persist_quietly(
            exchange=exchange,
            symbol=self.symbol,
            market=self.market,
            interval=self.interval,
            candles=candles,
        )

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
        if streamable(providers, self.interval):
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
                    self._forming, self._finished = None, []
                    async for item in self._poll(until_stream_returns=True):
                        yield item
                    self.transport = "stream"
                    continue

                provider, bar_update = update
                self.source = provider
                if bar_update.closed:
                    # The venue said so. Nothing left forming behind it — but
                    # the bar may still be inside ``BAR_CONFIRM_LAG_MS``, and
                    # ``_accept`` refuses one that is. Handing it straight to
                    # ``_accept`` therefore *dropped* it: cleared from
                    # ``_forming`` and refused by the gate, with nothing left
                    # holding it. On an active pair the venue's first frame
                    # past ``T`` almost always lands inside the two-second lag,
                    # which is where the recurring "1 bar(s) missing —
                    # refetching" came from. Queue it like any other finished
                    # bar and let the release gate decide when it may be used.
                    self._forming = None
                    self._finished.append(bar_update.candle)
                    for item in await self._release(provider):
                        yield item
                    continue
                for item in await self._rollover(bar_update.candle, provider):
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

    async def _rollover(self, candle: Candle, provider: str) -> list[FeedBar]:
        """Bars proved finished by a later one arriving, rather than by a flag.

        **A stream's own ``closed`` flag cannot be the only signal.** Hyperliquid
        — the pinned market-data venue — marks a candle's end with ``T``, the
        last millisecond it accepts trades, and simply stops sending frames for
        that bar once it is done. So the last frame a bar receives almost always
        arrives with ``now < T`` and is computed ``closed=False``; the flag
        fires only when one happens to land after ``T``, which is luck.
        Measured on ZECUSDC 1m: one run saw four complete bars and 118 updates
        without a single flag, a second saw one flag in five bars. A feed
        waiting on that flag loses most bars and stalls outright on a quiet
        pair — which is why every run of this platform's bots so far evaluated
        zero bars while looking perfectly healthy.

        Rollover is the signal that does arrive. An update for a *later* bar is
        the venue saying it has moved on, which is proof the earlier one
        finished, and it is true of every exchange rather than one frame format.
        Q23 still decides when that bar may be *used*: ``is_confirmed`` gates it
        exactly as before, so a bar inside ``BAR_CONFIRM_LAG_MS`` is held here
        and admitted on the next update rather than dropped.
        """
        if self._forming is not None and self._forming.time < candle.time:
            self._finished.append(self._forming)
        self._forming = candle

        # **And rollover cannot be the only signal either.** A stream can stay
        # connected, keep pushing frames, and still stop moving forward. On
        # 2026-09-14 the Hyperliquid socket did exactly that on ZECUSDC 30m:
        # frames kept arriving — the 90s idle timeout never fired, the venue
        # only closed the socket with "Expired" two hours later — but no frame
        # ever carried a *later* bar, so nothing was ever rolled over and the
        # bot evaluated nothing from 17:30 until Q25's no-bars stop killed it.
        # A bar whose own window has closed and been confirmed is finished
        # whatever the venue does next, so the clock releases it here.
        if self._forming is not None and is_confirmed(self._forming.time, self.interval):
            self._finished.append(self._forming)
            self._forming = None

        out = await self._catch_up(provider)
        out.extend(await self._release(provider))
        return out

    async def _release(self, provider: str) -> list[FeedBar]:
        """Hand over every held bar Q23 now allows, oldest first."""
        ready = [row for row in self._finished if is_confirmed(row.time, self.interval)]
        if not ready:
            return []
        released = {row.time for row in ready}
        self._finished = [row for row in self._finished if row.time not in released]
        out: list[FeedBar] = []
        for row in sorted(ready, key=lambda item: item.time):
            out.extend(await self._accept(row, provider))
        return out

    async def _catch_up(self, provider: str) -> list[FeedBar]:
        """Bars the market has finished and the stream never offered.

        The safety net under ``_rollover``'s clock release, for the case that
        release cannot reach: a socket that keeps re-sending a bar already
        delivered, or simply never mentions the next one. Rollover is defined
        as "a later bar arrived" and the clock release only promotes the bar
        the venue last named, so neither notices a stream frozen *behind* the
        market. The wall clock does, and the REST source the repair path
        already uses has the bars.

        Deliberately lazy: it does nothing until the bar after the last one
        delivered has been closed for a whole further bar plus
        ``STREAM_CATCHUP_GRACE``, so it can never race the stream's own
        delivery, and it retries no faster than one fetch per
        ``poll_seconds`` while a fetch keeps failing. Everything it fetches
        goes through ``_accept``, so ordering, de-duplication and Q25's
        unrepairable-gap stop are the same rules as every other path.
        """
        from apps.exchanges import marketdata

        if self.last_bar_time is None:
            return []
        behind = self.last_bar_time + 2 * self.step + STREAM_CATCHUP_GRACE
        now = time.time()
        if now < behind or now - self._catch_up_at < self.poll_seconds:
            return []
        self._catch_up_at = now
        missing = int((now - self.last_bar_time) // self.step)
        logger.warning(
            "bot feed %s %s: the stream is %d bar(s) behind the market — asking the "
            "REST feed instead",
            self.symbol,
            self.interval,
            missing,
            extra={"category": "BOT"},
        )
        try:
            payload = await sync_to_async(marketdata.get_candles)(
                symbol=self.symbol,
                interval=self.interval,
                market=self.market,
                limit=min(1000, missing + 10),
            )
        except Exception as exc:  # noqa: BLE001 - one failed fetch is not a gap
            logger.info("bot feed %s: catch-up fetch failed (%s)", self.symbol, exc)
            return []
        candles = sorted(
            (_candle_from(row) for row in payload.get("candles", [])),
            key=lambda item: item.time,
        )
        out: list[FeedBar] = []
        for candle in candles:
            if not is_confirmed(candle.time, self.interval):
                continue
            out.extend(await self._accept(candle, payload.get("source") or provider))
        return out

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
                await sync_to_async(self._archive)(list(repaired))
                self.last_bar_time = repaired[-1].time if repaired else self.last_bar_time

        self.last_bar_time = candle.time
        if not untraded(candle):
            out.append(FeedBar(bar=to_bar(candle), source=provider, transport=self.transport))
        # Every confirmed bar this feed admits, including the repaired ones,
        # goes into the archive on its way past. `_accept` is the single funnel
        # — stream, poll, catch-up and repair all come through here — so one
        # write here is the whole rule rather than four that have to agree.
        # This is also what makes the *next* backtest deeper than this one:
        # the venue serves 5000 bars and forgets, and the archive does not.
        await sync_to_async(self._archive)([candle])
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
        # A slot the venue answers with an untraded filler is accounted for, not
        # missing: nothing happened there, and TradingView has no bar for it.
        recovered = [by_time[t] for t in wanted if t in by_time and not untraded(by_time[t])]
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
