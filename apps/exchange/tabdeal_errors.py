"""Tabdeal exchange error code mapping.

UNVERIFIED: codes below are placeholders modeled on Binance's `{"code", "msg"}`
error envelope, since Tabdeal's real error taxonomy is not yet documented.
Replace `_ERROR_MAP` entries once real API docs/sandbox responses are available.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TabdealErrorInfo:
    code: str
    message: str
    action: str


_ERROR_MAP: dict[str, TabdealErrorInfo] = {
    "-1013": TabdealErrorInfo(
        "-1013",
        "Filter failure (min notional / lot size)",  # TODO: verify against real Tabdeal codes
        "Increase order size or check pair filters",
    ),
    "-2010": TabdealErrorInfo(
        "-2010",
        "Insufficient balance",  # TODO: verify
        "Reduce order size or add funds",
    ),
    "-1021": TabdealErrorInfo(
        "-1021",
        "Timestamp outside of recvWindow",  # TODO: verify
        "Check server clock skew and recvWindow setting",
    ),
    "-2015": TabdealErrorInfo(
        "-2015",
        "Invalid API key, IP, or permissions",  # TODO: verify
        "Re-verify credentials and IP allowlist",
    ),
}


def parse_response(resp_json: dict) -> tuple[bool, TabdealErrorInfo | None]:
    """Return (ok, error_info) for a raw Tabdeal JSON response.

    UNVERIFIED: assumes a Binance-style `{"code": <int>, "msg": <str>}` shape
    on failure and the absence of a top-level "code" key on success.
    """
    if not isinstance(resp_json, dict):
        return False, TabdealErrorInfo("Unknown", str(resp_json), "Review response format")
    code = resp_json.get("code")
    if code is None:
        return True, None
    info = _ERROR_MAP.get(str(code))
    if info is not None:
        return False, info
    return False, TabdealErrorInfo(str(code), resp_json.get("msg", "Unknown error"), "Review order parameters")
