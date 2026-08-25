"""One bar, as the runtime sees it.

Frozen and ``Decimal``-typed, matching ``apps.exchanges.feed_base.Candle`` field
for field without importing it — this package may not reach into ``apps.*``
(``bot-plan.md`` §1.1). ``apps.bots.feed`` converts one to the other at the
boundary, which is also where "is this bar closed?" is decided.

``time`` is the bar's **open** time in UNIX seconds, which is what
``public_sources`` already returns and what every exchange keys a candle on.
Using the close time instead is a subtle way to be one bar out for a whole run.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Bar:
    time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def as_dict(self) -> dict:
        return {
            "t": self.time,
            "o": str(self.open),
            "h": str(self.high),
            "l": str(self.low),
            "c": str(self.close),
            "v": str(self.volume),
        }
