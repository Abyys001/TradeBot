"""Backtest metrics, and the assumptions without which they mean nothing.

Every report carries its own fill model at the top. Not a disclaimer for its own
sake: a reader who does not know whether entries filled at the signal bar's
close or the next bar's open cannot interpret the Sharpe, and the difference
between those two is most of the edge in a lot of strategies.

The pessimistic reading is chosen wherever there is a choice — most visibly,
**when one bar touches both the stop and the target, the stop is assumed**. It
is the only honest reading without tick data, and it is stated in the report
rather than buried here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")

#: Bars in a year, per interval — for annualising a Sharpe ratio. Crypto trades
#: every day, so there is no 252-day convention to apply here.
BARS_PER_YEAR = {
    "1m": 525_600,
    "5m": 105_120,
    "15m": 35_040,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
}


@dataclass(frozen=True, slots=True)
class Assumptions:
    """The fill model, recorded with the numbers it produced."""

    slippage_bps: Decimal
    fee_bps: Decimal
    entry_rule: str = "next bar's open"
    ambiguous_bar_rule: str = "stop assumed when one bar touches both SL and TP"
    balance_fraction: Decimal = Decimal("0.99")
    leverage: int = 1
    initial_equity: Decimal = Decimal("10000")
    #: The resolved Properties tab. Recorded whole, because "which numbers
    #: produced this report" is the question a stored backtest has to be able to
    #: answer a month later, and the script may have declared any of them.
    properties: object = None
    #: Fixed cash charged per order, and per contract, from
    #: ``commission_type = strategy.commission.cash_per_order`` /
    #: ``cash_per_contract``. Zero under the percentage model, which is the
    #: default and the only one crypto venues actually use.
    commission_per_order: Decimal = Decimal("0")
    commission_per_contract: Decimal = Decimal("0")
    #: Slippage in *ticks*, TradingView's own unit, when the script declared it.
    #: ``None`` leaves ``slippage_bps`` in force — see ``StrategyProperties``.
    slippage_ticks: int | None = None
    mintick: Decimal = Decimal("0.01")
    #: What the backtest simulates that live will not do, in the script's own
    #: words. Empty is the common case and prints nothing.
    departures: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "slippage_bps": str(self.slippage_bps),
            "fee_bps": str(self.fee_bps),
            "entry_rule": self.entry_rule,
            "ambiguous_bar_rule": self.ambiguous_bar_rule,
            "balance_fraction": str(self.balance_fraction),
            "leverage": self.leverage,
            "initial_equity": str(self.initial_equity),
            "commission_per_order": str(self.commission_per_order),
            "commission_per_contract": str(self.commission_per_contract),
            "slippage_ticks": self.slippage_ticks,
            "mintick": str(self.mintick),
            "departures": list(self.departures),
            "properties": self.properties.as_dict() if self.properties is not None else None,
        }

    def lines(self) -> list[str]:
        """The header every rendering of this report starts with."""
        slippage = (
            f"{self.slippage_ticks} tick(s)"
            if self.slippage_ticks is not None
            else f"{self.slippage_bps} bps"
        )
        fee = f"taker fee {self.fee_bps} bps per side"
        if self.commission_per_order:
            fee += f", plus {self.commission_per_order} per order"
        if self.commission_per_contract:
            fee += f", plus {self.commission_per_contract} per contract"
        return [
            f"Entries fill at the {self.entry_rule}, never the signal bar's close.",
            f"Slippage {slippage} per side; {fee}.",
            f"SL/TP are checked against following bars' high/low; {self.ambiguous_bar_rule}.",
            self._sizing_line(),
            *(
                f"This backtest departs from live here: {line}"
                for line in self.departures
            ),
            "A backtest is a description of the past. It is not a forecast, and it does "
            "not include funding, exchange outages, or the account being unable to fill.",
        ]

    def _sizing_line(self) -> str:
        """Whose sizing rule this report used — the platform's, or the script's.

        A report sized by ``default_qty_type`` describes an account the bot will
        not trade (spec §5 sizes every account at 99% of its own balance), so
        the line has to say which one it is rather than always claiming §5.
        """
        properties = self.properties
        if properties is None or getattr(properties, "default_qty_type", None) is None:
            return (
                f"Sizing mirrors spec §5: {self.balance_fraction} of equity as margin at "
                f"{self.leverage}× leverage."
            )
        qty_type = properties.default_qty_type
        if qty_type.value == "platform":
            return (
                f"Sizing mirrors spec §5: {self.balance_fraction} of equity as margin at "
                f"{self.leverage}× leverage."
            )
        described = {
            "fixed": f"{properties.default_qty_value} contracts per entry",
            "cash": f"{properties.default_qty_value} of equity currency per entry",
            "percent_of_equity": f"{properties.default_qty_value}% of equity per entry",
        }[qty_type.value]
        return (
            f"Sizing follows the script's own default_qty_type: {described}. Live sizes "
            f"every account at {self.balance_fraction} of its own balance instead (§5)."
        )


@dataclass(slots=True)
class ClosedTrade:
    side: str
    entry_time: int
    entry_price: Decimal
    exit_time: int
    exit_price: Decimal
    qty: Decimal
    pnl: Decimal
    fees: Decimal
    bars_held: int
    exit_reason: str
    entry_reason: str = ""
    #: Which line asked for this trade. Carried from Phase 1's spans so the
    #: Phase 8 chart can highlight the code that fired.
    entry_span: dict | None = None

    def as_dict(self) -> dict:
        row = asdict(self)
        for key in ("entry_price", "exit_price", "qty", "pnl", "fees"):
            row[key] = str(row[key])
        return row


@dataclass(slots=True)
class Report:
    assumptions: Assumptions
    symbol: str
    interval: str
    from_time: int
    to_time: int
    bars: int
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[tuple[int, Decimal]] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    intent_digest: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "from_time": self.from_time,
            "to_time": self.to_time,
            "bars": self.bars,
            "assumptions": self.assumptions.as_dict(),
            "assumption_lines": self.assumptions.lines(),
            "metrics": {
                k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.metrics.items()
            },
            "equity_curve": [[t, str(v)] for t, v in self.equity_curve],
            "trades": [t.as_dict() for t in self.trades],
            "intent_digest": self.intent_digest,
            "warnings": list(self.warnings),
        }

    def summary_lines(self) -> list[str]:
        """What ``pine_backtest`` prints. Assumptions first, always."""
        out = ["Fill model and limits:"]
        out.extend(f"  - {line}" for line in self.assumptions.lines())
        out.append("")
        out.append(
            f"{self.symbol} {self.interval}  {self.bars} bars  "
            f"{self.from_time}→{self.to_time}"
        )
        for key, label in _SUMMARY_ORDER:
            if key in self.metrics:
                out.append(f"  {label:<24} {self.metrics[key]}")
        for warning in self.warnings:
            out.append(f"  ! {warning}")
        return out


_SUMMARY_ORDER = (
    ("net_pnl", "net PnL"),
    ("return_pct", "return %"),
    ("max_drawdown_pct", "max drawdown %"),
    ("sharpe", "Sharpe"),
    ("trades", "trades"),
    ("win_rate_pct", "win rate %"),
    ("profit_factor", "profit factor"),
    ("expectancy", "expectancy"),
    ("average_win", "average win"),
    ("average_loss", "average loss"),
    ("worst_trade", "worst trade"),
    ("max_consecutive_losses", "max consecutive losses"),
    ("average_bars_held", "average bars held"),
    ("time_in_market_pct", "time in market %"),
    ("longest_flat_bars", "longest flat (bars)"),
)


def compute_metrics(
    *,
    trades: list[ClosedTrade],
    equity_curve: list[tuple[int, Decimal]],
    bars: int,
    interval: str,
    initial_equity: Decimal,
) -> dict:
    """Every number in ``bot-mode.md`` Phase 4's list, from the trades and curve."""
    wins = [t for t in trades if t.pnl > ZERO]
    losses = [t for t in trades if t.pnl <= ZERO]
    gross_win = sum((t.pnl for t in wins), ZERO)
    gross_loss = sum((-t.pnl for t in losses), ZERO)
    net = sum((t.pnl for t in trades), ZERO)

    final_equity = equity_curve[-1][1] if equity_curve else initial_equity
    in_market = sum(t.bars_held for t in trades)

    metrics: dict = {
        "trades": len(trades),
        "net_pnl": _q(net),
        "final_equity": _q(final_equity),
        "return_pct": _q(net / initial_equity * HUNDRED) if initial_equity else ZERO,
        "win_rate_pct": _q(Decimal(len(wins)) / Decimal(len(trades)) * HUNDRED) if trades else ZERO,
        "gross_profit": _q(gross_win),
        "gross_loss": _q(gross_loss),
        "profit_factor": _q(gross_win / gross_loss) if gross_loss > ZERO else None,
        "average_win": _q(gross_win / Decimal(len(wins))) if wins else ZERO,
        "average_loss": _q(-gross_loss / Decimal(len(losses))) if losses else ZERO,
        "expectancy": _q(net / Decimal(len(trades))) if trades else ZERO,
        "worst_trade": _q(min((t.pnl for t in trades), default=ZERO)),
        "best_trade": _q(max((t.pnl for t in trades), default=ZERO)),
        "max_consecutive_losses": _max_consecutive_losses(trades),
        "average_bars_held": (
            _q(Decimal(in_market) / Decimal(len(trades))) if trades else ZERO
        ),
        "time_in_market_pct": _q(Decimal(in_market) / Decimal(bars) * HUNDRED) if bars else ZERO,
        "longest_flat_bars": _longest_flat(trades, bars),
        "total_fees": _q(sum((t.fees for t in trades), ZERO)),
    }
    metrics["max_drawdown_pct"] = _q(_max_drawdown_pct(equity_curve))
    metrics["sharpe"] = _sharpe(equity_curve, interval)
    return metrics


def _q(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.00000001"))


def _max_consecutive_losses(trades: list[ClosedTrade]) -> int:
    worst = run = 0
    for trade in trades:
        run = run + 1 if trade.pnl <= ZERO else 0
        worst = max(worst, run)
    return worst


def _longest_flat(trades: list[ClosedTrade], bars: int) -> int:
    """The longest stretch with no position, in bars.

    Worth a number because a strategy that makes its return in three weeks of a
    two-year window is a different proposition from one that trades steadily,
    and the equity curve alone does not say which you have.
    """
    if not trades:
        return bars
    held = sum(t.bars_held for t in trades)
    if len(trades) == 1:
        return max(0, bars - held)
    gaps = []
    for earlier, later in zip(trades, trades[1:], strict=False):
        gaps.append(max(0, later.entry_time - earlier.exit_time))
    longest_seconds = max(gaps, default=0)
    span = trades[-1].exit_time - trades[0].entry_time
    if span <= 0:
        return max(0, bars - held)
    # Convert the widest gap back into bars using the run's own bar spacing.
    per_bar = Decimal(span) / Decimal(max(1, bars))
    return int(Decimal(longest_seconds) / per_bar) if per_bar > ZERO else 0


def _max_drawdown_pct(curve: list[tuple[int, Decimal]]) -> Decimal:
    peak = None
    worst = ZERO
    for _time, equity in curve:
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > ZERO:
            drop = (peak - equity) / peak * HUNDRED
            worst = max(worst, drop)
    return worst


def _sharpe(curve: list[tuple[int, Decimal]], interval: str) -> Decimal | None:
    """Annualised, from per-bar equity returns, at a zero risk-free rate.

    Per-bar rather than per-trade because a strategy holding through a drawdown
    and one that sat out the same period have the same trade list and very
    different risk, and the trade list cannot tell them apart.
    """
    if len(curve) < 3:
        return None
    returns: list[Decimal] = []
    for (_t0, previous), (_t1, current) in zip(curve, curve[1:], strict=False):
        if previous <= ZERO:
            continue
        returns.append((current - previous) / previous)
    if len(returns) < 2:
        return None
    count = Decimal(len(returns))
    mean = sum(returns, ZERO) / count
    variance = sum(((r - mean) ** 2 for r in returns), ZERO) / count
    if variance <= ZERO:
        return None
    per_year = Decimal(BARS_PER_YEAR.get(interval, 8760))
    return (mean / variance.sqrt() * per_year.sqrt()).quantize(Decimal("0.0001"))
