"""Enhanced simulated broker for realistic backtests."""
from __future__ import annotations

from apps.transpiler.metrics import compute_metrics


class Trade:
    __slots__ = (
        "oid", "side", "entry_price", "exit_price", "size", "pnl",
        "gross_pnl", "commission", "entry_bar", "exit_bar",
        "stop_px", "limit_px", "exit_reason",
        "entry_time", "exit_time",
    )

    def __init__(self, oid, side, entry_price, size, entry_bar, entry_commission=0.0, entry_time=0):
        self.oid = oid
        self.side = side
        self.entry_price = entry_price
        self.exit_price = None
        self.size = size
        self.pnl = 0.0
        self.gross_pnl = 0.0
        self.commission = entry_commission
        self.entry_bar = entry_bar
        self.exit_bar = None
        self.stop_px = None
        self.limit_px = None
        self.exit_reason = ""
        self.entry_time = entry_time
        self.exit_time = None


class SimBroker:
    """In-memory simulated broker with funding, leverage, liquidation, SL/TP."""

    fill_at_next_open = True

    def __init__(
        self,
        default_qty: float = 1.0,
        commission: float = 0.0,
        slippage: float = 0.0,
        *,
        leverage: float = 1.0,
        initial_balance: float = 10_000.0,
        maintenance_margin_rate: float = 0.04,
        funding_rates: dict[int, float] | None = None,
        allow_pyramiding: bool = False,
        risk_manager=None,
        qty_is_percent_of_equity: bool = False,
    ):
        self.default_qty = default_qty
        self.commission = commission
        self.slippage = slippage
        self.leverage = max(leverage, 1.0)
        self.initial_balance = initial_balance
        self.cash = initial_balance
        self.maintenance_margin_rate = maintenance_margin_rate
        self.funding_rates = funding_rates or {}
        self.allow_pyramiding = allow_pyramiding
        self.risk_manager = risk_manager
        self.qty_is_percent_of_equity = qty_is_percent_of_equity

        self.open_trades: dict[str, Trade] = {}
        self.closed: list[Trade] = []
        self.realized = 0.0
        self.funding_paid = 0.0
        self.equity_series: list[float] = []
        self._last_funding_ts: int | None = None
        self.liquidations = 0
        self._bar_times: dict[int, int] = {}

    def _entry_fill(self, side: str, price: float) -> float:
        return price * (1.0 + self.slippage) if side == "long" else price * (1.0 - self.slippage)

    def _exit_fill(self, side: str, price: float) -> float:
        return price * (1.0 - self.slippage) if side == "long" else price * (1.0 + self.slippage)

    def _commission_cost(self, price: float, size: float) -> float:
        return self.commission * abs(price * size)

    def _notional(self, price: float, size: float) -> float:
        return abs(price * size)

    def _margin_used(self, price: float | None = None) -> float:
        mark = price or 0.0
        total = 0.0
        for t in self.open_trades.values():
            p = mark if mark else t.entry_price
            total += self._notional(p, t.size) / self.leverage
        return total

    def _exposure_pct(self, price: float) -> float:
        eq = self.equity(price)
        if eq <= 0:
            return 100.0
        return sum(self._notional(price, t.size) for t in self.open_trades.values()) / eq * 100.0

    def _close_trade(self, t: Trade, fill: float, bar_index: int, reason: str = "") -> None:
        t.exit_price = fill
        t.exit_bar = bar_index
        t.exit_time = self._bar_times.get(bar_index, 0)
        t.exit_reason = reason
        direction = 1.0 if t.side == "long" else -1.0
        t.gross_pnl = (fill - t.entry_price) * t.size * direction
        t.commission += self._commission_cost(fill, t.size)
        t.pnl = t.gross_pnl - t.commission
        self.realized += t.pnl
        self.cash += t.pnl
        self.closed.append(t)

    def close(self, oid, price, bar_index, **kwargs):
        t = self.open_trades.get(oid)
        if t is None:
            return
        qty_pct = kwargs.get("qty_pct", 1.0)
        qty_pct = max(0.0, min(1.0, float(qty_pct)))
        if qty_pct >= 1.0:
            t = self.open_trades.pop(oid)
        else:
            partial_size = t.size * qty_pct
            t.size -= partial_size
            partial = Trade(t.oid, t.side, t.entry_price, partial_size, t.entry_bar, t.commission * qty_pct)
            fill = self._exit_fill(t.side, price)
            self._close_trade(partial, fill, bar_index, reason="partial")
            return

        fill = self._exit_fill(t.side, price)
        self._close_trade(t, fill, bar_index, reason=kwargs.get("reason", ""))

    def exit(self, oid, price, bar_index, **kwargs):
        stop_px = kwargs.get("stop")
        limit_px = kwargs.get("limit")
        if stop_px is not None or limit_px is not None:
            t = self.open_trades.get(oid)
            if t is None:
                return
            if stop_px is not None:
                t.stop_px = float(stop_px)
            if limit_px is not None:
                t.limit_px = float(limit_px)
            return
        self.close(oid, price, bar_index)

    def entry(self, oid, direction, price, bar_index, qty=None, **kwargs):
        if oid in self.open_trades and not self.allow_pyramiding:
            return

        side = "long" if str(direction).lower() in ("long", "strategy.long") else "short"

        if not self.allow_pyramiding:
            for open_oid in list(self.open_trades):
                t = self.open_trades[open_oid]
                if t.side != side:
                    self.close(open_oid, price, bar_index, reason="reversal")

        if self.risk_manager:
            eq = self.equity(price)
            decision = self.risk_manager.pre_trade(
                equity=eq,
                open_trades=len(self.open_trades),
                exposure_pct=self._exposure_pct(price),
                leverage=self.leverage,
            )
            if not decision.ok:
                return

        if qty is not None:
            size = float(qty)
        elif self.qty_is_percent_of_equity:
            eq = self.equity(price)
            pct = self.default_qty / 100.0
            size = (eq * pct) / price if price > 0 else 0.0
        else:
            size = self.default_qty
        fill = self._entry_fill(side, price)
        entry_comm = self._commission_cost(fill, size)
        self.cash -= entry_comm
        self.open_trades[oid] = Trade(oid, side, fill, size, bar_index, entry_commission=entry_comm, entry_time=self._bar_times.get(bar_index, 0))

    def check_stops(self, bar_high: float, bar_low: float, bar_index: int) -> None:
        for oid in list(self.open_trades):
            t = self.open_trades[oid]
            if t.side == "long":
                if t.stop_px is not None and bar_low <= t.stop_px:
                    self.close(oid, t.stop_px, bar_index, reason="stop")
                    continue
                if t.limit_px is not None and bar_high >= t.limit_px:
                    self.close(oid, t.limit_px, bar_index, reason="take_profit")
            else:
                if t.stop_px is not None and bar_high >= t.stop_px:
                    self.close(oid, t.stop_px, bar_index, reason="stop")
                    continue
                if t.limit_px is not None and bar_low <= t.limit_px:
                    self.close(oid, t.limit_px, bar_index, reason="take_profit")

    def check_liquidation(self, mark_price: float, bar_index: int) -> None:
        if not self.open_trades:
            return
        equity = self.equity(mark_price)
        notional = sum(self._notional(mark_price, t.size) for t in self.open_trades.values())
        maint = notional * self.maintenance_margin_rate
        if equity < maint:
            for oid in list(self.open_trades):
                self.close(oid, mark_price, bar_index, reason="liquidation")
                self.liquidations += 1

    def apply_funding(self, ts: int, mark_price: float) -> None:
        rate = self.funding_rates.get(ts)
        if rate is None:
            return
        for t in self.open_trades.values():
            notional = self._notional(mark_price, t.size)
            payment = notional * rate * (1.0 if t.side == "long" else -1.0)
            self.funding_paid += payment
            self.cash -= payment
            self.realized -= payment

    def on_bar(self, bar_index: int, ts: int, o: float, h: float, l: float, c: float) -> None:
        self._bar_times[bar_index] = ts
        self.apply_funding(ts, c)
        self.check_stops(h, l, bar_index)
        self.check_liquidation(c, bar_index)
        self.equity_series.append(self.equity(c))
        if self.risk_manager:
            self.risk_manager.update_equity(self.equity(c))

    def finalize(self, last_price, last_bar):
        for oid in list(self.open_trades):
            self.close(oid, last_price, last_bar, reason="finalize")

    def position_size(self) -> float:
        return sum(t.size * (1.0 if t.side == "long" else -1.0) for t in self.open_trades.values())

    def open_profit(self, price: float) -> float:
        return sum(
            (price - t.entry_price) * t.size * (1.0 if t.side == "long" else -1.0)
            for t in self.open_trades.values()
        )

    def equity(self, price: float) -> float:
        return self.cash + self.open_profit(price)

    def metrics(self) -> dict:
        base = compute_metrics(
            self.closed,
            equity_series=self.equity_series,
            initial_balance=self.initial_balance,
            funding_paid=self.funding_paid,
        )
        base["leverage"] = self.leverage
        base["liquidations"] = self.liquidations
        base["initial_balance"] = self.initial_balance
        base["final_equity"] = round(self.equity(self.equity_series[-1] if self.equity_series else self.initial_balance), 8)
        if self.equity_series:
            base["equity_series"] = [round(x, 4) for x in self.equity_series]
        return base

    def trades(self) -> list[dict]:
        return [
            {
                "oid": t.oid,
                "side": t.side,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "size": t.size,
                "pnl": round(t.pnl, 8),
                "gross_pnl": round(t.gross_pnl, 8),
                "commission": round(t.commission, 8),
                "entry_bar": t.entry_bar,
                "exit_bar": t.exit_bar,
                "exit_reason": t.exit_reason,
                "stop_px": t.stop_px,
                "limit_px": t.limit_px,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
            }
            for t in self.closed
        ]
