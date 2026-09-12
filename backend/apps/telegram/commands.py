"""What the linked chat can ask, and how a chat becomes the linked one.

Read-only by decision (Q36): nothing here places, amends or closes an order,
touches the halt, or starts a bot. A chat that is not the linked one gets no
answer at all — not "unauthorised", which would confirm the bot belongs to a
trading platform to anyone who found its name.

The answers are built from the same functions the panel reads, filtered as a
reader who is not ``_svc``: ``market_views.open_positions(sees_hidden=False)``
and ``visibility.accessible(None)``. A second implementation of "what is open"
for the chat would be a second opinion about a total.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.logging.utils import system_log
from apps.telegram.messages import escape, t, value
from apps.telegram.models import TelegramBot


@dataclass(frozen=True, slots=True)
class Reply:
    chat_id: int
    text: str


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def advance_offset(offset: int) -> None:
    TelegramBot.objects.filter(pk=1).update(update_offset=offset)


def handle(update: dict[str, Any]) -> Reply | None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    if not text.startswith("/") or not isinstance(chat.get("id"), int):
        return None

    row = TelegramBot.load()
    language = row.language
    command, _, argument = text.partition(" ")
    command = command.split("@", 1)[0].lower()

    if command == "/start" and argument.strip():
        if _link(row, chat, message.get("from") or {}, argument.strip()):
            return Reply(chat["id"], t("linked", language))
        return None

    if row.chat_id is None or chat["id"] != row.chat_id:
        return None
    if command in ("/start", "/help"):
        return Reply(chat["id"], t("help", language))
    answer = COMMANDS.get(command)
    return Reply(chat["id"], answer(language) if answer else t("unknown", language))


def _link(row: TelegramBot, chat: dict, sender: dict, code: str) -> bool:
    """Three things must hold, and each closes a different hole.

    The code proves the person pressing Start came from the panel. The
    username proves it is the recipient the operator named, not whoever the
    link was forwarded to. A private chat keeps a group — where every member
    would read the book — from being linked at all.
    """
    expires = row.link_code_expires_at
    if not row.link_code_hash or expires is None or expires < timezone.now():
        return False
    if not hmac.compare_digest(hash_code(code), row.link_code_hash):
        return False
    if chat.get("type") != "private":
        return False
    username = (sender.get("username") or "").lower()
    if not username or username != row.recipient_username.lower():
        return False
    # Linking switches delivery on: the chat is about to be told it "will now
    # receive the panel's notifications", and a link left waiting on a second
    # switch was a notifier that confirmed itself and then sent nothing.
    # ``log_cursor=None`` starts it at the head, as the switch does.
    TelegramBot.objects.filter(pk=row.pk).update(
        chat_id=chat["id"],
        link_code_hash="",
        link_code_expires_at=None,
        last_error="",
        enabled=True,
        log_cursor=None,
    )
    system_log(
        "INFO",
        "ADMIN",
        f"Telegram chat linked to @{username}",
        source="apps.telegram",
        error_code="telegram_changed",
        context={"changed": ["chat"], "username": f"@{username}"},
    )
    return True


# --- the answers ------------------------------------------------------------


def _money(raw: Any) -> str:
    if raw in (None, ""):
        return "—"
    return escape(f"{Decimal(str(raw)).quantize(Decimal('0.01')):,}")


def status(language: str) -> str:
    from apps.bots.models import Bot, BotState
    from apps.trading import killswitch

    halted = killswitch.state()["stop_all"]
    running = list(
        Bot.objects.filter(state__in=[BotState.PAPER, BotState.LIVE]).order_by("name")
    )
    lines = [
        f"<b>{t('status', language)}</b>",
        f"{'🚨' if halted else '🟢'} {t('halt', language)}: "
        f"<b>{t('halt_on_word' if halted else 'halt_off_word', language)}</b>",
        f"🤖 {t('running_bots', language)}: "
        + (
            ", ".join(f"{escape(b.name)} ({value(b.state, language)})" for b in running)
            or t("none", language)
        ),
    ]
    lines.append(_position_line(language))
    return "\n".join(lines)


def _position_line(language: str) -> str:
    from apps.trading.market_views import open_positions

    payload = open_positions(sees_hidden=False)
    trade = payload["trade"]
    if trade is None:
        return f"📭 {t('no_position', language)}"
    totals = payload["totals"] or {}
    pnl = totals.get("pnl")
    return (
        f"📈 {t('open_position', language)}: <b>{escape(trade['symbol'])} "
        f"{value(trade['side'], language)} {trade['leverage']}×</b> — "
        f"{totals.get('accounts', 0)} {t('accounts', language)}, "
        + (f"PnL <b>{_money(pnl)}</b>" if pnl is not None else t("no_feed", language))
    )


def positions(language: str) -> str:
    from apps.trading.market_views import open_positions

    payload = open_positions(sees_hidden=False)
    trade = payload["trade"]
    if trade is None:
        return f"📭 {t('no_position', language)}"
    lines = [
        f"<b>{t('positions', language)}</b> · {escape(trade['symbol'])} "
        f"{value(trade['side'], language)} {trade['leverage']}×"
    ]
    for leg in payload["legs"]:
        name = f"{escape(leg['account_label'])} ({escape(leg['exchange'])})"
        if not leg["ok"]:
            lines.append(f"❌ {name} — {escape(leg['error'] or leg['error_code'] or '')[:120]}")
            continue
        pnl = f"PnL {_money(leg['pnl'])}" if leg["pnl"] is not None else t("no_feed", language)
        lines.append(
            f"• {name}: {escape(leg['qty'])} @ {escape(leg['entry_price'])} — {pnl}"
            + (f" ({escape(leg['roe_pct'][:6])}%)" if leg["roe_pct"] else "")
        )
    totals = payload["totals"] or {}
    if totals.get("pnl") is not None:
        lines.append(
            f"<b>{t('total', language)}</b>: margin {_money(totals['margin'])} · "
            f"PnL {_money(totals['pnl'])}"
        )
    elif payload.get("feed_error"):
        lines.append(t("no_feed", language))
    return "\n".join(lines)


def balance(language: str) -> str:
    from apps.accounts.models import AccountStatus
    from apps.accounts.visibility import accessible

    accounts = list(accessible(None).order_by("label"))
    if not accounts:
        return t("no_accounts", language)
    lines = [f"<b>{t('balances', language)}</b>"]
    total = Decimal("0")
    for account in accounts:
        marker = "⏸" if account.status != AccountStatus.ACTIVE else "•"
        amount = account.last_balance
        asset = escape(account.last_balance_asset or "")
        line = (
            f"{marker} {escape(account.label)} ({escape(account.exchange)}): "
            f"{_money(amount)} {asset}"
        )
        if account.last_balance_asset and not account.balance_is_usdt:
            line += f" — {t('non_usdt', language)}"
        elif amount is not None:
            total += amount
        if account.status != AccountStatus.ACTIVE:
            line += f" — {t('paused', language)}"
        lines.append(line)
    lines.append(f"<b>{t('total', language)}</b>: {_money(total)} USDT")
    return "\n".join(lines)


def bots(language: str) -> str:
    from apps.bots.models import Bot

    rows = list(Bot.objects.order_by("name"))
    if not rows:
        return t("no_bots", language)
    lines = [f"<b>{t('bots', language)}</b>"]
    for bot in rows:
        lines.append(
            f"• {escape(bot.name)} — {escape(bot.symbol)} {escape(bot.interval)} — "
            f"<b>{value(bot.state, language)}</b>"
        )
    return "\n".join(lines)


COMMANDS = {
    "/status": status,
    "/positions": positions,
    "/balance": balance,
    "/bots": bots,
}
