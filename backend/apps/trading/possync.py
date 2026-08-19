"""Position sync — the platform's record against what each exchange holds.

Everything else in this codebase reconciles at the moment of an action: the
entry re-reads a leg that overran its deadline, close re-reads what it could
not flatten, the positions poll settles legs whose outcome was never confirmed.
All of that answers "what happened to the request I just sent". None of it
answers the question the exchange can change on its own, with no request from
here at all:

  - **the platform says open, the exchange is flat.** A stop or a take profit
    fired, the position was liquidated, or someone flattened it in the venue's
    own app. The panel keeps drawing a position at leverage that does not
    exist, marks it to market, counts its margin in the totals, and the account
    stays blocked from the next trade (spec §5 allows one open trade each) —
    until a human notices.
  - **the platform says flat, the exchange holds a position.** A leg written
    off as ``not_filled`` on one point-in-time read, a close that reported
    success on a leg the venue had not actually flattened, or a trade retired
    while one account was unreachable. That is a live leveraged position on
    partner capital that the panel cannot see and close cannot reach, because
    close only routes to legs the platform believes in.

This module closes both gaps by asking the exchanges, on a timer, and writing
what they say. The exchange is the source of truth; the database is a cache of
it. Where the two disagree, the database is wrong.

**What it will not do.** It reads positions and it repairs records. It never
places, amends, or cancels an order — a desync is a bookkeeping fact, and the
answer to one is a corrected record plus a notice the admin has to dismiss, not
an order nobody asked for. And it only ever writes about an account whose read
*succeeded*: an exchange that did not answer proves nothing, which is the same
rule ``fanout.NEVER_SENT_CODES`` encodes on the routing side.

**What it cannot see.** It asks about the symbols the platform has records for
(the open trade, plus anything traded inside ``LOOKBACK``). A position opened by
hand on the exchange, in a pair this platform never traded, is invisible to it —
``ExchangeAdapter`` has ``get_position(symbol)`` and no way to enumerate. Adding
one means a per-venue reverse mapping from the exchange's own contract name back
to a platform symbol, which is a different change and a guessable one; this
module is built so that adding it later is a new branch in ``_read``, not a
rewrite.

Run it from the positions poll (cheap, guarded) and from
``manage.py sync_positions``, which is the loop that keeps it running when no
panel is open — a stop that fires at 3am is exactly the case a panel-driven
sweep misses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccountStatus, ConnectedAccount, Notification
from apps.engine.fanout import FanOutResult, fan_out
from apps.exchanges.base import ExchangeAdapter, Position
from apps.trading.models import Trade, TradeLeg, TradeStatus

logger = logging.getLogger(__name__)

#: Minimum spacing between sweeps, in seconds. Every open panel polls
#: ``/positions/`` and the management loop runs as well; without this the
#: exchanges would see one read per poller. Three seconds is the "few seconds"
#: this exists to deliver: fast enough that a stop firing shows up before the
#: admin can act on the stale row, slow enough to be one read per account.
SYNC_INTERVAL = 3
_GUARD_KEY = "trading:possync:swept_at"

#: How often the sweep widens from "the open trade's symbol" to "every symbol
#: traded inside LOOKBACK". The wide sweep is what catches a close that did not
#: actually flatten, which is rarer and does not need three-second latency, and
#: it costs one exchange call per account per extra symbol.
DEEP_INTERVAL = 60
_DEEP_KEY = "trading:possync:deep_at"

#: How far back the wide sweep looks for symbols worth re-checking.
LOOKBACK = timedelta(hours=24)

#: A leg younger than this is left alone. The entry and the exchange's own
#: position endpoint are not always consistent within the same second — a fill
#: can be acknowledged before it appears in the position list — and closing a
#: leg that the exchange simply has not published yet would be this module
#: inventing the very desync it exists to remove.
GRACE = timedelta(seconds=20)

#: Relative difference in size or entry price below which the exchange's
#: numbers are treated as agreeing with ours. Rounding on the venue's side
#: (contract multipliers, funding-adjusted entries) moves the last digits
#: constantly; rewriting the row for that would be write amplification, not
#: accuracy.
DRIFT = Decimal("0.0005")


@dataclass(frozen=True, slots=True)
class Held:
    """What one account answered with, and whether it answered at all.

    ``positions`` is keyed by normalised symbol. An account missing from the
    reconcile's map did not answer, and nothing is written about it.
    """

    positions: dict[str, Position]


@dataclass
class SyncReport:
    """What one sweep changed. Returned so callers and tests can assert on it."""

    closed: list[int] = field(default_factory=list)
    adopted: list[int] = field(default_factory=list)
    drifted: list[int] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    unreachable: list[int] = field(default_factory=list)
    trade_retired: bool = False
    reopened: int | None = None

    @property
    def changed(self) -> bool:
        return bool(
            self.closed
            or self.adopted
            or self.drifted
            or self.untracked
            or self.trade_retired
            or self.reopened
        )


def norm(symbol: str) -> str:
    """One spelling for a pair, so a venue's punctuation cannot hide a match.

    ``BTC-USDT``, ``BTC_USDT`` and ``btcusdt`` are the same market. Nothing
    stronger than this: ``BTCUSDT`` and ``BTCUSDC`` are *not* the same market on
    most venues, and treating them as one would let a sync close the wrong leg.
    """
    return symbol.upper().replace("-", "").replace("_", "").replace("/", "")


# --- reading ----------------------------------------------------------------


@sync_to_async
def _plan(*, deep: bool) -> tuple[Trade | None, list[ConnectedAccount], list[str]]:
    """The open trade, the accounts to ask, and the symbols to ask about.

    Accounts are every connected account that is not in ``ERROR``, not only the
    active ones: pausing an account stops new orders, it does not close the
    position that is already live at leverage, and that position is exactly the
    one a sync must keep honest.
    """
    trade = (
        Trade.objects.filter(status=TradeStatus.OPEN)
        .prefetch_related("legs")
        .first()
    )
    symbols: list[str] = []
    if trade is not None:
        symbols.append(trade.symbol)
    if deep:
        recent = (
            Trade.objects.filter(closed_at__gte=timezone.now() - LOOKBACK)
            .values_list("symbol", flat=True)
            .distinct()
        )
        seen = {norm(s) for s in symbols}
        for symbol in recent:
            if norm(symbol) not in seen:
                seen.add(norm(symbol))
                symbols.append(symbol)
    if not symbols:
        return trade, [], []
    accounts = list(ConnectedAccount.objects.exclude(status=AccountStatus.ERROR))
    return trade, accounts, symbols


def _read(adapter: ExchangeAdapter, symbols: list[str]):
    """One account's read, as a zero-argument coroutine factory for ``fan_out``.

    A raise anywhere in here makes the whole leg fail, which is the wanted
    behaviour: a partial read is indistinguishable from "the exchange holds
    nothing on the symbols I did not get to", and acting on that would close
    live legs.
    """

    async def op() -> Held:
        found: dict[str, Position] = {}
        for symbol in symbols:
            position = await adapter.get_position(symbol)
            if position is not None and position.size != 0:
                found[norm(symbol)] = position
        return Held(positions=found)

    return op


# --- writing ----------------------------------------------------------------


def _notify(*, account_id: int | None, code: str, message: str) -> dict | None:
    """One persistent notice, not one per sweep.

    Spec §4 notices clear only by hand. A sweep every three seconds over a
    desync that takes the admin a minute to look at would mint twenty identical
    cards, so an undismissed notice with the same code for the same account
    suppresses the next one. The condition is still live; the card already
    says so.
    """
    if Notification.objects.filter(
        account_id=account_id, code=code, dismissed_at__isnull=True
    ).exists():
        return None
    notification = Notification.objects.create(
        account_id=account_id, code=code, message=message
    )
    return {
        "id": notification.id,
        "account_id": notification.account_id,
        "message": notification.message,
        "code": notification.code,
    }


def _drifted(ours: Decimal | None, theirs: Decimal) -> bool:
    if ours is None:
        return theirs != 0
    if theirs == 0:
        return False
    return abs(ours - theirs) / theirs > DRIFT


def _apply(leg: TradeLeg, position: Position) -> list[str]:
    """Copy the exchange's numbers onto a leg. Returns the fields it touched."""
    fields: list[str] = []
    if _drifted(leg.qty, position.size):
        leg.qty = position.size
        fields.append("qty")
    if _drifted(leg.entry_price, position.entry_price) and position.entry_price > 0:
        leg.entry_price = position.entry_price
        fields.append("entry_price")
    return fields


@transaction.atomic
def _reconcile(
    trade_id: int | None, held: dict[int, Held]
) -> tuple[SyncReport, list[dict]]:
    """Write the exchanges' answers over the platform's record.

    Called with only the accounts that answered. Every branch below is keyed on
    one of the two disagreements this module exists for, and each one leaves a
    persistent notice, because a record silently rewritten under the admin is
    the same surprise as a wrong record.
    """
    from apps.trading.services import retire_if_nothing_open

    report = SyncReport()
    notices: list[dict] = []
    now = timezone.now()

    trade = (
        Trade.objects.select_for_update().filter(pk=trade_id).first()
        if trade_id is not None
        else None
    )
    # Deliberately not prefetched: ``retire_if_nothing_open`` re-reads the legs
    # at the end of this function, and a prefetch cache filled before the
    # repairs below would hide a leg this sweep had just adopted — closing a
    # trade that has a live position under it.
    legs = list(trade.legs.all()) if trade is not None else []

    matched: set[tuple[int, str]] = set()

    if trade is not None:
        key = norm(trade.symbol)
        for leg in legs:
            answer = held.get(leg.account_id)
            if answer is None:
                # The exchange did not answer for this account. Nothing is
                # written about it — see the module docstring.
                continue
            position = answer.positions.get(key)
            if position is not None:
                matched.add((leg.account_id, key))

            if position is not None and position.side.value != trade.side:
                # The exchange holds the *opposite* direction on this pair. That
                # is not this trade's leg — closing it as one would flatten a
                # position the platform never opened, and treating it as a match
                # would show the admin a long where the money is short. Report
                # it and touch nothing.
                report.untracked.append(f"{leg.account_id}:{position.symbol}")
                logger.error(
                    "position sync: account=%s holds %s %s while trade=%s is %s — "
                    "the record was left alone",
                    leg.account_id,
                    position.side.value,
                    position.symbol,
                    trade.id,
                    trade.side,
                    extra={"account_id": leg.account_id, "trade_id": trade.id},
                )
                notice = _notify(
                    account_id=leg.account_id,
                    code="side_mismatch",
                    message=(
                        f"{position.symbol}: the exchange holds a "
                        f"{position.side.value} position on this account while the "
                        f"platform's trade is {trade.side}. Nothing was changed — "
                        f"check this account on the exchange."
                    ),
                )
                if notice:
                    notices.append(notice)
                continue

            if leg.closed_at is None and leg.ok:
                if position is not None:
                    fields = _apply(leg, position)
                    if fields:
                        leg.save(update_fields=fields)
                        report.drifted.append(leg.account_id)
                    continue
                if now - leg.opened_at < GRACE:
                    # Too young to judge; the venue may not have published it.
                    continue
                leg.closed_at = now
                leg.error_code = "closed_on_exchange"
                leg.error = (
                    "the exchange no longer holds this position — it was closed "
                    "there (stop, take profit, liquidation, or by hand), not from "
                    "the panel"
                )
                leg.save(update_fields=["closed_at", "error_code", "error"])
                report.closed.append(leg.account_id)
                notice = _notify(
                    account_id=leg.account_id,
                    code="closed_on_exchange",
                    message=(
                        f"{trade.symbol}: the position was closed on the exchange, "
                        f"not from the panel. The platform's record has been "
                        f"corrected; the exit price and PnL are unknown."
                    ),
                )
                if notice:
                    notices.append(notice)
                continue

            if position is not None and (leg.closed_at is not None or not leg.ok):
                # The platform had written this leg off; the exchange holds it.
                # Repairing it is what puts the position back inside close's
                # reach — the alternative is a live leveraged position with no
                # route out through the panel.
                leg.closed_at = None
                leg.ok = True
                leg.error_code = "found_on_exchange"
                leg.error = (
                    "the exchange holds this position although the platform had "
                    "recorded the account as flat; the record was corrected from "
                    "the exchange"
                )
                leg.qty = position.size
                if position.entry_price > 0:
                    leg.entry_price = position.entry_price
                leg.save(
                    update_fields=[
                        "closed_at",
                        "ok",
                        "error_code",
                        "error",
                        "qty",
                        "entry_price",
                    ]
                )
                report.adopted.append(leg.account_id)
                notice = _notify(
                    account_id=leg.account_id,
                    code="found_on_exchange",
                    message=(
                        f"{trade.symbol}: the exchange holds a position this "
                        f"platform had recorded as closed or never opened. It is "
                        f"back in the panel and can be closed from there."
                    ),
                )
                if notice:
                    notices.append(notice)

        # A leg on the open trade's symbol for an account the trade never
        # touched. Spec §6 keeps an account out of a trade in progress, and this
        # does not break that: the position already exists on the exchange, so
        # recording it is the only way the panel can show it and close can reach
        # it. Nothing is routed on its behalf.
        known = {leg.account_id for leg in legs}
        for account_id, answer in held.items():
            position = answer.positions.get(key)
            if position is None or account_id in known:
                continue
            matched.add((account_id, key))
            if position.side.value != trade.side:
                # Same pair, opposite direction: not a leg of this trade.
                report.untracked.append(f"{account_id}:{position.symbol}")
                notice = _notify(
                    account_id=account_id,
                    code="side_mismatch",
                    message=(
                        f"{position.symbol}: the exchange holds a "
                        f"{position.side.value} position on this account, which "
                        f"belongs to no trade in this platform. It cannot be closed "
                        f"from the panel — close it on the exchange."
                    ),
                )
                if notice:
                    notices.append(notice)
                continue
            TradeLeg.objects.create(
                trade=trade,
                account_id=account_id,
                ok=True,
                error_code="found_on_exchange",
                error=(
                    "found on the exchange: this account holds a position in the "
                    "open trade's pair but had no leg in it"
                ),
                qty=position.size,
                entry_price=position.entry_price or None,
            )
            report.adopted.append(account_id)
            notice = _notify(
                account_id=account_id,
                code="found_on_exchange",
                message=(
                    f"{trade.symbol}: the exchange holds a position on this account "
                    f"that the platform had no record of. It is now in the panel and "
                    f"can be closed from there."
                ),
            )
            if notice:
                notices.append(notice)

        if retire_if_nothing_open(trade):
            report.trade_retired = True

    # Anything left is a position on a symbol with no open trade behind it.
    for account_id, answer in held.items():
        for key, position in answer.positions.items():
            if (account_id, key) in matched:
                continue
            reopened = _reopen(account_id, position, now)
            if reopened is not None:
                report.reopened = reopened
                report.adopted.append(account_id)
                notice = _notify(
                    account_id=account_id,
                    code="found_on_exchange",
                    message=(
                        f"{position.symbol}: the exchange still holds this position "
                        f"although the platform had closed the trade. The trade was "
                        f"reopened so it can be closed from the panel."
                    ),
                )
                if notice:
                    notices.append(notice)
                continue
            report.untracked.append(f"{account_id}:{position.symbol}")
            notice = _notify(
                account_id=account_id,
                code="untracked_position",
                message=(
                    f"{position.symbol}: the exchange holds a "
                    f"{position.side.value} position of {position.size} on this "
                    f"account that belongs to no trade in this platform. It cannot "
                    f"be closed from the panel — close it on the exchange."
                ),
            )
            if notice:
                notices.append(notice)

    return report, notices


def _reopen(account_id: int, position: Position, now) -> int | None:
    """Put a closed trade back if the exchange never actually flattened it.

    Only a trade this account was part of, on this pair, closed inside
    ``LOOKBACK``, and only when no other trade is open — the rest of the
    platform is built around one open trade at a time (``Trade.objects.filter
    (status=OPEN).first()``), so minting a second one would make the panel and
    the router disagree about which trade is *the* trade. Where that guard bites,
    the caller falls through to an untracked-position notice instead, which says
    the true thing rather than a convenient one.
    """
    if Trade.objects.filter(status=TradeStatus.OPEN).exists():
        return None
    candidates = (
        Trade.objects.filter(
            status=TradeStatus.CLOSED,
            closed_at__gte=now - LOOKBACK,
            legs__account_id=account_id,
        )
        .order_by("-closed_at")
        .distinct()
    )
    trade = next(
        (
            t
            for t in candidates
            if norm(t.symbol) == norm(position.symbol) and t.side == position.side.value
        ),
        None,
    )
    if trade is None:
        return None
    leg = trade.legs.filter(account_id=account_id).first()
    if leg is None:
        return None
    trade.status = TradeStatus.OPEN
    trade.closed_at = None
    trade.save(update_fields=["status", "closed_at"])
    leg.closed_at = None
    leg.ok = True
    leg.error_code = "found_on_exchange"
    leg.error = (
        "the exchange still held this position after the trade was closed; the "
        "trade was reopened from the exchange's own state"
    )
    leg.qty = position.size
    if position.entry_price > 0:
        leg.entry_price = position.entry_price
    leg.exit_price = None
    leg.pnl = None
    leg.save(
        update_fields=[
            "closed_at",
            "ok",
            "error_code",
            "error",
            "qty",
            "entry_price",
            "exit_price",
            "pnl",
        ]
    )
    logger.error(
        "trade=%s was closed while account=%s still held the position on the "
        "exchange — reopened from the exchange",
        trade.id,
        account_id,
        extra={"trade_id": trade.id, "account_id": account_id},
    )
    return trade.id


# --- the sweep --------------------------------------------------------------


async def sync_positions(*, force: bool = False, deep: bool | None = None) -> SyncReport:
    """One sweep: ask every account, then write what they said.

    Idempotent and safe to call from anywhere — the positions poll, the loop
    command, a test. ``force`` skips the shared interval guard; ``deep`` forces
    (or forbids) the wider symbol set that otherwise runs once a minute.
    """
    if not force and not await sync_to_async(_claim)():
        return SyncReport()
    if deep is None:
        deep = await sync_to_async(_claim_deep)()

    trade, accounts, symbols = await _plan(deep=deep)
    if not accounts or not symbols:
        return SyncReport()

    from apps.trading.services import _adapters, _broadcast

    # Called straight, not through ``sync_to_async``: ``pool.get`` keys its warm
    # adapters on the running event loop, and a threadpool has none — every
    # sweep would build (and discard) a fresh client per account.
    adapters = _adapters(accounts)
    if not adapters:
        return SyncReport()

    result: FanOutResult[Held] = await fan_out(
        [(account_id, _read(adapter, symbols)) for account_id, adapter in adapters],
        timeout=settings.TRADING["FANOUT_TIMEOUT_SECONDS"],
        # Q14: the halt stops *routing*. This sends no order — refusing to read
        # while halted would blind the panel exactly when the admin has stopped
        # everything and most needs to know what is actually still open.
        respect_stop_all=False,
    )

    held: dict[int, Held] = {}
    unreachable: list[int] = []
    for leg in result.legs:
        if leg.ok and isinstance(leg.value, Held):
            held[leg.account_id] = leg.value
        else:
            unreachable.append(leg.account_id)
            logger.info(
                "position sync: account=%s did not answer (%s) — nothing written "
                "about it",
                leg.account_id,
                leg.error_code or leg.error,
            )
    if not held:
        return SyncReport(unreachable=unreachable)

    report, notices = await sync_to_async(_reconcile)(
        trade.id if trade is not None else None, held
    )
    report.unreachable = unreachable

    for notice in notices:
        await _broadcast("notification", notice)
    if report.changed:
        logger.warning(
            "position sync corrected the record: closed=%s adopted=%s drifted=%s "
            "untracked=%s reopened=%s",
            report.closed,
            report.adopted,
            report.drifted,
            report.untracked,
            report.reopened,
        )
        await _broadcast(
            "positions_changed",
            {
                "closed": report.closed,
                "adopted": report.adopted,
                "drifted": report.drifted,
                "untracked": report.untracked,
                "reopened": report.reopened,
            },
        )
    return report


def _claim() -> bool:
    return bool(cache.add(_GUARD_KEY, "1", SYNC_INTERVAL))


def _claim_deep() -> bool:
    return bool(cache.add(_DEEP_KEY, "1", DEEP_INTERVAL))


__all__ = ["SYNC_INTERVAL", "SyncReport", "norm", "sync_positions"]
