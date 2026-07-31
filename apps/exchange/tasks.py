"""Celery tasks for periodic account state sync and history downloads."""
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.credentials.models import ExchangeCredential
from apps.dashboard.publish import publish_dashboard
from apps.strategies.models import Strategy, StrategyState

from .models import HistoryDownload

logger = logging.getLogger(__name__)


def _final_job_status(progress: dict) -> str:
    values = list(progress.values())
    if not values:
        return HistoryDownload.Status.FAILED

    has_done = any(v.get("status") in {"done", "partial"} for v in values)
    has_empty = any(v.get("status") == "empty" for v in values)
    has_failed = any(v.get("status") == "failed" for v in values)
    has_skipped = any(v.get("status") == "skipped" for v in values)
    has_partial = any(v.get("status") == "partial" for v in values)

    if not has_done and (has_empty or has_failed):
        return HistoryDownload.Status.FAILED
    if has_failed or has_empty or has_skipped or has_partial:
        return HistoryDownload.Status.PARTIAL
    return HistoryDownload.Status.DONE


@shared_task(name="exchange.import_archive")
def import_archive_task(
    file_path: str,
    coin: str | None = None,
    interval: str | None = None,
    network: str = "mainnet",
    job_id: int | None = None,
) -> dict:
    """Celery task: import a Dwellir Parquet/CSV archive into local storage."""
    from .archive_importer import import_archive as _do_import

    if job_id:
        from .models import HistoryDownload
        job = HistoryDownload.objects.filter(pk=job_id).first()
        if job:
            job.status = HistoryDownload.Status.RUNNING
            job.save(update_fields=["status"])

    try:
        result = _do_import(file_path, coin=coin, interval=interval, network=network)
        key = f"{result['coin']}/{result['interval']}"
        progress = {
            key: {
                "key": key,
                "status": "done",
                "bars": result["bars"],
                "start_ts": result["start_ts"],
                "end_ts": result["end_ts"],
                "path": result["path"],
            }
        }
        if job_id and job:
            job.progress = progress
            job.status = HistoryDownload.Status.DONE
            job.save(update_fields=["status", "progress"])
            from apps.dashboard.publish import publish_dashboard
            publish_dashboard(job.user_id, {
                "source": "history_download",
                "job_id": job.id,
                "status": "done",
                "progress": progress,
            })
        return {"ok": True, **result}
    except Exception as exc:
        logger.error("archive import failed: %s", exc)
        if job_id and job:
            job.status = HistoryDownload.Status.FAILED
            job.error = str(exc)
            job.save(update_fields=["status", "error"])
        return {"ok": False, "error": str(exc)}


@shared_task(name="exchange.download_history")
def download_history_task(job_id: int) -> dict:
    """Download history from exchange. DEPRECATED: HL download removed."""
    try:
        job = HistoryDownload.objects.select_related("user").get(pk=job_id)
    except HistoryDownload.DoesNotExist:
        logger.warning("download_history_task: job %s not found", job_id)
        return {"ok": False, "error": "job not found"}
    
    job.status = HistoryDownload.Status.FAILED
    job.error = "Hyperliquid download has been removed. Use Tabdeal ingest instead."
    job.save(update_fields=["status", "error"])
    return {"ok": False, "error": "HL download removed"}


@shared_task(
    name="exchange.collect_open_interest",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=30,
    retry_backoff_max=120,
    retry_jitter=True,
)
def collect_open_interest_task() -> dict:
    """Collect open interest. DEPRECATED: HL OI collection removed."""
    logger.warning("collect_open_interest: HL OI collection removed")
    return {"ok": True, "coins": 0}


@shared_task(
    name="exchange.sync_history_incremental",
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=60,
    retry_backoff_max=300,
    retry_jitter=True,
)
def sync_history_incremental_task() -> dict:
    """Incremental sync. DEPRECATED: HL sync removed."""
    logger.warning("sync_history_incremental: HL sync removed")
    return {"ok": True, "pairs_done": 0, "partial": 0, "failed": 0}


@shared_task(name="exchange.sync_account_state")
def sync_account_state_task(credential_id: int) -> dict:
    """Sync account state. DEPRECATED: HL sync removed."""
    logger.warning("sync_account_state: HL sync removed for cred %s", credential_id)
    return {"ok": True, "credential_id": credential_id, "pnl": "0"}


@shared_task(name="exchange.download_dwellir_archive", bind=True, max_retries=3)
def download_dwellir_archive_task(
    self,
    coin: str,
    interval: str,
    network: str = "mainnet",
    job_id: int | None = None,
) -> dict:
    """Download a Dwellir OHLCV archive and import it into local storage."""
    import tempfile
    from pathlib import Path

    from apps.exchange.dwellir import DwellirDownloadError, DwellirDownloader

    tmp_dir = Path(tempfile.mkdtemp(prefix="dwellir_"))
    local_path: Path | None = None
    try:
        local_path = DwellirDownloader().download(coin, interval, dest_dir=tmp_dir)
        result = import_archive_task(
            str(local_path),
            coin=coin,
            interval=interval,
            network=network,
            job_id=job_id,
        )
        return result
    except DwellirDownloadError as exc:
        logger.error("dwellir download failed coin=%s interval=%s: %s", coin, interval, exc)
        delay = 30 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=delay)
    except Exception as exc:  # noqa: BLE001
        logger.error("dwellir import failed coin=%s interval=%s: %s", coin, interval, exc)
        return {"ok": False, "error": str(exc)}
    finally:
        if local_path is not None:
            local_path.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


@shared_task(name="exchange.fetch_fills_rest")
def fetch_fills_rest_task(credential_id: int, since_ms: int | None = None) -> dict:
    """Fetch fills via REST. DEPRECATED: HL fills fetch removed."""
    logger.warning("fetch_fills_rest: HL fills fetch removed for cred %s", credential_id)
    return {"ok": True, "applied": 0}


@shared_task(name="exchange.sync_active_accounts")
def sync_active_accounts_task() -> dict:
    creds = (
        ExchangeCredential.objects.filter(is_active=True, strategies__status=Strategy.Status.ACTIVE)
        .distinct()
        .values_list("id", flat=True)
    )
    for cid in creds:
        sync_account_state_task.delay(cid)
    return {"ok": True, "count": len(list(creds))}


@shared_task(name="exchange.backfill_candles")
def backfill_candles_task(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    strategy_id: int | None = None,
) -> dict:
    """Celery wrapper around the ``backfill_candles`` command.

    Rebuilding a long recording run can take minutes, so the dashboard fires this
    rather than blocking a request.
    """
    import io

    from django.core.management import call_command

    args: list[str] = []
    if strategy_id:
        args += ["--strategy-id", str(strategy_id)]
    if symbols:
        args += ["--symbols", *symbols]
    if timeframes:
        args += ["--timeframes", *timeframes]

    out = io.StringIO()
    try:
        call_command("backfill_candles", *args, stdout=out, stderr=out)
    except Exception as exc:  # noqa: BLE001 — report failure to the caller, don't retry blindly
        return {"ok": False, "error": str(exc), "output": out.getvalue()}
    return {"ok": True, "output": out.getvalue()}
