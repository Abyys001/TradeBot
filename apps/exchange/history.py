"""Paginated Hyperliquid OHLCV backfill for offline backtesting.

``candleSnapshot`` returns at most ~5000 rows per request. When the requested
range is larger, Hyperliquid returns the **most recent** 5000 bars inside
``[start_ms, end_ms]``. We therefore shrink ``end_ms`` to the oldest bar minus
one millisecond and repeat until ``start_ms`` or the HL history floor is reached.

Note: HL also enforces a retention window per interval (e.g. ~5000 most recent
1h bars). Older intraday history is not available regardless of pagination.
"""
from __future__ import annotations

import time

import pandas as pd

from .candles import _INTERVAL_MS, _normalize_rows
from .hl_constants import normalize_coin, normalize_interval, network_url
from .hl_rate_limit import sanitize_hl_error, with_rate_limit

# Max rows HL returns per candleSnapshot call.
_MAX_ROWS = 5000
# Funding/OI endpoints cap ~500 rows per call.
_FUNDING_MAX_ROWS = 500
# Courtesy pause between paginated calls (seconds) for rate-limit safety.
_SLEEP = 0.2
_FUNDING_SLEEP = 0.6


class HistoryFetchError(Exception):
    """Raised when a paginated history fetch fails."""


@with_rate_limit(weight=20, max_retries=5, max_backoff=16.0)
def _call_candles(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@with_rate_limit(weight=2, max_retries=12, max_backoff=30.0)
def _call_funding(fn, *args, **kwargs):
    return fn(*args, **kwargs)


def fetch_candles_range(
    coin: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    network: str = "testnet",
    sleep: float = _SLEEP,
) -> pd.DataFrame:
    """Fetch all closed candles for *coin*/*interval* in ``[start_ms, end_ms]``.

    Hyperliquid returns up to 5000 candles per call, preferring the newest bars
    inside the requested range. When a full page is returned and the oldest bar
    is still after ``start_ms``, we move ``end_ms`` backward and request again.
    """
    if start_ms >= end_ms:
        raise ValueError("start_ms must be before end_ms")

    from hyperliquid.info import Info

    sym = normalize_coin(coin)
    iv = normalize_interval(interval)

    info = Info(network_url(network), skip_ws=True)

    frames: list[pd.DataFrame] = []
    seen: set[int] = set()
    cursor_end = end_ms

    while cursor_end > start_ms:
        try:
            rows = _call_candles(info.candles_snapshot, sym, iv, start_ms, cursor_end)
        except Exception as exc:  # noqa: BLE001
            raise HistoryFetchError(f"{sym}/{iv}: {exc}") from exc

        df = _normalize_rows(rows)
        if df.empty:
            break

        new = df[~df["ts"].isin(seen)]
        if new.empty:
            break

        frames.append(new)
        seen.update(int(t) for t in new["ts"].tolist())

        oldest = int(new["ts"].min())
        if oldest <= start_ms or len(rows) < _MAX_ROWS:
            break

        cursor_end = oldest - 1
        if sleep:
            time.sleep(sleep)

    if not frames:
        return _normalize_rows([])

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    out = out[(out["ts"] >= start_ms) & (out["ts"] <= end_ms)].reset_index(drop=True)
    return out


_FUNDING_COLUMNS = ["ts", "funding_rate", "premium"]
_OI_COLUMNS = ["ts", "coin", "open_interest"]


def _empty_funding() -> pd.DataFrame:
    return pd.DataFrame(columns=_FUNDING_COLUMNS)


def fetch_funding_range(
    coin: str,
    start_ms: int,
    end_ms: int,
    *,
    network: str = "mainnet",
    sleep: float = _FUNDING_SLEEP,
) -> pd.DataFrame:
    """Fetch funding-rate history for *coin* in ``[start_ms, end_ms]``.

    Pages through ``Info.funding_history`` (~500 rows/call), advancing past the
    newest ``time`` each loop. Stops on the history floor (no new rows) or when
    ``end_ms`` is reached. Returns a deduped, ascending frame with columns
    ``ts, funding_rate, premium``.
    """
    if start_ms >= end_ms:
        raise ValueError("start_ms must be before end_ms")

    from hyperliquid.info import Info

    sym = normalize_coin(coin)
    info = Info(network_url(network), skip_ws=True)

    frames: list[pd.DataFrame] = []
    seen: set[int] = set()
    cursor = start_ms

    while cursor < end_ms:
        try:
            rows = _call_funding(info.funding_history, sym, cursor, end_ms)
        except Exception as exc:  # noqa: BLE001
            raise HistoryFetchError(f"{sym}/funding: {sanitize_hl_error(exc)}") from exc

        if not rows:
            break

        records = []
        for row in rows:
            ts = int(row.get("time"))
            records.append(
                {
                    "ts": ts,
                    "funding_rate": float(row.get("fundingRate", 0) or 0),
                    "premium": float(row.get("premium", 0) or 0),
                }
            )
        df = pd.DataFrame(records, columns=_FUNDING_COLUMNS)
        new = df[~df["ts"].isin(seen)] if not df.empty else df
        if new.empty:
            break

        frames.append(new)
        seen.update(int(t) for t in new["ts"].tolist())

        last_ts = int(new["ts"].max())
        cursor = last_ts + 1
        # Short-circuit when HL returned a partial (<cap) final page.
        if len(rows) < _FUNDING_MAX_ROWS:
            break

        if sleep:
            time.sleep(sleep)

    if not frames:
        return _empty_funding()

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    out = out[(out["ts"] >= start_ms) & (out["ts"] <= end_ms)].reset_index(drop=True)
    return out


def fetch_open_interest_snapshot(
    coins: list[str],
    *,
    network: str = "mainnet",
) -> pd.DataFrame:
    """Return a current open-interest snapshot for *coins*.

    HL exposes no OI history endpoint — ``meta_and_asset_ctxs`` is a point-in-time
    snapshot. One row per requested coin: ``ts=now, coin, open_interest``. Build
    history by polling this forward over time (see ``collect_open_interest``).
    """
    from hyperliquid.info import Info

    wanted = {normalize_coin(c) for c in coins}
    info = Info(network_url(network), skip_ws=True)

    try:
        meta, ctxs = _call_candles(info.meta_and_asset_ctxs)
    except Exception as exc:  # noqa: BLE001
        raise HistoryFetchError(f"open_interest: {exc}") from exc

    universe = (meta or {}).get("universe") or []
    now = int(time.time() * 1000)
    records = []
    for asset, ctx in zip(universe, ctxs or []):
        name = asset.get("name")
        if name in wanted:
            records.append(
                {
                    "ts": now,
                    "coin": name,
                    "open_interest": float((ctx or {}).get("openInterest", 0) or 0),
                }
            )
    return pd.DataFrame(records, columns=_OI_COLUMNS)


__all__ = [
    "HistoryFetchError",
    "fetch_candles_range",
    "fetch_funding_range",
    "fetch_open_interest_snapshot",
]
