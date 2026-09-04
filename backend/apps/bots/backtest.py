"""Replay a strategy over stored history. Two jobs, and the second is the point.

1. The admin needs to see whether a strategy is worth running at all.
2. **It is the correctness harness for Phases 1–3.** Live mode and backtest mode
   feed the *same runtime object*; if they ever produce different intents from
   the same bars, something is broken, and this is where finding that out costs
   nothing. ``divergence.digest_intents`` is how the two are compared.

The fill model is deliberately pessimistic and is stated in every report:

  **Entry at the next bar's open, never the signal bar's close.** A backtest
  that fills at the close of the bar that produced the signal has seen the
  future. This is the single most common way a backtest lies.

  **When one bar touches both the stop and the target, the stop is assumed.**
  Without tick data there is no way to know which came first, and the optimistic
  reading turns a losing strategy into a winning one on paper.

Sizing mirrors spec §5 for one notional account — 99% of equity as margin with
leverage on top — because that is what the platform will actually do. It does
*not* model per-account minimum notionals or step rounding: those differ per
account and per venue, and a backtest that pretended to know them would be
inventing precision it does not have. ``sizing.py`` owns that at execution time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from apps.bots.config import decimal_setting, limits
from apps.bots.divergence import digest_intents
from apps.bots.feed import interval_seconds, to_bar, warmup_bars_needed
from apps.bots.report import Assumptions, ClosedTrade, Report, compute_metrics
from apps.exchanges.base import MarketType
from apps.pine import properties as props_module
from apps.pine.bar import Bar
from apps.pine.errors import PineRuntimeError
from apps.pine.intent import Side
from apps.pine.properties import CommissionType, QtyType, StrategyProperties
from apps.pine.runtime import Runtime
from apps.pine.symbol import SymbolInfo, TimeframeInfo
from apps.pine.validate import validate

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
BPS = Decimal("10000")


@dataclass(slots=True)
class _Position:
    side: Side
    entry_time: int
    entry_price: Decimal
    qty: Decimal
    notional: Decimal
    entry_fee: Decimal
    stop: Decimal | None
    target: Decimal | None
    bars: int = 0
    reason: str = ""
    span: dict | None = None


class BacktestError(Exception):
    """The run could not be produced. Never a partial report presented as whole."""


def load_bars(
    *,
    symbol: str,
    interval: str,
    market: MarketType,
    from_time: int,
    to_time: int,
    warmup: int,
) -> list[Bar]:
    """Bars for the window plus ``warmup`` bars before it, oldest first.

    Reads the archive first — it is a local table with an index on exactly this
    query, and serving depth out of it is the reason bars are kept — then fills
    the head from the live feed. Nothing is invented: a window the archive does
    not cover comes back short and the caller says so.
    """
    from apps.exchanges import candlestore, marketdata

    step = interval_seconds(interval)
    wanted_from = from_time - warmup * step

    stored = candlestore.read_window(
        symbol=symbol.upper(),
        interval=interval,
        market=market,
        limit=int((to_time - wanted_from) / step) + warmup + 10,
        end=to_time,
        exchange=marketdata.pinned_provider(),
    )
    candles = list(stored[0]) if stored else []

    if not candles:
        try:
            payload = marketdata.get_candles(
                symbol=symbol.upper(), interval=interval, market=market, limit=1000, end=to_time
            )
            candles = [
                candlestore.Candle(
                    time=int(row["t"]),
                    open=Decimal(row["o"]),
                    high=Decimal(row["h"]),
                    low=Decimal(row["l"]),
                    close=Decimal(row["c"]),
                    volume=Decimal(row.get("v", "0")),
                )
                for row in payload.get("candles", [])
            ]
        except Exception as exc:  # noqa: BLE001 - reported, never silently empty
            raise BacktestError(
                f"no stored history for {symbol} {interval} and the live feed could not "
                f"be reached ({exc}). Run `manage.py market_sync` or open the chart for "
                f"this pair first."
            ) from exc

    return [to_bar(c) for c in candles if wanted_from <= c.time <= to_time]


def run(
    *,
    source: str,
    symbol: str,
    interval: str,
    market: MarketType = MarketType.FUTURES,
    from_time: int,
    to_time: int,
    leverage: int = 1,
    sl_pct: Decimal | None = None,
    tp_pct: Decimal | None = None,
    inputs: dict | None = None,
    initial_equity: Decimal = Decimal("10000"),
    bars: list[Bar] | None = None,
    property_overrides: dict | None = None,
    mintick: Decimal | None = None,
) -> Report:
    """Validate, replay, and report. ``bars`` is for tests and the divergence check."""
    result = validate(source, limits=limits())
    if not result.ok:
        raise BacktestError("; ".join(str(e) for e in result.errors))

    warmup = warmup_bars_needed(_longest_lookback(result))
    series = bars if bars is not None else load_bars(
        symbol=symbol,
        interval=interval,
        market=market,
        from_time=from_time,
        to_time=to_time,
        warmup=warmup,
    )
    if not series:
        raise BacktestError(
            f"no bars for {symbol} {interval} between {from_time} and {to_time}"
        )

    # Platform default → what `strategy()` declared → what the panel overrode.
    # `properties.resolve` is the only place that order exists, so the header on
    # the report and the form that produced it cannot disagree about which won.
    platform_fee_bps = decimal_setting("BACKTEST_FEE_BPS")
    resolved = props_module.resolve(
        platform=StrategyProperties(
            initial_capital=initial_equity,
            commission_value=platform_fee_bps / Decimal(100),
        ),
        declared={
            key: getattr(result.properties, key) for key in result.properties.declared
        },
        overrides=property_overrides or {},
    )
    # The tick is part of the market data, so a caller who supplies its own
    # bars supplies its own tick: `bars=` is the divergence harness and the
    # test suite, neither of which has an exchange listing to read.
    tick = mintick if mintick is not None else (
        _mintick_for(symbol, market) if bars is None else Decimal("0.01")
    )

    assumptions = Assumptions(
        slippage_bps=decimal_setting("BACKTEST_SLIPPAGE_BPS"),
        fee_bps=(
            resolved.commission_value * Decimal(100)
            if resolved.commission_type is CommissionType.PERCENT
            else ZERO
        ),
        balance_fraction=Decimal(str(settings.TRADING["BALANCE_FRACTION"])),
        leverage=leverage,
        initial_equity=resolved.initial_capital,
        properties=resolved,
        commission_per_order=(
            resolved.commission_value
            if resolved.commission_type is CommissionType.CASH_PER_ORDER
            else ZERO
        ),
        commission_per_contract=(
            resolved.commission_value
            if resolved.commission_type is CommissionType.CASH_PER_CONTRACT
            else ZERO
        ),
        slippage_ticks=resolved.slippage,
        mintick=tick,
        departures=tuple(resolved.live_departures()),
    )

    runtime = Runtime(
        result.program,
        symbol=symbol.upper(),
        inputs=inputs or {},
        limits=limits(),
        symbol_info=SymbolInfo.for_symbol(symbol, market=str(market), mintick=tick),
        timeframe=TimeframeInfo.for_interval(interval),
    )
    engine = _Engine(
        runtime=runtime,
        assumptions=assumptions,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
    )

    warnings: list[str] = []
    evaluated = 0
    for index, bar in enumerate(series):
        history = bar.time < from_time
        try:
            engine.step(bar, ishistory=history)
        except PineRuntimeError as exc:
            raise BacktestError(f"the script failed on bar {index} ({bar.time}): {exc}") from exc
        if not history:
            evaluated += 1

    engine.finish(series[-1])

    if runtime.advance_failures:
        warnings.append(
            f"{len(runtime.advance_failures)} ta.* call site(s) could not be advanced on "
            f"bars that did not reach them — see the upload warnings"
        )
    warnings.extend(resolved.inert_here())
    if evaluated == 0:
        warnings.append(
            "every bar in this window was consumed by warm-up; widen the range or the "
            "report describes nothing"
        )
    history_bars = sum(1 for candle in series if candle.time < from_time)
    if history_bars < warmup:
        # The window opens on indicators that have not converged, so the first
        # trades in this report are decided by numbers TradingView would still
        # be showing as `na`. Cheap to say, and invisible if it is not said.
        warnings.append(
            f"only {history_bars} of the {warmup} warm-up bars this script needs were "
            f"available, so the earliest signals ran on unconverged indicators"
        )

    report = Report(
        assumptions=assumptions,
        symbol=symbol.upper(),
        interval=interval,
        from_time=from_time,
        to_time=to_time,
        bars=evaluated,
        trades=engine.trades,
        equity_curve=engine.curve,
        intent_digest=digest_intents(engine.intents),
        warnings=warnings,
    )
    report.metrics = compute_metrics(
        trades=engine.trades,
        equity_curve=engine.curve,
        bars=evaluated,
        interval=interval,
        initial_equity=resolved.initial_capital,
    )
    return report


def _mintick_for(symbol: str, market: MarketType) -> Decimal:
    """The finest tick any connected venue quotes for this pair.

    Only ``math.round_to_mintick``, ``str.tostring(x, format.mintick)`` and a
    tick-denominated ``slippage`` read it, so a pair nothing lists falls back to
    two decimals rather than refusing the report.
    """
    from apps.trading.models import ExchangeSymbol

    listing = (
        ExchangeSymbol.objects.filter(symbol=symbol.upper(), market=str(market), active=True)
        .exclude(price_tick=None)
        .order_by("price_tick")
        .first()
    )
    return listing.price_tick if listing is not None else Decimal("0.01")


def _longest_lookback(result) -> int:
    """The largest constant length any ``ta.*`` call asks for.

    An over-estimate is cheap (a few hundred extra warm-up bars) and an
    under-estimate is an indicator that trades before it has converged, so this
    leans high deliberately: it takes the largest literal in the script rather
    than trying to trace which argument is a length.
    """
    from apps.pine import ast_nodes as ast

    longest = 0
    if result.program is None:
        return longest
    for node in ast.walk(result.program):
        if isinstance(node, ast.NumberLit):
            try:
                value = int(Decimal(node.value))
            except (ValueError, ArithmeticError):
                continue
            # A price or a percentage is not a lookback. Anything past a few
            # hundred bars is one of those, and warm-up is already floored at
            # WARMUP_MIN_BARS, so ignoring them costs nothing.
            if 0 < value <= 500:
                longest = max(longest, value)
    return longest


class _Engine:
    """The fill model. One notional account, spec §5 sizing, pessimistic exits."""

    def __init__(
        self,
        *,
        runtime: Runtime,
        assumptions: Assumptions,
        sl_pct: Decimal | None,
        tp_pct: Decimal | None,
    ) -> None:
        self.runtime = runtime
        self.a = assumptions
        self.bot_sl = sl_pct
        self.bot_tp = tp_pct
        self.equity = assumptions.initial_equity
        self.position: _Position | None = None
        self.pending: (
            tuple[Side | None, Decimal | None, Decimal | None, str, dict | None] | None
        ) = None
        self.trades: list[ClosedTrade] = []
        self.curve: list[tuple[int, Decimal]] = []
        self.intents: list = []

    # --- one bar ------------------------------------------------------------

    def step(self, bar: Bar, *, ishistory: bool) -> None:
        # 1. Yesterday's signal fills at *this* bar's open. Never at the close
        #    of the bar that produced it — that is the look-ahead bug.
        if self.pending is not None and not ishistory:
            self._execute(self.pending, bar)
            self.pending = None

        # 2. Resting SL/TP are checked against this bar's range, including the
        #    bar that opened the position.
        if self.position is not None:
            self.position.bars += 1
            self._check_exits(bar)

        # 3. The strategy sees the bar, told what is actually held.
        self.runtime.sync_position(
            size_sign=(
                0 if self.position is None
                else (1 if self.position.side is Side.LONG else -1)
            ),
            avg_price=self.position.entry_price if self.position else None,
            equity=self.equity,
            netprofit=self.equity - self.a.initial_equity,
            opentrades=0 if self.position is None else 1,
            performance=self._performance(bar),
        )
        result = self.runtime.run_bar(bar, ishistory=ishistory)

        if ishistory:
            # Warm-up converges indicators; it does not trade, and its intents
            # are discarded rather than recorded.
            return

        intent = result.intent
        self.intents.append(intent)
        self.curve.append((bar.time, self._mark_to_market(bar)))

        desired = intent.desired_side
        held = self.position.side if self.position else None
        if desired != held:
            self.pending = (
                desired,
                intent.sl_pct if intent.sl_pct is not None else self.bot_sl,
                intent.tp_pct if intent.tp_pct is not None else self.bot_tp,
                intent.reason,
                intent.source_span.as_dict() if intent.source_span else None,
            )

    def finish(self, last: Bar) -> None:
        """Close anything still open at the last bar, so the report is complete.

        Marked at the last close rather than left open: an unrealised position
        reported as a trade that never ended flatters every metric that divides
        by trade count.
        """
        if self.position is not None:
            self._close(last, last.close, "end of window")

    # --- fills --------------------------------------------------------------

    def _execute(self, pending, bar: Bar) -> None:
        side, sl_pct, tp_pct, reason, span = pending

        if self.position is not None:
            # A reversal closes first and then opens, in that order, never both
            # at once — the same rule Phase 5 enforces against a live venue.
            self._close(bar, self._slipped(bar.open, closing=True), "signal")
        if side is None:
            return

        price = self._slipped(bar.open, closing=False, side=side)
        qty, notional, margin = self._size(price)
        if price <= ZERO or notional <= ZERO or qty <= ZERO:
            return
        fee = self._commission(notional, qty)
        self.equity -= fee

        stop, target = _resolve_levels(
            price,
            side,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            leverage=self.a.leverage,
            notional=notional,
            margin=margin,
        )
        self.position = _Position(
            side=side,
            entry_time=bar.time,
            entry_price=price,
            qty=qty,
            notional=notional,
            entry_fee=fee,
            stop=stop,
            target=target,
            reason=reason,
            span=span,
        )

    def _performance(self, bar: Bar) -> dict:
        """``strategy.closedtrades`` and the rest, as this simulated account.

        Built here rather than tallied inside the runtime for the same reason
        ``position_size`` is: the driver owns the account, and a runtime keeping
        its own scoreboard would be a second one that could disagree. A
        published strategy reads these to draw its dashboard and to fill in an
        alert payload, so "not supported" would refuse the script over a table.
        """
        capital = self.a.initial_equity or Decimal(1)
        wins = [t for t in self.trades if t.pnl > ZERO]
        losses = [t for t in self.trades if t.pnl < ZERO]
        gross_profit = sum((t.pnl for t in wins), ZERO)
        gross_loss = -sum((t.pnl for t in losses), ZERO)
        net = self.equity - self.a.initial_equity
        open_profit = self._mark_to_market(bar) - self.equity
        peak = max((value for _, value in self.curve), default=self.a.initial_equity)
        drawdown = max(
            (peak_so_far - value for peak_so_far, value in self._peaks()), default=ZERO
        )
        return {
            "closedtrades": Decimal(len(self.trades)),
            "wintrades": Decimal(len(wins)),
            "losstrades": Decimal(len(losses)),
            "eventrades": Decimal(len(self.trades) - len(wins) - len(losses)),
            "initial_capital": self.a.initial_equity,
            "netprofit": net,
            "netprofit_percent": net / capital * Decimal(100),
            "openprofit": open_profit,
            "openprofit_percent": open_profit / capital * Decimal(100),
            "grossprofit": gross_profit,
            "grossprofit_percent": gross_profit / capital * Decimal(100),
            "grossloss": gross_loss,
            "grossloss_percent": gross_loss / capital * Decimal(100),
            "max_drawdown": drawdown,
            "max_drawdown_percent": drawdown / capital * Decimal(100),
            "max_runup": max(peak - self.a.initial_equity, ZERO),
            "max_runup_percent": max(peak - self.a.initial_equity, ZERO) / capital * Decimal(100),
            "avg_trade": (net / Decimal(len(self.trades))) if self.trades else ZERO,
            "avg_trade_percent": (
                net / Decimal(len(self.trades)) / capital * Decimal(100) if self.trades else ZERO
            ),
            "avg_winning_trade": (
                gross_profit / Decimal(len(wins)) if wins else ZERO
            ),
            "avg_losing_trade": (gross_loss / Decimal(len(losses)) if losses else ZERO),
            "account_currency": "USDT",
        }

    def _peaks(self):
        """``(running peak, value)`` down the equity curve — the drawdown input."""
        peak = self.a.initial_equity
        for _, value in self.curve:
            peak = max(peak, value)
            yield peak, value

    def _size(self, price: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        """``(qty, notional, margin)`` — the script's rule, or the platform's.

        ``default_qty_type`` is a *backtest* property (spec §5 sizes every live
        account at 99% of its own balance), and honouring it is what makes this
        report comparable with the one TradingView produced from the same
        script. ``Assumptions._sizing_line`` says which rule was in force, and
        ``live_departures`` says so again in the header, so nobody reads a
        percent-of-equity curve as a prediction of live.
        """
        properties = self.a.properties
        qty_type = getattr(properties, "default_qty_type", None) or QtyType.PLATFORM
        value = getattr(properties, "default_qty_value", ZERO)

        if qty_type is QtyType.PLATFORM:
            margin = self.equity * self.a.balance_fraction
            notional = margin * Decimal(self.a.leverage)
            return (notional / price if price > ZERO else ZERO), notional, margin
        if qty_type is QtyType.FIXED:
            qty = value
        elif qty_type is QtyType.CASH:
            qty = value / price if price > ZERO else ZERO
        else:  # percent_of_equity
            qty = (self.equity * value / Decimal(100)) / price if price > ZERO else ZERO
        notional = qty * price
        # `margin_long`/`margin_short` are a percent of the position the account
        # must fund; TradingView's own default is 0, meaning "no requirement".
        requirement = getattr(properties, "margin_long", ZERO)
        margin = notional * requirement / Decimal(100) if requirement else notional
        return qty, notional, margin

    def _commission(self, notional: Decimal, qty: Decimal) -> Decimal:
        """One side's cost under whichever of the three models is in force."""
        return (
            notional * self.a.fee_bps / BPS
            + self.a.commission_per_order
            + self.a.commission_per_contract * qty
        )

    def _check_exits(self, bar: Bar) -> None:
        position = self.position
        if position is None:
            return
        hit_stop = position.stop is not None and (
            bar.low <= position.stop if position.side is Side.LONG else bar.high >= position.stop
        )
        hit_target = position.target is not None and (
            bar.high >= position.target
            if position.side is Side.LONG
            else bar.low <= position.target
        )
        if hit_stop:
            # Both touched in one bar: the stop is assumed. Stated in the report.
            self._close(bar, position.stop, "stop" if not hit_target else "stop (ambiguous bar)")
        elif hit_target:
            self._close(bar, position.target, "target")

    def _close(self, bar: Bar, price: Decimal, reason: str) -> None:
        position = self.position
        if position is None:
            return
        direction = Decimal(1) if position.side is Side.LONG else Decimal(-1)
        gross = (price - position.entry_price) * position.qty * direction
        exit_fee = self._commission(price * position.qty, position.qty)
        self.equity += gross - exit_fee

        self.trades.append(
            ClosedTrade(
                side=position.side.value,
                entry_time=position.entry_time,
                entry_price=position.entry_price,
                exit_time=bar.time,
                exit_price=price,
                qty=position.qty,
                pnl=gross - exit_fee - position.entry_fee,
                fees=exit_fee + position.entry_fee,
                bars_held=position.bars,
                exit_reason=reason,
                entry_reason=position.reason,
                entry_span=position.span,
            )
        )
        self.position = None

    def _slipped(self, price: Decimal, *, closing: bool, side: Side | None = None) -> Decimal:
        """Slippage always against the trade — the only assumption worth making.

        In ticks when ``strategy(slippage = n)`` said so, in basis points
        otherwise. The two are different units and are never averaged: a report
        states which one it used.
        """
        drift = (
            self.a.mintick * Decimal(self.a.slippage_ticks)
            if self.a.slippage_ticks is not None
            else price * self.a.slippage_bps / BPS
        )
        if closing:
            reference = self.position.side if self.position else Side.LONG
            return price - drift if reference is Side.LONG else price + drift
        return price + drift if side is Side.LONG else price - drift

    def _mark_to_market(self, bar: Bar) -> Decimal:
        if self.position is None:
            return self.equity
        direction = Decimal(1) if self.position.side is Side.LONG else Decimal(-1)
        return self.equity + (bar.close - self.position.entry_price) * self.position.qty * direction


def _resolve_levels(
    entry: Decimal,
    side: Side,
    *,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
    leverage: int,
    notional: Decimal,
    margin: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    """SL/TP prices from percentages, through ``apps.trading.sltp``.

    Reused rather than re-derived: whichever Q5a basis is in force decides
    whether "2%" is a move in price or a loss of margin, and a backtest that
    put the stop somewhere the live platform would not is a backtest of a
    different platform.
    """
    if sl_pct is None and tp_pct is None:
        return None, None
    from apps.exchanges.base import Side as ExchangeSide
    from apps.trading import sltp

    line = sltp.resolve(
        side=ExchangeSide(side.value),
        entry=entry,
        leverage=leverage,
        margin=margin,
        notional=notional,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        reading=sltp.basis(),
    )
    return line.stop_price, line.take_profit_price
