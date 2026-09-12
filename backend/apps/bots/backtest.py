"""Replay a strategy over stored history. Two jobs, and the second is the point.

1. The admin needs to see whether a strategy is worth running at all.
2. **It is the correctness harness for Phases 1–3.** Live mode and backtest mode
   feed the *same runtime object*; if they ever produce different intents from
   the same bars, something is broken, and this is where finding that out costs
   nothing. ``divergence.digest_intents`` is how the two are compared.

The fill model is deliberately pessimistic and is stated in every report:

  **Orders fill where TradingView's Strategy Tester fills them.** At the next
  bar's open by default; at the signal bar's own close when the script sets
  ``process_orders_on_close = true``. The second is not a look-ahead — the
  decision needs that close and nothing after it — and it is also what live
  does, since the bot routes at market the moment the bar closes. Filling a
  ``process_orders_on_close`` script at the next open anyway made every entry a
  bar late against the report the operator was checking this one against.

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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    #: What the entry filled. ``qty`` shrinks as the position is scaled out
    #: (Q33); every level is a share of *this*, so the rounding does not
    #: compound and a 40/30/30 split arrives at the third with the size the
    #: script asked for.
    entry_qty: Decimal = ZERO
    #: How much of the entry is still open, in ``(0, 1]``.
    fraction: Decimal = Decimal(1)


class BacktestError(Exception):
    """The run could not be produced. Never a partial report presented as whole."""


#: What a caller is told while a run is in flight. ``phase`` is one of
#: ``"validating" | "downloading" | "replaying" | "finishing"``, ``done`` is a
#: fraction in ``[0, 1]`` *within that phase*, and ``detail`` carries whatever
#: the phase can honestly count — pages fetched, bars written, bars replayed.
#:
#: A callback and not a return value because the interesting number is the one
#: that exists **before** the answer does: a download that will take forty
#: seconds behind a bare spinner is indistinguishable from a hang, and that is
#: the whole reason this exists.
Progress = Callable[[str, float, dict], None]


def _noop_progress(phase: str, done: float, detail: dict) -> None:
    """The default. A backtest with nobody watching pays nothing for progress."""


#: How long a backtest may spend downloading history it does not hold before it
#: settles for the span it managed to cover. A backtest is a foreground request:
#: a five-minute download behind a spinner is a hang. What arrives inside the
#: budget is replayed and the report says where the data actually started.
DOWNLOAD_BUDGET_SECONDS = 90.0

#: A window is "covered" when the archive holds this share of the bars the
#: interval implies. Venues skip bars (halts, listings, thin pairs), so
#: demanding every one would re-download a series that is already whole.
COVERAGE_RATIO = Decimal("0.9")


@dataclass(slots=True)
class HistoryWindow:
    """The bars a backtest will replay, and what had to happen to get them."""

    bars: list[Bar]
    #: Rows written to the archive by this call. Zero on the second run of the
    #: same window, which is the whole point of writing them.
    downloaded: int = 0
    #: Said in the report when the venue could not go back as far as asked.
    notes: list[str] = field(default_factory=list)
    #: Bars the archive already held before this call. ``downloaded == 0`` and
    #: this non-zero is the cache hit the second run of a pair gets, and the
    #: panel says so rather than leaving the operator to infer it from speed.
    from_archive: int = 0


def _download_window(
    *,
    exchange: str,
    symbol: str,
    interval: str,
    market: MarketType,
    since: int,
    progress: Progress = _noop_progress,
) -> int:
    """Page back to ``since`` from now, writing every page to the archive.

    Deliberately not ``catalogue.backfill_series``: that one is expressed in
    whole days from now and runs on a worker for the chart. A backtest asks for
    an exact second, in the foreground, on a clock — so the walk is here, and
    it stops on the budget rather than on a page count.
    """
    from apps.exchanges import catalogue
    from apps.exchanges.feed_base import BACKFILL_TIMEOUT, fetch_candles
    from apps.exchanges.marketdata import source_for

    source = source_for(exchange, timeout=BACKFILL_TIMEOUT)
    page = max(1, source.page_limit)
    started = time.monotonic()
    deadline = started + DOWNLOAD_BUDGET_SECONDS
    end: int | None = None
    written = 0
    pages = 0
    # Progress is measured against *time already walked back*, not pages: pages
    # are a venue's own quirk (500 here, 1000 there) and a bar counter would run
    # backwards on a pair with gaps. The span from `since` to now is fixed and
    # known before the first request, which is what a progress bar needs.
    span = max(1, int(time.time()) - since)

    progress("downloading", 0.0, {"exchange": exchange, "pages": 0, "bars": 0})

    while time.monotonic() < deadline:
        candles = fetch_candles(
            source, symbol=symbol, interval=interval, market=market, limit=page, end=end
        )
        if not candles:
            break
        written += catalogue.write_candles(exchange, symbol, market, interval, candles)
        pages += 1
        oldest = min(candle.time for candle in candles)
        progress(
            "downloading",
            min(1.0, max(0.0, (int(time.time()) - oldest) / span)),
            {
                "exchange": exchange,
                "pages": pages,
                "bars": written,
                "oldest": oldest,
                # The budget is the other half of the honesty: a walk that runs
                # out of time stops and the report says where the data began,
                # so the bar has to show that clock too.
                "elapsed": round(time.monotonic() - started, 1),
                "budget": DOWNLOAD_BUDGET_SECONDS,
            },
        )
        if end is not None and oldest >= end:
            break  # the venue is not paging any further back
        if oldest <= since:
            break
        end = oldest - 1
        time.sleep(catalogue.REQUEST_PAUSE)

    progress("downloading", 1.0, {"exchange": exchange, "pages": pages, "bars": written})
    return written


def load_bars(
    *,
    symbol: str,
    interval: str,
    market: MarketType,
    from_time: int,
    to_time: int,
    warmup: int,
    progress: Progress = _noop_progress,
) -> HistoryWindow:
    """Bars for the window plus ``warmup`` bars before it, oldest first.

    The archive is read first — it is a local table with an index on exactly
    this query, and serving depth out of it is the reason bars are kept. A
    window it does not cover is **downloaded here and written back**, so the
    second backtest of a pair costs one query: "run market_sync first" is a
    chore handed to the operator for something the platform can do itself.

    Nothing is invented. When the venue's own history stops short of the
    request the run proceeds over what exists and ``notes`` says where it
    really began — a shorter honest window beats a refusal.
    """
    from apps.exchanges import candlestore, marketdata

    step = interval_seconds(interval)
    wanted_from = from_time - warmup * step
    symbol = symbol.upper()
    exchange = marketdata.pinned_provider() or _first_provider()
    notes: list[str] = []

    def archived() -> list:
        stored = candlestore.read_window(
            symbol=symbol,
            interval=interval,
            market=market,
            limit=int((to_time - wanted_from) / step) + warmup + 10,
            end=to_time,
            exchange=marketdata.pinned_provider(),
        )
        rows = list(stored[0]) if stored else []
        return [c for c in rows if wanted_from <= c.time <= to_time]

    candles = archived()
    from_archive = len(candles)
    downloaded = 0

    if _covers(candles, wanted_from=wanted_from, to_time=to_time, step=step):
        # Nothing to fetch. Said explicitly so the panel can show "served from
        # the archive" instead of a progress bar that flashes past.
        progress("downloading", 1.0, {"cached": True, "bars": from_archive})
    else:
        if not exchange:
            raise BacktestError(
                f"no stored history for {symbol} {interval} and no public market-data "
                f"source is configured, so there is nothing to download it from"
            )
        try:
            downloaded = _download_window(
                exchange=exchange,
                symbol=symbol,
                interval=interval,
                market=market,
                since=wanted_from,
                progress=progress,
            )
        except Exception as exc:  # noqa: BLE001 - reported, never a silent empty series
            logger.warning("backtest history download failed for %s %s: %s", symbol, interval, exc)
            if not candles:
                raise BacktestError(
                    f"{symbol} {interval} has no stored history and {exchange} could not "
                    f"be reached to download it ({exc})"
                ) from exc
            notes.append(
                f"{exchange} could not be reached to extend this window ({exc}), so the "
                f"report covers only the history already stored"
            )
        else:
            candles = archived()

    if not candles:
        raise BacktestError(
            f"{exchange or 'the configured feed'} returned no {interval} bars for "
            f"{symbol} in this window — check the symbol, or pick a market this pair "
            f"actually trades on"
        )

    earliest = min(candle.time for candle in candles)
    if earliest > from_time + step:
        notes.append(
            f"history for {symbol} {interval} begins at {utc_text(earliest)}, so the "
            f"report starts there rather than at the date requested"
        )

    return HistoryWindow(
        bars=[to_bar(candle) for candle in candles],
        downloaded=downloaded,
        notes=notes,
        from_archive=from_archive,
    )


def _covers(candles: list, *, wanted_from: int, to_time: int, step: int) -> bool:
    """True when the archive already holds this window densely enough.

    Both ends matter: a pair downloaded a month ago has the start of the window
    and none of the end, and a run that only checked the count would replay it
    and stop early without saying so.
    """
    if not candles:
        return False
    expected = max(1, (to_time - wanted_from) // step)
    if Decimal(len(candles)) < COVERAGE_RATIO * Decimal(expected):
        return False
    newest = max(candle.time for candle in candles)
    oldest = min(candle.time for candle in candles)
    return oldest <= wanted_from + step and newest >= to_time - 2 * step


def _first_provider() -> str:
    """The venue an unpinned feed would quote, used as the download source."""
    from apps.exchanges import marketdata

    providers = marketdata._configured_providers()
    return providers[0] if providers else ""


def utc_text(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, tz=UTC).strftime("%Y-%m-%d %H:%M")


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
    progress: Progress = _noop_progress,
) -> Report:
    """Validate, replay, and report. ``bars`` is for tests and the divergence check."""
    progress("validating", 0.0, {})
    result = validate(source, limits=limits())
    if not result.ok:
        raise BacktestError("; ".join(str(e) for e in result.errors))
    progress("validating", 1.0, {})

    warmup = warmup_bars_needed(_longest_lookback(result))
    history_notes: list[str] = []
    data_source: dict = {"downloaded": 0, "from_archive": len(bars or ())}
    if bars is not None:
        series = bars
    else:
        window = load_bars(
            symbol=symbol,
            interval=interval,
            market=market,
            from_time=from_time,
            to_time=to_time,
            warmup=warmup,
            progress=progress,
        )
        series, history_notes = window.bars, window.notes
        data_source = {
            "downloaded": window.downloaded,
            "from_archive": window.from_archive,
            "total": len(window.bars),
        }
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
        entry_rule=(
            "signal bar's close (process_orders_on_close)"
            if resolved.process_orders_on_close
            else "next bar's open"
        ),
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

    warnings: list[str] = list(history_notes)
    evaluated = 0
    total = len(series)
    # One update per percent, not one per bar: a 200,000-bar replay would
    # otherwise spend more time reporting on itself than replaying.
    every = max(1, total // 100)
    progress("replaying", 0.0, {"bars": 0, "total": total})
    for index, bar in enumerate(series):
        history = bar.time < from_time
        try:
            engine.step(bar, ishistory=history)
        except PineRuntimeError as exc:
            raise BacktestError(f"the script failed on bar {index} ({bar.time}): {exc}") from exc
        if not history:
            evaluated += 1
        if index % every == 0:
            progress(
                "replaying",
                (index + 1) / total,
                {"bars": index + 1, "total": total, "trades": len(engine.trades)},
            )

    progress("replaying", 1.0, {"bars": total, "total": total, "trades": len(engine.trades)})
    engine.finish(series[-1])
    progress("finishing", 0.0, {"trades": len(engine.trades)})

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
    report.data_source = data_source
    progress("finishing", 1.0, {"trades": len(engine.trades)})
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
    # `strategy(max_lines_count = 500)` is a drawing budget, not a lookback. Read
    # as one it tripled the warm-up to 1500 bars — a month of 30m history spent
    # before the first trade, on a venue that only keeps 5000 bars at all.
    declaration = {
        id(child)
        for node in ast.walk(result.program)
        if isinstance(node, ast.Call)
        and ast.dotted_name(node.func) in ("strategy", "indicator", "study")
        for child in ast.walk(node)
    }
    for node in ast.walk(result.program):
        if isinstance(node, ast.NumberLit) and id(node) not in declaration:
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
        #: The scale-outs a bar asked for — ``(fraction left, reason)`` each, in
        #: order — filling under the same rule as an entry.
        self.pending_reduce: tuple[tuple[Decimal, str], ...] | None = None
        self.trades: list[ClosedTrade] = []
        self.curve: list[tuple[int, Decimal]] = []
        self.intents: list = []

    # --- one bar ------------------------------------------------------------

    def step(self, bar: Bar, *, ishistory: bool) -> None:
        on_close = bool(getattr(self.a.properties, "process_orders_on_close", False))
        # 1. Yesterday's signal fills at *this* bar's open — TradingView's own
        #    default. A script that set `process_orders_on_close` filled at the
        #    signal bar's close instead, in step 4.
        if not ishistory and not on_close:
            self._fill(bar, bar.open)

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
            # What the scale-outs left, as the supervisor passes from the
            # exchange. Omitted, the runtime restarted every bar from a whole
            # position: TP2's "30% of what is left" read as no change from
            # TP1's 70% and was skipped, and TP3 cut to 60% instead of 29.4%.
            fraction=self.position.fraction if self.position is not None else None,
        )
        result = self.runtime.run_bar(bar, ishistory=ishistory)

        if ishistory:
            # Warm-up converges indicators; it does not trade, and its intents
            # are discarded rather than recorded.
            return

        intent = result.intent
        self.intents.append(intent)

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
        elif self.position is not None and intent.position_fraction < self.position.fraction:
            # Q33: the side is unchanged and the size is not, which is the one
            # change the side comparison above cannot see. Same fill rule as an
            # entry — decided on this bar, filled at the next one's open.
            # One step per `strategy.close(qty_percent =)` the bar made: TP2 and
            # TP3 on the same bar are two rows in TradingView's List of Trades.
            self.pending_reduce = intent.scale_steps or (
                (intent.position_fraction, intent.reason or "scale out"),
            )

        # 4. `process_orders_on_close = true`: what this bar decided fills at
        #    this bar's close, as it does in TradingView's Strategy Tester. Not a
        #    look-ahead — the decision needs the close and nothing after it — and
        #    it is what live does too: the bot routes at market the moment the
        #    bar closes.
        if on_close:
            self._fill(bar, bar.close)
        self.curve.append((bar.time, self._mark_to_market(bar)))

    def _fill(self, bar: Bar, basis: Decimal) -> None:
        """Fill whatever is waiting at ``basis`` — the scale-out first, then the entry."""
        if self.pending_reduce is not None:
            price = self._slipped(basis, closing=True)
            for to_fraction, why in self.pending_reduce:
                self._reduce(bar, price, to_fraction, why)
            self.pending_reduce = None
        if self.pending is not None:
            self._execute(self.pending, bar, basis)
            self.pending = None

    def finish(self, last: Bar) -> None:
        """Close anything still open at the last bar, so the report is complete.

        Marked at the last close rather than left open: an unrealised position
        reported as a trade that never ended flatters every metric that divides
        by trade count.
        """
        if self.position is not None:
            self._close(last, last.close, "end of window")

    # --- fills --------------------------------------------------------------

    def _execute(self, pending, bar: Bar, basis: Decimal) -> None:
        side, sl_pct, tp_pct, reason, span = pending

        if self.position is not None:
            # A reversal closes first and then opens, in that order, never both
            # at once — the same rule Phase 5 enforces against a live venue.
            self._close(bar, self._slipped(basis, closing=True), "signal")
        if side is None:
            return

        price = self._slipped(basis, closing=False, side=side)
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
            entry_qty=qty,
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

    def _reduce(self, bar: Bar, price: Decimal, to_fraction: Decimal, reason: str) -> None:
        """Take a share off and leave the rest running (Q33).

        Realised now, not at the final close: a scale-out is money in the
        account from this bar on, and an equity curve that banked it only at the
        end would understate the drawdown the strategy actually ran.

        **Each slice is its own closed trade**, as in TradingView's List of
        Trades: a TP1/TP2/TP3 position is four rows there, each with the entry
        it came from. Counting it as one made this report say "4 trades" beside
        a Strategy Tester saying 58 for the same entries, and put the win rate
        and profit factor on a different basis from the numbers being checked.
        """
        position = self.position
        if position is None or position.entry_qty <= ZERO:
            return
        remaining = position.entry_qty * to_fraction
        qty = position.qty - remaining
        if qty <= ZERO:
            return

        direction = Decimal(1) if position.side is Side.LONG else Decimal(-1)
        gross = (price - position.entry_price) * qty * direction
        exit_fee = self._commission(price * qty, qty)
        # The entry fee follows the size out of the position, so the slice
        # carries its own share and the remainder is not charged for it twice.
        entry_share = position.entry_fee * qty / position.entry_qty

        self.equity += gross - exit_fee
        position.qty = remaining
        position.fraction = to_fraction
        position.entry_fee -= entry_share
        self.trades.append(
            ClosedTrade(
                side=position.side.value,
                entry_time=position.entry_time,
                entry_price=position.entry_price,
                exit_time=bar.time,
                exit_price=price,
                qty=qty,
                pnl=gross - exit_fee - entry_share,
                fees=exit_fee + entry_share,
                bars_held=position.bars,
                exit_reason=reason,
                entry_reason=position.reason,
                entry_span=position.span,
            )
        )

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
                # What was still open: the slices already scaled out are their
                # own rows, each carrying its own share of the entry fee.
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
        self.pending_reduce = None

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
