"""Everything needed to decide whether to intervene, in one payload — Q41.

The control tab asks one question: **does what the platform is holding match
what the chart says it should be holding?** Answering it from four tabs and a
second browser window is how a position gets closed twice or opened on the
wrong side, so the whole answer arrives at once:

  * what the strategy last said — the side it wants, whether that bar was an
    entry *signal* or a position simply persisting, and the words the script
    itself put on it;
  * what the platform is holding — the bot's own trade, marked to market
    through ``market_views.mark_to_market``, the same arithmetic the positions
    panel shows, per leg and in total;
  * what the money is — equity and free balance across the accounts this bot
    would actually reach, because an entry that cannot be sized is a button
    that does nothing;
  * and the difference between the first two, named rather than left for the
    reader to spot.

**Derived, never decided.** Every number here is read off a row that already
exists or computed by the module that owns it. The tab recomputes nothing and
this module decides nothing: pressing a button goes to ``intervene.py``, which
goes to the order path everything else goes through.

The divergence codes are codes, not sentences — the panel renders them through
i18n like everything else the bot app emits.
"""

from __future__ import annotations

from decimal import Decimal

from apps.accounts.models import AccountStatus, ConnectedAccount
from apps.accounts.visibility import _check, _filtered
from apps.bots import intervene
from apps.bots.models import Bot, BotAction, BotBar, BotState
from apps.bots.riskgate import _halted
from apps.bots.serializers import BotActionSerializer
from apps.exchanges.base import MarketType
from apps.exchanges.marketdata import MarketDataError, get_ticker
from apps.trading.market_views import mark_to_market
from apps.trading.models import Trade, TradeStatus

#: How many evaluated bars the signal list carries. Enough to see the last
#: entry and the bars since, not enough to be a chart — the chart tab is a
#: chart.
SIGNAL_BARS = 12

#: How many routed actions ride along. The activity tab is the log; this is
#: "what happened just now", which is the only part a decision depends on.
RECENT_ACTIONS = 6

ALIGNED = "aligned"
STRATEGY_WANTS_IN = "strategy_wants_in"
STRATEGY_WANTS_OUT = "strategy_wants_out"
SIDE_MISMATCH = "side_mismatch"
UNKNOWN = "unknown"


def payload(bot: Bot, *, user) -> dict:
    """The control tab's single read. One request, one picture."""
    run = intervene.open_run(bot) or intervene.latest_run(bot)
    trade = _held_trade(run)
    position = mark_to_market(trade, sees_hidden=_check(user))
    strategy = _strategy(run)
    held_side = trade.side if trade is not None else None

    return {
        "bot": {
            "id": bot.id,
            "name": bot.name,
            "symbol": bot.symbol,
            "interval": bot.interval,
            "market": bot.market,
            "leverage": bot.leverage,
            "state": bot.state,
            "dry_run": bot.dry_run,
            "exit_policy": bot.exit_policy,
            "sl_pct": _s(bot.sl_pct),
            "tp_pct": _s(bot.tp_pct),
            "safety_net_pct": _s(bot.safety_net_pct),
            "running": bot.state in (BotState.PAPER, BotState.LIVE),
        },
        "run": None
        if run is None
        else {
            "id": run.id,
            "started_at": run.started_at,
            "stopped_at": run.stopped_at,
            "stop_reason": run.stop_reason,
            "last_bar_time": run.last_bar_time,
            "bars_evaluated": run.bars_evaluated,
        },
        "strategy": strategy,
        "position": position,
        "capital": _capital(user),
        "mark": _mark(bot),
        # What the two disagree about, if anything. Named here rather than in
        # the browser: the panel would be a second opinion about the one
        # question the tab exists to answer.
        "divergence": _divergence(strategy, held_side),
        # Q41's guard, shown because an operator who closed by hand and sees
        # nothing reopen deserves to know whether that is the strategy being
        # quiet or the platform holding the side off.
        "hold_off": None
        if run is None or not run.manual_flat_side
        else {"side": run.manual_flat_side, "bar_time": run.manual_flat_bar},
        "actions": _recent_actions(bot, run, user),
        "can": _can(bot, run, held_side),
    }


# --- the pieces -------------------------------------------------------------


def _held_trade(run) -> Trade | None:
    if run is None:
        return None
    return (
        Trade.objects.filter(bot_run=run, status=TradeStatus.OPEN)
        .prefetch_related("legs__account")
        .order_by("-id")
        .first()
    )


def _strategy(run) -> dict | None:
    """What the script has been saying, newest bar first.

    Read off stored ``BotBar`` rows, so it is the same intent the bot acted on
    rather than a re-evaluation — a second run of the script against the same
    bars is a second opinion, and the whole point of this tab is to compare the
    *first* one against the chart.
    """
    if run is None:
        return None
    bars = list(run.bars.all()[:SIGNAL_BARS])
    if not bars:
        return None
    newest = bars[0]
    intent = newest.intent or {}
    return {
        "bar_time": newest.bar_time,
        "close": _s(newest.close),
        "desired_side": intent.get("side"),
        "entry_signal": bool(intent.get("entry_signal")),
        "reason": intent.get("reason", ""),
        "exit_reason": intent.get("exit_reason", ""),
        "sl_pct": intent.get("sl_pct"),
        "tp_pct": intent.get("tp_pct"),
        "position_fraction": intent.get("position_fraction"),
        "bars": [
            {
                "bar_time": bar.bar_time,
                "close": _s(bar.close),
                "side": (bar.intent or {}).get("side"),
                "entry_signal": bool((bar.intent or {}).get("entry_signal")),
                "reason": (bar.intent or {}).get("reason", ""),
                "exit_reason": (bar.intent or {}).get("exit_reason", ""),
            }
            for bar in bars
        ],
    }


def _divergence(strategy: dict | None, held_side: str | None) -> dict:
    """Where the strategy and the platform part company, as a code.

    ``unknown`` is its own answer and not a quiet ``aligned``: a bot with no
    evaluated bars has said nothing to compare against, and reporting that as
    agreement is how a stopped bot reads as a bot that is keeping up.
    """
    if strategy is None:
        return {
            "code": UNKNOWN,
            "wants": None,
            "holds": held_side,
            "bar_time": None,
        }
    wants = strategy["desired_side"]
    if wants == held_side:
        code = ALIGNED
    elif held_side is None:
        code = STRATEGY_WANTS_IN
    elif wants is None:
        code = STRATEGY_WANTS_OUT
    else:
        code = SIDE_MISMATCH
    return {
        "code": code,
        "wants": wants,
        "holds": held_side,
        "bar_time": strategy["bar_time"],
    }


def _capital(user) -> dict:
    """The money this bot can actually reach, per account and in total.

    Filtered exactly like every other read surface (Q27) — hidden accounts are
    gone before anything is summed, so the totals are over the visible rows
    rather than trimmed afterwards.

    ``eligible`` is the one that matters in front of an entry button: a bot
    routes only to accounts with ``bot_trading_enabled`` on, and that switch is
    off by default. Zero eligible accounts is the commonest reason a press does
    nothing, and it is said here rather than discovered in a failure notice.
    """
    hidden = _filtered(user)
    rows = ConnectedAccount.objects.exclude(id__in=hidden).order_by("label")
    busy = set(
        Trade.objects.filter(status=TradeStatus.OPEN)
        .values_list("legs__account_id", flat=True)
        .distinct()
    )
    equity = Decimal("0")
    available = Decimal("0")
    out = []
    for row in rows:
        eligible = row.status == AccountStatus.ACTIVE and row.bot_trading_enabled
        if eligible:
            equity += row.last_equity or Decimal("0")
            available += row.last_balance or Decimal("0")
        out.append(
            {
                "id": row.id,
                "label": row.label,
                "exchange": row.exchange,
                "status": row.status,
                "bot_trading_enabled": row.bot_trading_enabled,
                "eligible": eligible,
                "in_a_trade": row.id in busy,
                "equity": _s(row.last_equity),
                "available": _s(row.last_balance),
                "asset": row.last_balance_asset,
                "at": row.last_balance_at,
            }
        )
    return {
        "accounts": out,
        "eligible": sum(1 for row in out if row["eligible"]),
        # Only the reachable accounts are summed. A total that counted an
        # account this bot cannot route to is a number the next entry will not
        # be sized from.
        "equity": _s(equity),
        "available": _s(available),
        "asset": "USDT",
    }


def _mark(bot: Bot) -> dict | None:
    """The public feed's price for this bot's pair, or nothing.

    Nothing is a real answer: with no feed there is no price, and the panel
    says "no price feed" rather than drawing a number. Never fatal here — the
    position, the signals and the balances are all still worth showing.
    """
    try:
        return get_ticker(symbol=bot.symbol, market=MarketType(bot.market))
    except (MarketDataError, ValueError):
        return None


def _recent_actions(bot: Bot, run, user) -> list[dict]:
    """The last few routed decisions of this **bot**, across runs.

    Serialised through ``BotActionSerializer`` with the same context the
    activity tab builds, hidden accounts included: this is a surface that names
    accounts, and Q27 has one rule for all of them.
    """
    if run is None:
        return []
    rows = list(
        BotAction.objects.filter(run__bot_id=bot.id).order_by("-bar_time", "-id")[
            :RECENT_ACTIONS
        ]
    )
    if not rows:
        return []
    prices = dict(
        BotBar.objects.filter(
            run__bot_id=bot.id, bar_time__in=[row.bar_time for row in rows]
        ).values_list("bar_time", "close")
    )
    return BotActionSerializer(
        rows,
        many=True,
        context={
            "hidden_ids": _filtered(user),
            "bar_prices": prices,
            "symbol": bot.symbol,
            "interval": bot.interval,
        },
    ).data


def _can(bot: Bot, run, held_side: str | None) -> dict:
    """Which buttons are live, and the code explaining a dead one.

    The server decides this, not the browser: "may this bot open a position"
    is the same question ``intervene.act`` answers, and two implementations of
    it would disagree on the day it matters.
    """
    # Same order ``intervene.act`` refuses in, and for the same reason: with
    # the halt on, Q22 has already stopped the bot, so "not running" is the
    # symptom and the halt is the cause. A button greyed out for the wrong
    # reason sends the operator to press Start, which the halt refuses too.
    if _halted():
        return {"open": False, "close": held_side is not None, "code": "halt"}
    running = bot.state in (BotState.PAPER, BotState.LIVE) and run is not None
    if not running:
        return {"open": False, "close": held_side is not None, "code": "bot_not_running"}
    return {"open": True, "close": held_side is not None, "code": ""}


def _s(value) -> str | None:
    if value is None:
        return None
    return f"{Decimal(value).normalize():f}"
