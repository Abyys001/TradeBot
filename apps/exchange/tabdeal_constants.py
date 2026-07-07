"""Tabdeal network URL and config.

NOTE: Tabdeal's exact REST API base URL, endpoint paths, and response shapes
are UNVERIFIED against real documentation — this module and its siblings
(tabdeal_signing.py, tabdeal_errors.py, tabdeal_client.py) are a Binance-style
scaffold to be corrected once real docs or sandbox access are available.
"""
from __future__ import annotations

from django.conf import settings


def base_url() -> str:
    return getattr(settings, "TABDEAL_API_BASE_URL", "https://api.tabdeal.org")


def recv_window_ms() -> int:
    return getattr(settings, "TABDEAL_RECV_WINDOW_MS", 5000)
