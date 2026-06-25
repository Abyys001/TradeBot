"""Celery tasks for periodic account state sync and history downloads."""
from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
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
    except Exception as exc:  # noqa: BLE001
        job.status = HistoryDownload.Status.FAILED
        job.error = str(exc)
        job.save(update_fields=["status", "error"])
        publish_dashboard(
            job.user_id,
            {"source": "history_download", "job_id": job.id, "status": "failed", "error": str(exc)},
        )
        return {"ok": False, "error": str(exc)}


@shared_task(name="exchange.collect_open_interest")
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
        return {"ok": False, "error": str(exc)}

    saved = 0
    for coin in df["coin"].unique() if not df.empty else []:
        rows = df[df["coin"] == coin][["ts", "open_interest"]]
        try:
            save_open_interest(coin, rows, network=network)
            saved += 1
        except OSError as exc:
            logger.warning("collect_open_interest save %s: %s", coin, exc)
    return {"ok": True, "coins": saved}


@shared_task(name="exchange.sync_history_incremental")
def sync_history_incremental_task() -> dict:
    """Periodic incremental sync for configured assets and timeframes."""
    coins = getattr(settings, "HISTORY_SYNC_ASSETS", ["BTC", "ETH", "SOL", "HYPE"])
    intervals = getattr(settings, "HISTORY_SYNC_TIMEFRAMES", ["1m", "5m", "15m", "1h"])
    network = getattr(settings, "HISTORY_SYNC_NETWORK", "mainnet")
    start_ms = int((__import__("time").time() - 365 * 86400) * 1000)

    logger.info("sync started scheduled network=%s coins=%s", network, coins)
    outcome = download_history(
        coins,
        intervals,
        start_ms,
        network=network,
        data_types=["ohlcv"],
    )
    done = sum(1 for v in outcome["progress"].values() if v.get("status") == "done")
    logger.info("sync completed scheduled pairs_done=%s", done)
    return {"ok": True, "pairs_done": done, "progress": outcome["progress"]}


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

