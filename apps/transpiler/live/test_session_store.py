"""Tests for live session persistence (Redis save/load/restore round-trip)."""
import pandas as pd

from apps.transpiler.engine import compile
from apps.transpiler.live import session_store
from apps.transpiler.live.sliding_window import SlidingWindow
from apps.transpiler.runtime import interpreter
from apps.transpiler.runtime.context import ExecutionContext
from apps.transpiler.runtime.order_router import WarmupBroker


class _FakeRedis:
    """Minimal in-memory stand-in for redis.Redis (decode_responses=True)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def exists(self, key):
        return 1 if key in self.store else 0


def _ohlcv_df(n=15):
    rows = [{"ts": 1000 + i, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 10} for i in range(n)]
    return pd.DataFrame(rows)


SRC = 'strategy("x")\nvar int counter = 0\ncounter := counter + 1\n'


def _make_ctx_and_window():
    df = _ohlcv_df()
    program = compile(SRC)
    window = SlidingWindow(max_size=len(df))
    window.load_df(df)
    ctx = ExecutionContext(window.to_dataframe(), WarmupBroker(), header=program.header)
    interpreter.run_warmup(program, ctx)
    return ctx, window


def test_session_save_load_round_trip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(session_store, "_client", lambda: fake)

    ctx, window = _make_ctx_and_window()
    session_store.save_session(42, window=window, ctx=ctx, source=SRC)

    assert session_store.session_exists(42) is True
    loaded = session_store.load_session(42)
    assert loaded is not None
    assert loaded["source_hash"] == session_store.source_hash(SRC)
    assert loaded["bar_count"] == ctx.n
    assert len(loaded["window"]) == len(window)


def test_restore_scalars_rebuilds_buffers(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(session_store, "_client", lambda: fake)

    ctx, window = _make_ctx_and_window()
    session_store.save_session(7, window=window, ctx=ctx, source=SRC)
    loaded = session_store.load_session(7)
    scalars = session_store.restore_scalars(loaded)

    assert "counter" in scalars
    # counter incremented once per bar
    assert scalars["counter"].values[-1] == ctx.scalars["counter"].values[-1]


def test_delete_session(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(session_store, "_client", lambda: fake)
    ctx, window = _make_ctx_and_window()
    session_store.save_session(1, window=window, ctx=ctx, source=SRC)
    session_store.delete_session(1)
    assert session_store.session_exists(1) is False
    assert session_store.load_session(1) is None
