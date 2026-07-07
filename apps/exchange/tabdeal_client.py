"""Tabdeal REST client scaffold.

UNVERIFIED: Tabdeal has no official Python SDK (unlike Hyperliquid), and we
do not yet have real API docs or sandbox credentials. Endpoint paths, request
shapes, and response shapes below are placeholders modeled on Binance's
public REST API (which Tabdeal is said to mirror) — every TODO must be
checked against real Tabdeal documentation before this client is used against
a live account.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

from .tabdeal_constants import base_url, recv_window_ms
from .tabdeal_signing import build_signed_query

logger = logging.getLogger(__name__)


class TabdealClient:
    """Hand-rolled REST wrapper for a single ExchangeCredential (exchange=TABDEAL)."""

    def __init__(self, credential):
        self._credential = credential
        self._api_key = credential.get_api_key()
        self._api_secret = credential.get_api_secret()
        self._base_url = base_url()
        self._timeout = getattr(settings, "HL_API_TIMEOUT", 30)

    def _headers(self) -> dict:
        # TODO: confirm Tabdeal's auth header name (assumed Binance-style X-MBX-APIKEY).
        return {"X-MBX-APIKEY": self._api_key}

    def _signed_request(self, method: str, path: str, params: dict | None = None) -> dict:
        query = build_signed_query(self._api_secret, params or {}, recv_window_ms=recv_window_ms())
        url = f"{self._base_url}{path}?{query}"
        resp = requests.request(method, url, headers=self._headers(), timeout=self._timeout)
        return resp.json()

    def verify_credentials(self) -> tuple[bool, str]:
        """Confirm the API key/secret are valid and can read account data."""
        # TODO: confirm real endpoint path (assumed GET /api/v1/account).
        try:
            resp = self._signed_request("GET", "/api/v1/account")
        except Exception as exc:  # noqa: BLE001
            logger.warning("tabdeal verify_credentials failed: %s", type(exc).__name__)
            return False, str(exc)
        if resp.get("code") is not None:
            return False, resp.get("msg", "verification failed")
        return True, "ok"

    def get_balance(self, asset: str | None = None) -> dict:
        """Return account balance. If `asset` is given, return that asset's free/locked amounts."""
        # TODO: confirm real endpoint path and response shape.
        resp = self._signed_request("GET", "/api/v1/account")
        balances = {b["asset"]: b for b in resp.get("balances", [])}
        if asset:
            return balances.get(asset, {"asset": asset, "free": "0", "locked": "0"})
        return balances

    def place_market_order(
        self,
        *,
        pair: str,
        side: str,
        quote_qty: float | None = None,
        base_qty: float | None = None,
    ) -> dict:
        """Place a market order. BUY sizes off `quote_qty`, SELL sizes off `base_qty`."""
        # TODO: confirm real endpoint path/params (assumed POST /api/v1/order).
        params = {"symbol": pair, "side": side.upper(), "type": "MARKET"}
        if quote_qty is not None:
            params["quoteOrderQty"] = quote_qty
        if base_qty is not None:
            params["quantity"] = base_qty
        return self._signed_request("POST", "/api/v1/order", params)
