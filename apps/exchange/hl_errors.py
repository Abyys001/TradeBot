"""Hyperliquid exchange error code mapping."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HLErrorInfo:
    code: str
    message: str
    action: str


_ERROR_MAP: dict[str, HLErrorInfo] = {
    "Tick": HLErrorInfo(
        "Tick",
        "Price does not match tick size",
        "Round price to the asset tick grid",
    ),
    "MinTradeNtl": HLErrorInfo(
        "MinTradeNtl",
        "Order notional below minimum (~$10)",
        "Increase size or price",
    ),
    "PerpMargin": HLErrorInfo(
        "PerpMargin",
        "Insufficient margin for perp order",
        "Reduce size or add collateral",
    ),
    "MissingOrder": HLErrorInfo(
        "MissingOrder",
        "Order already filled or canceled",
        "Refresh open orders before cancel/modify",
    ),
    "PositionIncreaseAtOpenInterestCap": HLErrorInfo(
        "PositionIncreaseAtOpenInterestCap",
        "Open interest cap reached",
        "Wait or use reduce-only orders",
    ),
    "ReduceOnly": HLErrorInfo(
        "ReduceOnly",
        "Order would increase position while reduce-only",
        "Check position direction and size",
    ),
    "BadAloPx": HLErrorInfo(
        "BadAloPx",
        "Post-only order would cross the book",
        "Adjust limit price or use IOC/GTC",
    ),
}


def parse_order_status(status: dict) -> tuple[str | None, HLErrorInfo | None]:
    """Return (exchange_oid, error_info) from a single HL order status dict."""
    if "filled" in status:
        return str(status["filled"].get("oid", "")), None
    if "resting" in status:
        return str(status["resting"].get("oid", "")), None
    if "error" in status:
        err = str(status["error"])
        for code, info in _ERROR_MAP.items():
            if code in err:
                return None, info
        return None, HLErrorInfo("Unknown", err, "Review order parameters")
    return None, None


def parse_exchange_response(resp: dict) -> list[tuple[str | None, HLErrorInfo | None]]:
    """Parse all per-order statuses from an exchange API response."""
    if not isinstance(resp, dict) or resp.get("status") != "ok":
        return [(None, HLErrorInfo("RequestFailed", str(resp), "Retry or check logs"))]
    statuses = (resp.get("response") or {}).get("data", {}).get("statuses") or []
    return [parse_order_status(st) for st in statuses]
