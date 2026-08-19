"""The candle archive: every closed bar the platform has ever seen, kept forever.

`StoredCandle` existed before this module, but almost nothing wrote to it. Only
the two backfill jobs in `catalogue` did — the bulk sync and the chart-driven
download — so the archive was whatever those had been asked to fetch, and the
two feeds the panel actually runs on (the REST poll in `marketdata.get_candles`
and the exchange WebSocket behind `trading.streamhub`) threw their bars away
after drawing them. A chart could therefore be showing a bar that the platform
would have to ask the exchange for again a minute later, and could not show at
all once the venue stopped serving it.

This module is the one place that reads and writes the archive, so there is a
single answer to what gets kept:

**A forming bar is stored, but never frozen.** The bar at the head of any feed is
still being built, and the naive write is the dangerous one: insert it, and the
unique constraint on the series stops the finished version ever replacing it, so
the archive keeps a partial candle for ever. Dropping it instead is no better —
a daily chart would then have no bar for today at all.

So the two are written differently. Bars that have closed are *inserted*, and a
duplicate is ignored because settled history does not change. The forming bar,
and the newest bar already on disk (which may have been written while it was
still forming), are *upserted* — every poll rewrites their OHLCV until they
settle. One row, rewritten a few times, and then never touched again.

**Nothing is ever deleted.** There is no retention window, no pruning job, and
deliberately no setting for one. The table only grows, which is the point — the
chart's scrollback deepens on its own while the panel is open. `docs/deploy.md`
covers what that costs on disk and how to watch it.

**Provenance stays attached.** Every row records the venue that produced it, so
a pinned feed can refuse to serve another exchange's bars under its own badge
(see `marketdata.get_candles`).
"""

from __future__ import annotations

import logging
import time

from django.db import transaction

from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import INTERVALS, Candle

logger = logging.getLogger(__name__)

#: Rows per INSERT. Big enough to be fast, small enough that a failure loses
#: little and no single statement is enormous.
WRITE_BATCH = 2000

#: The unique constraint a bar is identified by — `StoredCandle.unique_bar_per_series`.
SERIES_KEY = ("exchange", "market", "symbol", "interval", "open_time")
#: What an upsert of a still-forming bar is allowed to change.
OHLCV = ("open", "high", "low", "close", "volume")


def is_closed(candle: Candle, interval: str, *, now: int | None = None) -> bool:
    """True when this bar's interval has fully elapsed.

    The bar at the head of any live response is still forming — see the module
    docstring for why that one must not be archived.
    """
    step = INTERVALS.get(interval)
    if step is None:
        return False
    return candle.time + step <= (time.time() if now is None else now)


def persist(
    *,
    exchange: str,
    symbol: str,
    market: MarketType,
    interval: str,
    candles,
    since: int | None = None,
) -> int:
    """Archive ``candles``. Returns how many rows were written or refreshed.

    ``since`` is the newest open time already on disk — callers on the hot path
    pass ``newest_stored(...)``. Anything older than it is settled and skipped,
    so a chart polling every fifteen seconds offers one or two bars rather than
    re-offering the three hundred already stored.

    That bar *at* ``since`` is deliberately not skipped: it is the one that may
    have been written while it was still forming, so it is re-read every time
    until it closes.
    """
    from apps.trading.models import StoredCandle

    if not exchange or not symbol:
        return 0

    def row(candle) -> StoredCandle:
        return StoredCandle(
            exchange=exchange,
            symbol=symbol,
            market=market.value,
            interval=interval,
            open_time=candle.time,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )

    settled: list[StoredCandle] = []
    unsettled: list[StoredCandle] = []
    for candle in candles:
        if since is not None and candle.time < since:
            continue
        closed = is_closed(candle, interval)
        # `candle.time == since` goes in the unsettled bucket whatever its state:
        # that is the row that may be a partial bar needing its final values.
        if closed and candle.time != since:
            settled.append(row(candle))
        else:
            unsettled.append(row(candle))

    written = 0
    for start in range(0, len(settled), WRITE_BATCH):
        chunk = settled[start : start + WRITE_BATCH]
        with transaction.atomic():
            written += len(StoredCandle.objects.bulk_create(chunk, ignore_conflicts=True))

    for start in range(0, len(unsettled), WRITE_BATCH):
        chunk = unsettled[start : start + WRITE_BATCH]
        with transaction.atomic():
            StoredCandle.objects.bulk_create(
                chunk,
                update_conflicts=True,
                unique_fields=SERIES_KEY,
                update_fields=OHLCV,
            )
        written += len(chunk)
    return written


def persist_quietly(**kwargs) -> int:
    """``persist`` that swallows its own failures.

    For the live paths. The archive is a side effect of drawing a chart; a
    database that will not take the write must degrade to "no history was
    recorded", never to a chart that does not draw or a stream that stalls.
    """
    try:
        return persist(**kwargs)
    except Exception:  # noqa: BLE001 - archiving must not break the feed it rides on
        logger.exception(
            "could not archive %s %s bars", kwargs.get("symbol"), kwargs.get("interval")
        )
        return 0


def newest_stored(
    *, symbol: str, interval: str, market: MarketType, exchange: str = ""
) -> int | None:
    """The newest archived open time for a series, or None when it is empty."""
    from apps.trading.models import StoredCandle

    rows = StoredCandle.objects.filter(symbol=symbol, interval=interval, market=market.value)
    if exchange:
        rows = rows.filter(exchange=exchange)
    return rows.order_by("-open_time").values_list("open_time", flat=True).first()


def oldest_stored(*, symbol: str, interval: str, market: MarketType) -> int | None:
    """The oldest archived open time for a series — how far the chart can pan."""
    from apps.trading.models import StoredCandle

    return (
        StoredCandle.objects.filter(symbol=symbol, interval=interval, market=market.value)
        .order_by("open_time")
        .values_list("open_time", flat=True)
        .first()
    )


def read_window(
    *,
    symbol: str,
    interval: str,
    market: MarketType,
    limit: int,
    end: int | None = None,
    exchange: str = "",
) -> tuple[list[Candle], str] | None:
    """The newest ``limit`` archived bars at or before ``end``, oldest first.

    ``exchange`` restricts the answer to one venue's rows; empty means any.
    Returns the bars and the venue that produced the oldest of them, or None
    when the archive has nothing for this window.
    """
    from apps.trading.models import StoredCandle

    rows = StoredCandle.objects.filter(symbol=symbol, interval=interval, market=market.value)
    if exchange:
        rows = rows.filter(exchange=exchange)
    if end is not None:
        rows = rows.filter(open_time__lte=end)
    rows = list(rows.order_by("-open_time")[:limit])
    if not rows:
        return None
    rows.reverse()
    candles = [
        Candle(
            time=row.open_time,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    ]
    return candles, rows[0].exchange


def merge(stored: list[Candle], live: list[Candle]) -> list[Candle]:
    """Union two series by open time, oldest first, live winning any collision.

    The live copy wins because it is the exchange's current word on that bar:
    the one at the head is still forming, and the one behind it may have been
    revised after a late trade. The archive supplies only the depth the venue's
    page limit could not reach.
    """
    by_time = {candle.time: candle for candle in stored}
    by_time.update({candle.time: candle for candle in live})
    return [by_time[key] for key in sorted(by_time)]
