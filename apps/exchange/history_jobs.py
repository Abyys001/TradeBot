"""Exchange-agnostic helpers for history/archive import job tracking.

Extracted from the deleted Hyperliquid ``history_download`` module — these are the
pure job-progress + date utilities that survive the move to Tabdeal-only (which has
no candle backfill). The HL download-from-exchange logic itself is gone; only the
Dwellir archive-import path (apps.exchange.archive_importer) still creates jobs.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .constants import normalize_coin, normalize_interval

DEFAULT_START = "2020-01-01"
VALID_DATA_TYPES = ("ohlcv", "funding", "open_interest")


def date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def reset_pairs_for_retry(progress: dict | None) -> dict:
    """Re-queue pairs that failed or returned no data."""
    updated = dict(progress or {})
    for key, entry in updated.items():
        if entry.get("status") in {"empty", "failed", "skipped"}:
            updated[key] = {"key": key, "status": "queued"}
    return updated


def job_has_retryable_pairs(progress: dict | None) -> bool:
    return any(
        entry.get("status") in {"empty", "failed", "skipped"}
        for entry in (progress or {}).values()
    )


def build_initial_progress(
    coins: list[str],
    intervals: list[str],
    data_types: list[str] | None = None,
) -> dict[str, dict]:
    """Pre-populate progress keys so the UI can show queued pairs immediately."""
    data_types = data_types or ["ohlcv"]
    progress: dict[str, dict] = {}
    norm_coins = [normalize_coin(c) for c in coins]

    if "ohlcv" in data_types:
        for coin in norm_coins:
            for interval in intervals:
                iv = normalize_interval(interval)
                key = f"{coin}/{iv}"
                progress[key] = {"key": key, "status": "queued"}

    if "funding" in data_types:
        for coin in norm_coins:
            key = f"{coin}/funding"
            progress[key] = {"key": key, "status": "queued"}

    if "open_interest" in data_types:
        for coin in norm_coins:
            key = f"{coin}/oi"
            progress[key] = {"key": key, "status": "queued"}

    return progress
