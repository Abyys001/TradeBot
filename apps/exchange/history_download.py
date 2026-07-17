"""Download market history from Hyperliquid into hybrid PG + Parquet storage."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from django.conf import settings

from apps.exchange.candle_store import earliest_timestamp, latest_timestamp, save_candles, save_funding, save_open_interest
from apps.exchange.candles import _INTERVAL_MS
from apps.exchange.history import (
    HistoryFetchError,
    fetch_candles_range,
    fetch_funding_range,
    fetch_open_interest_snapshot,
)
from apps.exchange.hl_constants import normalize_coin, normalize_interval
from apps.exchange.hl_rate_limit import sanitize_hl_error

logger = logging.getLogger(__name__)

DEFAULT_START = "2020-01-01"

# When Hyperliquid lacks data for a fine interval (~5000 candle retention),
# automatically fall back to coarser intervals for the older range.
_FALLBACK_CHAIN: dict[str, list[str]] = {
    "1m": ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"],
    "3m": ["15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"],
    "5m": ["15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"],
    "15m": ["30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"],
    "30m": ["1h", "2h", "4h", "6h", "12h", "1d", "1w"],
    "1h": ["4h", "12h", "1d", "1w"],
    "2h": ["4h", "12h", "1d", "1w"],
    "4h": ["12h", "1d", "1w"],
    "6h": ["12h", "1d", "1w"],
    "12h": ["1d", "1w"],
    "1d": ["1w"],
    "1w": [],
}
VALID_DATA_TYPES = ("ohlcv", "funding", "open_interest")


def date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def known_perp_coins(network: str) -> set[str]:
    from apps.exchange.hl_meta import _load_meta

    data = _load_meta(network)
    perp = data.get("perp") or {}
    return {item.get("name") for item in perp.get("universe") or [] if item.get("name")}


def ensure_data_available(
    coin: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    network: str = "mainnet",
) -> dict:
    """Guarantee that [start_ms, end_ms] is locally stored; download if needed.

    Returns ``{"status": "ok", ...}`` on success or ``{"status": "failed", "error": ...}``.
    Never raises — failures are encoded in the returned dict.
    """
    from apps.exchange.candle_store import dataset_coverage

    coin = normalize_coin(coin)
    interval = normalize_interval(interval)

    cov = dataset_coverage(network, coin, interval, kind="ohlcv")
    if cov is not None:
        if cov["start_ts"] <= start_ms and cov["end_ts"] >= end_ms:
            return {"status": "ok", "bars": cov["bars"], "note": "coverage satisfied"}

    result = download_pair(coin, interval, start_ms, end_ms, network=network, fallback=True)
    if result.get("status") in ("done", "partial", "skipped"):
        return {"status": "ok", **result}
    return {"status": "failed", "error": result.get("error", "download failed")}


def _effective_start_ms(
    network: str,
    coin: str,
    interval: str,
    requested_start_ms: int,
    *,
    kind: str = "ohlcv",
) -> int:
    """Incremental sync: fetch after latest bar, or backfill if head of range is missing."""
    latest = latest_timestamp(network, coin, interval if kind == "ohlcv" else None, kind=kind)
    if latest is None:
        return requested_start_ms
    if kind == "ohlcv":
        bar_ms = _INTERVAL_MS.get(normalize_interval(interval), 60_000)
        earliest = earliest_timestamp(network, coin, interval, kind="ohlcv")
        if earliest is not None and earliest > requested_start_ms + bar_ms:
            return requested_start_ms
        return max(requested_start_ms, latest + bar_ms)
    return max(requested_start_ms, latest + 1)


def download_pair(
    coin: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    network: str = "mainnet",
    known: set[str] | None = None,
    fallback: bool = True,
) -> dict:
    """Download one coin/interval pair. Returns a progress result dict.

    When *fallback* is True and Hyperliquid returns fewer candles than needed
    (its ~5000-candle retention limit), automatically downloads coarser
    intervals for the missing older range.
    """
    coin = normalize_coin(coin)
    interval = normalize_interval(interval)
    key = f"{coin}/{interval}"

    if known and coin not in known:
        return {"key": key, "status": "skipped", "error": f"{coin} not a HL perp on {network}"}

    effective_start = _effective_start_ms(network, coin, interval, start_ms, kind="ohlcv")
    if effective_start >= end_ms:
        logger.info("asset up to date asset=%s timeframe=%s network=%s", coin, interval, network)
        return {
            "key": key,
            "status": "skipped",
            "error": "already up to date",
            "bars": 0,
        }

    logger.info(
        "sync started asset=%s timeframe=%s network=%s start_ms=%s end_ms=%s",
        coin,
        interval,
        network,
        effective_start,
        end_ms,
    )

    try:
        df = fetch_candles_range(coin, interval, effective_start, end_ms, network=network)
    except HistoryFetchError as exc:
        logger.warning("API failure asset=%s timeframe=%s error=%s", coin, interval, exc)
        return {"key": key, "status": "failed", "error": str(exc)}

    if df.empty:
        return {
            "key": key,
            "status": "empty",
            "bars": 0,
            "error": (
                "Hyperliquid returned no candles for this range. "
                "Try a more recent start date or a coarser interval (1h/4h/1d)."
            ),
        }

    try:
        path = save_candles(coin, interval, df, network=network)
    except OSError as exc:
        return {"key": key, "status": "failed", "error": str(exc)}

    actual_start = int(df["ts"].min())
    bar_ms = _INTERVAL_MS.get(interval, 60_000)
    fallback_results: list[dict] = []
    result: dict = {
        "key": key,
        "status": "done",
        "bars": int(len(df)),
        "start_ts": actual_start,
        "end_ts": int(df["ts"].max()),
        "path": str(path),
    }

    if actual_start > effective_start + bar_ms:
        result["status"] = "partial"
        oldest_available = _ms_to_date(actual_start)
        result["note"] = (
            f"Hyperliquid retains at most ~5000 recent {interval} candles "
            f"(earliest available: {oldest_available}; "
            f"requested {_ms_to_date(start_ms)}). "
            f"Use 1d or 1w for longer history."
        )

        if fallback:
            fb_intervals = _FALLBACK_CHAIN.get(interval, [])
            missing_end = actual_start
            for fb_iv in fb_intervals:
                if start_ms >= missing_end:
                    break
                logger.info(
                    "fallback asset=%s from=%s to=%s range=%s..%s",
                    coin, interval, fb_iv,
                    _ms_to_date(start_ms), _ms_to_date(missing_end),
                )
                try:
                    fb_df = fetch_candles_range(coin, fb_iv, start_ms, missing_end, network=network)
                except HistoryFetchError as exc:
                    logger.warning("fallback API err asset=%s tf=%s err=%s", coin, fb_iv, exc)
                    continue
                if fb_df.empty:
                    continue
                try:
                    fb_path = save_candles(coin, fb_iv, fb_df, network=network)
                except OSError as exc:
                    logger.warning("fallback save err asset=%s tf=%s err=%s", coin, fb_iv, exc)
                    continue
                fb_oldest = int(fb_df["ts"].min())
                fb_bar_ms = _INTERVAL_MS.get(fb_iv, 86_400_000)
                fallback_results.append({
                    "interval": fb_iv,
                    "bars": int(len(fb_df)),
                    "start_ts": fb_oldest,
                    "end_ts": int(fb_df["ts"].max()),
                    "path": str(fb_path),
                })
                if fb_oldest <= start_ms + fb_bar_ms:
                    break
                missing_end = fb_oldest

            if fallback_results:
                joined = ", ".join(r["interval"] for r in fallback_results)
                result["fallback"] = fallback_results
                result["note"] += (
                    f" Auto-downloaded fallback: {joined}."
                )

    logger.info(
        "asset downloaded asset=%s timeframe=%s network=%s bars=%s",
        coin,
        interval,
        network,
        len(df),
    )
    return result


def download_funding(
    coin: str,
    start_ms: int,
    end_ms: int,
    *,
    network: str = "mainnet",
    known: set[str] | None = None,
) -> dict:
    """Backfill funding-rate history for one coin. Returns a progress result dict."""
    coin = normalize_coin(coin)
    key = f"{coin}/funding"

    if known and coin not in known:
        return {"key": key, "status": "skipped", "error": f"{coin} not a HL perp on {network}"}

    effective_start = _effective_start_ms(network, coin, "", start_ms, kind="funding")
    if effective_start >= end_ms:
        return {"key": key, "status": "skipped", "error": "already up to date", "bars": 0}

    logger.info("sync started asset=%s type=funding network=%s", coin, network)

    try:
        df = fetch_funding_range(coin, effective_start, end_ms, network=network)
    except HistoryFetchError as exc:
        logger.warning("API failure asset=%s type=funding error=%s", coin, exc)
        return {"key": key, "status": "failed", "error": str(exc)}

    if df.empty:
        return {"key": key, "status": "empty", "bars": 0}

    try:
        path = save_funding(coin, df, network=network)
    except OSError as exc:
        return {"key": key, "status": "failed", "error": str(exc)}

    logger.info("asset downloaded asset=%s type=funding network=%s bars=%s", coin, network, len(df))
    return {
        "key": key,
        "status": "done",
        "bars": int(len(df)),
        "start_ts": int(df["ts"].min()),
        "end_ts": int(df["ts"].max()),
        "path": str(path),
    }


def download_open_interest(
    coins: list[str],
    *,
    network: str = "mainnet",
    known: set[str] | None = None,
) -> dict[str, dict]:
    """Snapshot current open interest for *coins*. One progress dict per coin."""
    norm = [normalize_coin(c) for c in coins]
    wanted = [c for c in norm if not known or c in known]
    results: dict[str, dict] = {}

    for coin in norm:
        if coin not in wanted:
            results[f"{coin}/oi"] = {
                "key": f"{coin}/oi",
                "status": "skipped",
                "error": f"{coin} not a HL perp on {network}",
            }

    if not wanted:
        return results

    try:
        df = fetch_open_interest_snapshot(wanted, network=network)
    except HistoryFetchError as exc:
        for coin in wanted:
            results[f"{coin}/oi"] = {"key": f"{coin}/oi", "status": "failed", "error": str(exc)}
        return results

    for coin in wanted:
        key = f"{coin}/oi"
        rows = df[df["coin"] == coin][["ts", "open_interest"]] if not df.empty else df
        if rows.empty:
            results[key] = {"key": key, "status": "empty", "bars": 0}
            continue
        try:
            path = save_open_interest(coin, rows, network=network)
        except OSError as exc:
            results[key] = {"key": key, "status": "failed", "error": str(exc)}
            continue
        results[key] = {
            "key": key,
            "status": "done",
            "bars": int(len(rows)),
            "start_ts": int(rows["ts"].min()),
            "end_ts": int(rows["ts"].max()),
            "path": str(path),
            "note": "snapshot — enable scheduled collection for history",
        }
    return results


def _ms_to_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _should_skip_pair(key: str, existing_progress: dict | None) -> bool:
    if not existing_progress:
        return False
    prev = existing_progress.get(key, {})
    if prev.get("status") != "done":
        return False
    return int(prev.get("bars") or 0) > 0


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


def download_history(
    coins: list[str],
    intervals: list[str],
    start_ms: int,
    end_ms: int | None = None,
    *,
    network: str = "mainnet",
    data_types: list[str] | None = None,
    on_progress=None,
    existing_progress: dict | None = None,
    fallback: bool = True,
) -> dict:
    """Download requested *data_types* for *coins*. Optional *on_progress(key, result)*."""
    end_ms = end_ms or int(time.time() * 1000)
    intervals = [normalize_interval(i) for i in intervals]
    data_types = data_types or ["ohlcv"]
    max_workers = getattr(settings, "HISTORY_DOWNLOAD_WORKERS", 4)

    logger.info(
        "sync started coins=%s intervals=%s network=%s data_types=%s",
        coins,
        intervals,
        network,
        data_types,
    )

    try:
        known = known_perp_coins(network)
    except Exception:  # noqa: BLE001
        known = set()

    progress: dict[str, dict] = dict(existing_progress or {})

    def emit(result: dict) -> None:
        progress[result["key"]] = result
        if on_progress:
            on_progress(result["key"], result)

    tasks: list[tuple[str, callable]] = []
    funding_tasks: list[tuple[str, callable]] = []

    if "ohlcv" in data_types:
        for raw_coin in coins:
            for interval in intervals:
                coin = normalize_coin(raw_coin)
                key = f"{coin}/{interval}"
                if _should_skip_pair(key, existing_progress):
                    continue
                tasks.append(
                    (
                        key,
                        lambda c=raw_coin, iv=interval: download_pair(
                            c, iv, start_ms, end_ms, network=network, known=known,
                            fallback=fallback,
                        ),
                    )
                )

    if "funding" in data_types:
        for raw_coin in coins:
            coin = normalize_coin(raw_coin)
            key = f"{coin}/funding"
            if _should_skip_pair(key, existing_progress):
                continue
            funding_tasks.append(
                (
                    key,
                    lambda c=raw_coin: download_funding(
                        c, start_ms, end_ms, network=network, known=known
                    ),
                )
            )

    if "open_interest" in data_types:
        oi_results = download_open_interest(coins, network=network, known=known)
        for result in oi_results.values():
            if not _should_skip_pair(result["key"], existing_progress):
                emit(result)

    if tasks:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fn): key for key, fn in tasks}
            for future in as_completed(futures):
                try:
                    emit(future.result())
                except Exception as exc:  # noqa: BLE001
                    key = futures[future]
                    emit({"key": key, "status": "failed", "error": sanitize_hl_error(exc)})

    if funding_tasks:
        funding_pause = getattr(settings, "HISTORY_FUNDING_COOLDOWN_SEC", 1.5)
        if tasks:
            time.sleep(funding_pause)
        for idx, (key, fn) in enumerate(funding_tasks):
            if idx > 0:
                time.sleep(funding_pause)
            try:
                emit(fn())
            except Exception as exc:  # noqa: BLE001
                emit({"key": key, "status": "failed", "error": sanitize_hl_error(exc)})

    logger.info("sync completed network=%s pairs=%s", network, len(progress))
    return {"progress": progress, "end_ms": end_ms}


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
