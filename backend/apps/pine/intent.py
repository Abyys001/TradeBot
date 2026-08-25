"""``StrategyIntent`` — what the strategy wants to be true after this bar.

Declarative on purpose. The intent says "be long" or "be flat"; it says nothing
about how much, at what leverage, in which account, or at what price. Those are
the platform's (Q20, Q21), and **the type is how that is enforced**: there is no
quantity field, no leverage field, no account field and no price field, so a
script's ``qty=2`` has nowhere to travel to even if some future translator
wanted to honour it.

``Side`` is redeclared here rather than imported from ``apps.exchanges.base``
because this package may not import ``apps.*`` (``bot-plan.md`` §1.1). The
values are identical strings, so ``apps.bots.translate`` converts with
``Side(intent.desired_side)`` and a divergence between the two would fail that
conversion loudly rather than silently mapping to the wrong direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from apps.pine.tokens import Span


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class Annotation:
    """One ``plot``/``plotshape``/``alert`` value, recorded and never executed."""

    kind: str
    title: str
    value: object
    span: Span


@dataclass(frozen=True, slots=True)
class StrategyIntent:
    """The bar's outcome. Frozen: it is a value, and Phase 5 diffs against it."""

    bar_time: int
    symbol: str
    #: ``None`` means flat. There is no third state — "leave it alone" is
    #: expressed by the intent being equal to the previous one, which the
    #: translator diffs, not by a sentinel nobody would remember to handle.
    desired_side: Side | None
    #: From a percent ``strategy.exit`` (Q21). ``None`` means "use the bot's
    #: configured pair", which is the common case.
    sl_pct: Decimal | None = None
    tp_pct: Decimal | None = None
    #: Human-readable, for the action log: "entry: L", "close: exit long".
    reason: str = ""
    #: Which line asked. Carried from Phase 1 through to the chart annotation
    #: in Phase 4 and the editor link in Phase 8.
    source_span: Span | None = None
    plots: dict[str, object] = field(default_factory=dict)
    alerts: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        """Wire and storage shape. Decimals become strings so no float artefact
        is introduced between the runtime and the database."""
        return {
            "bar_time": self.bar_time,
            "symbol": self.symbol,
            "side": self.desired_side.value if self.desired_side else None,
            "sl_pct": str(self.sl_pct) if self.sl_pct is not None else None,
            "tp_pct": str(self.tp_pct) if self.tp_pct is not None else None,
            "reason": self.reason,
            "span": self.source_span.as_dict() if self.source_span else None,
            "plots": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.plots.items()},
            "alerts": list(self.alerts),
        }

    def same_position_as(self, other: StrategyIntent | None) -> bool:
        """Whether these two describe the same desired position.

        Compares side and the SL/TP pair only — not the bar, not the plots.
        Phase 5 uses it to answer "did anything change?" without re-deriving the
        rule in two places.
        """
        if other is None:
            return False
        return (
            self.desired_side == other.desired_side
            and self.sl_pct == other.sl_pct
            and self.tp_pct == other.tp_pct
        )
