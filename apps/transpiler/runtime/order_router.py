"""Order routing for `strategy.entry / close / exit`.

Two backends behind one interface:
  - SimBroker  — backtest fills at the current bar price; tracks position and
    realised PnL; emits trade records and summary metrics.
  - LiveBroker — routes to Hyperliquid via agent-signed orders
    (`apps.exchange.hl_client.build_exchange`) and persists
    `apps.execution.OrderRecord` + `ExecutionLog`. Honours the per-user
    `is_trading_enabled` kill-switch before any live order.
"""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class Trade:
    __slots__ = ("oid", "side", "entry_price", "exit_price", "size", "pnl",
                 "entry_bar", "exit_bar")

    def __init__(self, oid, side, entry_price, size, entry_bar):
        self.oid = oid
        self.side = side
        self.entry_price = entry_price
        self.exit_price = None
        self.size = size
        self.pnl = 0.0
        self.entry_bar = entry_bar
        self.exit_bar = None


class WarmupBroker:
    """No-op broker used during historical warmup (no orders placed)."""

    def entry(self, oid, direction, price, bar_index, qty=None):
        return None

    def close(self, oid, price, bar_index):
        return None

    def exit(self, oid, price, bar_index):
        return None

    def finalize(self, last_price, last_bar):
        return None

    def metrics(self):
        return {}

    def trades(self):
        return []


class SimBroker:
    """In-memory simulated broker for backtests."""

    def __init__(self, default_qty: float = 1.0):
        self.default_qty = default_qty
        self.open_trades: dict[str, Trade] = {}
        self.closed: list[Trade] = []

    def entry(self, oid, direction, price, bar_index, qty=None):
        # Pyramiding off: an entry with an existing id is ignored.
        if oid in self.open_trades:
            return
        side = "long" if str(direction).lower() in ("long", "strategy.long") else "short"
        self.open_trades[oid] = Trade(oid, side, price, qty or self.default_qty, bar_index)

    def close(self, oid, price, bar_index):
        t = self.open_trades.pop(oid, None)
        if t is None:
            return
        t.exit_price = price
        t.exit_bar = bar_index
        direction = 1.0 if t.side == "long" else -1.0
        t.pnl = (price - t.entry_price) * t.size * direction
        self.closed.append(t)

    def exit(self, oid, price, bar_index):
        # `strategy.exit` (without stop/limit args) behaves like a close here.
        self.close(oid, price, bar_index)

    def finalize(self, last_price, last_bar):
        # Close any still-open positions at the final price (mark-to-market).
        for oid in list(self.open_trades):
            self.close(oid, last_price, last_bar)

    def metrics(self) -> dict:
        n = len(self.closed)
        pnl = sum(t.pnl for t in self.closed)
        wins = sum(1 for t in self.closed if t.pnl > 0)
        # Simple equity-curve max drawdown.
        equity, peak, max_dd = 0.0, 0.0, 0.0
        for t in self.closed:
            equity += t.pnl
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)
        return {
            "num_trades": n,
            "net_pnl": round(pnl, 8),
            "win_rate": round(wins / n, 4) if n else 0.0,
            "max_drawdown": round(max_dd, 8),
        }

    def trades(self) -> list[dict]:
        return [
            {
                "oid": t.oid, "side": t.side,
                "entry_price": t.entry_price, "exit_price": t.exit_price,
                "size": t.size, "pnl": round(t.pnl, 8),
                "entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
            }
            for t in self.closed
        ]


class LiveBroker:
    """Routes orders to Hyperliquid via agent-signed transactions."""

    def __init__(self, credential, strategy, symbol):
        self.credential = credential
        self.strategy = strategy
        self.symbol = symbol
        self._exchange = None
        self.last_action = "No Action"

    def _get_exchange(self):
        if self._exchange is None:
            from apps.exchange.hl_client import build_exchange
            from apps.exchange.hl_constants import normalize_coin

            self._coin = normalize_coin(self.symbol)
            self._exchange = build_exchange(self.credential)
        return self._exchange

    def _kill_switch_ok(self) -> bool:
        return bool(getattr(self.strategy.user, "is_trading_enabled", False))

    @staticmethod
    def _extract_order_id(resp) -> str:
        if not isinstance(resp, dict) or resp.get("status") != "ok":
            return ""
        statuses = (resp.get("response") or {}).get("data", {}).get("statuses") or []
        if not statuses:
            return ""
        st = statuses[0]
        if "filled" in st:
            return str(st["filled"].get("oid", ""))
        if "resting" in st:
            return str(st["resting"].get("oid", ""))
        return ""

    def _place_perp(self, *, is_buy: bool, oid, price, qty):
        from apps.execution.models import ExecutionLog, OrderRecord

        if not self._kill_switch_ok():
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": "is_trading_enabled is False", "oid": oid},
            )
            return None

        exchange = self._get_exchange()
        resp = exchange.market_open(
            name=self._coin,
            is_buy=is_buy,
            sz=float(qty),
            px=None,
            slippage=0.01,
        )
        side = OrderRecord.Side.BUY if is_buy else OrderRecord.Side.SELL
        exchange_id = self._extract_order_id(resp)
        rec = OrderRecord.objects.create(
            strategy=self.strategy,
            exchange_order_id=exchange_id,
            client_order_id=str(oid),
            symbol=self._coin,
            side=side,
            order_type="market",
            size=Decimal(str(qty)),
            price=Decimal(str(price)) if price is not None else None,
            status="submitted",
            raw=resp if isinstance(resp, dict) else {},
        )
        self.last_action = f"{'BUY' if is_buy else 'SELL'} at {price}"
        ExecutionLog.objects.create(
            strategy=self.strategy,
            level="info",
            event="order.placed",
            payload={
                "oid": oid,
                "side": side,
                "symbol": self._coin,
                "price": price,
                "exchange_order_id": exchange_id,
            },
        )
        return rec

    def _place_spot(self, *, is_buy: bool, oid, price, qty):
        from apps.execution.models import ExecutionLog, OrderRecord

        if not self._kill_switch_ok():
            ExecutionLog.objects.create(
                strategy=self.strategy,
                level="warning",
                event="order.blocked",
                payload={"reason": "is_trading_enabled is False", "oid": oid},
            )
            return None

        exchange = self._get_exchange()
        resp = exchange.order(
            self._coin,
            is_buy,
            float(qty),
            float(price) if price else 0.0,
            {"limit": {"tif": "Ioc"}},
        )
        side = OrderRecord.Side.BUY if is_buy else OrderRecord.Side.SELL
        exchange_id = self._extract_order_id(resp)
        rec = OrderRecord.objects.create(
            strategy=self.strategy,
            exchange_order_id=exchange_id,
            client_order_id=str(oid),
            symbol=self._coin,
            side=side,
            order_type="market",
            size=Decimal(str(qty)),
            price=Decimal(str(price)) if price is not None else None,
            status="submitted",
            raw=resp if isinstance(resp, dict) else {},
        )
        self.last_action = f"{'BUY' if is_buy else 'SELL'} at {price}"
        ExecutionLog.objects.create(
            strategy=self.strategy,
            level="info",
            event="order.placed",
            payload={
                "oid": oid,
                "side": side,
                "symbol": self._coin,
                "price": price,
                "exchange_order_id": exchange_id,
            },
        )
        return rec

    def _is_spot(self) -> bool:
        from apps.strategies.models import Strategy

        return getattr(self.strategy, "market_type", Strategy.MarketType.PERP) == Strategy.MarketType.SPOT

    def entry(self, oid, direction, price, bar_index, qty=None):
        is_buy = str(direction).lower() in ("long", "strategy.long")
        qty = qty or 1
        if self._is_spot():
            return self._place_spot(is_buy=is_buy, oid=oid, price=price, qty=qty)
        return self._place_perp(is_buy=is_buy, oid=oid, price=price, qty=qty)

    def close(self, oid, price, bar_index):
        if self._is_spot():
            return self._place_spot(is_buy=False, oid=oid, price=price, qty=1)
        if not self._kill_switch_ok():
            return None
        exchange = self._get_exchange()
        resp = exchange.market_close(coin=self._coin, sz=None)
        self.last_action = f"CLOSE at {price}"
        return resp

    def exit(self, oid, price, bar_index):
        return self.close(oid, price, bar_index)

    # Live broker has no synthetic metrics.
    def finalize(self, last_price, last_bar):
        return

    def metrics(self):
        return {}

    def trades(self):
        return []
