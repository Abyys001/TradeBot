"""Celery tasks for paper trading."""
from __future__ import annotations

import logging

from celery import shared_task

from .models import PaperAccount
from .runner import PaperIncrementalRunner

logger = logging.getLogger(__name__)


@shared_task(name="paper.start", autoretry_for=(Exception,), max_retries=3, default_retry_delay=10)
def start_paper_task(account_id: int):
    account = PaperAccount.objects.select_related("strategy", "strategy__user").get(pk=account_id)
    runner = PaperIncrementalRunner()
    try:
        runner.start(account)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@shared_task(name="paper.stop")
def stop_paper_task(account_id: int):
    account = PaperAccount.objects.select_related("strategy").get(pk=account_id)
    PaperIncrementalRunner().stop(account)
    return {"ok": True}


@shared_task(name="paper.process_bar", autoretry_for=(Exception,), max_retries=2, default_retry_delay=5)
def process_paper_bar_task(strategy_id: int, candle: dict):
    accounts = PaperAccount.objects.filter(
        is_active=True,
        strategy_id=strategy_id,
    ).select_related("strategy")
    if not accounts:
        return {"ok": True, "skipped": True}

    runner = PaperIncrementalRunner()
    processed = 0
    for account in accounts:
        try:
            if runner.on_closed_candle(account, candle):
                processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("paper bar processing failed for account strategy=%s", strategy_id)
            return {"ok": False, "error": str(exc)}
    return {"ok": True, "processed": processed}
