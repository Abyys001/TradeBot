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
from datetime import UTC, datetime

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import BACKFILL_TIMEOUT, INTERVALS, MarketDataError, SymbolInfo
from apps.exchanges.marketdata import connected_exchanges, source_for
from apps.trading.models import (
    ExchangeSymbol,
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
#: Rows per INSERT. Big enough to be fast, small enough that a failure loses
#: little and SQLite's parameter cap is never hit.
WRITE_BATCH = 2000


def catalogue_sources() -> list[str]:
    """Which exchanges to download from — and empty means "connect an account".

    Connected exchanges first, because that is where the orders go. A demo
    (paper) account has no exchange to ask, so the configured public providers
    stand in for it; that is still real exchange data, and it keeps spec §9's
    demo mode usable. With **no** account connected at all this is empty and
    the panel says so instead of quietly inventing a pair list.
    """
    from apps.accounts.models import ConnectedAccount
    from apps.exchanges.public_sources import SOURCES

    live = connected_exchanges()
    if live:
        return live
    if not ConnectedAccount.objects.exists():
        return []
    return [p.strip() for p in settings.MARKET_DATA["PROVIDERS"] if p.strip() in SOURCES]


def backfill_settings() -> dict:
    return {
        "intervals": [i for i in settings.MARKET_DATA["BACKFILL_INTERVALS"] if i in INTERVALS],
        "pairs": int(settings.MARKET_DATA["BACKFILL_PAIRS"]),
        "days": int(settings.MARKET_DATA["BACKFILL_DAYS"]),
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
    """The busiest listed pairs, which is what a chart is opened on."""
    rows = ExchangeSymbol.objects.filter(
        exchange=exchange, market=market.value, active=True
    ).order_by("-volume_24h", "symbol")
    return [row.symbol for row in rows[:limit]]


# --- history ----------------------------------------------------------------


def write_candles(exchange: str, symbol: str, market: MarketType, interval: str, candles) -> int:
    """Store bars, ignoring ones already downloaded. Returns rows written."""
    rows = [
        StoredCandle(
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
        for candle in candles
    ]
    written = 0
    for start in range(0, len(rows), WRITE_BATCH):
        chunk = rows[start : start + WRITE_BATCH]
        with transaction.atomic():
            written += len(StoredCandle.objects.bulk_create(chunk, ignore_conflicts=True))
    return written


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
            logger.warning("history download failed for %s %s %s: %s", exchange, symbol, interval, exc)
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
