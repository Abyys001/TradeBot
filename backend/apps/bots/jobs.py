"""A backtest as a job, so the wait can be shown instead of endured.

A first run on a pair the archive has never seen spends most of its time
downloading — up to ``DOWNLOAD_BUDGET_SECONDS`` of paging back through a public
endpoint — and a request that returns in ninety seconds behind a spinner is
indistinguishable from one that has hung. So the POST opens a ``BacktestJob``
and returns immediately, a thread does the work, and the panel polls the row.

A thread and not a broker, following ``apps/exchanges/catalogue.py``: this
deployment runs no Celery worker for anything, the work is one bounded call, and
a broker round trip would add a hop to something that already has a clock.

**Phase weighting lives here and nowhere else.** The panel draws one bar; if it
had to know that downloading is most of the wait and validation is none of it,
every client would carry a copy of that judgement. The server sends one number.

The job never holds the report. It points at a ``BacktestRun``, which is where
stored reports have always lived, so nothing downstream learns about jobs.
"""

from __future__ import annotations

import logging
import threading
from decimal import Decimal, InvalidOperation

from django.db import close_old_connections
from django.utils import timezone

from apps.bots.models import BacktestJob, BacktestRun, JobStatus, StrategyVersion

logger = logging.getLogger(__name__)

#: How much of the single progress bar each phase owns, in order. Downloading
#: gets the lion's share because it is the lion's share of the wall clock; the
#: alternative is a bar that sits at 4% for a minute and then jumps to done.
PHASE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("validating", 0.02),
    ("downloading", 0.70),
    ("replaying", 0.26),
    ("finishing", 0.02),
)

#: Written at most this often per phase, so a 200,000-bar replay does not spend
#: its time writing progress rows.
MIN_PROGRESS_STEP = 0.005


def start(version: StrategyVersion, payload: dict, *, actor: str = "") -> BacktestJob:
    """Open the row and hand it to a thread. Returns before any work happens."""
    job = BacktestJob.objects.create(
        strategy_version=version,
        request=payload,
        status=JobStatus.QUEUED,
        created_by=actor,
    )
    thread = threading.Thread(target=_work, args=(job.pk,), daemon=True, name=f"backtest-{job.pk}")
    thread.start()
    return job


def state(job: BacktestJob) -> dict:
    """What the panel polls. Flat, small, and safe to fetch every second."""
    return {
        "id": job.id,
        "status": job.status,
        "progress": round(job.progress, 4),
        "detail": job.detail or {},
        "error": job.error,
        "backtest_id": job.result_id,
        "finished": job.finished,
        "created_at": job.created_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


# --- the worker -------------------------------------------------------------


def _work(job_id: int) -> None:
    close_old_connections()
    try:
        _execute(job_id)
    except Exception as exc:  # noqa: BLE001 - a thread must never die silently
        logger.exception("backtest job %s failed", job_id)
        BacktestJob.objects.filter(pk=job_id).update(
            status=JobStatus.FAILED, error=str(exc), finished_at=timezone.now()
        )
    finally:
        close_old_connections()


def _execute(job_id: int) -> None:
    from apps.bots import backtest
    from apps.exchanges.base import MarketType
    from apps.pine import properties as props

    job = BacktestJob.objects.select_related("strategy_version").get(pk=job_id)
    payload = job.request or {}
    reporter = _Reporter(job_id)

    overrides, errors = props.validate_overrides(payload.get("property_overrides"))
    if errors:
        _fail(job_id, "; ".join(row["message"] for row in errors))
        return

    try:
        report = backtest.run(
            source=job.strategy_version.source,
            symbol=str(payload.get("symbol", "")).upper(),
            interval=str(payload.get("interval", "1h")),
            market=MarketType(payload.get("market", "futures")),
            from_time=int(payload["from_time"]),
            to_time=int(payload["to_time"]),
            leverage=int(payload.get("leverage", 1)),
            sl_pct=_decimal(payload.get("sl_pct")),
            tp_pct=_decimal(payload.get("tp_pct")),
            inputs=payload.get("inputs") or {},
            property_overrides=overrides,
            progress=reporter,
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        _fail(job_id, f"bad request: {exc}")
        return
    except backtest.BacktestError as exc:
        _fail(job_id, str(exc))
        return

    stored = store(job.strategy_version, report, payload, job.created_by)
    BacktestJob.objects.filter(pk=job_id).update(
        status=JobStatus.DONE,
        progress=1.0,
        result=stored,
        detail={"trades": len(report.trades), "bars": report.bars, **report.data_source},
        finished_at=timezone.now(),
    )


def store(version: StrategyVersion, report, payload: dict, actor: str) -> BacktestRun:
    """Persist a finished report. Shared with the synchronous endpoint.

    One function because the two entry points must produce identical rows: a
    report opened from history has to read the same whether the run that made it
    was polled or awaited.
    """
    data = report.as_dict()
    return BacktestRun.objects.create(
        strategy_version=version,
        symbol=report.symbol,
        interval=report.interval,
        market=payload.get("market", "futures"),
        from_time=report.from_time,
        to_time=report.to_time,
        input_values=payload.get("inputs") or {},
        bars=report.bars,
        trades=len(report.trades),
        metrics=data["metrics"],
        # The sentences travel with the numbers. Reopening a stored run has to
        # show the same header the run was read under, and `lines()` is derived
        # from wording that will be edited — a row rebuilt from today's code
        # would caption last month's report with this month's assumptions.
        assumptions={
            **data["assumptions"],
            "lines": report.assumptions.lines(),
            "data_source": data["data_source"],
        },
        equity_curve=data["equity_curve"],
        trade_log=data["trades"],
        intent_digest=report.intent_digest,
        created_by=actor,
    )


class _Reporter:
    """Turns ``(phase, fraction, detail)`` into one number and one row write."""

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        self.last = -1.0
        self.offsets: dict[str, tuple[float, float]] = {}
        running = 0.0
        for name, weight in PHASE_WEIGHTS:
            self.offsets[name] = (running, weight)
            running += weight

    def __call__(self, phase: str, done: float, detail: dict) -> None:
        offset, weight = self.offsets.get(phase, (0.0, 0.0))
        overall = min(1.0, max(0.0, offset + weight * min(1.0, max(0.0, done))))
        # A phase boundary is always written even when the bar barely moved:
        # the phase *label* changing is information on its own, and it is what
        # tells an operator the download finished and the replay began.
        crossed = phase != (self._phase or "")
        if not crossed and overall - self.last < MIN_PROGRESS_STEP:
            return
        self.last = overall
        self._phase = phase
        BacktestJob.objects.filter(pk=self.job_id).update(
            status=phase if phase in JobStatus.values else JobStatus.REPLAYING,
            progress=overall,
            detail={"phase": phase, **detail},
        )

    _phase: str | None = None


def _fail(job_id: int, message: str) -> None:
    BacktestJob.objects.filter(pk=job_id).update(
        status=JobStatus.FAILED, error=message, finished_at=timezone.now()
    )


def _decimal(value):
    return None if value in (None, "") else Decimal(str(value))
