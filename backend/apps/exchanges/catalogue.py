"""Downloading what an exchange knows: its pairs, and a year of their history.

Two jobs, one progress row:

1. **Pairs.** Until an account is connected there is no exchange to ask, so
   there is no picker — the panel says "connect an account" rather than
   offering a list somebody made up. Once keys exist, every connected
   exchange's catalogue is pulled and stored.
2. **History.** The chart can only pan back as far as something has stored.
   A year of the busiest pairs is downloaded once, in the background, and the
   accounts page shows how far it has got — a first connect takes minutes to
   an hour and a silent spinner is indistinguishable from a hang.

Both use the credential-free public sources, never an adapter: this is bulk
downloading, it must not share a rate limiter or a key with order routing.

It runs in a thread rather than Celery for the same reason the fan-out does
not use a broker — there is no worker in this deployment. A thread that dies
takes only the download with it; the progress row records why.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from apps.exchanges import candlestore
from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import BACKFILL_TIMEOUT, INTERVALS, MarketDataError, SymbolInfo
from apps.exchanges.marketdata import connected_exchanges, source_for
from apps.trading.models import (
    ExchangeSymbol,
    HistoryRequest,
    HistoryRequestStatus,
    MarketDataSync,
    StoredCandle,
    SyncPhase,
    SyncStatus,
)

logger = logging.getLogger(__name__)

#: Pause between bulk requests. Deliberately generous: this is a background
#: download and being rate-limited off the exchange would also hurt the panel's
#: live feed, which shares the same public endpoints.
REQUEST_PAUSE = 0.12
#: Rows per INSERT, owned by the archive itself.
WRITE_BATCH = candlestore.WRITE_BATCH


def catalogue_sources() -> list[str]:
    """Which exchanges to download the pair list from.

    Connected exchanges first, because that is where the orders go, then the
    configured public providers.

    This used to return nothing at all until an account existed, on the
    reasoning that a pair list with no account behind it was meaningless. It
    was the wrong call twice over: these catalogues are *public* and need no
    credentials, so refusing to fetch them protected nothing — and it left a
    fresh install with an empty symbol picker and no way to see what the
    platform could trade before committing a key to it. The pair list is real
    exchange data either way; what an account changes is only which venues lead
    the order.

    A **pinned** feed (`MARKET_DATA_PIN`) narrows this to that one venue. The
    picker and the price feed have to agree: offering a pair the pinned venue
    does not list means a chart that can only ever answer "no price feed", and
    an order sized off nothing.
    """
    from apps.exchanges.marketdata import pinned_provider
    from apps.exchanges.public_sources import SOURCES

    pin = pinned_provider()
    if pin:
        return [pin]

    ordered = list(connected_exchanges())
    for name in settings.MARKET_DATA["PROVIDERS"]:
        name = name.strip()
        if name in SOURCES and name not in ordered:
            ordered.append(name)
    return ordered


def backfill_settings() -> dict:
    return {
        "intervals": [i for i in settings.MARKET_DATA["BACKFILL_INTERVALS"] if i in INTERVALS],
        "pairs": int(settings.MARKET_DATA["BACKFILL_PAIRS"]),
        "days": int(settings.MARKET_DATA["BACKFILL_DAYS"]),
        "priority_pairs": list(settings.MARKET_DATA.get("BACKFILL_PRIORITY_PAIRS") or []),
    }


# --- pairs ------------------------------------------------------------------


def store_symbols(exchange: str, market: MarketType, rows: list[SymbolInfo]) -> int:
    """Upsert one exchange's catalogue. Delisted pairs are deactivated, not deleted."""
    seen: set[str] = set()
    for info in rows:
        if not info.symbol or not info.base or not info.quote:
            continue
        seen.add(info.symbol)
        ExchangeSymbol.objects.update_or_create(
            exchange=exchange,
            market=market.value,
            symbol=info.symbol,
            defaults={
                "base": info.base,
                "quote": info.quote,
                "native_symbol": info.native,
                "price_tick": info.price_tick,
                "qty_step": info.qty_step,
                "min_qty": info.min_qty,
                "min_notional": info.min_notional,
                "max_leverage": info.max_leverage,
                "volume_24h": info.volume_24h,
                "active": True,
            },
        )
    # A pair the exchange stopped listing must stop being offered, but its
    # stored history and any past trade on it stay readable.
    ExchangeSymbol.objects.filter(exchange=exchange, market=market.value).exclude(
        symbol__in=seen
    ).update(active=False)
    return len(seen)


def sync_symbols(exchange: str) -> int:
    """Download and store every pair ``exchange`` lists. Returns how many.

    Spot is best-effort: several of these venues are futures-only here, and a
    missing spot catalogue is not a failed sync.
    """
    source = source_for(exchange)
    total = 0
    errors: list[str] = []
    for market in (MarketType.FUTURES, MarketType.SPOT):
        try:
            rows = source.symbols(market=market)
        except MarketDataError as exc:
            errors.append(str(exc))
            continue
        except Exception as exc:  # noqa: BLE001 - one market must not kill the other
            errors.append(f"{exchange}: {exc}")
            logger.warning("symbol sync failed for %s %s: %s", exchange, market.value, exc)
            continue
        total += store_symbols(exchange, market, rows)
    if not total:
        raise MarketDataError(
            f"{exchange}: no pairs could be downloaded — " + "; ".join(errors or ["no data"])
        )
    return total


def top_symbols(exchange: str, market: MarketType, limit: int) -> list[str]:
    """The busiest listed pairs, which is what a chart is opened on.

    Priority pairs (from ``BACKFILL_PRIORITY_PAIRS``) are always included
    regardless of their 24h volume, prepended before the volume-sorted list
    and deduplicated by base asset.  Pairs not listed on the exchange are
    skipped so they do not waste a slot.
    """
    rows = ExchangeSymbol.objects.filter(
        exchange=exchange, market=market.value, active=True
    ).order_by("-volume_24h", "symbol")
    priority = [
        p.upper() for p in settings.MARKET_DATA.get("BACKFILL_PRIORITY_PAIRS") or []
    ]
    priority_bases = set(priority)
    # Map each priority base to its full symbol (e.g. "BTC" → "BTCUSDT").
    priority_map: dict[str, str] = {}
    for row in rows:
        base = row.base.upper()
        if base in priority_bases:
            priority_map[base] = row.symbol

    result: list[str] = []
    seen_bases: set[str] = set()
    # Priority pairs first.
    for p in priority:
        sym = priority_map.get(p)
        if sym:
            result.append(sym)
            seen_bases.add(p)
    # Volume-sorted fill.
    for row in rows:
        base = row.base.upper()
        if base not in seen_bases and base not in priority_bases:
            result.append(row.symbol)
            seen_bases.add(base)
            if len(result) >= limit:
                break
    return result


# --- history ----------------------------------------------------------------


def write_candles(exchange: str, symbol: str, market: MarketType, interval: str, candles) -> int:
    """Store bars, ignoring ones already downloaded. Returns rows written.

    A thin delegate so the backfill and the two live writers share one archive
    policy — closed bars only, never pruned. See `exchanges.candlestore`.
    """
    return candlestore.persist(
        exchange=exchange,
        symbol=symbol,
        market=market,
        interval=interval,
        candles=candles,
    )


def backfill_series(
    *,
    exchange: str,
    symbol: str,
    interval: str,
    market: MarketType,
    days: int,
    source=None,
) -> int:
    """Walk one pair/interval back ``days`` and store what the exchange has.

    Exchanges keep different amounts of history (Hyperliquid serves only the
    last 5000 bars at any interval), so "the download stopped early" is a fact
    about the venue, not a failure. Whatever exists is stored; nothing is
    extrapolated to fill the rest.
    """
    source = source or source_for(exchange, timeout=BACKFILL_TIMEOUT)
    step = INTERVALS[interval]
    now = int(time.time())
    floor = now - days * 86400
    page = max(1, source.page_limit)
    # +2 covers the partial first page and one empty probe at the end.
    max_pages = (days * 86400) // (step * page) + 2

    end: int | None = None
    written = 0
    for _ in range(int(max_pages)):
        candles = source.candles(
            symbol=symbol, interval=interval, market=market, limit=page, end=end
        )
        candles = [c for c in candles if c.time >= floor]
        if not candles:
            break
        written += write_candles(exchange, symbol, market, interval, candles)
        oldest = min(c.time for c in candles)
        if end is not None and oldest >= end:
            break  # the exchange is not paging any further back
        end = oldest - 1
        if end <= floor:
            break
        time.sleep(REQUEST_PAUSE)
    return written


# --- the job ----------------------------------------------------------------


def _finish(job: MarketDataSync, status: str, *, detail: str = "", error: str = "") -> None:
    job.status = status
    job.phase = SyncPhase.DONE if status == SyncStatus.DONE else job.phase
    job.detail = detail or job.detail
    job.error = error
    job.finished_at = timezone.now()
    job.save()


def run_sync(job_id: int) -> None:
    """Execute one download job. Safe to call directly (tests, management command)."""
    job = MarketDataSync.objects.get(pk=job_id)
    config = backfill_settings()
    market = MarketType.FUTURES

    job.status = SyncStatus.RUNNING
    job.phase = SyncPhase.SYMBOLS
    job.detail = "downloading pairs"
    job.save()

    exchanges = [job.exchange] if job.exchange else catalogue_sources()
    if not exchanges:
        _finish(
            job,
            SyncStatus.FAILED,
            error="no connected exchange to download from — connect an account first",
        )
        return

    found = 0
    problems: list[str] = []
    for exchange in exchanges:
        try:
            found += sync_symbols(exchange)
        except Exception as exc:  # noqa: BLE001 - recorded, not raised into the thread
            problems.append(f"{exchange}: {exc}")
            logger.warning("pair download failed for %s: %s", exchange, exc)

    job.symbols_found = found
    if not found:
        _finish(job, SyncStatus.FAILED, error="; ".join(problems) or "no pairs downloaded")
        return

    # --- history ---------------------------------------------------------
    plan: list[tuple[str, str, str]] = []
    for exchange in exchanges:
        for symbol in top_symbols(exchange, market, config["pairs"]):
            for interval in config["intervals"]:
                plan.append((exchange, symbol, interval))

    job.phase = SyncPhase.CANDLES
    job.series_total = len(plan)
    job.series_done = 0
    job.detail = f"{config['days']} days of history for {len(plan)} series"
    job.save()

    sources = {name: source_for(name, timeout=BACKFILL_TIMEOUT) for name in exchanges}
    for exchange, symbol, interval in plan:
        if _superseded(job):
            _finish(job, SyncStatus.FAILED, error="superseded by a newer download")
            return
        try:
            job.bars_written += backfill_series(
                exchange=exchange,
                symbol=symbol,
                interval=interval,
                market=market,
                days=config["days"],
                source=sources[exchange],
            )
        except Exception as exc:  # noqa: BLE001 - one pair must not stop the run
            problems.append(f"{exchange} {symbol} {interval}: {exc}")
            logger.warning(
                "history download failed for %s %s %s: %s", exchange, symbol, interval, exc
            )
        job.series_done += 1
        job.detail = f"{symbol} {interval}"
        job.save(update_fields=["series_done", "bars_written", "detail", "updated_at"])

    _finish(
        job,
        SyncStatus.DONE,
        detail=f"{job.bars_written} bars across {job.series_done} series",
        # Partial failures are kept visible rather than swallowed by a green bar.
        error="; ".join(problems[:5]),
    )


def _superseded(job: MarketDataSync) -> bool:
    return MarketDataSync.objects.filter(started_at__gt=job.started_at).exists()


def current_sync() -> MarketDataSync | None:
    return MarketDataSync.objects.order_by("-started_at").first()


def start_sync(exchange: str = "", *, force: bool = False) -> MarketDataSync | None:
    """Kick off a download in the background. Returns the job row it will fill.

    A run already in flight is left alone unless ``force``: the accounts page
    polls this, and a second connect during the first download must not restart
    an hour of work.
    """
    existing = current_sync()
    if existing and existing.status in (SyncStatus.PENDING, SyncStatus.RUNNING) and not force:
        return existing
    if not settings.MARKET_DATA["ENABLED"]:
        return existing

    job = MarketDataSync.objects.create(exchange=exchange)
    thread = threading.Thread(target=_run_in_thread, args=(job.pk,), daemon=True)
    thread.start()
    return job


def _run_in_thread(job_id: int) -> None:
    close_old_connections()
    try:
        run_sync(job_id)
    except Exception as exc:  # noqa: BLE001 - a thread must not die silently
        logger.exception("market data sync failed")
        MarketDataSync.objects.filter(pk=job_id).update(
            status=SyncStatus.FAILED, error=str(exc), finished_at=timezone.now()
        )
    finally:
        close_old_connections()


def sync_state() -> dict:
    """What the accounts page draws: a bar, a phase, and an honest end state."""
    job = current_sync()
    pairs = ExchangeSymbol.objects.filter(active=True).count()
    bars = StoredCandle.objects.count()
    if job is None:
        return {
            "status": "idle",
            "phase": "",
            "percent": 0,
            "pairs": pairs,
            "bars": bars,
            "detail": "",
            "error": "",
            "exchange": "",
            "started_at": None,
            "finished_at": None,
            "connected": bool(catalogue_sources()),
        }
    return {
        "status": job.status,
        "phase": job.phase,
        "percent": job.percent,
        "pairs": pairs,
        "bars": bars,
        "series_done": job.series_done,
        "series_total": job.series_total,
        "bars_written": job.bars_written,
        "detail": job.detail,
        "error": job.error,
        "exchange": job.exchange,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "connected": bool(catalogue_sources()),
    }


def utc(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


# --- on-demand chart history -------------------------------------------------
#
# The bulk download above stores a year for the busiest pairs; every pair after
# that was a blank chart the first time it was opened. ``ensure_history`` is the
# smaller, chart-driven download — at least a day across every timeframe, asked
# for by opening the pair's chart and served by a single worker thread that runs
# the queue oldest-first (FIFO = who asked first wins).

#: A failed pair is not retried on the next poll for this long. Opening the
#: chart polls every CANDLE_POLL_MS; without the cooldown one flaky venue would
#: re-queue the download every poll.
CHART_RETRY_AFTER = 600
#: A row left RUNNING longer than this was a worker that died mid-download; it
#: is reclaimed as failed so the pair can be asked again.
CHART_RUN_TIMEOUT = 900
#: The worker's idle wake-up. A couple of rows are common and cheap to notice.
WORKER_IDLE_SLEEP = 1.0

_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None


def chart_backfill_settings() -> dict:
    return {
        "intervals": [i for i in settings.MARKET_DATA["BACKFILL_INTERVALS"] if i in INTERVALS],
        "days": int(settings.MARKET_DATA["CHART_BACKFILL_DAYS"]),
    }


def _series_covered(market: str, symbol: str, interval: str, days: int) -> bool:
    """True when the pair already has stored history spanning back ``days``.

    One interval step of slack, not the exact floor: venues align bars to their
    own grid, and the paged walk stops with its oldest bar anywhere in
    ``(floor, floor + step]``. Requiring the exact second would re-download a
    pair whose history already covers the span.
    """
    step = INTERVALS.get(interval, INTERVALS["1m"])
    oldest = candlestore.oldest_stored(
        symbol=symbol, interval=interval, market=MarketType(market)
    )
    return oldest is not None and oldest <= int(time.time()) - days * 86400 + step


def _active_request(market: str, symbol: str) -> HistoryRequest | None:
    return (
        HistoryRequest.objects.filter(
            market=market,
            symbol=symbol,
            status__in=(HistoryRequestStatus.PENDING, HistoryRequestStatus.RUNNING),
        )
        .first()
    )


def _last_failure(market: str, symbol: str) -> HistoryRequest | None:
    return (
        HistoryRequest.objects.filter(
            market=market, symbol=symbol, status=HistoryRequestStatus.FAILED
        )
        .exclude(finished_at__isnull=True)
        .order_by("-finished_at")
        .first()
    )


def _queued() -> int:
    return HistoryRequest.objects.filter(
        status__in=(HistoryRequestStatus.PENDING, HistoryRequestStatus.RUNNING)
    ).count()


def _status_dict(
    job: HistoryRequest | None,
    queued: int,
    interval: str,
    *,
    state: str = "",
    error: str = "",
) -> dict:
    """The wire shape for the chart's history block. Kept light — polled often."""
    if not state:
        if job is None:
            state = "none"
        elif job.status in (HistoryRequestStatus.PENDING, HistoryRequestStatus.RUNNING):
            state = "downloading"
        elif job.status == HistoryRequestStatus.DONE:
            state = "ready"
        else:
            state = "failed"
    intervals = [i for i in (job.intervals.split(",") if job and job.intervals else [])]
    return {
        "state": state,
        "interval": interval,
        "days": job.days if job else chart_backfill_settings()["days"],
        "intervals": intervals,
        "series_done": job.series_done if job else 0,
        "series_total": job.series_total if job else 0,
        "percent": job.percent if job else 0,
        "queued": queued,
        "error": error or (job.error if job else ""),
    }


def ensure_history(market: str, symbol: str, interval: str) -> dict:
    """The chart's own history for a pair the bulk backfill never reached.

    Called on every chart poll, so it is cheap: a row is only created the
    first time a pair that has no stored history and no active download needs
    one. Answers a state the panel can draw without parsing anything:

    - ``none`` — chart history is off (no public feed configured).
    - ``ready`` — stored history covers the configured span.
    - ``downloading`` — a download is queued or running; ``percent`` is how far.
    - ``failed`` — the last attempt failed and is inside its retry cooldown.

    Never raises — a history download failing must never take the chart with
    it. When the feed itself is down the caller answers 503 first and this is
    simply not reached.
    """
    config = chart_backfill_settings()
    if not settings.MARKET_DATA["ENABLED"] or not catalogue_sources():
        return _status_dict(None, 0, interval)
    if _series_covered(market, symbol, interval, config["days"]):
        return _status_dict(None, 0, interval, state="ready")

    job = _active_request(market, symbol)
    if job:
        if interval != job.priority_interval:
            # The chart moved timeframes mid-download; make that one first.
            job.priority_interval = interval
            job.save(update_fields=["priority_interval", "updated_at"])
        return _status_dict(job, _queued(), interval)

    last_fail = _last_failure(market, symbol)
    if last_fail and timezone.now() - last_fail.finished_at < timedelta(
        seconds=CHART_RETRY_AFTER
    ):
        return _status_dict(last_fail, _queued(), interval)

    job = HistoryRequest.objects.create(
        market=market,
        symbol=symbol,
        days=config["days"],
        intervals=",".join(config["intervals"]),
        priority_interval=interval,
        series_total=len(config["intervals"]),
    )
    _ensure_worker()
    return _status_dict(job, _queued(), interval)


def _ensure_worker() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(
                target=_worker_loop, name="history-worker", daemon=True
            )
            _worker_thread.start()


def _worker_loop() -> None:
    close_old_connections()
    try:
        while True:
            try:
                if not _drain_once():
                    time.sleep(WORKER_IDLE_SLEEP)
            except Exception:  # noqa: BLE001 - one bad pass must not kill the loop
                logger.exception("history worker pass failed")
                time.sleep(WORKER_IDLE_SLEEP)
    finally:
        close_old_connections()


def _drain_once() -> bool:
    """Run one queued download. Returns True if anything was worked on."""
    reclaimed = _reclaim_stale()
    job = (
        HistoryRequest.objects.filter(status=HistoryRequestStatus.PENDING)
        .order_by("created_at")
        .first()
    )
    if job is None:
        return bool(reclaimed)
    try:
        run_history_request(job.pk)
    except Exception as exc:  # noqa: BLE001 - a failed row is not a dead worker
        logger.exception("history download failed for %s", job.symbol)
        HistoryRequest.objects.filter(pk=job.pk).update(
            status=HistoryRequestStatus.FAILED,
            error=str(exc),
            finished_at=timezone.now(),
        )
    return True


def _reclaim_stale() -> int:
    """A download interrupted by a restart must not sit RUNNING forever."""
    cutoff = timezone.now() - timedelta(seconds=CHART_RUN_TIMEOUT)
    return HistoryRequest.objects.filter(
        status=HistoryRequestStatus.RUNNING, updated_at__lt=cutoff
    ).update(
        status=HistoryRequestStatus.FAILED,
        error="download was interrupted (worker restarted)",
        finished_at=timezone.now(),
    )


def run_history_request(job_id: int) -> None:
    """Execute one on-demand chart download. Safe to call directly (tests)."""
    job = HistoryRequest.objects.get(pk=job_id)
    job.status = HistoryRequestStatus.RUNNING
    job.save(update_fields=["status", "updated_at"])

    intervals = [i for i in job.intervals.split(",") if i]
    if job.priority_interval in intervals:
        intervals = [job.priority_interval] + [i for i in intervals if i != job.priority_interval]

    picked = False
    for exchange in catalogue_sources():
        source = source_for(exchange)
        try:
            probe = source.candles(
                symbol=job.symbol, interval=job.priority_interval, market=MarketType(job.market),
                limit=1,
            )
        except Exception as exc:  # noqa: BLE001 - one venue is not the end of the search
            logger.info("no %s history from %s: %s", job.symbol, exchange, exc)
            continue
        if not probe:
            continue
        job.exchange = exchange
        job.save(update_fields=["exchange", "updated_at"])
        picked = True
        break

    if not picked:
        _finish_request(
            job, HistoryRequestStatus.FAILED, error=f"{job.symbol}: no venue serves history"
        )
        return

    problems: list[str] = []
    for interval in intervals:
        try:
            job.bars_written += backfill_series(
                exchange=job.exchange,
                symbol=job.symbol,
                interval=interval,
                market=MarketType(job.market),
                days=job.days,
            )
        except Exception as exc:  # noqa: BLE001 - one interval must not stop the rest
            problems.append(f"{interval}: {exc}")
            logger.warning("chart history failed for %s %s: %s", job.symbol, interval, exc)
        job.series_done += 1
        job.detail = f"{job.symbol} {interval}"
        job.save(update_fields=["series_done", "bars_written", "detail", "updated_at"])

    if problems:
        # Some intervals stored, some did not: the pair is retryable, not green.
        _finish_request(job, HistoryRequestStatus.FAILED, error="; ".join(problems[:5]))
    else:
        _finish_request(
            job,
            HistoryRequestStatus.DONE,
            detail=f"{job.bars_written} bars across {job.series_done} series",
        )


def _finish_request(job: HistoryRequest, status: str, *, detail: str = "", error: str = "") -> None:
    job.status = status
    job.detail = detail or job.detail
    job.error = error
    job.finished_at = timezone.now()
    job.save()
