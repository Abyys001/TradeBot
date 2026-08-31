"""Declarative intent → the imperative calls that already exist.

Pine says "I should be long." The platform's API says ``route_open(...)``. This
module is the whole of the difference, and it is deliberately small: everything
below ``route_*`` — sizing, the fan-out and its deadline, account isolation,
``NEVER_SENT_CODES`` reconciliation, the halt, per-account history — is reused
untouched. **If a diff here ever adds a second order path it is wrong regardless
of what it does.**

Four rules carry the file:

  **A reversal is two actions, sequenced, never concurrent.** Close, confirm
  flat, then open. Fired together at a venue that nets positions, the result is
  a doubled position or a cancelled one depending on which request arrived
  first — and which one that is, is not something this side gets to decide.

  **Actual state comes from the exchange, not this database.** ``CLAUDE.md`` is
  explicit about it and ``possync`` exists because of it. The diff runs *after*
  ``reconcile_open_trade``.

  **A failed leg is not proof nothing happened.** ``accounts_in_open_trades``
  already treats an unconfirmed leg as possibly holding, and the bot inherits
  that asymmetry: such an account is reported **"sat out"** (Q22), never as a
  failure, and is never re-entered.

  **Idempotency is a database constraint.** ``(run, bar_time, action_type)`` is
  written as a ``BotAction`` with a ``UNIQUE`` key *before* dispatch. Application
  logic alone does not survive a restart in the middle of a fan-out, because at
  that moment there is no application logic running.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from asgiref.sync import sync_to_async

from apps.bots.models import ActionType, Bot, BotAction, BotRun
from apps.exchanges.base import MarketType, OrderType
from apps.exchanges.base import Side as ExchangeSide
from apps.pine.intent import Side, StrategyIntent

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Action:
    """One call the bot wants to make. Pure data — nothing here has run yet."""

    type: str
    side: Side | None = None
    sl_pct: Decimal | None = None
    tp_pct: Decimal | None = None
    reason: str = ""
    trade_id: int | None = None
    #: True for the close half of a reversal, so the dispatcher knows it must
    #: confirm flat before the open that follows it.
    is_reversal_leg: bool = False

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "side": self.side.value if self.side else None,
            "sl_pct": str(self.sl_pct) if self.sl_pct is not None else None,
            "tp_pct": str(self.tp_pct) if self.tp_pct is not None else None,
            "reason": self.reason,
            "trade_id": self.trade_id,
        }


@dataclass(frozen=True, slots=True)
class Held:
    """What the bot is actually holding, as read back from the exchange."""

    trade_id: int | None
    side: Side | None
    sl_pct: Decimal | None
    tp_pct: Decimal | None

    @property
    def flat(self) -> bool:
        return self.side is None


FLAT = Held(trade_id=None, side=None, sl_pct=None, tp_pct=None)


def plan(
    *,
    intent: StrategyIntent,
    held: Held,
    default_sl: Decimal | None,
    default_tp: Decimal | None,
) -> list[Action]:
    """The diff, as a pure function. The table in ``bot-mode.md`` §5.1, in code.

    Pure so it can be tested exhaustively without a database, an exchange, or a
    clock — every row of that table is a two-line test.
    """
    # Q21: a percent `strategy.exit` in the script wins for this trade; the
    # bot's configured pair is the fallback, not the other way round.
    wanted_sl = intent.sl_pct if intent.sl_pct is not None else default_sl
    wanted_tp = intent.tp_pct if intent.tp_pct is not None else default_tp
    desired = intent.desired_side

    if desired is None:
        if held.flat:
            return []
        return [
            Action(
                type=ActionType.CLOSE,
                reason=intent.reason or "flat",
                trade_id=held.trade_id,
            )
        ]

    if held.flat:
        return [
            Action(
                type=ActionType.OPEN,
                side=desired,
                sl_pct=wanted_sl,
                tp_pct=wanted_tp,
                reason=intent.reason or f"enter {desired.value}",
            )
        ]

    if held.side is desired:
        if held.sl_pct == wanted_sl and held.tp_pct == wanted_tp:
            return []
        return [
            Action(
                type=ActionType.AMEND,
                side=desired,
                sl_pct=wanted_sl,
                tp_pct=wanted_tp,
                reason=intent.reason or "sl/tp changed",
                trade_id=held.trade_id,
            )
        ]

    # A reversal. Two actions, and the dispatcher runs them in this order with a
    # confirmation between them — never as one concurrent pair.
    return [
        Action(
            type=ActionType.CLOSE,
            reason=f"reverse to {desired.value}",
            trade_id=held.trade_id,
            is_reversal_leg=True,
        ),
        Action(
            type=ActionType.OPEN,
            side=desired,
            sl_pct=wanted_sl,
            tp_pct=wanted_tp,
            reason=intent.reason or f"reverse to {desired.value}",
        ),
    ]


def idempotency_key(run_id: int, bar_time: int, action_type: str, ordinal: int = 0) -> str:
    """``(run, bar, action type)`` — the tuple ``bot-plan.md`` §7 names.

    ``ordinal`` separates the two halves of a reversal, which share the bar and
    would otherwise collide on the close and never place the open.
    """
    suffix = f":{ordinal}" if ordinal else ""
    return f"{run_id}:{bar_time}:{action_type}{suffix}"


@sync_to_async
def read_held(run: BotRun) -> Held:
    """What this bot run is holding, from the platform's record of its own trades.

    The record is only trustworthy *after* ``reconcile_open_trade`` has run —
    the caller is responsible for that, and ``supervisor.py`` does it on every
    bar before calling this.
    """
    from apps.trading.models import Trade, TradeStatus

    trade = (
        Trade.objects.filter(bot_run=run, status=TradeStatus.OPEN).order_by("-id").first()
    )
    if trade is None:
        return FLAT
    return Held(
        trade_id=trade.id,
        side=Side(trade.side),
        sl_pct=trade.sl_pct,
        tp_pct=trade.tp_pct,
    )


@sync_to_async
def claim(run: BotRun, bar_time: int, action: Action, ordinal: int) -> BotAction | None:
    """Write the action down *before* dispatching it.

    Returns ``None`` when the key already exists, which means this action was
    already dispatched — by this process before a restart, or by another. The
    unique constraint is doing the work; the ``get_or_create`` is only how the
    result is read back.
    """
    key = idempotency_key(run.id, bar_time, action.type, ordinal)
    row, created = BotAction.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "run": run,
            "bar_time": bar_time,
            "action_type": action.type,
            "reason": action.reason[:200],
            "intent": action.as_dict(),
        },
    )
    return row if created else None


@sync_to_async
def settle(row: BotAction, *, ok: bool, result: dict, error: str = "", trade_id=None) -> None:
    from django.utils import timezone

    row.ok = ok
    row.result = result
    row.error = error[:2000]
    row.settled_at = timezone.now()
    if trade_id is not None:
        row.trade_id = trade_id
    row.save(update_fields=["ok", "result", "error", "settled_at", "trade"])


@sync_to_async
def mark_dispatched(row: BotAction) -> None:
    from django.utils import timezone

    row.dispatched_at = timezone.now()
    row.save(update_fields=["dispatched_at"])


@sync_to_async
def _link_trade(trade, run: BotRun) -> None:
    """Stamp the bot run onto the trade it just produced.

    This is what lets §8 history say which trades a bot made without a parallel
    history table to keep in step. The manual path leaves it null and is
    unchanged.
    """
    trade.bot_run = run
    trade.save(update_fields=["bot_run"])


async def dispatch(
    *, bot: Bot, run: BotRun, bar_time: int, actions: list[Action]
) -> list[dict]:
    """Run the plan through ``services.route_*``. One fan-out at a time.

    Sequential by construction: a reversal's close must confirm flat before its
    open goes out, and even without a reversal there is never a reason for one
    bot to have two fan-outs in the air — the second would contend with the
    first for the same accounts.
    """
    from apps.trading import services

    outcomes: list[dict] = []
    for ordinal, action in enumerate(actions):
        row = await claim(run, bar_time, action, ordinal)
        if row is None:
            logger.info(
                "bot %s: action %s at bar %s already recorded — not re-sending",
                bot.id,
                action.type,
                bar_time,
                extra={"category": "BOT"},
            )
            outcomes.append({"action": action.as_dict(), "skipped": "already_dispatched"})
            continue

        await mark_dispatched(row)
        try:
            outcome = await _route(bot=bot, run=run, action=action, services=services)
        except Exception as exc:  # noqa: BLE001 - the bot must never die on one action
            await settle(row, ok=False, result={}, error=str(exc))
            outcomes.append({"action": action.as_dict(), "error": str(exc)})
            # A failed close in a reversal must not be followed by the open —
            # that is how a position gets doubled instead of flipped.
            if action.is_reversal_leg:
                logger.error(
                    "bot %s: the close half of a reversal failed (%s) — the open is "
                    "not being sent",
                    bot.id,
                    exc,
                    extra={"category": "BOT"},
                )
                break
            continue

        await settle(
            row,
            ok=bool(outcome.get("ok")),
            result=outcome,
            trade_id=outcome.get("trade_id"),
        )
        outcomes.append({"action": action.as_dict(), **outcome})

        if action.is_reversal_leg and not outcome.get("flat"):
            logger.error(
                "bot %s: the close half of a reversal did not leave every account flat "
                "— the open is not being sent",
                bot.id,
                extra={"category": "BOT"},
            )
            break
    return outcomes


async def _route(*, bot: Bot, run: BotRun, action: Action, services) -> dict:
    """The one place a bot touches the order path. Nothing else calls ``route_*``."""
    if action.type == ActionType.OPEN:
        trade, result = await services.route_open(
            symbol=bot.symbol,
            side=ExchangeSide(action.side.value),
            market=MarketType(bot.market),
            order_type=OrderType.MARKET,
            leverage=bot.leverage,
            sl_pct=action.sl_pct,
            tp_pct=action.tp_pct,
            source="bot",
        )
        if trade is None:
            # No account is both eligible and opted into bot trading right now
            # — either every one is already in a trade, or none has switched
            # bot trading on. Q22: "sat out", not a failure — the accounts join
            # the next one (spec §6).
            return {"ok": True, "sat_out": True, "legs": []}
        await _link_trade(trade, run)
        return {
            "ok": any(leg.ok for leg in result.legs),
            "trade_id": trade.id,
            "legs": _legs(result),
            "fanout_ms": round(result.total_ms, 1),
        }

    if action.type == ActionType.AMEND:
        trade = await _trade(action.trade_id)
        if trade is None:
            return {"ok": False, "error": "the trade to amend no longer exists"}
        result = await services.route_amend(
            trade=trade, sl_pct=action.sl_pct, tp_pct=action.tp_pct
        )
        return {
            "ok": any(leg.ok for leg in result.legs),
            "trade_id": trade.id,
            "legs": _legs(result),
        }

    if action.type == ActionType.CLOSE:
        trade = await _trade(action.trade_id)
        if trade is None:
            return {"ok": True, "flat": True, "legs": []}
        result = await services.route_close(trade=trade)
        legs = _legs(result)
        return {
            "ok": all(leg["ok"] for leg in legs) if legs else True,
            "flat": await _is_flat(trade.id),
            "trade_id": trade.id,
            "legs": legs,
        }

    raise ValueError(f"unknown action type {action.type!r}")


@sync_to_async
def _trade(trade_id: int | None):
    from apps.trading.models import Trade

    if trade_id is None:
        return None
    return Trade.objects.filter(id=trade_id).first()


@sync_to_async
def _is_flat(trade_id: int) -> bool:
    """Whether the close actually left every leg flat.

    Read back rather than inferred from the fan-out result, because a leg that
    failed after its request went out may still be holding — the same asymmetry
    ``NEVER_SENT_CODES`` encodes. The open half of a reversal waits on this.
    """
    from apps.trading.models import Trade, TradeStatus

    trade = Trade.objects.filter(id=trade_id).first()
    if trade is None:
        return True
    return trade.status != TradeStatus.OPEN


def _legs(result) -> list[dict]:
    return [
        {
            "account_id": leg.account_id,
            "ok": leg.ok,
            "error": leg.error,
            "code": leg.error_code,
            "ms": round(leg.duration_ms, 1),
        }
        for leg in result.legs
    ]
