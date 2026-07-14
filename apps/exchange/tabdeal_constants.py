"""Tabdeal network URL and config.

Verified against Tabdeal_API_Reference.md: REST base host is
``https://api1.tabdeal.org``. Futures endpoints live under the ``fapi``
namespace and are structurally Binance-Futures compatible. Read (GET) paths are
generally ``r/``-prefixed; write paths (POST/DELETE) omit it — always use the
exact path per endpoint.
"""
from __future__ import annotations

from django.conf import settings

DEFAULT_BASE_URL = "https://api1.tabdeal.org"


def base_url() -> str:
    return getattr(settings, "TABDEAL_API_BASE_URL", DEFAULT_BASE_URL)


def recv_window_ms() -> int:
    return getattr(settings, "TABDEAL_RECV_WINDOW_MS", 5000)
