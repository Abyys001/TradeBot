"""Append-only raw trade ledger — the authoritative record (Master Plan §3.1, invariant 3).

The ledger is written **from** the ingest socket and is the only durable source of
truth for market history: bars are a cache derived from it, never the reverse
(invariant 3). It is append-only and never mutated after write (invariant 2 in spirit).

Layout (partitioned per node, per symbol, per UTC day so appends stay cheap and
files stay bounded)::

    <CANDLE_DATA_DIR>/../ledger/<SYMBOL>/<NODE_ID>/<YYYYMMDD>.parquet
    <CANDLE_DATA_DIR>/../ledger/<SYMBOL>/<NODE_ID>/_coverage.json

Redundancy (Master Plan §0.1, §1 of P1): N≥2 ingest nodes each write their own
``<NODE_ID>`` partition. Effective coverage is the **union** across nodes and the
effective trade stream is the cross-node merge deduped by ``trade_id``. A single
node losing its socket is a Class-2 (partial) gap another node covers; only the
simultaneous failure of every node is an unrecoverable Class-3 hole.

Columns: ``trade_id`` (str, exchange-assigned) · ``ts`` (int, exchange ms —
invariant 4, never local arrival time) · ``price`` (float) · ``qty`` (float) ·
``side`` (str: ``buy``/``sell``/``""``) · ``raw`` (str, original JSON for forensics).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    import portalocker as fcntl
else:
    import fcntl

import pandas as pd
from django.conf import settings

logger = logging.getLogger(__name__)

LEDGER_COLUMNS = ["trade_id", "ts", "price", "qty", "side", "raw"]

# A reconnect gap larger than this (ms) closes the current coverage interval and
# starts a new one, so coverage honestly reflects the socket-down window.
COVERAGE_GAP_MS = 2_000


def _data_root() -> Path:
    candle_dir = Path(getattr(settings, "CANDLE_DATA_DIR", settings.BASE_DIR / "data" / "candles"))
    return candle_dir.parent


def ledger_dir() -> Path:
    return _data_root() / "ledger"


def _norm_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def node_dir(symbol: str, node_id: str) -> Path:
    return ledger_dir() / _norm_symbol(symbol) / node_id


def _day_key(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y%m%d")


def day_path(symbol: str, node_id: str, ts_ms: int) -> Path:
    return node_dir(symbol, node_id) / f"{_day_key(ts_ms)}.parquet"


def _coverage_path(symbol: str, node_id: str) -> Path:
    return node_dir(symbol, node_id) / "_coverage.json"


@contextmanager
def _flock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@dataclass
class LedgerWriter:
    """Buffered append-only writer for one ingest node.

    Durability outranks latency here (Master Plan §3.1): ``flush`` appends the
    buffer to the per-day parquet, deduped by ``trade_id``, and fsyncs. The caller
    (ingest command) flushes on a short cadence (~200ms) or when the buffer fills.
    """

    node_id: str
    _buffer: dict[str, list[dict]] = field(default_factory=dict)  # symbol -> rows
    _last_ts: dict[str, int] = field(default_factory=dict)         # symbol -> last appended ts

    def add(self, symbol: str, trade: dict) -> None:
        """Queue one normalized trade dict (keys: trade_id, ts, price, qty, side, raw)."""
        symbol = _norm_symbol(symbol)
        self._buffer.setdefault(symbol, []).append(trade)

    def buffered(self) -> int:
        return sum(len(v) for v in self._buffer.values())

    def flush(self) -> int:
        """Persist all buffered trades. Returns rows written. Idempotent on trade_id."""
        written = 0
        for symbol, rows in list(self._buffer.items()):
            if not rows:
                continue
            written += self._flush_symbol(symbol, rows)
            self._buffer[symbol] = []
        return written

    def _flush_symbol(self, symbol: str, rows: list[dict]) -> int:
        # Rows may straddle a UTC-day boundary; group by day file.
        by_day: dict[Path, list[dict]] = {}
        for r in rows:
            by_day.setdefault(day_path(symbol, self.node_id, int(r["ts"])), []).append(r)

        total = 0
        min_ts = min(int(r["ts"]) for r in rows)
        max_ts = max(int(r["ts"]) for r in rows)
        for path, day_rows in by_day.items():
            total += self._append_parquet(path, day_rows)
        self._extend_coverage(symbol, min_ts, max_ts)
        self._last_ts[symbol] = max(self._last_ts.get(symbol, 0), max_ts)
        return total

    def _append_parquet(self, path: Path, rows: list[dict]) -> int:
        incoming = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
        with _flock(path):
            if path.exists():
                existing = pd.read_parquet(path)
                merged = pd.concat([existing, incoming], ignore_index=True)
            else:
                merged = incoming
            before = len(merged)
            merged = (
                merged.drop_duplicates(subset="trade_id", keep="first")
                .sort_values("ts")
                .reset_index(drop=True)
            )
            new_rows = len(merged) - (before - len(incoming))
            merged.to_parquet(path, index=False, engine="pyarrow")
            self._fsync(path)
        return max(new_rows, 0)

    @staticmethod
    def _fsync(path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:  # pragma: no cover - platform dependent
            logger.warning("ledger fsync failed for %s: %s", path, exc)

    def mark_gap(self, symbol: str) -> None:
        """Signal a socket reconnect so the next write starts a fresh coverage interval."""
        symbol = _norm_symbol(symbol)
        self._last_ts[symbol] = -1  # force a new interval on next _extend_coverage

    def _extend_coverage(self, symbol: str, start_ts: int, end_ts: int) -> None:
        path = _coverage_path(symbol, self.node_id)
        with _flock(path):
            intervals = _load_coverage(path)
            gap_flag = self._last_ts.get(symbol) == -1
            if intervals and not gap_flag and start_ts - intervals[-1][1] <= COVERAGE_GAP_MS:
                intervals[-1][1] = max(intervals[-1][1], end_ts)
            else:
                intervals.append([start_ts, end_ts])
            path.write_text(json.dumps({"intervals": intervals}), encoding="utf-8")


def _load_coverage(path: Path) -> list[list[int]]:
    if not path.exists():
        return []
    try:
        return [list(iv) for iv in json.loads(path.read_text(encoding="utf-8")).get("intervals", [])]
    except (json.JSONDecodeError, OSError):
        return []


# ----- read / merge API (cross-node) -----


def list_nodes(symbol: str) -> list[str]:
    base = ledger_dir() / _norm_symbol(symbol)
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def read_trades(symbol: str, start_ms: int, end_ms: int, nodes: list[str] | None = None) -> pd.DataFrame:
    """Merged, deduped, time-sorted trades in ``[start_ms, end_ms)`` across nodes.

    This is the effective stream the aggregator and self-heal read (invariant 3,
    Master Plan §0.1/§4.4): the union of every node, deduped by ``trade_id``.
    """
    symbol = _norm_symbol(symbol)
    nodes = nodes if nodes is not None else list_nodes(symbol)
    frames: list[pd.DataFrame] = []
    for node_id in nodes:
        d = node_dir(symbol, node_id)
        if not d.exists():
            continue
        for pq in sorted(d.glob("*.parquet")):
            df = pd.read_parquet(pq)
            df = df[(df["ts"] >= start_ms) & (df["ts"] < end_ms)]
            if not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    merged = pd.concat(frames, ignore_index=True)
    return (
        merged.drop_duplicates(subset="trade_id", keep="first")
        .sort_values("ts")
        .reset_index(drop=True)
    )


def union_coverage(symbol: str, nodes: list[str] | None = None) -> list[list[int]]:
    """Effective coverage = union of all node coverage intervals (Master Plan §0.1)."""
    symbol = _norm_symbol(symbol)
    nodes = nodes if nodes is not None else list_nodes(symbol)
    intervals: list[list[int]] = []
    for node_id in nodes:
        intervals.extend(_load_coverage(_coverage_path(symbol, node_id)))
    return _merge_intervals(intervals)


def available_range(symbol: str, nodes: list[str] | None = None) -> tuple[int, int] | None:
    """``(first_ms, last_ms)`` the ledger holds for *symbol*, or None if empty.

    Every caller that needs "how far back does recorded data go" should use this
    rather than re-deriving it from ``union_coverage`` edges.
    """
    cov = union_coverage(symbol, nodes)
    if not cov:
        return None
    return int(cov[0][0]), int(cov[-1][1])


def coverage_gaps(symbol: str, start_ms: int, end_ms: int, nodes: list[str] | None = None) -> list[list[int]]:
    """Sub-windows of ``[start_ms, end_ms)`` not covered by any node — the honest holes."""
    covered = union_coverage(symbol, nodes)
    gaps: list[list[int]] = []
    cursor = start_ms
    for lo, hi in covered:
        if hi < start_ms or lo > end_ms:
            continue
        lo = max(lo, start_ms)
        if lo > cursor:
            gaps.append([cursor, min(lo, end_ms)])
        cursor = max(cursor, min(hi, end_ms))
    if cursor < end_ms:
        gaps.append([cursor, end_ms])
    return [g for g in gaps if g[0] < g[1]]


def _merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    if not intervals:
        return []
    ordered = sorted([list(iv) for iv in intervals])
    out = [ordered[0]]
    for lo, hi in ordered[1:]:
        if lo <= out[-1][1] + COVERAGE_GAP_MS:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out
