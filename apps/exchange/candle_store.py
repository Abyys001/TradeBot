"""Hybrid market-data storage: PostgreSQL (canonical) + Parquet (backtest reads).

Layout: ``<CANDLE_DATA_DIR>/<network>/<COIN>/<interval>.parquet``. Legacy paths
without the network segment are still read for backward compatibility.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import sys
if sys.platform == "win32":
    import portalocker as fcntl
else:
    import fcntl

import pandas as pd
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Min

from .hl_constants import normalize_coin, normalize_interval
from .models import Candle, FundingRate, OpenInterest

logger = logging.getLogger(__name__)

_COLUMNS = ["ts", "open", "high", "low", "close", "volume"]
_FUNDING_COLUMNS = ["ts", "funding_rate", "premium"]
_OI_COLUMNS = ["ts", "open_interest"]
_BULK_CHUNK = 1000


def _data_root() -> Path:
    return candle_data_dir().parent


def candle_data_dir() -> Path:
    return Path(getattr(settings, "CANDLE_DATA_DIR", settings.BASE_DIR / "data" / "candles"))


def candle_path(coin: str, interval: str, *, network: str = "mainnet") -> Path:
    coin = normalize_coin(coin)
    interval = normalize_interval(interval)
    return candle_data_dir() / network / coin / f"{interval}.parquet"


def _legacy_candle_path(coin: str, interval: str) -> Path:
    coin = normalize_coin(coin)
    interval = normalize_interval(interval)
    return candle_data_dir() / coin / f"{interval}.parquet"


def funding_path(coin: str, *, network: str = "mainnet") -> Path:
    return _data_root() / "funding" / network / f"{normalize_coin(coin)}.parquet"


def _legacy_funding_path(coin: str) -> Path:
    return _data_root() / "funding" / f"{normalize_coin(coin)}.parquet"


def open_interest_path(coin: str, *, network: str = "mainnet") -> Path:
    return _data_root() / "open_interest" / network / f"{normalize_coin(coin)}.parquet"


def _legacy_open_interest_path(coin: str) -> Path:
    return _data_root() / "open_interest" / f"{normalize_coin(coin)}.parquet"


def _resolve_path(new_path: Path, legacy_path: Path) -> Path | None:
    if new_path.exists():
        return new_path
    if legacy_path.exists():
        return legacy_path
    return None


@contextmanager
def _parquet_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _save_parquet(path: Path, df: pd.DataFrame, columns: list[str], dedup_key: str) -> Path:
    incoming = df[columns].copy() if not df.empty else pd.DataFrame(columns=columns)
    with _parquet_lock(path):
        if path.exists():
            existing = pd.read_parquet(path)
            merged = pd.concat([existing, incoming], ignore_index=True)
        else:
            merged = incoming

        merged = (
            merged.drop_duplicates(subset=dedup_key)
            .sort_values(dedup_key)
            .reset_index(drop=True)
        )
        merged.to_parquet(path, index=False, engine="pyarrow")
    return path


def _bulk_insert(model, objects: list) -> int:
    if not objects:
        return 0
    inserted = 0
    for i in range(0, len(objects), _BULK_CHUNK):
        chunk = objects[i : i + _BULK_CHUNK]
        model.objects.bulk_create(chunk, ignore_conflicts=True)
        inserted += len(chunk)
    return inserted


def _df_to_candles(network: str, coin: str, interval: str, df: pd.DataFrame) -> list[Candle]:
    coin = normalize_coin(coin)
    interval = normalize_interval(interval)
    rows: list[Candle] = []
    for row in df.itertuples(index=False):
        rows.append(
            Candle(
                network=network,
                asset=coin,
                timeframe=interval,
                timestamp=int(row.ts),
                open=Decimal(str(row.open)),
                high=Decimal(str(row.high)),
                low=Decimal(str(row.low)),
                close=Decimal(str(row.close)),
                volume=Decimal(str(row.volume)),
            )
        )
    return rows


def save_candles(
    coin: str,
    interval: str,
    df: pd.DataFrame,
    *,
    network: str = "mainnet",
) -> Path:
    """Dual-write: PostgreSQL bulk insert + Parquet merge."""
    coin = normalize_coin(coin)
    interval = normalize_interval(interval)
    path = candle_path(coin, interval, network=network)

    if not df.empty:
        projected = df[_COLUMNS].copy()
        count = _bulk_insert(Candle, _df_to_candles(network, coin, interval, projected))
        logger.info(
            "records inserted asset=%s timeframe=%s network=%s count=%s",
            coin,
            interval,
            network,
            count,
        )
        try:
            _save_parquet(path, projected, _COLUMNS, "ts")
        except Exception as exc:
            raise OSError(f"Parquet write failed for {coin}/{interval}: {exc}") from exc
    return path


def save_funding(
    coin: str,
    df: pd.DataFrame,
    *,
    network: str = "mainnet",
) -> Path:
    coin = normalize_coin(coin)
    path = funding_path(coin, network=network)
    if not df.empty:
        projected = df[_FUNDING_COLUMNS].copy()
        objects = [
            FundingRate(
                network=network,
                asset=coin,
                timestamp=int(row.ts),
                funding_rate=Decimal(str(row.funding_rate)),
                premium=Decimal(str(getattr(row, "premium", 0))),
            )
            for row in projected.itertuples(index=False)
        ]
        _bulk_insert(FundingRate, objects)
        try:
            _save_parquet(path, projected, _FUNDING_COLUMNS, "ts")
        except Exception as exc:
            raise OSError(f"Parquet write failed for funding {coin}: {exc}") from exc
    return path


def save_open_interest(
    coin: str,
    df: pd.DataFrame,
    *,
    network: str = "mainnet",
) -> Path:
    coin = normalize_coin(coin)
    path = open_interest_path(coin, network=network)
    if not df.empty:
        projected = df[_OI_COLUMNS].copy()
        objects = [
            OpenInterest(
                network=network,
                asset=coin,
                timestamp=int(row.ts),
                value=Decimal(str(row.open_interest)),
            )
            for row in projected.itertuples(index=False)
        ]
        _bulk_insert(OpenInterest, objects)
        try:
            _save_parquet(path, projected, _OI_COLUMNS, "ts")
        except Exception as exc:
            raise OSError(f"Parquet write failed for open_interest {coin}: {exc}") from exc
    return path


def load_candles(
    coin: str,
    interval: str,
    start: int | None = None,
    end: int | None = None,
    *,
    network: str = "mainnet",
) -> pd.DataFrame:
    """Load candles from Parquet with PostgreSQL fallback for backtesting."""
    path = _resolve_path(
        candle_path(coin, interval, network=network),
        _legacy_candle_path(coin, interval),
    )

    df = pd.DataFrame(columns=_COLUMNS)
    if path is not None:
        df = pd.read_parquet(path)
        if start is not None:
            df = df[df["ts"] >= start]
        if end is not None:
            df = df[df["ts"] <= end]
        df = df.sort_values("ts").reset_index(drop=True)

    if df.empty:
        df = load_candles_from_db(coin, interval, start, end, network=network)
    return df


def load_candles_from_db(
    coin: str,
    interval: str,
    start: int | None = None,
    end: int | None = None,
    *,
    network: str = "mainnet",
    limit: int | None = None,
) -> pd.DataFrame:
    """Load candles from PostgreSQL (API / dashboard queries)."""
    coin = normalize_coin(coin)
    interval = normalize_interval(interval)
    qs = Candle.objects.filter(network=network, asset=coin, timeframe=interval)
    if start is not None:
        qs = qs.filter(timestamp__gte=start)
    if end is not None:
        qs = qs.filter(timestamp__lte=end)
    qs = qs.order_by("timestamp")
    if limit:
        qs = qs.reverse()[:limit]
        rows = list(reversed(list(qs)))
    else:
        rows = list(qs)
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    return pd.DataFrame(
        {
            "ts": [r.timestamp for r in rows],
            "open": [float(r.open) for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [float(r.volume) for r in rows],
        }
    )


def _load_range(path: Path | None, columns: list[str], start: int | None, end: int | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=columns)
    df = pd.read_parquet(path)
    if start is not None:
        df = df[df["ts"] >= start]
    if end is not None:
        df = df[df["ts"] <= end]
    return df.sort_values("ts").reset_index(drop=True)


def load_funding(
    coin: str,
    start: int | None = None,
    end: int | None = None,
    *,
    network: str = "mainnet",
) -> pd.DataFrame:
    path = _resolve_path(funding_path(coin, network=network), _legacy_funding_path(coin))
    return _load_range(path, _FUNDING_COLUMNS, start, end)


def load_funding_from_db(
    coin: str,
    start: int | None = None,
    end: int | None = None,
    *,
    network: str = "mainnet",
) -> pd.DataFrame:
    coin = normalize_coin(coin)
    qs = FundingRate.objects.filter(network=network, asset=coin)
    if start is not None:
        qs = qs.filter(timestamp__gte=start)
    if end is not None:
        qs = qs.filter(timestamp__lte=end)
    rows = list(qs.order_by("timestamp"))
    if not rows:
        return pd.DataFrame(columns=_FUNDING_COLUMNS)
    return pd.DataFrame(
        {
            "ts": [r.timestamp for r in rows],
            "funding_rate": [float(r.funding_rate) for r in rows],
            "premium": [float(r.premium) for r in rows],
        }
    )


def load_open_interest(
    coin: str,
    start: int | None = None,
    end: int | None = None,
    *,
    network: str = "mainnet",
) -> pd.DataFrame:
    path = _resolve_path(
        open_interest_path(coin, network=network),
        _legacy_open_interest_path(coin),
    )
    return _load_range(path, _OI_COLUMNS, start, end)


def latest_timestamp(
    network: str,
    asset: str,
    timeframe: str | None = None,
    *,
    kind: str = "ohlcv",
) -> int | None:
    """Return the latest stored timestamp (ms) for incremental sync."""
    asset = normalize_coin(asset)
    if kind == "ohlcv":
        if not timeframe:
            return None
        tf = normalize_interval(timeframe)
        result = (
            Candle.objects.filter(network=network, asset=asset, timeframe=tf)
            .aggregate(latest=Max("timestamp"))
            .get("latest")
        )
    elif kind == "funding":
        result = (
            FundingRate.objects.filter(network=network, asset=asset)
            .aggregate(latest=Max("timestamp"))
            .get("latest")
        )
    elif kind == "open_interest":
        result = (
            OpenInterest.objects.filter(network=network, asset=asset)
            .aggregate(latest=Max("timestamp"))
            .get("latest")
        )
    else:
        return None
    return int(result) if result is not None else None


def earliest_timestamp(
    network: str,
    asset: str,
    timeframe: str | None = None,
    *,
    kind: str = "ohlcv",
) -> int | None:
    """Return the earliest stored timestamp (ms) for coverage checks."""
    asset = normalize_coin(asset)
    if kind == "ohlcv":
        if not timeframe:
            return None
        tf = normalize_interval(timeframe)
        result = (
            Candle.objects.filter(network=network, asset=asset, timeframe=tf)
            .aggregate(earliest=Min("timestamp"))
            .get("earliest")
        )
    elif kind == "funding":
        result = (
            FundingRate.objects.filter(network=network, asset=asset)
            .aggregate(earliest=Min("timestamp"))
            .get("earliest")
        )
    elif kind == "open_interest":
        result = (
            OpenInterest.objects.filter(network=network, asset=asset)
            .aggregate(earliest=Min("timestamp"))
            .get("earliest")
        )
    else:
        return None
    return int(result) if result is not None else None


def dataset_coverage(
    network: str,
    coin: str,
    interval: str,
    *,
    kind: str = "ohlcv",
) -> dict | None:
    """Return start/end/bar count for a dataset, or None if missing."""
    coin = normalize_coin(coin)
    if kind == "ohlcv":
        interval = normalize_interval(interval)
        agg = (
            Candle.objects.filter(network=network, asset=coin, timeframe=interval)
            .aggregate(bars=Count("id"), start_ts=Min("timestamp"), end_ts=Max("timestamp"))
        )
        if not agg["bars"]:
            path = _resolve_path(
                candle_path(coin, interval, network=network),
                _legacy_candle_path(coin, interval),
            )
            if path is None:
                return None
            df = pd.read_parquet(path, columns=["ts"])
            if df.empty:
                return None
            return {
                "network": network,
                "coin": coin,
                "interval": interval,
                "kind": kind,
                "bars": int(len(df)),
                "start_ts": int(df["ts"].min()),
                "end_ts": int(df["ts"].max()),
                "size_bytes": path.stat().st_size,
            }
        path = candle_path(coin, interval, network=network)
        size = path.stat().st_size if path.exists() else 0
        return {
            "network": network,
            "coin": coin,
            "interval": interval,
            "kind": kind,
            "bars": agg["bars"],
            "start_ts": int(agg["start_ts"]),
            "end_ts": int(agg["end_ts"]),
            "size_bytes": size,
        }
    if kind == "funding":
        agg = (
            FundingRate.objects.filter(network=network, asset=coin)
            .aggregate(bars=Count("id"), start_ts=Min("timestamp"), end_ts=Max("timestamp"))
        )
        if not agg["bars"]:
            return None
        path = funding_path(coin, network=network)
        size = path.stat().st_size if path.exists() else 0
        return {
            "network": network,
            "coin": coin,
            "interval": "funding",
            "kind": kind,
            "bars": agg["bars"],
            "start_ts": int(agg["start_ts"]),
            "end_ts": int(agg["end_ts"]),
            "size_bytes": size,
        }
    if kind == "open_interest":
        agg = (
            OpenInterest.objects.filter(network=network, asset=coin)
            .aggregate(bars=Count("id"), start_ts=Min("timestamp"), end_ts=Max("timestamp"))
        )
        if not agg["bars"]:
            return None
        path = open_interest_path(coin, network=network)
        size = path.stat().st_size if path.exists() else 0
        return {
            "network": network,
            "coin": coin,
            "interval": "open_interest",
            "kind": kind,
            "bars": agg["bars"],
            "start_ts": int(agg["start_ts"]),
            "end_ts": int(agg["end_ts"]),
            "size_bytes": size,
        }
    return None


def list_datasets(*, network: str | None = None) -> list[dict]:
    """Return metadata aggregated from PostgreSQL (falls back to Parquet scan)."""
    datasets: list[dict] = []

    candle_qs = Candle.objects.all()
    if network:
        candle_qs = candle_qs.filter(network=network)
    for row in (
        candle_qs.values("network", "asset", "timeframe")
        .annotate(bars=Count("id"), start_ts=Min("timestamp"), end_ts=Max("timestamp"))
        .order_by("network", "asset", "timeframe")
    ):
        path = candle_path(row["asset"], row["timeframe"], network=row["network"])
        datasets.append(
            {
                "network": row["network"],
                "coin": row["asset"],
                "interval": row["timeframe"],
                "kind": "ohlcv",
                "bars": row["bars"],
                "start_ts": int(row["start_ts"]),
                "end_ts": int(row["end_ts"]),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
        )

    funding_qs = FundingRate.objects.all()
    if network:
        funding_qs = funding_qs.filter(network=network)
    for row in (
        funding_qs.values("network", "asset")
        .annotate(bars=Count("id"), start_ts=Min("timestamp"), end_ts=Max("timestamp"))
        .order_by("network", "asset")
    ):
        path = funding_path(row["asset"], network=row["network"])
        datasets.append(
            {
                "network": row["network"],
                "coin": row["asset"],
                "interval": "funding",
                "kind": "funding",
                "bars": row["bars"],
                "start_ts": int(row["start_ts"]),
                "end_ts": int(row["end_ts"]),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
        )

    oi_qs = OpenInterest.objects.all()
    if network:
        oi_qs = oi_qs.filter(network=network)
    for row in (
        oi_qs.values("network", "asset")
        .annotate(bars=Count("id"), start_ts=Min("timestamp"), end_ts=Max("timestamp"))
        .order_by("network", "asset")
    ):
        path = open_interest_path(row["asset"], network=row["network"])
        datasets.append(
            {
                "network": row["network"],
                "coin": row["asset"],
                "interval": "open_interest",
                "kind": "open_interest",
                "bars": row["bars"],
                "start_ts": int(row["start_ts"]),
                "end_ts": int(row["end_ts"]),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
        )

    if datasets:
        return datasets

    return _list_datasets_parquet(network=network)


def _scan_flat_dir(subdir: str, kind: str, *, network: str | None = None) -> list[dict]:
    root = _data_root() / subdir
    if not root.exists():
        return []
    datasets: list[dict] = []
    patterns = [root.glob("**/*.parquet")] if network is None else [root.glob(f"{network}/*.parquet")]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(pattern)
    if network is None:
        paths.extend(root.glob("*.parquet"))
    for path in sorted(set(paths)):
        try:
            df = pd.read_parquet(path, columns=["ts"])
        except Exception:  # noqa: BLE001
            continue
        if df.empty:
            continue
        net = path.parent.name if path.parent.parent.name == subdir else "mainnet"
        datasets.append(
            {
                "network": net,
                "coin": path.stem,
                "interval": kind,
                "kind": kind,
                "bars": int(len(df)),
                "start_ts": int(df["ts"].min()),
                "end_ts": int(df["ts"].max()),
                "size_bytes": path.stat().st_size,
            }
        )
    return datasets


def _list_datasets_parquet(*, network: str | None = None) -> list[dict]:
    datasets: list[dict] = []
    root = candle_data_dir()
    if root.exists():
        if network:
            search_roots = [root / network]
        else:
            search_roots = [p for p in root.iterdir() if p.is_dir()]
        for net_dir in search_roots:
            net = net_dir.name
            for coin_dir in sorted(net_dir.iterdir()):
                if not coin_dir.is_dir():
                    continue
                coin = coin_dir.name
                for path in sorted(coin_dir.glob("*.parquet")):
                    interval = path.stem
                    try:
                        df = pd.read_parquet(path, columns=["ts"])
                    except Exception:  # noqa: BLE001
                        continue
                    if df.empty:
                        continue
                    datasets.append(
                        {
                            "network": net,
                            "coin": coin,
                            "interval": interval,
                            "kind": "ohlcv",
                            "bars": int(len(df)),
                            "start_ts": int(df["ts"].min()),
                            "end_ts": int(df["ts"].max()),
                            "size_bytes": path.stat().st_size,
                        }
                    )
        # Legacy layout: <root>/<coin>/<interval>.parquet
        for coin_dir in sorted(root.iterdir()):
            if not coin_dir.is_dir():
                continue
            for path in sorted(coin_dir.glob("*.parquet")):
                if path.parent.parent != root:
                    continue
                try:
                    df = pd.read_parquet(path, columns=["ts"])
                except Exception:  # noqa: BLE001
                    continue
                if df.empty:
                    continue
                datasets.append(
                    {
                        "network": "mainnet",
                        "coin": coin_dir.name,
                        "interval": path.stem,
                        "kind": "ohlcv",
                        "bars": int(len(df)),
                        "start_ts": int(df["ts"].min()),
                        "end_ts": int(df["ts"].max()),
                        "size_bytes": path.stat().st_size,
                    }
                )

    datasets.extend(_scan_flat_dir("funding", "funding", network=network))
    datasets.extend(_scan_flat_dir("open_interest", "open_interest", network=network))
    return datasets


def delete_dataset(
    network: str,
    coin: str,
    interval: str,
    *,
    kind: str = "ohlcv",
) -> bool:
    """Remove a dataset from PostgreSQL and Parquet."""
    coin = normalize_coin(coin)
    deleted = False
    with transaction.atomic():
        if kind == "ohlcv":
            interval = normalize_interval(interval)
            count, _ = Candle.objects.filter(
                network=network, asset=coin, timeframe=interval
            ).delete()
            deleted = count > 0
            for path in (
                candle_path(coin, interval, network=network),
                _legacy_candle_path(coin, interval),
            ):
                if path.exists():
                    path.unlink()
                    deleted = True
        elif kind == "funding":
            count, _ = FundingRate.objects.filter(network=network, asset=coin).delete()
            deleted = count > 0
            for path in (funding_path(coin, network=network), _legacy_funding_path(coin)):
                if path.exists():
                    path.unlink()
                    deleted = True
        elif kind == "open_interest":
            count, _ = OpenInterest.objects.filter(network=network, asset=coin).delete()
            deleted = count > 0
            for path in (
                open_interest_path(coin, network=network),
                _legacy_open_interest_path(coin),
            ):
                if path.exists():
                    path.unlink()
                    deleted = True
    return deleted


def export_parquet_from_pg(
    coin: str,
    interval: str,
    *,
    network: str = "mainnet",
) -> Path | None:
    """Rebuild Parquet from PostgreSQL if files are missing or stale."""
    df = load_candles_from_db(coin, interval, network=network)
    if df.empty:
        return None
    return _save_parquet(candle_path(coin, interval, network=network), df, _COLUMNS, "ts")


__all__ = [
    "candle_data_dir",
    "candle_path",
    "dataset_coverage",
    "delete_dataset",
    "export_parquet_from_pg",
    "earliest_timestamp",
    "funding_path",
    "latest_timestamp",
    "list_datasets",
    "load_candles",
    "load_candles_from_db",
    "load_funding",
    "load_funding_from_db",
    "load_open_interest",
    "open_interest_path",
    "save_candles",
    "save_funding",
    "save_open_interest",
]
