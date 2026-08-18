"""Regression test for the production hang traced to `DatabaseHandler`.

`_broadcast` used to call `async_to_sync(layer.group_send)` directly. A log
call issued from a thread that already has its own asyncio event loop running
(streamhub's `_pump`, or a sync Django view dispatched onto Channels' shared
thread-sensitive worker) sent that call straight back into the loop it was
already running on top of — asgiref's classic same-thread `AsyncToSync`
reentrancy trap. In production this froze the whole ASGI process at 0% CPU;
only a manual restart brought it back. `_broadcast` now hands the coroutine to
a dedicated background loop via `run_coroutine_threadsafe`, which shares no
thread-sensitive lineage with the caller and so cannot deadlock against it.
"""

from __future__ import annotations

import asyncio
import logging
import threading

import pytest

from apps.logging.handlers import DatabaseHandler

pytestmark = pytest.mark.django_db(transaction=True)


def _record(message: str = "test message") -> logging.LogRecord:
    return logging.LogRecord(
        "apps.trading.streamhub", logging.INFO, __file__, 1, message, (), None
    )


def test_emit_from_a_thread_running_its_own_event_loop_does_not_hang():
    """The exact shape of the production trigger: a log call issued while the
    calling thread is itself inside `loop.run_forever()`."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    handler = DatabaseHandler()
    done = threading.Event()
    outcome: dict[str, object] = {}

    def call_emit() -> None:
        try:
            handler.emit(_record())
            outcome["ok"] = True
        except Exception as exc:  # pragma: no cover - would fail the test anyway
            outcome["error"] = exc
        finally:
            done.set()

    try:
        loop.call_soon_threadsafe(call_emit)
        assert done.wait(timeout=5), "DatabaseHandler.emit() deadlocked"
        assert outcome.get("ok") is True, outcome.get("error")
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)


def test_emit_from_a_plain_sync_thread_still_persists_and_broadcasts():
    from apps.logging.models import LogEntry

    handler = DatabaseHandler()
    handler.emit(_record("plain thread message"))

    assert LogEntry.objects.filter(message="plain thread message").exists()


def test_emit_from_an_event_loop_thread_still_reaches_the_database():
    """Not hanging was never enough — the row has to land.

    Every engine and adapter log call is made from Daphne's event-loop thread,
    where the ORM raises `SynchronousOnlyOperation`. `emit()`'s catch-all sent
    that to `handleError`, so the System Log page had no ENGINE row in it ever
    while the same lines were on stderr all along — including the fan-out
    timeout and the reconcile verdict behind a live unprotected position.
    """
    from apps.logging.models import LogEntry

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    handler = DatabaseHandler()
    done = threading.Event()

    def call_emit() -> None:
        handler.emit(_record("engine message from the loop"))
        done.set()

    try:
        loop.call_soon_threadsafe(call_emit)
        assert done.wait(timeout=5)
        handler.flush()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)

    assert LogEntry.objects.filter(message="engine message from the loop").exists()
