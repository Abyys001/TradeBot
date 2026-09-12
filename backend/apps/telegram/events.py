"""Which log rows are Telegram events, and what each one carries.

The bus is the log table. An event is announced with the ordinary
``apps.logging.utils.system_log(level, category, message, error_code=CODE,
account_id=..., trade_id=..., context={...})`` — nothing on the emitting side
imports this app — and ``sink`` picks it out of ``LogEntry`` by its code. So a
new event is a code here, a title in ``messages``, and one ``system_log`` call
at the place it happens; ``tests/test_telegram_events.py`` fails until all three
exist.

Context keys are shared across codes rather than defined per code, so the
formatter renders any of them with one label table (``messages.LABELS``). Money
and sizes go in as ``str(Decimal)``: the JSON column cannot hold a Decimal, and
a float would round a price the operator is going to compare with the exchange.

Every row that names an account carries it as ``account_id`` — or, for a
fan-out, as ``context["legs"][i]["account_id"]`` — because that is the only
place ``sink`` looks when it drops hidden accounts. A label in free text is
not filtered on its own.
"""

from __future__ import annotations

from dataclasses import dataclass


class Group:
    """What the operator switches on and off, one checkbox each."""

    TRADES = "trades"
    BOTS = "bots"
    MONEY = "money"
    RISK = "risk"
    SYSTEM = "system"
    ADMIN = "admin"


GROUPS: tuple[str, ...] = (
    Group.TRADES,
    Group.BOTS,
    Group.MONEY,
    Group.RISK,
    Group.SYSTEM,
    Group.ADMIN,
)


@dataclass(frozen=True, slots=True)
class Event:
    group: str


#: code -> event. Titles live in ``messages.TITLES`` in both languages.
EVENTS: dict[str, Event] = {
    # --- trades: one row per fan-out, legs in context ------------------------
    # context: symbol, side, market, leverage, order_type, sl_pct, tp_pct,
    # fraction (reduce only), origin ("manual" | "bot"), bot, fanout_ms,
    # legs[{account_id, account, exchange, ok, qty, price, error_code, error}]
    "trade_opened": Event(Group.TRADES),
    "trade_amended": Event(Group.TRADES),
    "trade_closed": Event(Group.TRADES),
    "trade_reduced": Event(Group.TRADES),
    # --- the venue acted, or disagrees with the record ----------------------
    # context: account, exchange, symbol, side, qty, entry_price, exit_price,
    # pnl, detail
    "closed_on_exchange": Event(Group.TRADES),
    "sltp_failed": Event(Group.RISK),
    "sltp_unprotected": Event(Group.RISK),
    "side_mismatch": Event(Group.RISK),
    "found_on_exchange": Event(Group.RISK),
    "untracked_position": Event(Group.RISK),
    "trade_reopened": Event(Group.RISK),
    # --- bots: context bot, bot_id, symbol, interval, mode, reason, detail ---
    "bot_started": Event(Group.BOTS),
    "bot_promoted": Event(Group.BOTS),
    "bot_stopped": Event(Group.BOTS),
    "bot_paused": Event(Group.BOTS),
    "bot_gate_changed": Event(Group.ADMIN),
    # The Q25 auto-stops, logged by ``supervisor._announce_stop`` with the
    # ``StopReason`` value as the code. ``halt`` and ``manual`` are not here:
    # the halt has its own event and a manual stop is ``bot_stopped``.
    "consecutive_losses": Event(Group.RISK),
    "drawdown": Event(Group.RISK),
    "feed_gap": Event(Group.RISK),
    "script_error": Event(Group.RISK),
    "state_disagreement": Event(Group.RISK),
    "trade_rate": Event(Group.RISK),
    "no_bars": Event(Group.RISK),
    "risk_gate": Event(Group.RISK),
    # --- money: context account, exchange, amount, detail -------------------
    "ledger_deposit": Event(Group.MONEY),
    "ledger_withdrawal": Event(Group.MONEY),
    "ledger_changed": Event(Group.MONEY),
    "split_changed": Event(Group.MONEY),
    "balance_unexplained": Event(Group.MONEY),
    # --- accounts and credentials: context account, exchange, reason, days --
    "account_connected": Event(Group.ADMIN),
    "account_refused": Event(Group.SYSTEM),
    "account_resumed": Event(Group.ADMIN),
    "account_removed": Event(Group.ADMIN),
    "credential_expiring": Event(Group.SYSTEM),
    "credential_expired": Event(Group.SYSTEM),
    # --- the platform: context actor, reason, changed, ip, device -----------
    "halt_on": Event(Group.RISK),
    "halt_off": Event(Group.RISK),
    "new_device": Event(Group.ADMIN),
    "security_changed": Event(Group.ADMIN),
    "telegram_changed": Event(Group.ADMIN),
}

#: The code a row without a registered code is shown under, when it is an
#: ERROR or worse and the ``system`` group is on.
GENERIC = "system_error"

#: ERROR-level codes that another event already reports. A bot stopped by the
#: halt is the halt (``halt_on``), and a manual stop is ``bot_stopped`` — sent
#: again as a "system error" they would read as a second, separate failure.
QUIET = frozenset({"halt", "manual"})
