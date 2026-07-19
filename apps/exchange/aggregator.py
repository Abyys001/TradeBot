"""Trade → bar aggregator for the hot path (Master Plan §3.3, candle design §2.3).

Folds a stream of trades into sealed OHLCV bars keyed by **exchange trade timestamp**
(invariant 4), on a fixed timeframe. Seal rules:

- **Next-trade seal:** the first trade whose ts falls in a later bucket seals the current
  bar (~0 latency on a liquid market).
- **Quiet-timeout seal:** ``flush(now_ms)`` seals a bar whose boundary passed more than
  ``grace_ms`` (≤750ms) ago even if no newer trade arrived — the dominant latency term on a
  quiet bar (§0.2).

Invariants realized: a sealed bar is never mutated afterwards (invariant 2); bars are never
forward-filled to *cover a gap* (invariant 2). A quiet bucket that is genuinely inside the
covered stream emits a **FLAT** carry-forward bar (open=high=low=close=prev close, volume 0,
``trade_count`` 0) — legitimate "no trade, price unchanged", not fabricated data. The FLAT vs
MISSING distinction (covered vs uncovered) is decided later by ``data_quality.classify_bar``
against ledger coverage, not here — this class is coverage-agnostic.

Large jumps are **not** FLAT-filled: if trades skip more than ``max_flat_fill`` buckets, the
real bar seals and the aggregator jumps to the new bucket, leaving the hole for the coverage /
self-heal layer to classify (SUSPECT/MISSING) and halt on. FLAT-filling a big gap would be
forward-filling to cover it.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def bucket_start(ts_ms: int, tf_ms: int) -> int:
    """UTC-aligned bucket origin for a fixed timeframe (epoch-anchored)."""
    return (ts_ms // tf_ms) * tf_ms


@dataclass
class TradeAggregator:
    symbol: str
    tf_ms: int
    grace_ms: int = 750
    max_flat_fill: int = 5

    _t0: int | None = None
    _o: float = 0.0
    _h: float = 0.0
    _l: float = 0.0
    _c: float = 0.0
    _v: float = 0.0
    _n: int = 0
    _last_close: float | None = None
    _last_ts: int = field(default=-1)  # last trade ts seen (for idempotent dedupe)

    def add_trade(self, ts_ms: int, price: float, qty: float = 0.0) -> list[dict]:
        """Feed one trade. Returns any bars sealed as a result (newest last)."""
        ts_ms = int(ts_ms)
        price = float(price)
        b = bucket_start(ts_ms, self.tf_ms)
        sealed: list[dict] = []

        if self._t0 is None:
            self._open_bucket(b, price, qty)
            self._last_ts = ts_ms
            return sealed

        if b < self._t0:
            # Out-of-order/late trade for an already-sealed bar — drop (bars are immutable).
            return sealed

        if b == self._t0:
            self._h = max(self._h, price)
            self._l = min(self._l, price)
            self._c = price
            self._v += float(qty)
            self._n += 1
            self._last_ts = ts_ms
            return sealed

        # b > current bucket: seal the current (real) bar, then bridge the gap.
        sealed.append(self._seal())
        empty = (b - self._t0) // self.tf_ms - 1
        if 0 < empty <= self.max_flat_fill:
            sealed.extend(self._flat_bars(self._t0 + self.tf_ms, empty))
        # else: large gap — leave it uncovered for the quality/self-heal layer.
        self._open_bucket(b, price, qty)
        self._last_ts = ts_ms
        return sealed

    def flush(self, now_ms: int) -> list[dict]:
        """Seal the open bar if its boundary passed more than ``grace_ms`` ago."""
        if self._t0 is None:
            return []
        if now_ms >= self._t0 + self.tf_ms + self.grace_ms:
            bar = self._seal()
            self._t0 = None
            return [bar]
        return []

    # ----- internals -----

    def _open_bucket(self, t0: int, price: float, qty: float) -> None:
        self._t0, self._o, self._h, self._l, self._c = t0, price, price, price, price
        self._v = float(qty)
        self._n = 1

    def _seal(self) -> dict:
        bar = {
            "ts": self._t0, "open": self._o, "high": self._h, "low": self._l,
            "close": self._c, "volume": self._v, "trade_count": self._n,
        }
        self._last_close = self._c
        return bar

    def _flat_bars(self, start_t0: int, count: int) -> list[dict]:
        c = self._last_close if self._last_close is not None else self._c
        bars = []
        for i in range(count):
            t0 = start_t0 + i * self.tf_ms
            bars.append({"ts": t0, "open": c, "high": c, "low": c, "close": c,
                         "volume": 0.0, "trade_count": 0})
        return bars
