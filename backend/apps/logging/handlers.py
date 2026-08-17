"""Custom logging handler that persists log entries to the database and
broadcasts them over the WebSocket for live tail."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

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

EXTRA_ATTRS = ("account_id", "trade_id", "exchange", "error_code", "context", "request_id", "category")


def _derive_category(name: str) -> str:
    for prefix, category in CATEGORY_PREFIXES.items():
        if name.startswith(prefix):
            return category
    return "SYSTEM"


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
                "message": record.getMessage(),
                "account_id": extra.get("account_id"),
                "trade_id": extra.get("trade_id"),
                "exchange": extra.get("exchange"),
                "error_code": extra.get("error_code"),
                "context": extra.get("context"),
                "request_id": extra.get("request_id"),
            }

            from apps.logging.models import LogEntry

            entry = LogEntry.objects.create(**entry_data)

            self._broadcast(entry)
        except Exception:  # noqa: BLE001 — a logging handler must never raise
            self.handleError(record)

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
                        },
                    },
                ),
                _broadcast_loop(),
            )
        except Exception:  # noqa: BLE001 — broadcast failure must not break logging
            pass
