"""Custom logging handler that persists log entries to the database and
broadcasts them over the WebSocket for live tail."""

from __future__ import annotations

import logging
from typing import Any

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
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            if layer is None:
                return
            async_to_sync(layer.group_send)(
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
            )
        except Exception:  # noqa: BLE001 — broadcast failure must not break logging
            pass
