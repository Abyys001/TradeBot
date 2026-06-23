"""Redis persistence for live interpreter sessions."""
from __future__ import annotations

import hashlib
import json

import redis
from django.conf import settings

from ..runtime.context import NA, SeriesBuffer
from .sliding_window import SlidingWindow


def _client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(strategy_id: int) -> str:
    prefix = getattr(settings, "LIVE_SESSION_KEY_PREFIX", "live:session")
    return f"{prefix}:{strategy_id}"


def source_hash(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def save_session(strategy_id: int, *, window: SlidingWindow, ctx, source: str) -> None:
    scalar_state = {}
    for name, buf in ctx.scalars.items():
        scalar_state[name] = {
            "values": [_serialize(v) for v in buf.values],
            "current": _serialize(buf.current),
        }
    payload = {
        "window": window.to_rows(),
        "scalar_state": scalar_state,
        "source_hash": source_hash(source),
        "bar_count": ctx.n,
    }
    _client().set(_key(strategy_id), json.dumps(payload))


def load_session(strategy_id: int) -> dict | None:
    raw = _client().get(_key(strategy_id))
    if raw is None:
        return None
    return json.loads(raw)


def delete_session(strategy_id: int) -> None:
    _client().delete(_key(strategy_id))


def session_exists(strategy_id: int) -> bool:
    return _client().exists(_key(strategy_id)) > 0


def restore_scalars(session: dict) -> dict[str, SeriesBuffer]:
    out: dict[str, SeriesBuffer] = {}
    for name, data in session.get("scalar_state", {}).items():
        buf = SeriesBuffer()
        buf.values = [_deserialize(v) for v in data.get("values", [])]
        buf.current = _deserialize(data.get("current", NA))
        out[name] = buf
    return out


def _serialize(v):
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return None
    if isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def _deserialize(v):
    if v is None:
        return NA
    return v
