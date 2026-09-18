"""The bot's chart, as a visual backtest rather than a log of what happened.

The distinction is the whole module. A chart built from ``BotBar`` can only
draw the bars the bot has been running for, so a bot started this morning has a
chart that begins this morning — and the question an operator actually has
("would this have traded last night, and did it?") cannot be asked of it at
all.

So the chart is a **replay over real history**, and the live run is drawn on
top of it:

  **Candles** come from the archive (`candlestore`), downloaded from the pinned
  venue — Hyperliquid by default — when the window reaches past what is stored.
  Real bars from the venue the bot trades on, never a synthetic series.

  **Entries and exits** come from ``backtest.run`` over that same window: the
  fill model the report uses, so a mark on the chart is at the price the
  Strategy Tester would print. They are what the strategy *would* have done.

  **Actions** come from ``BotAction`` — what was really routed, if the bot was
  running at the time. Drawn as their own marks, because the gap between an
  entry the replay found and an action that never happened is the diagnosis.

Paging back is the same call with ``before`` set: each page carries its own
warm-up bars ahead of the window, so an older page's indicators are converged
the same way the newest page's are.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from apps.bots import backtest
from apps.bots.config import limits
from apps.bots.feed import interval_seconds
from apps.bots.models import Bot, BotAction
from apps.exchanges.base import MarketType
from apps.pine.validate import validate

logger = logging.getLogger(__name__)

#: Hard ceiling on one page. Lightweight Charts handles far more than this, but
#: every bar costs a replay step and the page is a foreground request.
MAX_BARS = 1500

#: How far from a replayed entry a routed action may sit and still count as
#: *that* entry. One bar: an order routed on the close of the signal bar and
#: one filled at the next open are the same decision, and anything further
#: apart is a different one.
MATCH_BARS = 1


def payload(
    bot: Bot,
    *,
    interval: str,
    limit: int,
    before: int | None = None,
) -> dict:
    """One page of chart: candles, the script's series, and where it traded.

    ``before`` is an exclusive upper bound in epoch seconds — the oldest bar
    the panel already holds — which is what makes dragging the chart back a
    request for the page before this one rather than a wider re-read of the
    same one.
    """
    step = interval_seconds(interval)  # raises ValueError on an unknown interval
    limit = max(10, min(limit, MAX_BARS))
    market = MarketType(bot.market)

    to_time = (before - step) if before else backtest.last_closed_bar(step)
    from_time = to_time - (limit - 1) * step
    if to_time <= 0:
        return _empty(bot, interval, note="no_history")

    result = validate(bot.strategy_version.source, limits=limits())
    if not result.ok:
        return _empty(bot, interval, note="invalid_strategy")

    try:
        report = backtest.run(
            source=bot.strategy_version.source,
            symbol=bot.symbol,
            interval=interval,
            market=market,
            from_time=from_time,
            to_time=to_time,
            leverage=bot.leverage,
            sl_pct=bot.sl_pct,
            tp_pct=bot.tp_pct,
            inputs=bot.input_values or {},
            property_overrides=bot.property_overrides or {},
            trace=True,
        )
    except backtest.BacktestError as exc:
        # A window older than the venue will serve is not an error: it is the
        # end of the scrollback, and the panel stops asking for more.
        logger.info("bot %s chart window %s–%s: %s", bot.id, from_time, to_time, exc)
        return _empty(bot, interval, note="no_history")

    candles = _candles(bot, interval=interval, market=market, from_time=from_time, to_time=to_time)
    if not candles:
        return _empty(bot, interval, note="no_history")

    trades = [trade.as_dict() for trade in report.trades]
    actions = _actions(bot, from_time=from_time, to_time=to_time)
    return {
        "interval": interval,
        "symbol": bot.symbol,
        "market": bot.market,
        "source": _source(),
        "from_time": candles[0]["time"],
        "to_time": candles[-1]["time"],
        "candles": candles,
        "series": _series_from(report.bar_trace),
        "markers": (
            _signal_markers(report.bar_trace) + _trade_markers(trades) + _action_markers(actions)
        ),
        "trades": trades,
        "summary": _summary(
            report,
            trades,
            actions,
            _run_spans(bot, from_time=from_time, to_time=to_time),
            step=step,
        ),
        "warnings": list(report.warnings),
        "note": "",
    }


def _empty(bot: Bot, interval: str, *, note: str) -> dict:
    return {
        "interval": interval,
        "symbol": bot.symbol,
        "market": bot.market,
        "source": _source(),
        "from_time": 0,
        "to_time": 0,
        "candles": [],
        "series": [],
        "markers": [],
        "trades": [],
        "summary": {},
        "warnings": [],
        "note": note,
    }


def _source() -> str:
    """The venue the bars and the live stream both come from.

    Named in the payload rather than left to the panel to assume: a chart that
    does not say which exchange quoted it is a chart whose price cannot be
    checked against anything.
    """
    from apps.exchanges import marketdata

    return marketdata.pinned_provider() or backtest._first_provider()


def _candles(
    bot: Bot, *, interval: str, market: MarketType, from_time: int, to_time: int
) -> list[dict]:
    """The window's bars, straight out of the archive ``run`` just filled."""
    from apps.exchanges import candlestore, marketdata

    step = interval_seconds(interval)
    stored = candlestore.read_window(
        symbol=bot.symbol.upper(),
        interval=interval,
        market=market,
        limit=int((to_time - from_time) / step) + 2,
        end=to_time,
        exchange=marketdata.pinned_provider(),
    )
    rows = list(stored[0]) if stored else []
    return [
        {
            "time": candle.time,
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume),
        }
        for candle in rows
        if from_time <= candle.time <= to_time
    ]


def _series_from(trace: list[tuple[int, dict]]) -> list[dict]:
    """Per-bar plot dictionaries → one array per named series, chart-ready.

    Sparse by construction: a bar where a series was ``na`` contributes no
    point, so a line breaks where the script had no value rather than being
    drawn through zero.
    """
    names: list[str] = []
    for _, intent in trace:
        for name in intent.get("plots") or {}:
            if name not in names:
                names.append(name)
    series = []
    for name in names:
        points = []
        for time, intent in trace:
            value = (intent.get("plots") or {}).get(name)
            if value is None or value == "":
                continue
            try:
                points.append({"time": time, "value": float(value)})
            except (TypeError, ValueError):
                continue
        if points:
            series.append({"name": name, "points": points})
    return series


def _signal_markers(trace: list[tuple[int, dict]]) -> list[dict]:
    """Where the *desired* side changed — one marker per change, never per bar.

    Distinct from an entry: a strategy can want a side on a bar whose order the
    fill model places on the next one, and on a chart those are two different
    places.
    """
    markers = []
    previous = None
    for time, intent in trace:
        side = intent.get("side")
        if side != previous:
            markers.append(
                {
                    "time": time,
                    "side": side,
                    "kind": "signal",
                    "price": None,
                    "reason": intent.get("reason") or "",
                }
            )
        previous = side
    return markers


def _trade_markers(trades: list[dict]) -> list[dict]:
    """The replay's fills — an entry and an exit per closed trade, at its price.

    This is what "would it have traded last night" looks like on a chart, and
    it is the fill model the Strategy Tester report uses, not a second one.
    """
    markers: list[dict] = []
    for index, trade in enumerate(trades):
        markers.append(
            {
                "time": trade["entry_time"],
                "side": trade["side"],
                "kind": "entry",
                "price": trade["entry_price"],
                "reason": trade.get("entry_reason") or "",
                "trade": index + 1,
            }
        )
        if trade["exit_time"]:
            markers.append(
                {
                    "time": trade["exit_time"],
                    "side": trade["side"],
                    "kind": "exit",
                    "price": trade["exit_price"],
                    "reason": trade.get("exit_reason") or "",
                    "pnl": trade["pnl"],
                    "trade": index + 1,
                }
            )
    return markers


def _actions(bot: Bot, *, from_time: int, to_time: int) -> list[BotAction]:
    """Every action this bot routed inside the window, across **all** its runs.

    Not just the latest run: a bot restarted at 08:00 did not stop having
    traded at 03:00, and a chart that forgot the earlier run would show exactly
    the "we took no trades" picture this module exists to disprove.
    """
    return list(
        BotAction.objects.filter(
            run__bot=bot, bar_time__gte=from_time, bar_time__lte=to_time
        ).order_by("bar_time")[:MAX_BARS]
    )


def _action_markers(actions: list[BotAction]) -> list[dict]:
    return [
        {
            "time": action.bar_time,
            "side": (action.intent or {}).get("side"),
            "kind": "action",
            "action_type": action.action_type,
            "ok": action.ok,
            "price": None,
            "reason": action.reason or "",
        }
        for action in actions
    ]


def _run_spans(bot: Bot, *, from_time: int, to_time: int) -> list[tuple[int, int]]:
    """When this bot was actually running, in epoch seconds, inside the window.

    Needed because "the replay found a trade and the bot sent nothing" is only
    a discrepancy while the bot was *on*. Without this every page of history
    older than the bot itself would report every trade on it as missed, which
    is the kind of alarm an operator learns to ignore — and then misses the
    real one.
    """
    spans: list[tuple[int, int]] = []
    for run in bot.runs.all():
        start = int(run.started_at.timestamp())
        end = int(run.stopped_at.timestamp()) if run.stopped_at else to_time
        if end < from_time or start > to_time:
            continue
        spans.append((max(start, from_time), min(end, to_time)))
    return spans


def _summary(
    report,
    trades: list[dict],
    actions: list[BotAction],
    spans: list[tuple[int, int]],
    *,
    step: int,
) -> dict:
    """The window in numbers, including the one nobody else counts.

    ``unrouted`` is replayed entries that fell **while the bot was running** and
    have no action of any kind within a bar of them. Both halves matter. The bot
    cannot be blamed for a trade on a bar it was switched off for, and a paper
    bot's decisions are ``shadow`` rows which route nothing on purpose — so
    excluding those would report every correct paper decision as a discrepancy.
    Whether an action reached a venue is the mark's own colour and the activity
    list beside it.

    A bot that was running while the replay found trades and decided none is the
    discrepancy an operator is looking at this chart to find, and leaving that to
    be spotted by eye across a hundred marks is leaving it unfound.
    """
    decided = [action.bar_time for action in actions]
    unrouted = 0
    for trade in trades:
        entry = trade["entry_time"]
        if not any(start <= entry <= end for start, end in spans):
            continue
        if not any(abs(bar - entry) <= MATCH_BARS * step for bar in decided):
            unrouted += 1
    wins = [t for t in trades if Decimal(t["pnl"]) > 0]
    return {
        "bars": report.bars,
        "trades": len(trades),
        "wins": len(wins),
        "net_profit": str(sum((Decimal(t["pnl"]) for t in trades), Decimal(0))),
        "actions": len(actions),
        "unrouted": unrouted,
        # How much of this window the bot was switched on for. "It took no
        # trades" and "it was not running" are different answers.
        "watched_seconds": sum(end - start for start, end in spans),
    }
