"""Order routing for `strategy.entry / close / exit`.

Backends behind one interface:
  - SimBroker   — backtest fills at the next bar's open with commission/slippage;
    tracks position and realised PnL; emits trade records and summary metrics.
  - WarmupBroker — no-op broker for historical warmup (places no orders).
  - LiveBroker  — DEPRECATED guard: Hyperliquid live trading has been removed.
    Constructing it raises; live trading goes through
    `apps.transpiler.runtime.tabdeal_live_broker.TabdealLiveBroker`.
"""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


from .sim_broker import SimBroker, Trade  # noqa: F401 — enhanced backtest broker


class WarmupBroker:
    """No-op broker used during historical warmup (no orders placed)."""

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        return None

    def close(self, oid, price, bar_index, **kwargs):
        return None

    def exit(self, oid, price, bar_index, **kwargs):
        return None

    def finalize(self, last_price, last_bar):
        return None

    def metrics(self):
        return {}

    def trades(self):
        return []


class LiveBroker:
    """DEPRECATED: Hyperliquid live broker removed. Use TabdealLiveBroker instead."""

    def __init__(self, credential, strategy, symbol):
        raise NotImplementedError(
            "Hyperliquid LiveBroker has been removed. Use TabdealLiveBroker for live trading."
        )
