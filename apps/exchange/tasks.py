"""Celery tasks for periodic account state sync and history downloads."""
from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from apps.credentials.models import ExchangeCredential
from apps.dashboard.publish import publish_dashboard
from apps.exchange.candle_store import save_open_interest
from apps.exchange.history import HistoryFetchError, fetch_open_interest_snapshot
from apps.exchange.hl_client import build_info
from apps.strategies.models import Strategy, StrategyState

from .history_download import download_history
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
    try:
        job = HistoryDownload.objects.select_related("user").get(pk=job_id)
    except HistoryDownload.DoesNotExist:
        logger.warning("download_history_task: job %s not found", job_id)
        return {"ok": False, "error": "job not found"}
    job.status = HistoryDownload.Status.RUNNING
    job.save(update_fields=["status"])
    # Mark queued pairs as running while worker is active
    if job.progress:
        updated = dict(job.progress)
        for key, entry in updated.items():
            if entry.get("status") == "queued":
                updated[key] = {**entry, "status": "running"}
        job.progress = updated
        job.save(update_fields=["progress"])
    publish_dashboard(
        job.user_id,
        {"source": "history_download", "job_id": job.id, "status": "running", "progress": job.progress},
    )

    def on_progress(key: str, result: dict):
        job.progress[key] = result
        job.save(update_fields=["progress"])
        publish_dashboard(
            job.user_id,
            {"source": "history_download", "job_id": job.id, "status": "running", "progress": job.progress},
        )

    try:
        outcome = download_history(
            job.coins,
            job.intervals,
            job.start_ms,
            job.end_ms,
            network=job.network,
            data_types=job.data_types or ["ohlcv"],
            on_progress=on_progress,
            existing_progress=job.progress or {},
        )
        job.progress = outcome["progress"]
        failed = [v for v in job.progress.values() if v.get("status") == "failed"]
        job.status = _final_job_status(job.progress)
        if failed:
            job.error = "; ".join(
                f"{k}: {v.get('error', '')}" for k, v in job.progress.items() if v.get("status") == "failed"
            )
        job.save(update_fields=["status", "progress", "error"])
        publish_dashboard(
            job.user_id,
            {"source": "history_download", "job_id": job.id, "status": job.status, "progress": job.progress},
        )
        return {"ok": True, "job_id": job.id}
    except SoftTimeLimitExceeded:
        # Worker is about to be killed — save current progress so the job can be resumed.
        job.status = HistoryDownload.Status.PARTIAL
        job.error = "task soft time limit reached — re-queue to resume"
        job.save(update_fields=["status", "error"])
        publish_dashboard(
            job.user_id,
            {"source": "history_download", "job_id": job.id, "status": "partial", "progress": job.progress},
        )
        return {"ok": False, "error": "soft time limit"}
    except Exception as exc:  # noqa: BLE001
        job.status = HistoryDownload.Status.FAILED
        job.error = str(exc)
        job.save(update_fields=["status", "error"])
        publish_dashboard(
            job.user_id,
            {"source": "history_download", "job_id": job.id, "status": "failed", "error": str(exc)},
        )
        return {"ok": False, "error": str(exc)}


@shared_task(
    name="exchange.collect_open_interest",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=30,
    retry_backoff_max=120,
    retry_jitter=True,
)
def collect_open_interest_task() -> dict:
    """Append a current open-interest snapshot for configured coins.

    HL exposes no OI history endpoint, so OI history can only be built by polling
    this snapshot forward on a schedule.
    """
    coins = getattr(settings, "OI_COLLECT_COINS", ["BTC", "ETH", "SOL", "HYPE"])
    network = getattr(settings, "OI_COLLECT_NETWORK", "mainnet")
    try:
        df = fetch_open_interest_snapshot(coins, network=network)
    except HistoryFetchError as exc:
        logger.warning("collect_open_interest: %s", exc)
        raise

    saved = 0
    for coin in df["coin"].unique() if not df.empty else []:
        rows = df[df["coin"] == coin][["ts", "open_interest"]]
        try:
            save_open_interest(coin, rows, network=network)
            saved += 1
        except OSError as exc:
            logger.warning("collect_open_interest save %s: %s", coin, exc)
    return {"ok": True, "coins": saved}


@shared_task(
    name="exchange.sync_history_incremental",
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=60,
    retry_backoff_max=300,
    retry_jitter=True,
)
def sync_history_incremental_task() -> dict:
    """Periodic incremental sync for configured assets and timeframes."""
    import time

    coins = getattr(settings, "HISTORY_SYNC_ASSETS", ["BTC", "ETH", "SOL", "HYPE"])
    intervals = getattr(settings, "HISTORY_SYNC_TIMEFRAMES", ["1m", "5m", "15m", "1h"])
    network = getattr(settings, "HISTORY_SYNC_NETWORK", "mainnet")
    # Look back far enough to capture the full HL retention window per interval.
    start_ms = int((time.time() - 400 * 86400) * 1000)

    logger.info("sync started scheduled network=%s coins=%s", network, coins)
    outcome = download_history(
        coins,
        intervals,
        start_ms,
        network=network,
        data_types=["ohlcv"],
        fallback=False,
    )
    done = sum(1 for v in outcome["progress"].values() if v.get("status") == "done")
    partial = sum(1 for v in outcome["progress"].values() if v.get("status") == "partial")
    failed = sum(1 for v in outcome["progress"].values() if v.get("status") == "failed")
    logger.info(
        "sync completed scheduled done=%s partial=%s failed=%s",
        done, partial, failed,
    )
    return {"ok": True, "pairs_done": done, "partial": partial, "failed": failed}


@shared_task(name="exchange.sync_account_state")
def sync_account_state_task(credential_id: int) -> dict:
    cred = ExchangeCredential.objects.filter(pk=credential_id, is_active=True).first()
    if cred is None:
        return {"ok": False, "error": "credential not active"}

    info = build_info(cred.network)
    state = info.user_state(cred.wallet_address) or {}
    positions = state.get("assetPositions") or []

    unrealized = Decimal("0")
    for item in positions:
        pos = (item or {}).get("position") or {}
        try:
            unrealized += Decimal(str(pos.get("unrealizedPnl", "0")))
        except Exception:  # noqa: BLE001
            continue

    StrategyState.objects.filter(strategy__credential=cred).update(
        position={"assetPositions": positions},
        pnl=unrealized,
    )
    return {"ok": True, "credential_id": credential_id, "pnl": str(unrealized)}


@shared_task(name="exchange.download_dwellir_archive", bind=True, max_retries=3)
def download_dwellir_archive_task(
    self,
    coin: str,
    interval: str,
    network: str = "mainnet",
    job_id: int | None = None,
) -> dict:
    """Download a Dwellir OHLCV archive and import it into local storage.

    Uses streaming HTTP download to avoid loading the whole file into RAM,
    then pipes to the existing columnar import pipeline (Parquet + PG bulk
    insert) without any row-by-row ORM interaction.
    """
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
    """Fetch fills via REST when the WS userFills channel reaches its 2000-item limit.

    Queries the ``userFillsByTime`` HL REST endpoint, deduplicates against
    existing ``OrderRecord.exchange_order_id`` values, and applies each new
    fill via ``apply_user_fill``.
    """
    import time

    import requests as http

    from apps.credentials.models import ExchangeCredential
    from apps.exchange.hl_constants import network_url
    from apps.execution.order_sync import apply_user_fill

    cred = ExchangeCredential.objects.filter(pk=credential_id, is_active=True).first()
    if cred is None:
        return {"ok": False, "error": "credential not found"}

    start_ms = since_ms or int((time.time() - 3600) * 1000)

    payload = {
        "type": "userFillsByTime",
        "user": cred.wallet_address,
        "startTime": start_ms,
    }
    try:
        resp = http.post(
            f"{network_url(cred.network)}/info",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        fills = resp.json() or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_fills_rest failed cred=%s: %s", credential_id, exc)
        return {"ok": False, "error": str(exc)}

    from apps.execution.models import OrderRecord

    base_qs = OrderRecord.objects.filter(strategy__credential_id=credential_id)
    existing_oids = set(base_qs.values_list("exchange_order_id", flat=True))
    existing_cloids = set(
        base_qs.exclude(client_order_id="").values_list("client_order_id", flat=True)
    )

    applied = 0
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        oid = str(fill.get("oid", "") or "")
        cloid = str(fill.get("cloid", "") or "")
        if (oid and oid in existing_oids) or (cloid and cloid in existing_cloids):
            continue
        try:
            apply_user_fill(credential_id=credential_id, fill=fill)
            applied += 1
        except Exception:  # noqa: BLE001
            logger.exception("apply_user_fill failed for oid=%s", oid)

    logger.info("fetch_fills_rest cred=%s applied=%d", credential_id, applied)
    return {"ok": True, "applied": applied}


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

