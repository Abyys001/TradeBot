"""Custom logging handler that persists log entries to the database and
broadcasts them over the WebSocket for live tail."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from apps.logging.context import get_request_id

#: A log call can happen on Daphne's own event-loop thread — directly (async
#: code like streamhub) or via Django's thread_sensitive dispatch for a
#: perfectly ordinary sync view. `async_to_sync` from either of those deadlocks
#: against the loop it needs (asgiref's CurrentThreadExecutor blocks the real
#: loop while it waits), which freezes the whole ASGI process. Routing the
#: broadcast through a dedicated background loop sidesteps the reentrancy
#: entirely: this thread is never the caller's thread, so there is nothing to
#: deadlock against, and `run_coroutine_threadsafe` doesn't block the caller
#: waiting for it to land.
_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_lock = threading.Lock()


def _broadcast_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop
    with _bg_lock:
        if _bg_loop is None:
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, daemon=True, name="log-broadcast").start()
            _bg_loop = loop
        return _bg_loop

#: The database write cannot run on an event-loop thread. Django's
#: ``async_unsafe`` guard raises ``SynchronousOnlyOperation`` for any ORM call
#: made from a thread with a running loop, and ``emit()``'s catch-all turned
#: that into ``handleError`` — stderr only. Every line the engine and the
#: adapters logged came from exactly there (fan-out legs, reconciles, SL/TP
#: attaches all run on Daphne's loop), so the trading log the admin reads had
#: no ENGINE or EXCHANGE rows in it at all while stderr had them the whole time.
#:
#: One worker, not a pool: writes stay in the order they were logged, and the
#: single long-lived database connection is the cheapest thing that works.
_db_pool: ThreadPoolExecutor | None = None
_db_lock = threading.Lock()

#: Writes allowed to queue before new records are dropped. A logging handler
#: must not become an unbounded buffer in front of a database that has stopped
#: answering — the trade going through matters more than the note about it.
_MAX_PENDING = 500
_pending = 0


def _db_writer() -> ThreadPoolExecutor:
    global _db_pool
    with _db_lock:
        if _db_pool is None:
            _db_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="log-db")
        return _db_pool


def _on_event_loop() -> bool:
    """True when the calling thread is running a loop, i.e. the ORM would raise."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


LEVEL_MAP = {
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

CATEGORY_PREFIXES = {
    "apps.engine": "ENGINE",
    "apps.exchanges": "EXCHANGE",
    "apps.trading": "TRADE",
    "apps.accounts": "ADMIN",
    "apps.logging": "SYSTEM",
    "django": "SYSTEM",
}

EXTRA_ATTRS = (
    "account_id",
    "trade_id",
    "exchange",
    "error_code",
    "context",
    "request_id",
    "category",
)


def _derive_category(name: str) -> str:
    for prefix, category in CATEGORY_PREFIXES.items():
        if name.startswith(prefix):
            return category
    return "SYSTEM"


#: Loggers whose INFO output is transport chatter, not platform events.
#:
#: The database handler hangs off the *root* logger, so before this filter every
#: library that logs at INFO wrote rows into the admin's trading log: one `httpx`
#: line per market-data poll, the autoreloader on every save, urllib3 retries.
#: They are still on the console, where a developer wants them.
#:
#: `httpx` is also the one that matters beyond tidiness — it logs the full
#: request URL, and Binance and Bybit carry `api_key` and `signature` in the
#: query string. Those rows went into the database *and* out over the WebSocket.
#: `_redact` below is the second line of defence for anything that still slips
#: through in a message somebody writes later.
NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "watchfiles",
    "django.utils.autoreload",
    "django.db.backends",
    "django.template",
    "daphne.http",
    "websockets",
    "hpack",
    # channels_redis logs "N of M channels over capacity in group trading" at
    # INFO whenever a socket falls behind. Broadcasting that line — like any
    # other log entry — sends it right back into the "trading" group it is
    # complaining about, which can retrigger the same warning and feed back
    # into itself: one slow client turns into an unbroken burst of identical
    # log rows. It belongs on the console only, never on the channel it is
    # reporting on.
    "channels_redis",
)

#: `key=value` pairs that must never reach the log table, whatever writes them.
_SECRET_PARAM = re.compile(
    r"(?i)\b(api[-_]?key|signature|sign|secret|token|passphrase|password)"
    r"(=|\"?\s*:\s*\"?)([^&\s,;\"'}]+)"
)


def _redact(text: str) -> str:
    return _SECRET_PARAM.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


#: The same names, as a whole JSON *key* rather than a `key=value` pair.
_SECRET_KEY = re.compile(r"(?i)^(api[-_]?key|signature|sign|secret|token|passphrase|password)$")


def _redact_context(value: Any) -> Any:
    """Same rule, applied through the JSON column."""
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, dict):
        return {
            k: "***" if isinstance(k, str) and _SECRET_KEY.match(k) else _redact_context(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_context(v) for v in value]
    return value


class NoiseFilter(logging.Filter):
    """Keeps library chatter out of the *database* handler only."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(NOISY_LOGGERS)


class DatabaseHandler(logging.Handler):
    """Emit log records as LogEntry rows and broadcast to WebSocket group."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = LEVEL_MAP.get(record.levelno)
            if level is None:
                return

            extra: dict[str, Any] = {}
            for attr in EXTRA_ATTRS:
                val = getattr(record, attr, None)
                if val is not None:
                    extra[attr] = val

            entry_data = {
                "level": level,
                "category": extra.get("category") or _derive_category(record.name),
                "source": record.name,
                "message": _redact(record.getMessage()),
                "account_id": extra.get("account_id"),
                "trade_id": extra.get("trade_id"),
                "exchange": extra.get("exchange"),
                "error_code": extra.get("error_code"),
                "context": _redact_context(extra.get("context")),
                # An explicit `extra` wins; otherwise the request being served
                # supplies it, which is how an engine warning ends up traceable
                # to the click that caused it.
                "request_id": extra.get("request_id") or get_request_id(),
            }

            if _on_event_loop():
                self._write_later(record, entry_data)
            else:
                self._write(entry_data)
        except Exception:  # noqa: BLE001 — a logging handler must never raise
            self.handleError(record)

    def _write(self, entry_data: dict[str, Any]) -> None:
        from apps.logging.models import LogEntry

        self._broadcast(LogEntry.objects.create(**entry_data))

    def _write_later(self, record: logging.LogRecord, entry_data: dict[str, Any]) -> None:
        """Hand the row to the writer thread, where the ORM is allowed to run."""
        global _pending

        with _db_lock:
            if _pending >= _MAX_PENDING:
                self.handleError(record)
                return
            _pending += 1

        def task() -> None:
            global _pending
            try:
                # The worker outlives every request on it, so a connection the
                # database has since dropped would wedge it permanently.
                from django.db import close_old_connections

                close_old_connections()
                self._write(entry_data)
            except Exception:  # noqa: BLE001 — still a logging handler
                self.handleError(record)
            finally:
                with _db_lock:
                    _pending -= 1

        _db_writer().submit(task)

    def flush(self, timeout: float = 5.0) -> None:
        """Wait for queued writes to land. Called by ``logging.shutdown()``, so
        a process that exits right after an error still has it in the table."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with _db_lock:
                if _pending == 0:
                    return
            time.sleep(0.01)

    def _broadcast(self, entry) -> None:
        """Fire-and-forget broadcast to the trading WebSocket group."""
        try:
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            if layer is None:
                return
            asyncio.run_coroutine_threadsafe(
                layer.group_send(
                    "trading",
                    {
                        "type": "system_log.entry",
                        "entry": {
                            "id": entry.id,
                            "timestamp": entry.timestamp.isoformat(),
                            "level": entry.level,
                            "category": entry.category,
                            "source": entry.source,
                            "message": entry.message,
                            "account_id": entry.account_id,
                            "trade_id": entry.trade_id,
                            "exchange": entry.exchange,
                            "error_code": entry.error_code,
                            "context": entry.context,
                            "request_id": entry.request_id,
                        },
                    },
                ),
                _broadcast_loop(),
            )
        except Exception:  # noqa: BLE001 — broadcast failure must not break logging
            pass
