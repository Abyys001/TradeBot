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


def _ws_host() -> str:
    """WS scheme host derived from the REST base (https -> wss)."""
    base = base_url()
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):]
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):]
    return base


def broadcast_url() -> str:
    """FAPI plain-text trade broadcast (Tabdeal_API_Reference.md §10.2)."""
    override = getattr(settings, "TABDEAL_BROADCAST_URL", "")
    return override or (_ws_host().rstrip("/") + "/special_margin/broadcast/")


def fapi_stream_url() -> str:
    """FAPI JSON order-book stream (Tabdeal_API_Reference.md §10.1)."""
    override = getattr(settings, "TABDEAL_FAPI_STREAM_URL", "")
    return override or (_ws_host().rstrip("/") + "/special_margin/stream/")
