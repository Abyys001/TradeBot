"""Tabdeal request signing.

Verified against Tabdeal_API_Reference.md §1: a signed (``TRADE``) request sends
the API key in an ``X-MBX-APIKEY`` header, appends a millisecond ``timestamp``
to the params, HMAC-SHA256s the resulting query string with the API secret, and
appends the hex digest as a ``signature`` param. Identical across Spot / Margin /
FAPI — only the header and base path differ.

``recvWindow`` is optional (spec error 1102 caps it at 60000). The FAPI order
docs do not list it, so callers may omit it by passing ``recv_window_ms=None``.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode


def sign_query(secret: str, query: str) -> str:
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def build_signed_query(secret: str, params: dict, *, recv_window_ms: int | None = None) -> str:
    """Build a ``key=value&...&signature=...`` query string for a signed request."""
    payload = {k: v for k, v in params.items() if v is not None}
    payload["timestamp"] = int(time.time() * 1000)
    if recv_window_ms is not None:
        payload["recvWindow"] = recv_window_ms
    query = urlencode(sorted(payload.items()))
    signature = sign_query(secret, query)
    return f"{query}&signature={signature}"
