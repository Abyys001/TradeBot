"""The four verbs, and the one shape they arrive in.

``BUY`` · ``SELL`` · ``EXIT_BUY`` · ``EXIT_SELL`` — a vocabulary rather than a
free-text field, because what arrives here moves partner capital and "close
long" spelled six ways is six chances to route the wrong one. Everything a
strategy could say is one of these four plus an optional protection override;
anything else is refused with its own reason.

**An exit is a trading instruction, not a notice.** ``EXIT_BUY`` means "close
the long", full stop — at whatever PnL happens to be true when it lands, in
profit or in loss, whether or not a percentage target was ever configured. That
is the whole of Q37 on this side of the wire: the platform does not consult a
threshold before honouring it, and there is no code path where an exit is
recorded and not acted on.

**What this module deliberately cannot express.** No quantity, no price, no
account, no leverage. Those are the platform's (Q20/Q21, §5) and an external
source has no more right to set them than a Pine script does — the same
reasoning that keeps ``qty`` off ``StrategyIntent``, applied to a sender this
platform does not control at all. A payload carrying them is refused by name
rather than ignored, so a strategy author finds out at the first test message
instead of wondering why their sizing never took.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from apps.pine.intent import Side, StrategyIntent


class Verb(StrEnum):
    """What the strategy is asking for. Case-insensitive on the wire."""

    BUY = "BUY"
    SELL = "SELL"
    EXIT_BUY = "EXIT_BUY"
    EXIT_SELL = "EXIT_SELL"

    @property
    def is_exit(self) -> bool:
        return self in (Verb.EXIT_BUY, Verb.EXIT_SELL)

    @property
    def side(self) -> Side:
        """The side this verb is *about* — the one it opens, or the one it closes."""
        return Side.LONG if self in (Verb.BUY, Verb.EXIT_BUY) else Side.SHORT


#: Accepted spellings, so a strategy author is not made to guess. Everything
#: maps onto exactly one verb; nothing maps onto two.
ALIASES: dict[str, Verb] = {
    "BUY": Verb.BUY,
    "LONG": Verb.BUY,
    "ENTER_LONG": Verb.BUY,
    "SELL": Verb.SELL,
    "SHORT": Verb.SELL,
    "ENTER_SHORT": Verb.SELL,
    "EXIT_BUY": Verb.EXIT_BUY,
    "EXIT_LONG": Verb.EXIT_BUY,
    "CLOSE_LONG": Verb.EXIT_BUY,
    "EXIT_SELL": Verb.EXIT_SELL,
    "EXIT_SHORT": Verb.EXIT_SELL,
    "CLOSE_SHORT": Verb.EXIT_SELL,
}

#: Fields an external source may not set, and why. Refused by name — a silently
#: ignored ``qty`` is a strategy author who thinks sizing is theirs.
FORBIDDEN: dict[str, str] = {
    "qty": "position size is the platform's (§5: 99% of each account's own balance)",
    "quantity": "position size is the platform's (§5: 99% of each account's own balance)",
    "size": "position size is the platform's (§5: 99% of each account's own balance)",
    "amount": "position size is the platform's (§5: 99% of each account's own balance)",
    "price": "entry price is the exchange's; this platform routes market orders",
    "limit_price": "a webhook signal routes at market — a resting limit has no bar to expire on",
    "leverage": "leverage is set on the bot and is identical across accounts (§4)",
    "account": "a signal reaches every eligible account; it cannot name one (§4)",
    "account_id": "a signal reaches every eligible account; it cannot name one (§4)",
}


class SignalRejected(ValueError):
    """The payload is not a signal this platform will act on."""

    def __init__(self, detail: str, code: str = "bad_payload") -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True, slots=True)
class Signal:
    """One parsed instruction. Pure data — nothing has been routed yet."""

    verb: Verb
    symbol: str
    #: The sender's own id for this signal. When two arrive with the same one,
    #: the second is a duplicate — TradingView retries, and so does every other
    #: alert system worth using. Defaults to a digest of the payload.
    signal_id: str = ""
    #: Optional per-signal protection override. Absent means "use the bot's".
    sl_pct: Decimal | None = None
    tp_pct: Decimal | None = None
    #: Free text the sender wants in the journal. Never parsed for meaning.
    comment: str = ""

    def as_intent(self, *, bar_time: int) -> StrategyIntent:
        """The same object a Pine bar produces, so the same translator runs.

        This is the join. An exit becomes ``desired_side = None``, which
        ``translate.plan`` turns into a ``CLOSE`` against whatever the exchange
        says is held — no PnL is consulted anywhere on that path, and it is the
        identical path a ``strategy.close()`` takes.

        ``EXIT_BUY`` while short is **not** an instruction to close the short:
        the verb names the side it acts on, and honouring it against the other
        one would turn a stale duplicate into an unwanted flatten. The caller
        (``service.apply``) holds the position to check that against; here the
        intent simply says flat, and the caller refuses before it is used.
        """
        return StrategyIntent(
            bar_time=bar_time,
            symbol=self.symbol,
            desired_side=None if self.verb.is_exit else self.verb.side,
            sl_pct=self.sl_pct,
            tp_pct=self.tp_pct,
            reason=(self.comment or self.verb.value)[:200],
            entry_signal=not self.verb.is_exit,
        )


def _decimal(raw: object, field: str) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise SignalRejected(f"{field} is not a number: {raw!r}") from None


def parse(body: dict, *, expected_symbol: str) -> Signal:
    """A JSON body to a ``Signal``, or a refusal naming what was wrong.

    ``expected_symbol`` is the bot's own pair. A signal for anything else is
    refused rather than retargeted: a source misconfigured onto the wrong chart
    would otherwise open a BTC position from an ETH strategy, and the platform
    has no way to tell that from a deliberate change.
    """
    if not isinstance(body, dict):
        raise SignalRejected("the body must be a JSON object")

    present = [key for key in FORBIDDEN if key in body]
    if present:
        reasons = "; ".join(f"{key}: {FORBIDDEN[key]}" for key in present)
        raise SignalRejected(
            f"a signal may not set {', '.join(present)} — {reasons}",
            code="forbidden_field",
        )

    raw_action = body.get("action") or body.get("signal") or body.get("side")
    if raw_action in (None, ""):
        raise SignalRejected("no action — send one of BUY, SELL, EXIT_BUY, EXIT_SELL")
    verb = ALIASES.get(str(raw_action).strip().upper().replace("-", "_").replace(" ", "_"))
    if verb is None:
        raise SignalRejected(
            f"unknown action {raw_action!r} — one of: "
            f"{', '.join(v.value for v in Verb)}",
            code="unknown_action",
        )

    symbol = str(body.get("symbol") or body.get("ticker") or "").strip().upper()
    if not symbol:
        raise SignalRejected("no symbol")
    if symbol != expected_symbol.upper():
        raise SignalRejected(
            f"this source is bound to {expected_symbol} and the signal names {symbol} "
            "— a signal is never retargeted onto another pair",
            code="symbol_mismatch",
        )

    return Signal(
        verb=verb,
        symbol=expected_symbol,
        signal_id=str(body.get("id") or body.get("signal_id") or "").strip()[:120],
        sl_pct=_decimal(body.get("sl_pct"), "sl_pct"),
        tp_pct=_decimal(body.get("tp_pct"), "tp_pct"),
        comment=str(body.get("comment") or body.get("note") or "")[:200],
    )
