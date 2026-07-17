"""Tabdeal futures client — Binance-compatible signed REST.

Auth: ``X-MBX-APIKEY`` header + HMAC-SHA256 signature over the query string
(params + ``timestamp``), appended as the ``signature`` param. Implements the
``apps.exchange.base.ExchangeClient`` interface so copy-trading can route
orders here the same way it does for Hyperliquid.

Base URL is overridable via the ``TABDEAL_BASE_URL`` setting; defaults to the
documented futures host. Best-effort: methods return a ``Result`` dict instead
of raising so fan-out over many investor accounts never aborts midway.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api1.tabdeal.org/fapi/v1"
RECV_WINDOW_MS = 5000
# Retryable transport/rate-limit signals: HTTP 429/418 and Binance-style
# rate-limit body codes (incl. Tabdeal's 1216).
_RETRY_HTTP = {418, 429}
_RETRY_CODES = {-1003, 1216}
_MAX_RETRIES = 3


class TabdealError(Exception):
    """Raised internally on a non-retryable API error."""


class TabdealClient:
    """``ExchangeClient`` for Tabdeal futures."""

    def __init__(self, credential):
        self.credential = credential
        self.base_url = getattr(settings, "TABDEAL_BASE_URL", "") or DEFAULT_BASE_URL
        self._session = requests.Session()

    # ---- signing -------------------------------------------------------
    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.credential.api_key}

    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        secret = self.credential.get_api_secret().encode("utf-8")
        return hmac.new(secret, query.encode("utf-8"), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, params: dict | None = None) -> dict:
        """Signed request with retry/backoff on rate-limit."""
        params = dict(params or {})
        last_err = "unknown"
        for attempt in range(_MAX_RETRIES):
            signed = dict(params)
            signed["timestamp"] = int(time.time() * 1000)
            signed["recvWindow"] = RECV_WINDOW_MS
            signed["signature"] = self._sign(signed)
            try:
                resp = self._session.request(
                    method,
                    f"{self.base_url}{path}",
                    params=signed,
                    headers=self._headers(),
                    timeout=10,
                )
            except requests.RequestException as exc:
                last_err = type(exc).__name__
                time.sleep(0.5 * (2**attempt))
                continue

            if resp.status_code in _RETRY_HTTP:
                last_err = f"http {resp.status_code}"
                time.sleep(0.5 * (2**attempt))
                continue

            try:
                body = resp.json()
            except ValueError:
                body = {}
            if isinstance(body, dict) and body.get("code") in _RETRY_CODES:
                last_err = f"code {body.get('code')}"
                time.sleep(0.5 * (2**attempt))
                continue

            if resp.status_code >= 400:
                msg = body.get("msg") if isinstance(body, dict) else resp.text[:120]
                raise TabdealError(f"{resp.status_code}: {msg}")
            return body
        raise TabdealError(f"rate-limited/unreachable after retries ({last_err})")

    # ---- symbol helper -------------------------------------------------
    @staticmethod
    def _symbol(coin: str) -> str:
        """Map an HL-style coin ("BTC") to a Tabdeal pair ("BTCUSDT")."""
        c = coin.upper()
        return c if c.endswith(("USDT", "USDC")) else f"{c}USDT"

    # ---- ExchangeClient interface -------------------------------------
    def verify(self) -> tuple[bool, str]:
        cred = self.credential
        if not cred.api_key or cred.api_secret_enc is None:
            return False, "missing api key or secret"
        try:
            self._request("GET", "/balance")
        except TabdealError as exc:
            cred.is_active = False
            cred.save(update_fields=["is_active"])
            return False, f"auth failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tabdeal verify %s failed: %s", cred.pk, type(exc).__name__)
            cred.is_active = False
            cred.save(update_fields=["is_active"])
            return False, f"request failed: {type(exc).__name__}"
        cred.is_active = True
        cred.last_verified_at = timezone.now()
        cred.permissions = {"exchange": "tabdeal", "verified": True}
        cred.save(update_fields=["is_active", "last_verified_at", "permissions"])
        return True, "verified"

    def place_order(
        self,
        coin: str,
        is_buy: bool,
        size: float,
        *,
        price: float | None = None,
        reduce_only: bool = False,
    ) -> dict:
        params = {
            "symbol": self._symbol(coin),
            "side": "BUY" if is_buy else "SELL",
            "type": "MARKET" if price is None else "LIMIT",
            "quantity": float(size),
            "reduceOnly": "true" if reduce_only else "false",
        }
        if price is not None:
            params["price"] = float(price)
            params["timeInForce"] = "GTC"
        try:
            resp = self._request("POST", "/order", params)
            return {"ok": True, "coin": coin, "response": resp}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Tabdeal place_order failed cred %s coin %s: %s",
                self.credential.pk,
                coin,
                type(exc).__name__,
            )
            return {"ok": False, "coin": coin, "error": str(exc)}

    def close_position(self, coin: str) -> dict:
        """Market-close by placing a reduce-only order opposite the position."""
        for pos in self.positions():
            if pos["coin"].upper() == self._symbol(coin):
                size = abs(pos["size"])
                if size == 0:
                    return {"ok": True, "coin": coin, "closed": 0}
                is_buy = pos["size"] < 0  # long -> sell, short -> buy
                return self.place_order(coin, is_buy, size, reduce_only=True)
        return {"ok": True, "coin": coin, "closed": 0}

    def positions(self) -> list[dict]:
        try:
            rows = self._request("GET", "/positionRisk")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Tabdeal positions failed cred %s: %s", self.credential.pk, type(exc).__name__
            )
            return []
        out = []
        for r in rows if isinstance(rows, list) else []:
            try:
                size = float(r.get("positionAmt", 0))
            except (TypeError, ValueError):
                continue
            if size == 0:
                continue
            out.append(
                {
                    "coin": r.get("symbol"),
                    "size": size,
                    "entry": r.get("entryPrice"),
                    "unrealized_pnl": r.get("unRealizedProfit"),
                }
            )
        return out

    def set_leverage(self, coin: str, leverage: int, *, is_cross: bool = True) -> dict:
        try:
            resp = self._request(
                "POST",
                "/leverage",
                {"symbol": self._symbol(coin), "leverage": int(leverage)},
            )
            return {"ok": True, "response": resp, "leverage": leverage, "coin": coin}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def cancel_all(self) -> dict:
        """Cancel all open orders across symbols that currently hold positions."""
        symbols = {p["coin"] for p in self.positions() if p.get("coin")}
        cancelled = 0
        errors = []
        for sym in symbols:
            try:
                self._request("DELETE", "/allOpenOrders", {"symbol": sym})
                cancelled += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        return {"ok": not errors, "cancelled": cancelled, "errors": errors}

    def balance(self) -> float:
        """Sum available + unrealized balance across USDT/USDC wallets."""
        try:
            rows = self._request("GET", "/balance")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Tabdeal balance failed cred %s: %s", self.credential.pk, type(exc).__name__
            )
            return 0.0
        total = 0.0
        for r in rows if isinstance(rows, list) else []:
            if str(r.get("asset", "")).upper() in ("USDT", "USDC", "USD"):
                try:
                    total += float(r.get("balance", 0) or 0)
                except (TypeError, ValueError):
                    continue
        return total
