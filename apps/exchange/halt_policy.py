"""Halt policy — §4.3, the most consequential decision in the system.

When the hot path detects SUSPECT/MISSING quality on a sealed bar, this module
decides what to do about an open position:

- **Class 1** (compute gap): B crashed, ledger complete → full recovery possible.
  If SL is confirmed → hold up to ``max_blind_hold`` bars, then flatten.
  If SL is missing → flatten immediately.
- **Class 2** (partial ingest): one A node down, union covers → same as Class 1.
- **Class 3** (total ingest): all A nodes down → bar is MISSING forever.
  Flatten immediately; strategy halts until hole scrolls out of warmup window.

Invariants enforced:
- Strategy never consumes a SUSPECT/MISSING bar (invariant 1).
- No position runs naked (no SL) for more than one bar (invariant 13).
- Flatten decision is made within ``T_self`` (watchdog §6.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HaltAction(Enum):
    """What the runner should do with the current position."""
    HOLD = "hold"          # SL confirmed attached, within blind-hold budget
    FLATTEN = "flatten"    # naked, class 3, or exceeded max_blind_hold


class FailureClass(Enum):
    """§0.1 classification of the quality failure."""
    COMPUTE_GAP = 1     # Node B crashed; ledger is complete
    PARTIAL_INGEST = 2  # One A node down; union covers the gap
    TOTAL_INGEST = 3    # All A nodes down; permanent hole


@dataclass(frozen=True)
class HaltDecision:
    """The output of ``evaluate_halt`` — tells the runner exactly what to do."""
    action: HaltAction
    reason: str
    failure_class: FailureClass
    sl_confirmed: bool
    bars_since_halt: int
    max_blind_hold: int

    @property
    def should_flatten(self) -> bool:
        return self.action == HaltAction.FLATTEN

    @property
    def eta_blind_hold(self) -> int:
        """Remaining bars before forced flatten (0 if already exceeded)."""
        return max(0, self.max_blind_hold - self.bars_since_halt)


def classify_failure_class(
    *,
    coverage_pct: float,
    has_any_node: bool,
) -> FailureClass:
    """§0.1: Classify the quality failure based on coverage.

    Args:
        coverage_pct: union coverage fraction [0.0, 1.0] for the bar window.
        has_any_node: True if at least one ingest node is reporting live data.
    """
    if not has_any_node:
        return FailureClass.TOTAL_INGEST
    if coverage_pct >= 0.99:
        return FailureClass.COMPUTE_GAP
    return FailureClass.PARTIAL_INGEST


def evaluate_halt(
    *,
    quality: str,
    sl_confirmed: bool,
    failure_class: FailureClass,
    bars_since_halt: int,
    max_blind_hold: int = 3,
) -> HaltDecision:
    """§4.3: The most consequential decision the system makes.

    Args:
        quality: "SUSPECT" or "MISSING" (CLEAN/FLAT never reach this path).
        sl_confirmed: True if a stop-loss order is confirmed attached to the position.
        failure_class: Class 1/2/3 from ``classify_failure_class``.
        bars_since_halt: how many bars have elapsed since the first SUSPECT/MISSING.
        max_blind_hold: max bars to hold a protected position blind (default 3).
    """
    # Class 3: unrecoverable — flatten immediately regardless of SL state.
    if failure_class == FailureClass.TOTAL_INGEST:
        return HaltDecision(
            action=HaltAction.FLATTEN,
            reason="class_3_total_ingest",
            failure_class=failure_class,
            sl_confirmed=sl_confirmed,
            bars_since_halt=bars_since_halt,
            max_blind_hold=max_blind_hold,
        )

    # Missing bar is always a flatten (no data to trade on).
    if quality == "MISSING":
        return HaltDecision(
            action=HaltAction.FLATTEN,
            reason="bar_missing",
            failure_class=failure_class,
            sl_confirmed=sl_confirmed,
            bars_since_halt=bars_since_halt,
            max_blind_hold=max_blind_hold,
        )

    # SUSPECT: SL confirmed → hold within budget; no SL → flatten immediately.
    if not sl_confirmed:
        return HaltDecision(
            action=HaltAction.FLATTEN,
            reason="naked_position",
            failure_class=failure_class,
            sl_confirmed=sl_confirmed,
            bars_since_halt=bars_since_halt,
            max_blind_hold=max_blind_hold,
        )

    if bars_since_halt >= max_blind_hold:
        return HaltDecision(
            action=HaltAction.FLATTEN,
            reason="exceeded_max_blind_hold",
            failure_class=failure_class,
            sl_confirmed=sl_confirmed,
            bars_since_halt=bars_since_halt,
            max_blind_hold=max_blind_hold,
        )

    return HaltDecision(
        action=HaltAction.HOLD,
        reason="sl_confirmed_within_budget",
        failure_class=failure_class,
        sl_confirmed=sl_confirmed,
        bars_since_halt=bars_since_halt,
        max_blind_hold=max_blind_hold,
    )
