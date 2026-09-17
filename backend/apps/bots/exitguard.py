"""The exit this platform takes on its own, when the venue's did not.

**Why it exists.** Under either policy the *intent* is that something ends a
losing trade: ``PROTECTED`` rests a stop and a target at the exchange,
``STRATEGY_MANAGED`` rests a safety net when one was configured. Both of those
are orders sent to somebody else's matching engine, and an order that was
rejected, silently dropped, cancelled by the venue, emulated by an adapter that
never re-armed it, or lost with the position when a leg was re-read looks
exactly like an order that is quietly waiting. There is no callback that says
"your stop is gone". The position simply keeps running.

So the platform watches the level itself. On every confirmed bar, before the
script is even asked what it wants, the held trade's own stop and target are
resolved from the percentages that were recorded with it and compared against
the bar's range. A level that was reached and a position that is still open is
an **exit signal** — the platform's own, owing nothing to the exchange — and it
goes out as an ordinary ``CLOSE`` down the one order path (``translate``,
``RiskGate``, ``route_close``, the fan-out), reaching every connected account
exactly as any other close does.

**It cannot invent a level.** Everything here comes off the ``Trade`` row the
platform wrote when it opened the position: the side, the admin entry price,
``sl_pct``/``tp_pct``, ``safety_net_pct``, the leverage and the Q5a basis that
was in force. A trade with nothing recorded is a trade with nothing to enforce,
and the guard says so rather than choosing a number for it.

**It is the backtest's rule, not a second one.** ``_Engine._check_exits``
already closes a simulated position on the bar that reaches its stop or target,
stop first when one bar touches both. This is the same comparison against the
same levels, resolved through the same ``sltp.resolve``, so switching the guard
on moves live *towards* the report rather than away from it. What it is not is
a tick-accurate fill: a 30m bar is seen once, at its close, so the guard
reports the level as the exit basis and the fan-out fills at market — the gap
between the two is slippage and is recorded like any other.

**It never opens, amends, or reverses anything.** One verb, one direction: out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from apps.bots.config import bot_settings
from apps.exchanges.base import Side as ExchangeSide
from apps.pine.bar import Bar

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

#: Reason codes. Short and stable — they are written onto ``BotAction.reason``,
#: read by ``narrate.py`` and shown in six locales, so they are keys and not
#: sentences.
#: The idempotency scope for an action the guard raised. Keeps a guard close
#: from ever colliding with the bar-driven close of the same bar.
SCOPE = "guard"

STOP = "stop"
TARGET = "target"
SAFETY_NET = "safety net"


@dataclass(frozen=True, slots=True)
class Breach:
    """A level this bar reached while the position was still open."""

    #: ``STOP`` / ``TARGET`` / ``SAFETY_NET``.
    kind: str
    #: The price the platform was protecting at.
    level: Decimal
    #: The extreme of the bar that reached it — the high for a target on a
    #: long, the low for its stop. Recorded so the action log can show what the
    #: decision was made on rather than only what it decided.
    reached: Decimal

    @property
    def reason(self) -> str:
        return f"exit signal: {self.kind}"


def enabled() -> bool:
    """Whether the guard may act. On by default — an unenforced stop is not one."""
    return bool(bot_settings().get("EXIT_GUARD", True))


def levels(
    *,
    side: str,
    entry: Decimal | None,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
    safety_net_pct: Decimal | None,
    leverage: int,
    basis: str,
) -> tuple[Decimal | None, Decimal | None, bool]:
    """``(stop, target, the stop is the safety net)`` for one trade.

    ``sltp.resolve`` is asked for the prices and nothing else, which is why the
    money arguments are zero: ``margin`` and ``notional`` scale the *loss* and
    *profit* figures on the returned line and have no part in either price. The
    guard is about where the price is, and every account's is the same (§5).

    The safety net stands in for a missing stop and never beside one —
    ``protection.Protection.resting_sl`` is the same precedence, and two stops
    on one position is the state Q5d exists to prevent.
    """
    from apps.trading import sltp

    if entry is None or entry <= ZERO:
        return None, None, False
    stop_pct = sl_pct if sl_pct is not None else safety_net_pct
    net_engaged = sl_pct is None and safety_net_pct is not None
    if stop_pct is None and tp_pct is None:
        return None, None, False
    line = sltp.resolve(
        side=ExchangeSide(side),
        entry=Decimal(entry),
        leverage=max(1, int(leverage or 1)),
        margin=ZERO,
        notional=ZERO,
        sl_pct=stop_pct,
        tp_pct=tp_pct,
        reading=basis,
    )
    return line.stop_price, line.take_profit_price, net_engaged


def check(
    *,
    side: str,
    entry: Decimal | None,
    bar: Bar,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
    safety_net_pct: Decimal | None,
    leverage: int,
    basis: str,
) -> Breach | None:
    """Whether this bar took the position past a level it was meant to stop at.

    **The stop wins an ambiguous bar.** One bar that touches both is the case
    with no honest answer without tick data, and the pessimistic reading is the
    one the backtest states in its own assumptions — so both sides of the
    platform give the same answer to the same bar.
    """
    stop, target, net = levels(
        side=side,
        entry=entry,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        safety_net_pct=safety_net_pct,
        leverage=leverage,
        basis=basis,
    )
    long = side == ExchangeSide.LONG.value
    if stop is not None:
        hit = bar.low <= stop if long else bar.high >= stop
        if hit:
            return Breach(
                kind=SAFETY_NET if net else STOP,
                level=stop,
                reached=bar.low if long else bar.high,
            )
    if target is not None:
        hit = bar.high >= target if long else bar.low <= target
        if hit:
            return Breach(kind=TARGET, level=target, reached=bar.high if long else bar.low)
    return None


def for_trade(trade, bar: Bar) -> Breach | None:
    """``check`` against a stored ``Trade`` row.

    Reads the trade's *own* recorded basis and policy rather than today's
    settings, for the same reason ``Trade.sltp_basis`` exists: a percentage
    recorded under one reading and enforced under another is a stop somewhere
    nobody put it.
    """
    if trade is None or not enabled():
        return None
    return check(
        side=trade.side,
        entry=trade.admin_entry_price,
        bar=bar,
        sl_pct=trade.sl_pct,
        tp_pct=trade.tp_pct,
        safety_net_pct=trade.safety_net_pct,
        leverage=trade.leverage,
        basis=trade.sltp_basis or "price",
    )
