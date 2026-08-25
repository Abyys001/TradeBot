"""One hash over a sequence of intents, computed the same way everywhere.

This is the whole argument that a backtest predicts anything: feed the same bars
to ``backtest.py`` and to the live loop and the intent sequences must be
*byte-identical*. A single function both sides call is what makes that a test
rather than two implementations agreeing by luck.

Only the parts of an intent that describe a decision go into the digest — side,
SL/TP, bar time, symbol. Plot values and the reason string are output for a
human, and a changed plot title is not a changed strategy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from apps.pine.intent import StrategyIntent


def intent_fingerprint(intent: StrategyIntent) -> dict:
    return {
        "t": intent.bar_time,
        "s": intent.symbol,
        "d": intent.desired_side.value if intent.desired_side else None,
        "sl": str(intent.sl_pct) if intent.sl_pct is not None else None,
        "tp": str(intent.tp_pct) if intent.tp_pct is not None else None,
    }


def digest_intents(intents: Iterable[StrategyIntent]) -> str:
    """SHA-256 over the decision sequence. Stable across processes and versions."""
    payload = json.dumps(
        [intent_fingerprint(i) for i in intents], separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare(backtest_digest: str, live_digest: str) -> bool:
    return bool(backtest_digest) and backtest_digest == live_digest
