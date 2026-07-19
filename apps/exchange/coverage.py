"""Coverage service — the honest answer to "do we have the data?" (Master Plan §0.1, §4.2).

Thin façade over the ledger's union coverage so the rest of the system asks one question:
*is ``[start, end)`` fully covered by the union of all ingest nodes?* A non-empty gap is a
Class-3 hole (permanently unrecoverable, §0.1) unless it is still inside the live stream's
reach. Consumed by self-heal (P4) and the readiness API (P3).
"""
from __future__ import annotations

from . import ledger


def symbol_coverage(symbol: str) -> list[list[int]]:
    """Merged coverage intervals (ms) across every ingest node for ``symbol``."""
    return ledger.union_coverage(symbol)


def coverage_gaps(symbol: str, start_ms: int, end_ms: int) -> list[list[int]]:
    """Sub-windows of ``[start_ms, end_ms)`` no node covers — the holes."""
    return ledger.coverage_gaps(symbol, start_ms, end_ms)


def is_covered(symbol: str, start_ms: int, end_ms: int) -> bool:
    """True iff every millisecond of ``[start_ms, end_ms)`` is covered by some node."""
    return not ledger.coverage_gaps(symbol, start_ms, end_ms)


def coverage_pct(symbol: str, start_ms: int, end_ms: int) -> float:
    """Fraction of ``[start_ms, end_ms)`` covered (1.0 = complete). 1.0 for an empty window."""
    span = end_ms - start_ms
    if span <= 0:
        return 1.0
    missing = sum(g[1] - g[0] for g in ledger.coverage_gaps(symbol, start_ms, end_ms))
    return max(0.0, 1.0 - missing / span)
