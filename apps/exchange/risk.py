"""Risk gates for live trading. DEPRECATED: HL-specific risk gate removed."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    reason: str = ""
    details: dict | None = None


def pre_trade_gate(*, credential, min_free_margin_usd: float = 50.0) -> RiskDecision:
    """Check margin health before sending a signed order. DEPRECATED."""
    return RiskDecision(ok=True, details={"deprecated": True})
