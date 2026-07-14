"""Tabdeal Futures (FAPI) REST client.

Verified against Tabdeal_API_Reference.md §9. The FAPI surface is
Binance-Futures-shaped: ``X-MBX-APIKEY`` header + ``timestamp`` + ``signature``
signing (see tabdeal_signing). Signed params are sent in the query string for
every method (Binance-compatible), which the spec permits ("params may go in
query string or JSON body").

Order types are limited to LIMIT/MARKET; protective SL/TP is attached to an
*existing* position via ``POST /fapi/v1/positionSlTp`` (§9.23), not the order
endpoint. Futures must be activated once per key via set-leverage (error 1207).
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.utils import timezone

from .tabdeal_constants import base_url, recv_window_ms
from .tabdeal_errors import TabdealAPIError, parse_response
from .tabdeal_signing import build_signed_query

logger = logging.getLogger(__name__)


class TabdealFuturesClient:
    """REST wrapper for one ExchangeCredential (exchange=TABDEAL), futures only."""

    def __init__(self, credential):
        self._credential = credential
        self._api_key = credential.get_api_key()
        self._api_secret = credential.get_api_secret()
        self._base_url = base_url()
        self._timeout = getattr(settings, "TABDEAL_API_TIMEOUT", getattr(settings, "HL_API_TIMEOUT", 30))

    # ----- low-level request helpers -----

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self._api_key}

    def _public(self, path: str, params: dict | None = None) -> dict:
        """Unsigned [NONE] GET (exchangeInfo, time, ping, depth)."""
        url = f"{self._base_url}{path}"
        resp = requests.get(url, params=params or {}, timeout=self._timeout)
        return self._parse(resp)

    def _signed(self, method: str, path: str, params: dict | None = None) -> dict:
        """Signed [TRADE] request; signed params go in the query string."""
        query = build_signed_query(self._api_secret, params or {})
        url = f"{self._base_url}{path}?{query}"
        resp = requests.request(method, url, headers=self._headers(), timeout=self._timeout)
        return self._parse(resp)

    @staticmethod
    def _parse(resp: "requests.Response") -> dict:
        try:
            data = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise TabdealAPIError(_generic(f"non-JSON response (HTTP {resp.status_code})"))
        # Tabdeal signals failure with a top-level {code, msg}; list responses are fine.
        if isinstance(data, dict):
            ok, info = parse_response(data)
            if not ok and info is not None:
                raise TabdealAPIError(info)
        return data

    # ----- public market metadata -----

    def server_time(self) -> int:
        return int(self._public("/r/fapi/v1/time").get("serverTime", 0))

    def exchange_info(self, symbol: str | None = None) -> dict:
        params = {"symbol": symbol} if symbol else None
        return self._public("/r/fapi/v1/exchangeInfo", params)

    def symbol_precision(self, symbol: str) -> tuple[int, int]:
        """Return (pricePrecision, quantityPrecision) for a futures symbol."""
        info = self.exchange_info(symbol)
        symbols = info.get("symbols") or info.get("data") or []
        for s in symbols:
            if s.get("symbol") == symbol:
                return int(s.get("pricePrecision", 2)), int(s.get("quantityPrecision", 3))
        return 2, 3

    # ----- account / balance / positions -----

    def verify_credentials(self) -> tuple[bool, str]:
        """Confirm the key/secret are valid and can read the futures account."""
        try:
            acct = self._signed("GET", "/r/fapi/v3/account")
        except TabdealAPIError as exc:
            # 1207 = futures not active yet; the key is otherwise valid.
            if exc.info.code == "1207":
                return False, "futures not active — set leverage once to activate (error 1207)"
            return False, exc.info.message
        except Exception as exc:  # noqa: BLE001
            logger.warning("tabdeal verify failed: %s", type(exc).__name__)
            return False, f"request failed: {type(exc).__name__}"
        if acct.get("canTrade") is False:
            return False, "API key cannot trade (enable futures trading permission)"
        return True, "verified"

    def get_balance(self) -> list[dict]:
        """Per-asset futures balance (walletBalance, availableBalance, crossUnPnl)."""
        data = self._signed("GET", "/r/fapi/v3/balance")
        return data if isinstance(data, list) else data.get("assets", [])

    def available_usdt(self) -> float:
        """USDT available balance in the futures wallet (0.0 if none)."""
        for b in self.get_balance():
            if b.get("asset") == "USDT":
                try:
                    return float(b.get("availableBalance", b.get("walletBalance", 0)))
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    def account(self) -> dict:
        return self._signed("GET", "/r/fapi/v3/account")

    def get_positions(self, symbol: str | None = None) -> list[dict]:
        params = {"symbol": symbol} if symbol else None
        data = self._signed("GET", "/r/fapi/v3/positionRisk", params)
        return data if isinstance(data, list) else data.get("positions", [])

    def get_position(self, symbol: str) -> dict | None:
        """Return the open position for a symbol (positionAmt != 0), else None."""
        for p in self.get_positions(symbol):
            if p.get("symbol") == symbol:
                try:
                    if float(p.get("positionAmt", 0)) != 0:
                        return p
                except (TypeError, ValueError):
                    continue
        return None

    # ----- leverage -----

    def get_leverage(self, symbol: str) -> int:
        data = self._signed("GET", "/r/fapi/v1/leverage", {"symbol": symbol})
        return int(data.get("leverage", 0))

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """Set leverage; also activates Futures/Pro-Leverage on first call (error 1207)."""
        return self._signed("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": int(leverage)})

    def activate_futures(self, symbol: str, leverage: int = 1) -> dict:
        """Idempotent onboarding: ensure futures is active by setting leverage once."""
        return self.set_leverage(symbol, leverage)

    # ----- orders -----

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict:
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
        }
        if price is not None:
            params["price"] = price
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._signed("POST", "/fapi/v1/order", params)

    def place_limit_order(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC",
        client_order_id: str | None = None,
    ) -> dict:
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "quantity": quantity,
            "price": price,
            "timeInForce": time_in_force,
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        return self._signed("POST", "/fapi/v1/order", params)

    def get_order(self, symbol: str, order_id: int) -> dict:
        return self._signed("GET", "/r/fapi/v1/order", {"symbol": symbol, "orderId": order_id})

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        return self._signed("DELETE", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id})

    def open_orders(self, symbol: str | None = None) -> list[dict]:
        params = {"symbol": symbol} if symbol else None
        data = self._signed("GET", "/r/fapi/v1/openOrders", params)
        return data if isinstance(data, list) else data.get("orders", [])

    # ----- position close & protective SL/TP -----

    def close_position(self, symbol: str) -> dict:
        """Market-close the entire open position for a symbol (§9.22)."""
        return self._signed("DELETE", "/fapi/v1/position", {"symbol": symbol})

    def set_position_sl_tp(
        self,
        *,
        position_id: int,
        sl_price: float | None = None,
        tp_price: float | None = None,
        symbol: str | None = None,
        working_type: str | None = None,
    ) -> dict:
        """Attach stop-loss/take-profit to an existing position (§9.23).

        At least one of sl_price/tp_price is required. Only one active SL and one
        active TP per position (errors 5017/5018).
        """
        if sl_price is None and tp_price is None:
            raise ValueError("at least one of sl_price/tp_price required")
        params: dict = {"positionId": position_id}
        if symbol:
            params["symbol"] = symbol
        if sl_price is not None:
            params["slPrice"] = sl_price
        if tp_price is not None:
            params["tpPrice"] = tp_price
        if working_type:
            params["workingType"] = working_type
        return self._signed("POST", "/fapi/v1/positionSlTp", params)

    def user_trades(self, symbol: str, *, limit: int = 50) -> list[dict]:
        data = self._signed("GET", "/r/fapi/v1/userTrades", {"symbol": symbol, "limit": limit})
        return data if isinstance(data, list) else data.get("trades", [])


def _generic(msg: str):
    from .tabdeal_errors import TabdealErrorInfo

    return TabdealErrorInfo("unknown", msg, "Review response")


def verify_tabdeal_credential(cred) -> tuple[bool, str]:
    """Validate a Tabdeal credential and persist is_active/last_verified_at.

    Mirrors apps.exchange.hl_client.verify_credential's persistence contract so
    the credentials verify view/task can dispatch on exchange transparently.
    """
    client = TabdealFuturesClient(cred)
    ok, detail = client.verify_credentials()
    if ok:
        cred.is_active = True
        cred.last_verified_at = timezone.now()
        cred.permissions = {"exchange": "tabdeal", "network": cred.network, "canTrade": True}
        cred.save(update_fields=["is_active", "last_verified_at", "permissions"])
    else:
        # Don't flip is_active off on a transient network error; only on a clear rejection.
        if not detail.startswith("request failed"):
            cred.is_active = False
            cred.save(update_fields=["is_active"])
    return ok, detail
