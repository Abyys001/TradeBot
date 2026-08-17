from __future__ import annotations

import logging
from typing import Any


def system_log(
    level: str,
    category: str,
    message: str,
    *,
    source: str | None = None,
    account_id: int | None = None,
    trade_id: int | None = None,
    exchange: str | None = None,
    error_code: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    extra: dict[str, Any] = {
        "category": category,
        "account_id": account_id,
        "trade_id": trade_id,
        "exchange": exchange,
        "error_code": error_code,
        "context": context,
    }
    logger_name = source or f"apps.logging.{category.lower()}"
    logger = logging.getLogger(logger_name)
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(log_level, message, extra=extra)
