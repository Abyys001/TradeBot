"""SignalCaptureBroker — records order *intents* without placing any order.

Used on the copy-trading fan-out path: the Pine interpreter is run **once** per
closed candle against the admin's signal strategy with this broker, which
captures the sequence of entry/close/exit intents. A fan-out step then replays
those intents against each investor's own account (sized off their own equity)
via a real per-account broker (e.g. TabdealBroker).

Implements the same broker interface as WarmupBroker/LiveBroker so the
interpreter drives it unchanged. It never touches an exchange.
"""
from __future__ import annotations


class SignalCaptureBroker:
    def __init__(self):
        self.actions: list[dict] = []
        self.last_action = "No Action"

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        is_buy = str(direction).lower() in ("long", "strategy.long")
        self.actions.append(
            {
                "type": "entry",
                "oid": str(oid),
                "direction": "long" if is_buy else "short",
                "price": price,
                "bar_index": bar_index,
                "qty": qty,
                "limit": kwargs.get("limit"),
                "alert_message": kwargs.get("alert_message"),
            }
        )
        self.last_action = f"{'LONG' if is_buy else 'SHORT'} Entry at {price}"
        return None

    def close(self, oid, price, bar_index, **kwargs):
        self.actions.append(
            {
                "type": "close",
                "oid": str(oid),
                "price": price,
                "bar_index": bar_index,
                "qty_pct": float(kwargs.get("qty_pct", 1.0)),
                "reason": kwargs.get("reason", "manual"),
            }
        )
        self.last_action = f"CLOSE at {price}"
        return None

    def exit(self, oid, price, bar_index, **kwargs):
        self.actions.append(
            {
                "type": "exit",
                "oid": str(oid),
                "price": price,
                "bar_index": bar_index,
                "stop": kwargs.get("stop"),
                "limit": kwargs.get("limit"),
                "update": bool(kwargs.get("update", False)),
            }
        )
        self.last_action = f"EXIT (SL/TP) at {price}"
        return None

    # No synthetic metrics — this broker only records intents.
    def finalize(self, last_price, last_bar):
        return None

    def metrics(self):
        return {}

    def trades(self):
        return []

    def has_actions(self) -> bool:
        return bool(self.actions)
