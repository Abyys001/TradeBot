"""Node B — hot compute: Redis Stream trades → sealed bars → strategy runner (Master Plan §2, §3.3).

Consumes the trade stream from an acked cursor (crash-safe), aggregates per active
(symbol, timeframe), tags each sealed bar with a quality from ledger coverage, and drives the
live strategy runner. A SUSPECT/MISSING bar halts the strategy in the runner (invariant 1).

The aggregator runs inline here (colocated with the runner, §2) — deliberately no network hop
on the hot path. Background resampling lives on Node C (separate process), never here (§0.2).
"""
from __future__ import annotations

import logging
import time

from django.conf import settings

from . import coverage
from .aggregator import TradeAggregator
from .data_quality import classify_bar
from .ingest import trade_stream_key
from .stream import StreamConsumer
from .timeframes import is_fixed, tf_to_ms

logger = logging.getLogger(__name__)

# Watchdog (Node D) reads this key to detect a dead/hung Node B (invariant 12, §6.2).
# Must match apps.watchdog.monitor.WatchdogMonitor.HEARTBEAT_KEY.
HOT_HEARTBEAT_KEY = "health:hot_compute:{strategy_id}"
HOT_HEARTBEAT_TTL_S = 30


def active_hot_targets() -> dict[str, list]:
    """Active Tabdeal live strategies grouped by ingest symbol.

    Returns ``{tabdeal_symbol: [(strategy, tf_ms, tf_str), ...]}`` for fixed timeframes only.
    """
    from apps.credentials.models import Exchange
    from apps.strategies.models import StrategyState
    from apps.transpiler.runtime.tabdeal_broker import to_tabdeal_symbol

    targets: dict[str, list] = {}
    states = (
        StrategyState.objects.select_related("strategy", "strategy__credential")
        .filter(live_started_at__isnull=False)
    )
    for st in states:
        strat = st.strategy
        if not strat.credential or strat.credential.exchange != Exchange.TABDEAL:
            continue
        if not is_fixed(strat.timeframe):
            continue
        symbol = to_tabdeal_symbol(strat.symbol)
        targets.setdefault(symbol, []).append((strat, tf_to_ms(strat.timeframe), strat.timeframe))
    return targets


def tag_quality(symbol: str, bar: dict, tf_ms: int) -> dict:
    """Attach ``bar['quality']`` from ledger coverage over the bar window (§3.2)."""
    t0 = int(bar["ts"])
    pct = coverage.coverage_pct(symbol, t0, t0 + tf_ms)
    covered_ms = int(round(pct * tf_ms))
    bar = dict(bar)
    bar["quality"] = classify_bar(bar, covered_ms=covered_ms, tf_ms=tf_ms).value
    return bar


class HotCompute:
    def __init__(self, *, group: str = "hotB", consumer: str | None = None):
        import socket
        self.group = group
        self.consumer = consumer or getattr(settings, "INGEST_NODE_ID", "") or socket.gethostname()
        self._aggs: dict[tuple[str, int], TradeAggregator] = {}
        self._targets = active_hot_targets()
        self._lat: list[float] = []

    def _agg(self, symbol: str, tf_ms: int) -> TradeAggregator:
        key = (symbol, tf_ms)
        if key not in self._aggs:
            self._aggs[key] = TradeAggregator(symbol, tf_ms)
        return self._aggs[key]

    def _beat(self) -> None:
        """Publish a liveness heartbeat per active strategy (invariant 12).

        The watchdog (Node D) reads ``health:hot_compute:{strategy_id}`` and, if the
        gap exceeds ``T_self``/``T_dead``, self-fences / takes over. This MUST fire on
        every loop tick (not only on trades), or a quiet market would look like a dead
        Node B and trip a false takeover.
        """
        from django.core.cache import cache

        now = time.time()
        for targets in self._targets.values():
            for strat, _tf_ms, _tf in targets:
                cache.set(
                    HOT_HEARTBEAT_KEY.format(strategy_id=strat.pk),
                    {"ts": now},
                    timeout=HOT_HEARTBEAT_TTL_S,
                )

    def _dispatch(self, symbol: str, tf_ms: int, bar: dict) -> None:
        from apps.transpiler.live.runner import LiveIncrementalRunner

        tagged = tag_quality(symbol, bar, tf_ms)
        runner = LiveIncrementalRunner()
        for strat, s_tf_ms, _ in self._targets.get(symbol, []):
            if s_tf_ms != tf_ms:
                continue
            try:
                runner.on_closed_candle(strat, tagged)
            except Exception:  # noqa: BLE001 - one strategy must not kill the loop
                logger.exception("hot dispatch failed for strategy %s", strat.pk)

    def run(self) -> None:
        self._targets = active_hot_targets()
        symbols = list(self._targets.keys())
        if not symbols:
            logger.warning("hot-compute: no active Tabdeal live strategies; idle")
        keys = [trade_stream_key(s) for s in symbols]
        consumer = StreamConsumer(keys, group=self.group, consumer=self.consumer) if keys else None
        logger.info("hot-compute node=%s symbols=%s", self.consumer, symbols)
        while True:
            self._beat()
            if consumer is None:
                time.sleep(2)
                self.run()  # re-scan for newly started strategies
                return
            for key, entry_id, fields in consumer.read(block_ms=1000, count=200):
                t_deq = time.monotonic()
                symbol = key.rsplit(":", 1)[-1]
                ts = int(fields["ts"])
                price = float(fields["price"])
                qty = float(fields.get("qty", 0) or 0)
                for _, tf_ms, _ in self._targets.get(symbol, []):
                    for bar in self._agg(symbol, tf_ms).add_trade(ts, price, qty):
                        self._dispatch(symbol, tf_ms, bar)
                consumer.ack(key, entry_id)
                self._record_latency(time.monotonic() - t_deq)
            # quiet-timeout seals for bars with no newer trade
            now_ms = int(time.time() * 1000)
            for (symbol, tf_ms), agg in self._aggs.items():
                for bar in agg.flush(now_ms):
                    self._dispatch(symbol, tf_ms, bar)

    def _record_latency(self, seconds: float) -> None:
        self._lat.append(seconds * 1000)
        if len(self._lat) >= 200:
            from django.core.cache import cache
            ordered = sorted(self._lat)
            p99 = ordered[int(len(ordered) * 0.99) - 1]
            cache.set("health:hot_path_latency_p99_ms", p99, timeout=30)
            self._lat = self._lat[-50:]


def run_hot_compute() -> None:
    HotCompute().run()
