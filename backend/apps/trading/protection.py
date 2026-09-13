"""What bounds a trade's loss — and which of the two ways this platform allows.

Until Q37 there was one answer: every order carries a stop loss *and* a take
profit, both resolved into trigger prices and sent to the exchange. That rule
exists because §4 fans an entry at leverage across accounts holding partner
capital, and a leg with nothing resting at the venue is one process death away
from an unbounded loss on money that is not the admin's.

Q37 does not retire that reasoning; it names the second way of satisfying it.
A strategy that decides its own exits — a structure break, a trailing rule, a
reversal, a target it computed on the bar — cannot express that exit as a pair
of percentages fixed at entry, and forcing it to declare one anyway produced
the worst of both: a stop nobody chose, sitting at the venue, firing ahead of
the logic that was supposed to close the trade.

So protection becomes a **policy**, with both branches built:

``PROTECTED``
    The rule as it was. Both percentages required, refused before any account
    is touched. This is still the default for every bot and every manual order,
    and every row that existed before Q37 is one.

``STRATEGY_MANAGED``
    The exit is a signal, not a level. Percentages are optional; whatever is
    supplied is still sent to the exchange, and what is not supplied is not
    invented. The strategy's ``EXIT_BUY``/``EXIT_SELL`` is what closes the
    trade, and it does so at any PnL — including a loss, which is the whole
    point and the thing a fixed stop cannot be told.

**The gap that policy opens, and the field that closes it.** A strategy-managed
position is protected by a *process*: the supervisor evaluating bars, or the
webhook that can reach us. A crash, a deploy, a severed feed, an expired
credential — and the position is live at leverage with nothing resting at the
venue to end it. ``safety_net_pct`` is the answer and is deliberately not a
stop loss: it is set far enough out that the strategy's own exit always gets
there first, and it exists so that *something* is resting on the exchange when
this platform is not there to act. It applies only when no real stop was given
— ``resting_sl`` is where that precedence lives, in one place, so no caller has
to remember it.

Nothing here decides *when* to exit. This module answers "what, if anything,
rests at the exchange", and the answer is the same for every account (§5) —
only the dollar size differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from apps.core.money import D


class ExitPolicy(StrEnum):
    """How a trade is allowed to end. Stored per trade and per bot."""

    #: Both percentages required; they are the exit.
    PROTECTED = "protected"
    #: The strategy's own exit signal is the exit. Percentages optional.
    STRATEGY_MANAGED = "strategy_managed"


DEFAULT_POLICY = ExitPolicy.PROTECTED

#: A stop past 100% is a price below zero; a take profit past it is only an
#: ambitious target. The same asymmetry ``order_views._percent`` has always had,
#: moved here so the bot and webhook paths inherit it rather than re-deriving it.
_CEILINGS: dict[str, Decimal | None] = {
    "sl_pct": D("100"),
    "tp_pct": None,
    "safety_net_pct": D("100"),
}


class ProtectionRequired(ValueError):
    """A ``PROTECTED`` order arrived without both percentages.

    A ``ValueError`` subclass because that is what every existing caller
    already catches — ``order_views`` turns it into a 400 and ``open_trade``
    lets it abort the whole fan-out, which is the correct blast radius: "some
    accounts opened unprotected" is the outcome the rule exists to prevent.
    """

    code = "protection_required"


class ProtectionInvalid(ValueError):
    """A percentage that is a typo rather than an instruction."""

    code = "protection_invalid"


def parse_policy(value: object, *, default: ExitPolicy = DEFAULT_POLICY) -> ExitPolicy:
    """A policy from the wire. Unknown values are refused, never defaulted.

    Defaulting an unrecognised policy to ``PROTECTED`` would be the safe side of
    the wrong question: a caller that meant ``strategy_managed`` and misspelled
    it would get its exits silently overridden by a stop it never chose.
    """
    if value in (None, ""):
        return default
    try:
        return ExitPolicy(str(value))
    except ValueError:
        options = ", ".join(p.value for p in ExitPolicy)
        raise ProtectionInvalid(f"unknown exit policy {value!r} — one of: {options}") from None


@dataclass(frozen=True, slots=True)
class Protection:
    """The resolved answer, for one trade, identical across every account.

    Frozen and computed once at the top of the routing path so that the
    exchange-facing numbers and the numbers written into history cannot drift
    apart: ``resting_sl`` is read by the executor *and* persisted on the trade.
    """

    policy: ExitPolicy
    #: What was asked for. ``None`` under ``STRATEGY_MANAGED`` means "the
    #: strategy will say when", not "nobody filled the box in".
    sl_pct: Decimal | None = None
    tp_pct: Decimal | None = None
    #: The disaster stop. Never an exit the strategy plans around.
    safety_net_pct: Decimal | None = None

    @property
    def resting_sl(self) -> Decimal | None:
        """The stop that actually goes to the exchange.

        The net is a fallback, not an addition: two stops on one position is
        the state Q5d exists to prevent, and the narrower of the two would fire
        first anyway, which would make the net a stop loss by another name.
        """
        return self.sl_pct if self.sl_pct is not None else self.safety_net_pct

    @property
    def resting_tp(self) -> Decimal | None:
        return self.tp_pct

    @property
    def net_engaged(self) -> bool:
        """True when what rests at the venue is the net rather than a stop."""
        return self.sl_pct is None and self.safety_net_pct is not None

    @property
    def unprotected(self) -> bool:
        """Nothing at all rests at the exchange for this trade.

        Legal under ``STRATEGY_MANAGED`` and reported everywhere it is true —
        the positions panel, the trade log and the bot page all say so. It is
        an accepted risk, not a hidden one.
        """
        return self.resting_sl is None and self.resting_tp is None

    def as_dict(self) -> dict:
        return {
            "exit_policy": self.policy.value,
            "sl_pct": _s(self.sl_pct),
            "tp_pct": _s(self.tp_pct),
            "safety_net_pct": _s(self.safety_net_pct),
            "resting_sl_pct": _s(self.resting_sl),
            "resting_tp_pct": _s(self.resting_tp),
            "net_engaged": self.net_engaged,
            "unprotected": self.unprotected,
        }


def _s(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _check(name: str, value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    value = D(value)
    if value <= 0:
        raise ProtectionInvalid(f"{name} must be greater than zero")
    ceiling = _CEILINGS.get(name)
    if ceiling is not None and value > ceiling:
        raise ProtectionInvalid(f"{name} must not exceed {ceiling:g}")
    return value


def net_reachable(safety_net_pct: Decimal, leverage: int) -> bool:
    """Whether a net that far out can ever fire before liquidation does.

    A safety net is meant to be wide — far enough that the strategy's own exit
    always gets there first. Past liquidation it stops being wide and starts
    being decorative: the position is gone before the trigger is reached, so
    the operator believes something is resting at the venue when nothing
    useful is.

    Liquidation sits ``1/leverage`` away in *price*, so at 10x a 20% price stop
    is already 10% past it. Under the margin basis (Q5a) the same number means
    a price move of ``pct/leverage``, which is always inside — the basis is
    read here rather than assumed, because the answer genuinely differs.

    ``executor``'s per-leg ``REJECT_SL_BEYOND_LIQUIDATION`` guard catches this
    too and would refuse the fan-out. That is the backstop; this is so the
    operator is told at the form, where it is a number they can change, rather
    than by an entry that silently never opens.
    """
    from apps.trading.sltp import basis

    if leverage <= 0:
        return True
    move = D(safety_net_pct)
    if basis() == "margin":
        move = move / D(leverage)
    return move < D("100") / D(leverage)


def resolve(
    *,
    policy: ExitPolicy | str | None = None,
    sl_pct: Decimal | None = None,
    tp_pct: Decimal | None = None,
    safety_net_pct: Decimal | None = None,
    leverage: int | None = None,
) -> Protection:
    """Validate one trade's protection, or refuse it.

    The single door. ``order_views``, ``services.route_open``, the bot
    translator and the webhook all come through here, so "what counts as a
    routable order" is one function rather than four agreeing conventions.
    """
    resolved = parse_policy(policy)
    sl_pct = _check("sl_pct", sl_pct)
    tp_pct = _check("tp_pct", tp_pct)
    safety_net_pct = _check("safety_net_pct", safety_net_pct)

    if resolved is ExitPolicy.PROTECTED:
        missing = [
            label
            for label, value in (("stop loss", sl_pct), ("take profit", tp_pct))
            if value is None
        ]
        if missing:
            raise ProtectionRequired(
                f"an order under the protected exit policy must carry both a stop loss "
                f"and a take profit; missing: {', '.join(missing)}. Set "
                f"exit_policy=\"{ExitPolicy.STRATEGY_MANAGED.value}\" if the strategy "
                f"closes this trade itself."
            )
        # The net cannot engage while a real stop exists, so it is dropped
        # rather than stored: a bot toggled back to PROTECTED keeps its net on
        # the *bot*, and the trade records what was actually true of the trade.
        safety_net_pct = None

    if (
        safety_net_pct is not None
        and leverage is not None
        and sl_pct is None
        and not net_reachable(safety_net_pct, leverage)
    ):
        raise ProtectionInvalid(
            f"a {safety_net_pct:g}% safety net sits past liquidation at {leverage}x, so "
            f"it could never fire — at this leverage the position is gone first. Use "
            f"less than {D('100') / D(leverage):.2f}%, or lower the leverage."
        )

    if (
        safety_net_pct is not None
        and sl_pct is not None
        and safety_net_pct <= sl_pct
    ):
        # Reachable only by an explicit pair under STRATEGY_MANAGED. The stop
        # wins by `resting_sl` and the net would never fire, so saying so beats
        # storing a number that does nothing.
        raise ProtectionInvalid(
            "the safety net must sit further out than the stop loss — it is the "
            "disaster stop for when this platform is not running, not a second exit"
        )

    return Protection(
        policy=resolved,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        safety_net_pct=safety_net_pct,
    )
