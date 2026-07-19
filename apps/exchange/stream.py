"""Redis Stream seam between Node A (ingest) and Node B (hot compute) — Master Plan §2.

Node A ``XADD``s trades; Node B consumes them through a **consumer group** that tracks an
acked cursor. On restart B resumes from its last unacked id — the Class-1 self-heal primitive
(§2): a compute crash costs a re-read, never lost history, because the ledger on A is the
durable record and the stream is just the fast path (retention ~24h; older ⇒ ledger replay).
"""
from __future__ import annotations

import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


def sync_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def publish_trade(client: redis.Redis, key: str, row: dict, *, node_id: str = "",
                  maxlen: int | None = None) -> str:
    fields = {"trade_id": row["trade_id"], "ts": row["ts"], "price": row["price"],
              "qty": row.get("qty", 0), "side": row.get("side", ""), "node": node_id}
    return client.xadd(key, fields, maxlen=maxlen, approximate=True)


def ensure_group(client: redis.Redis, key: str, group: str) -> None:
    try:
        client.xgroup_create(name=key, groupname=group, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


class StreamConsumer:
    """Consumer-group reader over one or more trade streams with an acked cursor."""

    def __init__(self, keys: list[str], *, group: str, consumer: str,
                 client: redis.Redis | None = None):
        self.keys = keys
        self.group = group
        self.consumer = consumer
        self.client = client or sync_client()
        self._drained_pending = False
        for k in keys:
            ensure_group(self.client, k, group)

    def read(self, *, block_ms: int = 1000, count: int = 100) -> list[tuple[str, str, dict]]:
        """Return ``(stream_key, entry_id, fields)`` tuples.

        First drains this consumer's *pending* (previously delivered, unacked) entries — the
        crash-recovery path — then switches to new messages (``>``).
        """
        if not self._drained_pending:
            streams = {k: "0" for k in self.keys}
            resp = self.client.xreadgroup(self.group, self.consumer, streams, count=count)
            out = _flatten(resp)
            if not out:
                self._drained_pending = True
            else:
                return out
        streams = {k: ">" for k in self.keys}
        resp = self.client.xreadgroup(self.group, self.consumer, streams, count=count, block=block_ms)
        return _flatten(resp)

    def ack(self, key: str, entry_id: str) -> None:
        self.client.xack(key, self.group, entry_id)


def _flatten(resp) -> list[tuple[str, str, dict]]:
    out: list[tuple[str, str, dict]] = []
    for key, entries in resp or []:
        for entry_id, fields in entries:
            out.append((key, entry_id, fields))
    return out
