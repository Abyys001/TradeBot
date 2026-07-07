"""Hyperliquid REST candle fetcher for live strategy warmup."""
from __future__ import annotations

import time

import pandas as pd

from .hl_constants import BAR_MAP, normalize_coin, normalize_interval, network_url

# Approximate ms per bar for pagination window sizing.
_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}


class CandleFetchError(Exception):
    """Raised when Hyperliquid candle fetch fails."""


def _normalize_rows(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])

    records = []
    for row in rows:
        records.append(
            {
                "ts": int(row["t"]),
                "open": float(row["o"]),
                "high": float(row["h"]),
                "low": float(row["l"]),
                "close": float(row["c"]),
                "volume": float(row.get("v", 0)),
            }
        )
    df = pd.DataFrame(records)
    return df.sort_values("ts").reset_index(drop=True)


def fetch_candles(
    coin: str,
    bar: str,
    limit: int,
    *,
    network: str = "testnet",
) -> pd.DataFrame:
    """Fetch the last *limit* closed candles via ``Info.candles_snapshot``."""
    if limit <= 0:
        raise ValueError("limit must be positive")

    from django.conf import settings
    from hyperliquid.info import Info

    interval = normalize_interval(bar)
    symbol = normalize_coin(coin)
    _timeout = getattr(settings, "HL_API_TIMEOUT", 30)
    info = Info(network_url(network), skip_ws=True, timeout=_timeout)

    end_time = int(time.time() * 1000)
    bar_ms = _INTERVAL_MS.get(interval, 60_000)
    start_time = end_time - (limit * bar_ms)

    try:
        rows = info.candles_snapshot(symbol, interval, start_time, end_time)
    except Exception as exc:  # noqa: BLE001
        raise CandleFetchError(str(exc)) from exc

    if not rows:
        return _normalize_rows([])

    df = _normalize_rows(rows)
    if len(df) > limit:
        df = df.iloc[-limit:].reset_index(drop=True)
    return df


# Re-export for dashboard / API consumers.
__all__ = ["BAR_MAP", "CandleFetchError", "fetch_candles"]
