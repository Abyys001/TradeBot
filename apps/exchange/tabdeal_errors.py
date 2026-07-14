"""Tabdeal exchange error code mapping.

Codes verified against Tabdeal_API_Reference.md §11. Tabdeal returns failures as
``{"code": <int>, "msg": "<string>"}``. FAPI reuses/overloads some numbers, so a
few entries are context-dependent (noted below).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TabdealErrorInfo:
    code: str
    message: str
    action: str


class TabdealAPIError(Exception):
    """Raised when Tabdeal returns a ``{code, msg}`` error envelope."""

    def __init__(self, info: "TabdealErrorInfo"):
        self.info = info
        super().__init__(f"[{info.code}] {info.message}")


_ERROR_MAP: dict[str, TabdealErrorInfo] = {
    # Auth
    "1100": TabdealErrorInfo("1100", "Missing signature/timestamp/api-key, or api-key unknown", "Check API key and signing"),
    "1101": TabdealErrorInfo("1101", "Invalid timestamp — clock skew > 60s or outside recv window", "Sync clock via /r/fapi/v1/time"),
    "1102": TabdealErrorInfo("1102", "Invalid recvWindow (must be <= 60000)", "Lower TABDEAL_RECV_WINDOW_MS"),
    "1103": TabdealErrorInfo("1103", "Invalid signature", "Re-check api-secret and query signing"),
    # Request
    "1201": TabdealErrorInfo("1201", "Invalid parameters sent", "Review order parameters"),
    "1203": TabdealErrorInfo("1203", "Required parameter missing/invalid (FAPI: type must be LIMIT or MARKET)", "Fix request params"),
    "1204": TabdealErrorInfo("1204", "Order not found", "Verify orderId/symbol"),
    "1206": TabdealErrorInfo("1206", "Market/symbol not found", "Check symbol"),
    "1208": TabdealErrorInfo("1208", "Order violates market rules / invalid symbol or asset", "Round to tick/step, check filters"),
    "1209": TabdealErrorInfo("1209", "Validation error on amount/price (balance, qty, min/max)", "Reduce size or fix price"),
    "1213": TabdealErrorInfo("1213", "An order already exists with this clientOrderId", "Use a fresh client order id"),
    "1216": TabdealErrorInfo("1216", "Rate limit exceeded", "Back off and retry"),
    "1218": TabdealErrorInfo("1218", "Insufficient balance/credit", "Add funds or reduce size"),
    # FAPI-specific
    "1207": TabdealErrorInfo("1207", "Futures/Pro-Leverage not active for this account", "Call set-leverage once to activate"),
    "1300": TabdealErrorInfo("1300", "Server error (unspecified)", "Retry later"),
    # Margin / position SL-TP
    "5015": TabdealErrorInfo("5015", "You have no open position currently", "Open a position before SL/TP"),
    "5016": TabdealErrorInfo("5016", "Order not filled / no open position — SL/TP needs an open position", "Wait for fill"),
    "5017": TabdealErrorInfo("5017", "Only one active stop-loss allowed per position", "Cancel existing SL first"),
    "5018": TabdealErrorInfo("5018", "Only one active take-profit allowed per position", "Cancel existing TP first"),
    "5019": TabdealErrorInfo("5019", "The entered price is invalid", "Fix SL/TP price"),
    "5020": TabdealErrorInfo("5020", "No active SL/TP exists for this position", "Nothing to modify"),
}


def error_info(code: object, msg: str = "") -> TabdealErrorInfo:
    info = _ERROR_MAP.get(str(code))
    if info is not None:
        return info
    return TabdealErrorInfo(str(code), msg or "Unknown error", "Review request")


def parse_response(resp_json: dict) -> tuple[bool, TabdealErrorInfo | None]:
    """Return ``(ok, error_info)`` for a raw Tabdeal JSON response.

    A ``{"code": <int>, "msg": <str>}`` shape signals failure; the absence of a
    top-level ``code`` key means success.
    """
    if not isinstance(resp_json, dict):
        return True, None
    code = resp_json.get("code")
    if code is None:
        return True, None
    return False, error_info(code, resp_json.get("msg", ""))
