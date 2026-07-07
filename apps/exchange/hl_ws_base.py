"""Shared WS resilience helpers (ping + reconnect primitives)."""
from __future__ import annotations

import time


class WSResilienceMixin:
    """Small mixin used by feed processes for ping+timestamps."""

    _last_msg_ts: float

    def mark_msg(self) -> None:
        self._last_msg_ts = time.time()

    def is_stale(self, *, stale_seconds: int = 60) -> bool:
        return time.time() - float(getattr(self, "_last_msg_ts", 0)) > stale_seconds

