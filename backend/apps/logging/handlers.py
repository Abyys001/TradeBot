"""Custom logging handler that persists log entries to the database and
broadcasts them over the WebSocket for live tail."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
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
                            "request_id": entry.request_id,
                        },
                    },
                ),
                _broadcast_loop(),
            )
        except Exception:  # noqa: BLE001 — broadcast failure must not break logging
            pass
