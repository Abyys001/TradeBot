"""Tabdeal trade ingest orchestrator — Node A (Master Plan §2, §3.1).

Wires the broadcast WS client to two consumers off a bounded queue:

    WS ──► on_trade ──┬──► ledger queue  (durable, backpressure — never drops)
                      └──► publish queue (sheddable — dropped on saturation)

**Durability outranks latency here** (§3.1): the ledger is the only thing nothing else
can rebuild, so its path applies backpressure (``await put``) and never loses a trade;
the Redis-Stream publisher (the A→B seam consumed by Node B in P2) is best-effort and
sheds under load, because B can always fall back to ledger replay.

Redundancy (§0.1): run this command as N≥2 replicas with distinct ``INGEST_NODE_ID``;
each writes its own ledger partition and the readers take the union.
"""
from __future__ import annotations

import asyncio
import logging
import time

import redis.asyncio as aioredis
from django.conf import settings

from .ledger import LedgerWriter
from .tabdeal_ws import TabdealBroadcastClient

logger = logging.getLogger(__name__)


def _cfg(name: str, default):
    return getattr(settings, name, default)


def trade_stream_key(symbol: str) -> str:
    prefix = _cfg("TABDEAL_TRADE_STREAM_PREFIX", "tabdeal:trades")
    return f"{prefix}:{symbol.upper()}"


class IngestService:
    def __init__(self, symbols: list[str], node_id: str):
        self.symbols = [s.strip().upper() for s in symbols]
        self.node_id = node_id
        self.writer = LedgerWriter(node_id=node_id)

        self._ledger_q: asyncio.Queue = asyncio.Queue(maxsize=int(_cfg("TABDEAL_INGEST_QUEUE_MAX", 20000)))
        self._publish_q: asyncio.Queue = asyncio.Queue(maxsize=int(_cfg("TABDEAL_PUBLISH_QUEUE_MAX", 20000)))
        self._pending_gap: set[str] = set()

        self._flush_ms = int(_cfg("TABDEAL_INGEST_FLUSH_MS", 200))
        self._batch_max = int(_cfg("TABDEAL_INGEST_BATCH_MAX", 500))
        self._stream_maxlen = int(_cfg("TABDEAL_TRADE_STREAM_MAXLEN", 1_000_000))

        self._shed = 0
        self._ingested = 0
        self._published = 0
        self._publish_errors = 0
        self._latencies_ms: list[float] = []
        self._stop = asyncio.Event()
        self._redis: aioredis.Redis | None = None
        self._started_at: float = 0.0

    # ----- callbacks from the WS client -----

    async def _on_trade(self, symbol: str, row: dict) -> None:
        await self._ledger_q.put((symbol, row))          # durable: backpressure, never drop
        try:
            self._publish_q.put_nowait((symbol, row))    # sheddable
        except asyncio.QueueFull:
            self._shed += 1
            if self._shed % 1000 == 1:
                logger.warning("publisher shedding under load (total shed=%d)", self._shed)

    def _on_gap(self, symbol: str) -> None:
        self._pending_gap.add(symbol.upper())

    # ----- consumers -----

    async def _ledger_loop(self) -> None:
        last_flush = time.monotonic()
        while not self._stop.is_set() or not self._ledger_q.empty():
            t_start = time.monotonic()
            try:
                symbol, row = await asyncio.wait_for(self._ledger_q.get(), timeout=self._flush_ms / 1000)
                if symbol in self._pending_gap:
                    self.writer.mark_gap(symbol)
                    self._pending_gap.discard(symbol)
                self.writer.add(symbol, row)
                self._ingested += 1
                latency_ms = (time.monotonic() - t_start) * 1000
                self._latencies_ms.append(latency_ms)
                if len(self._latencies_ms) >= 200:
                    self._latencies_ms = self._latencies_ms[-100:]
            except asyncio.TimeoutError:
                pass
            now = time.monotonic()
            if self.writer.buffered() >= self._batch_max or (now - last_flush) * 1000 >= self._flush_ms:
                if self.writer.buffered():
                    await asyncio.to_thread(self.writer.flush)
                self._heartbeat()
                last_flush = now

    async def _publish_loop(self) -> None:
        if self._redis is None:
            return
        while not self._stop.is_set() or not self._publish_q.empty():
            try:
                symbol, row = await asyncio.wait_for(self._publish_q.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            try:
                await self._redis.xadd(
                    trade_stream_key(symbol),
                    {"trade_id": row["trade_id"], "ts": row["ts"], "price": row["price"],
                     "qty": row["qty"], "side": row["side"], "node": self.node_id},
                    maxlen=self._stream_maxlen,
                    approximate=True,
                )
                self._published += 1
            except Exception as exc:  # noqa: BLE001 - publisher is best-effort
                self._publish_errors += 1
                logger.warning("stream publish failed (%s); shedding", exc)

    def _heartbeat(self) -> None:
        """Publish comprehensive health metrics to Redis (§0.1 health:tabdeal_ingest:{node_id})."""
        from django.core.cache import cache
        now = time.time()
        uptime_s = now - self._started_at if self._started_at else 0
        rate = self._ingested / uptime_s if uptime_s > 1 else 0.0

        p50 = p99 = 0.0
        if self._latencies_ms:
            ordered = sorted(self._latencies_ms)
            p50 = ordered[len(ordered) // 2]
            p99 = ordered[int(len(ordered) * 0.99)] if len(ordered) > 1 else ordered[-1]

        cache.set(
            f"health:tabdeal_ingest:{self.node_id}",
            {
                "ts": now,
                "uptime_s": round(uptime_s, 1),
                "ingested": self._ingested,
                "published": self._published,
                "publish_errors": self._publish_errors,
                "shed": self._shed,
                "rate_per_s": round(rate, 1),
                "ledger_q_depth": self._ledger_q.qsize(),
                "publish_q_depth": self._publish_q.qsize(),
                "p50_latency_ms": round(p50, 2),
                "p99_latency_ms": round(p99, 2),
                "symbols": self.symbols,
            },
            timeout=30,
        )

    # ----- lifecycle -----

    async def run(self) -> None:
        self._started_at = time.time()
        try:
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await self._redis.ping()
        except Exception as exc:  # noqa: BLE001 - stream is optional; ledger still runs
            logger.warning("Redis unavailable (%s); running ledger-only, publisher disabled", exc)
            self._redis = None

        client = TabdealBroadcastClient(self.symbols, self._on_trade, self._on_gap)
        tasks = [
            asyncio.create_task(client.run(), name="ws"),
            asyncio.create_task(self._ledger_loop(), name="ledger"),
            asyncio.create_task(self._publish_loop(), name="publish"),
        ]
        loop = asyncio.get_running_loop()
        stop = self._stop

        def _request_stop():
            client.stop()
            stop.set()

        import signal
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_stop)
            except NotImplementedError:  # pragma: no cover - Windows
                pass

        logger.info("tabdeal ingest node=%s symbols=%s", self.node_id, self.symbols)
        try:
            await stop.wait()
        finally:
            client.stop()
            # Drain the ledger so nothing buffered is lost on shutdown.
            await asyncio.sleep(0)
            if self.writer.buffered():
                await asyncio.to_thread(self.writer.flush)
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._redis is not None:
                await self._redis.aclose()


def run_ingest(symbols: list[str] | None = None, node_id: str | None = None) -> None:
    import socket
    symbols = symbols or _cfg("TABDEAL_INGEST_SYMBOLS", ["BTC_USDT"])
    node_id = node_id or _cfg("INGEST_NODE_ID", None) or socket.gethostname()
    asyncio.run(IngestService(symbols, node_id).run())
