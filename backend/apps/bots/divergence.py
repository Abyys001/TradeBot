"""One hash over a sequence of intents, computed the same way everywhere.

This is the whole argument that a backtest predicts anything: feed the same bars
to ``backtest.py`` and to the live loop and the intent sequences must be
*byte-identical*. A single function both sides call is what makes that a test
rather than two implementations agreeing by luck.

Only the parts of an intent that describe a decision go into the digest — side,
SL/TP, the surviving fraction after a scale-out, bar time, symbol. Plot values
and the reason string are output for a human, and a changed plot title is not a
changed strategy.

The fraction is written **only when it is not a whole position**, so every
script that never scales out digests to exactly the bytes it did before the
field existed. That is not cosmetic: the promotion gate compares a stored
paper-run digest against a fresh one, and a field appearing in every intent
would have invalidated every run recorded so far.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from decimal import Decimal

from apps.pine.intent import StrategyIntent

ONE = Decimal(1)


def intent_fingerprint(intent: StrategyIntent) -> dict:
    row = {
        "t": intent.bar_time,
        "s": intent.symbol,
        "d": intent.desired_side.value if intent.desired_side else None,
        "sl": str(intent.sl_pct) if intent.sl_pct is not None else None,
        "tp": str(intent.tp_pct) if intent.tp_pct is not None else None,
    }
    if intent.position_fraction != ONE:
        row["f"] = str(intent.position_fraction)
    return row


def digest_intents(intents: Iterable[StrategyIntent]) -> str:
    """SHA-256 over the decision sequence. Stable across processes and versions."""
    payload = json.dumps(
        [intent_fingerprint(i) for i in intents], separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare(backtest_digest: str, live_digest: str) -> bool:
    return bool(backtest_digest) and backtest_digest == live_digest
