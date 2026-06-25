"""Risk gates for live trading on Hyperliquid."""
from __future__ import annotations

from dataclasses import dataclass

from apps.exchange.hl_client import build_info


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    reason: str = ""
    details: dict | None = None


def pre_trade_gate(*, credential, min_free_margin_usd: float = 50.0) -> RiskDecision:
    """Check margin health before sending a signed order."""
    try:
        from django.conf import settings

        min_free_margin_usd = float(getattr(settings, "HL_MIN_FREE_MARGIN_USD", min_free_margin_usd))
    except Exception:  # noqa: BLE001
        pass
    try:
        info = build_info(credential.network)
        state = info.user_state(credential.wallet_address) or {}
        ms = state.get("marginSummary") or {}
        account_value = float(ms.get("accountValue", 0) or 0)
        margin_used = float(ms.get("totalMarginUsed", 0) or 0)
        free = account_value - margin_used
        if free < float(min_free_margin_usd):
            return RiskDecision(
                ok=False,
                reason="free margin below threshold",
                details={"account_value": account_value, "margin_used": margin_used, "free": free},
            )
        return RiskDecision(ok=True, details={"free": free, "account_value": account_value, "margin_used": margin_used})
    except Exception as exc:  # noqa: BLE001
        return RiskDecision(ok=False, reason="risk check failed", details={"error": type(exc).__name__})

