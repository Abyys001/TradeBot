"""Dwellir / full-archive OHLCV importer.

Reads columnar Parquet or compressed CSV files (``{market}-{interval}-full.parquet``
or ``{market}-{interval}-full.csv.gz``) and merges into the local PG + Parquet store.

Dwellir column schema:  s, i, t, T, o, h, l, c, v, q, n, x
  s = market/symbol    i = interval    t = open time (ms)    T = close time
  o = open             h = high         l = low               c = close
  v = volume           q = quote vol    n = trades            x = flag
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from apps.exchange.candle_store import save_candles
from apps.exchange.hl_constants import normalize_coin, normalize_interval

logger = logging.getLogger(__name__)

_COLUMNS = ["ts", "open", "high", "low", "close", "volume"]

_DWELLIR_TO_STD = {
    "t": "ts",
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "v": "volume",
}


def _detect_column_map(df: pd.DataFrame) -> dict[str, str]:
    """Map incoming column names to our standard ``_COLUMNS``.

    Supports:
      Dwellir schema (``t, o, h, l, c, v``)
      Binance/BYBIT schema (``timestamp, open, high, low, close, volume``)
      Our own schema (``ts, open, high, low, close, volume``)
    """
    cols_lower = {c.lower().strip(): c for c in df.columns}

    if "t" in cols_lower and "o" in cols_lower and "c" in cols_lower:
        mapping = {}
        for short, std in _DWELLIR_TO_STD.items():
            if short in cols_lower:
                mapping[cols_lower[short]] = std
        if mapping:
            return mapping

    mapping = {}
    for std in _COLUMNS:
        for variant in (std, std.lower(), std.upper()):
            if variant in cols_lower:
                mapping[cols_lower[variant]] = std
                break

    if "timestamp" in cols_lower:
        mapping[cols_lower["timestamp"]] = "ts"
    return mapping


def _parse_filename(path: Path) -> tuple[str | None, str | None]:
    """Extract coin and interval from a Dwellir-style filename.

    ``BTC-1h-full.parquet`` -> (``BTC``, ``1h``)
    ``eth-15m-full.csv.gz`` -> (``ETH``, ``15m``)
    """
    name = path.stem.replace(".csv", "").replace(".gz", "")
    parts = name.split("-")
    if len(parts) >= 2:
        coin_candidate = parts[0].upper()
        iv_candidate = "-".join(parts[1:-1]) if len(parts) > 2 else parts[1]
        return coin_candidate, iv_candidate.lower()
    return None, None


def read_archive(file_path: str | Path) -> pd.DataFrame:
    """Read a Parquet or gzipped CSV archive file into a DataFrame."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"archive not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix == ".gz" or str(path).endswith(".csv.gz"):
        df = pd.read_csv(path, compression="gzip")
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"unsupported archive format: {suffix} (use .parquet or .csv.gz)")

    if df.empty:
        raise ValueError("archive file is empty")
    return df


def normalize_archive(df: pd.DataFrame, *, coin: str | None = None, interval: str | None = None) -> pd.DataFrame:
    """Normalize an archive DataFrame to our standard schema and sort/dedup."""
    mapping = _detect_column_map(df)
    if not mapping:
        raise ValueError(
            f"could not map columns {list(df.columns)} to known schema. "
            f"Expected columns like: t, o, h, l, c, v (Dwellir) "
            f"or ts, open, high, low, close, volume"
        )

    projected = df.rename(columns=mapping)
    missing = [c for c in _COLUMNS if c not in projected.columns]
    if missing:
        raise ValueError(f"mapped columns missing after rename: {missing}")

    out = projected[_COLUMNS].copy()
    out["ts"] = pd.to_numeric(out["ts"], errors="coerce").astype("int64")
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["ts", "open", "high", "low", "close"])
    out = out.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)

    logger.info("normalized archive rows=%s range=%s..%s coin=%s interval=%s",
                len(out), out["ts"].min(), out["ts"].max(), coin, interval)
    return out


def import_archive(
    file_path: str | Path,
    *,
    coin: str | None = None,
    interval: str | None = None,
    network: str = "mainnet",
) -> dict:
    """Read, normalize, and save an archive file into the local store.

    Returns a summary dict with keys: coin, interval, bars, start_ts, end_ts, path.
    """
    path = Path(file_path)

    if coin is None or interval is None:
        guessed_coin, guessed_iv = _parse_filename(path)
        coin = coin or guessed_coin
        interval = interval or guessed_iv

    if not coin or not interval:
        raise ValueError(
            "could not determine coin/interval from filename; "
            "provide them explicitly"
        )

    coin = normalize_coin(coin)
    interval = normalize_interval(interval)

    df = read_archive(file_path)
    df = normalize_archive(df, coin=coin, interval=interval)

    saved_path = save_candles(coin, interval, df, network=network)

    result = {
        "coin": coin,
        "interval": interval,
        "network": network,
        "bars": int(len(df)),
        "start_ts": int(df["ts"].min()),
        "end_ts": int(df["ts"].max()),
        "path": str(saved_path),
    }
    logger.info("archive imported coin=%s interval=%s network=%s bars=%s",
                coin, interval, network, len(df))
    return result
