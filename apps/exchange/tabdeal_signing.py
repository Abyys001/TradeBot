"""Tabdeal request signing.

UNVERIFIED: assumes a Binance-style HMAC-SHA256 signature over the query
string, sent as a `signature` param with the API key in an `X-MBX-APIKEY`-
style header. Correct this once real Tabdeal docs are available.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode


def sign_query(secret: str, query: str) -> str:
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def build_signed_query(secret: str, params: dict, *, recv_window_ms: int) -> str:
    """Build a `key=value&...&signature=...` query string for a signed request."""
    payload = dict(params)
    payload["timestamp"] = int(time.time() * 1000)
    payload["recvWindow"] = recv_window_ms
    query = urlencode(sorted(payload.items()))
    signature = sign_query(secret, query)
    return f"{query}&signature={signature}"
