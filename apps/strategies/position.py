"""Position management helpers shared by brokers."""
from __future__ import annotations


def partial_size(current_size: float, qty_pct: float) -> float:
    pct = max(0.0, min(1.0, float(qty_pct)))
    return current_size * pct
