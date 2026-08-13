"""SL/TP maths — both readings of questions.md Q5a, side by side.

The admin has not yet chosen between them, so both are implemented and
``TRADING["SLTP_BASIS"]`` selects one. ``compare_bases`` renders both at once
and is what the risk endpoint uses so the choice can be made against real
numbers rather than prose.

Q5a in one line: at 10x with 99% of the account as margin, a 2% *price* stop
loses ~20% of the account, and liquidation sits ~10% away — a 2% *margin* stop
is a 0.2% price move, twenty times tighter for the same number in the box.

(Liquidation distance is 1/leverage — 10% at 10x, 20% at 5x — and does not
depend on how much of the account is committed as margin. An earlier version of
this docstring said ~1%; the correction is recorded in questions.md and the
numbers are asserted in tests/test_sltp.py.)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from apps.core.money import D, quantize_price
from apps.exchanges.base import Side


class SLTPRejection(Exception):
    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.code = code


@dataclass(frozen=True, slots=True)
class RiskLine:
    """One reading of a percentage, fully resolved into money."""

    basis: str
    stop_price: Decimal | None
    take_profit_price: Decimal | None
    loss_at_stop: Decimal
    loss_pct_of_account: Decimal
    profit_at_tp: Decimal
    price_move_pct: Decimal
    reachable: bool
    note: str = ""


def basis() -> str:
    return settings.TRADING["SLTP_BASIS"]


def _signed(side: Side, entry: Decimal, move_pct: Decimal, *, adverse: bool) -> Decimal:
    """Price that is ``move_pct`` away from entry, in the losing or winning direction."""
    direction = D("-1") if (side is Side.LONG) == adverse else D("1")
    return entry * (D("1") + direction * move_pct / D("100"))


def liquidation_price(side: Side, entry: Decimal, leverage: int) -> Decimal:
    """Simplified liquidation: ignores maintenance margin, fees and funding.

    Real adapters report the exchange's number; this is for the pre-trade guard
    and the risk preview, where being slightly conservative is the safe error.
    """
    move = entry / D(leverage)
    return entry - move if side is Side.LONG else entry + move


def resolve(
    *,
    side: Side,
    entry: Decimal,
    leverage: int,
    margin: Decimal,
    notional: Decimal,
    sl_pct: Decimal | None,
    tp_pct: Decimal | None,
    reading: str,
    price_tick: Decimal = D("0.01"),
) -> RiskLine:
    """Turn a percentage into prices and money under one reading.

    reading="price"  -> the percentage is a move in the underlying price
    reading="margin" -> the percentage is a fraction of the committed margin
    """
    entry, margin, notional = D(entry), D(margin), D(notional)

    def move_for(p: Decimal) -> Decimal:
        if reading == "price":
            return p
        if reading == "margin":
            # Losing p% of margin means a price move of p% / leverage.
            return p / D(leverage)
        raise ValueError(f"unknown SL/TP basis: {reading!r}")

    stop_price = tp_price = None
    loss = profit = D("0")
    move_pct = D("0")

    if sl_pct is not None:
        move_pct = move_for(D(sl_pct))
        stop_price = quantize_price(_signed(side, entry, move_pct, adverse=True), price_tick)
        loss = notional * move_pct / D("100")

    if tp_pct is not None:
        tp_move = move_for(D(tp_pct))
        tp_price = quantize_price(_signed(side, entry, tp_move, adverse=False), price_tick)
        profit = notional * tp_move / D("100")

    liq = liquidation_price(side, entry, leverage)
    if stop_price is None:
        reachable, note = True, ""
    elif side is Side.LONG:
        reachable = stop_price > liq
        note = "" if reachable else "stop sits below liquidation — it can never trigger"
    else:
        reachable = stop_price < liq
        note = "" if reachable else "stop sits above liquidation — it can never trigger"

    account = margin / D(settings.TRADING["BALANCE_FRACTION"]) if margin else D("1")
    return RiskLine(
        basis=reading,
        stop_price=stop_price,
        take_profit_price=tp_price,
        loss_at_stop=loss,
        loss_pct_of_account=(loss / account * D("100")) if account else D("0"),
        profit_at_tp=profit,
        price_move_pct=move_pct,
        reachable=reachable,
        note=note,
    )


def compare_bases(**kwargs) -> dict[str, RiskLine]:
    """Both readings of Q5a for the same inputs. Powers the risk preview UI."""
    return {
        "price": resolve(reading="price", **kwargs),
        "margin": resolve(reading="margin", **kwargs),
    }


def resolve_active(**kwargs) -> RiskLine:
    """The configured reading, with the liquidation guard applied."""
    line = resolve(reading=basis(), **kwargs)
    if settings.TRADING["REJECT_SL_BEYOND_LIQUIDATION"] and not line.reachable:
        raise SLTPRejection(line.note, code="sl_beyond_liquidation")
    return line


def anchor_price(*, admin_entry: Decimal, own_entry: Decimal) -> Decimal:
    """Q5b/Q5c: which fill price a leg's SL/TP percentage is measured from."""
    reference = settings.TRADING["SLTP_REFERENCE"]
    if reference == "own_fill":
        return D(own_entry)
    if reference == "admin_price":
        return D(admin_entry)
    raise ValueError(f"unknown SLTP_REFERENCE: {reference!r}")


def pct_from_drag(
    *, side: Side, admin_entry: Decimal, dragged_price: Decimal, leverage: int
) -> Decimal:
    """Q5c: convert a chart drag (an absolute price) back into a percentage.

    Always measured against the admin's own entry, so the resulting percentage
    can be re-applied to each account's own fill under
    ``SLTP_REFERENCE="own_fill"``. The returned percentage is expressed in the
    configured basis, so it round-trips through ``resolve()`` unchanged.
    """
    admin_entry, dragged_price = D(admin_entry), D(dragged_price)
    if admin_entry <= 0:
        raise SLTPRejection("no admin entry price to measure against", code="no_entry")
    move = (admin_entry - dragged_price) if side is Side.LONG else (dragged_price - admin_entry)
    price_pct = move / admin_entry * D("100")
    # resolve() divides a margin-basis percentage by leverage to get the price
    # move, so multiply here to invert it.
    return price_pct * D(leverage) if basis() == "margin" else price_pct
