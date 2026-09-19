"""Every word the notifier says, in both languages it says them in.

Kept side by side for the reason ``apps/accounts/statement_text.py`` is: a
wording change cannot land in one language and miss the other. The language is
the notifier's own setting, not the panel's — the chat is read on a phone,
away from the panel, by whoever set it up.

Digits, prices and timestamps stay Latin in Persian too, as the panel and the
statement do: the same figures appear in Latin digits on the exchange's screen,
and a message that disagrees with the exchange is one nobody can check.

Output is Telegram HTML. Everything that came from the log — labels, symbols,
error text — goes through ``html.escape``; only the markup written here is not.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape, unescape
from typing import Any

__all__ = ["escape", "unescape", "render", "t", "title", "label", "value", "when"]

from django.utils import timezone

from apps.telegram.events import GENERIC

LANGUAGES = ("en", "fa")

#: code -> (English, Persian)
TITLES: dict[str, tuple[str, str]] = {
    "trade_opened": ("Trade opened", "معامله باز شد"),
    "trade_amended": ("SL/TP changed", "حد ضرر/سود تغییر کرد"),
    "trade_closed": ("Trade closed", "معامله بسته شد"),
    "trade_reduced": ("Position reduced", "بخشی از پوزیشن بسته شد"),
    "closed_on_exchange": (
        "Closed on the exchange (SL/TP or liquidation)",
        "پوزیشن در صرافی بسته شد (حد ضرر/سود یا لیکوئید)",
    ),
    "sltp_failed": (
        "SL/TP could not be attached — position closed",
        "حد ضرر/سود ثبت نشد — پوزیشن بسته شد",
    ),
    "sltp_unprotected": (
        "Position is UNPROTECTED — no SL/TP",
        "پوزیشن بدون محافظ است — حد ضرر/سود ندارد",
    ),
    "side_mismatch": ("Exchange holds the opposite side", "جهت پوزیشن در صرافی برعکس است"),
    "found_on_exchange": (
        "Position found on the exchange — restored",
        "پوزیشن در صرافی پیدا شد — بازگردانده شد",
    ),
    "untracked_position": (
        "Position not tracked by the platform",
        "پوزیشنی خارج از کنترل پلتفرم",
    ),
    "trade_reopened": ("Trade reopened from the exchange", "معامله بر اساس صرافی دوباره باز شد"),
    "bot_started": ("Bot started", "ربات شروع به کار کرد"),
    "bot_promoted": ("Bot promoted to LIVE", "ربات به حالت واقعی (LIVE) رفت"),
    "bot_stopped": ("Bot stopped", "ربات متوقف شد"),
    "bot_paused": ("Bot paused by the risk gate", "ربات توسط کنترل ریسک موقتاً متوقف شد"),
    "bot_exit_guard": (
        "Position closed by the platform — its level was reached",
        "پلتفرم موقعیت را بست — سطح تعیین‌شده لمس شد",
    ),
    "bot_intervention": (
        "Bot position changed by hand",
        "پوزیشن ربات به‌صورت دستی تغییر کرد",
    ),
    "bot_gate_changed": ("Promotion gate changed", "دروازه ارتقا تغییر کرد"),
    "bot_deleted": ("Bot deleted", "ربات حذف شد"),
    "consecutive_losses": ("Bot auto-stopped: losing streak", "توقف خودکار ربات: ضررهای پیاپی"),
    "drawdown": ("Bot auto-stopped: drawdown limit", "توقف خودکار ربات: حد افت سرمایه"),
    "feed_gap": ("Bot auto-stopped: price feed gap", "توقف خودکار ربات: قطعی داده قیمت"),
    "script_error": ("Bot auto-stopped: script error", "توقف خودکار ربات: خطای اسکریپت"),
    "state_disagreement": (
        "Bot auto-stopped: record and exchange disagree",
        "توقف خودکار ربات: ناهمخوانی سوابق با صرافی",
    ),
    "trade_rate": (
        "Bot auto-stopped: too many trades",
        "توقف خودکار ربات: تعداد معاملات بیش از حد",
    ),
    "no_bars": ("Bot auto-stopped: no new bars", "توقف خودکار ربات: کندل جدیدی نرسید"),
    "risk_gate": ("Bot stopped by the risk gate", "ربات توسط کنترل ریسک متوقف شد"),
    "ledger_deposit": ("Deposit recorded", "واریز ثبت شد"),
    "ledger_withdrawal": ("Withdrawal recorded", "برداشت ثبت شد"),
    "ledger_changed": ("Ledger changed", "دفتر حساب تغییر کرد"),
    "split_changed": ("Profit split changed", "تقسیم سود تغییر کرد"),
    "balance_unexplained": ("Unexplained balance change", "تغییر موجودی بدون توضیح"),
    "account_connected": ("Account connected", "حساب متصل شد"),
    "account_refused": ("Account refused or paused", "حساب رد یا متوقف شد"),
    "account_resumed": ("Account resumed", "حساب از سر گرفته شد"),
    "account_paused": ("Account paused", "حساب متوقف شد"),
    "account_changed": ("Account settings changed", "تنظیمات حساب تغییر کرد"),
    "account_removed": ("Account removed", "حساب حذف شد"),
    "credential_expiring": ("API credential expiring soon", "اعتبار API به‌زودی منقضی می‌شود"),
    "credential_expired": ("API credential EXPIRED", "اعتبار API منقضی شد"),
    "halt_on": ("EMERGENCY HALT ON", "توقف اضطراری فعال شد"),
    "halt_off": ("Emergency halt cleared", "توقف اضطراری برداشته شد"),
    "new_device": ("Sign-in from a new device", "ورود از دستگاه جدید"),
    "signed_in": ("Signed in to the panel", "ورود به پنل"),
    "security_changed": ("Security settings changed", "تنظیمات امنیتی تغییر کرد"),
    "telegram_changed": ("Telegram settings changed", "تنظیمات تلگرام تغییر کرد"),
    GENERIC: ("System error", "خطای سیستم"),
}

#: context key -> (English, Persian). Also the render order: a key not listed
#: here is not shown, so a context field added for /logs cannot leak into a chat
#: by accident.
LABELS: dict[str, tuple[str, str]] = {
    "origin": ("Origin", "منشأ"),
    "bot": ("Bot", "ربات"),
    "account": ("Account", "حساب"),
    "exchange": ("Exchange", "صرافی"),
    "symbol": ("Symbol", "نماد"),
    "side": ("Side", "جهت"),
    "market": ("Market", "بازار"),
    "leverage": ("Leverage", "اهرم"),
    "order_type": ("Order", "نوع سفارش"),
    "interval": ("Timeframe", "تایم‌فریم"),
    "mode": ("Mode", "حالت"),
    "qty": ("Quantity", "مقدار"),
    "price": ("Price", "قیمت"),
    "entry_price": ("Entry", "ورود"),
    "exit_price": ("Exit", "خروج"),
    "pnl": ("PnL", "سود/زیان"),
    "amount": ("Amount", "مبلغ"),
    "sl_pct": ("SL %", "حد ضرر ٪"),
    "tp_pct": ("TP %", "حد سود ٪"),
    "fraction": ("Share closed", "سهم بسته‌شده"),
    "days": ("Days left", "روز باقی‌مانده"),
    "expires_at": ("Expires", "انقضا"),
    "gate_enforced": ("Gate enforced", "دروازه فعال"),
    "waived": ("Waived", "معاف‌شده"),
    "actor": ("By", "توسط"),
    "changed": ("Changed", "تغییرات"),
    "ip": ("IP", "آی‌پی"),
    "device": ("Device", "دستگاه"),
    "username": ("User", "کاربر"),
    "reason": ("Reason", "دلیل"),
    "detail": ("Detail", "جزئیات"),
    "error": ("Error", "خطا"),
    "fanout_ms": ("Fan-out ms", "زمان ارسال (ms)"),
    "category": ("Category", "دسته"),
    "source": ("Source", "منبع"),
    "message": ("Message", "پیام"),
}

#: Values worth translating. Everything else is shown as written.
VALUES: dict[str, tuple[str, str]] = {
    "long": ("long", "لانگ"),
    "short": ("short", "شورت"),
    "buy": ("buy", "خرید"),
    "sell": ("sell", "فروش"),
    "manual": ("manual", "دستی"),
    "bot": ("bot", "ربات"),
    "paper": ("paper", "آزمایشی"),
    "live": ("live", "واقعی"),
    "futures": ("futures", "فیوچرز"),
    "spot": ("spot", "اسپات"),
    "True": ("yes", "بله"),
    "False": ("no", "خیر"),
}

#: Free-standing phrases: commands, linking, summaries.
TEXT: dict[str, tuple[str, str]] = {
    "trade": ("Trade", "معامله"),
    "accounts_ok": ("{ok}/{total} accounts filled", "{ok} از {total} حساب انجام شد"),
    "accounts_closed": ("{ok}/{total} accounts closed", "{ok} از {total} حساب بسته شد"),
    "accounts_amended": ("{ok}/{total} accounts updated", "{ok} از {total} حساب به‌روزرسانی شد"),
    # The levels, written the way they are read: "SL 0.5%", not "SL % 0.5".
    "sl_short": ("SL", "حد ضرر"),
    "tp_short": ("TP", "حد سود"),
    "left_open": ("left open", "باز مانده"),
    "leg_failed": ("failed", "ناموفق"),
    "similar": ("+{n} similar in the last 10 min", "+{n} مورد مشابه در ۱۰ دقیقه گذشته"),
    "backlog": (
        "While the notifier was offline, {n} events were not delivered. "
        "Open /logs in the panel for the detail:",
        "در مدتی که اعلان‌رسان خاموش بود {n} رویداد ارسال نشد. جزئیات در بخش گزارش‌های پنل:",
    ),
    "linked": (
        "✅ Linked. This chat will now receive the panel's notifications.",
        "✅ متصل شد. از این پس اعلان‌های پنل به این گفتگو ارسال می‌شود.",
    ),
    "test": (
        "✅ Test message from the trading panel. Notifications are working.",
        "✅ پیام آزمایشی از پنل معاملات. اعلان‌ها کار می‌کنند.",
    ),
    "help": (
        "<b>Commands</b>\n"
        "/status — halt, bots and the open position\n"
        "/positions — open legs with PnL\n"
        "/balance — account balances\n"
        "/bots — every bot and its state\n"
        "/help — this list\n\n"
        "Everything here is read-only.",
        "<b>دستورها</b>\n"
        "/status — توقف اضطراری، ربات‌ها و پوزیشن باز\n"
        "/positions — پوزیشن‌های باز با سود/زیان\n"
        "/balance — موجودی حساب‌ها\n"
        "/bots — ربات‌ها و وضعیتشان\n"
        "/help — همین فهرست\n\n"
        "همه فقط‌خواندنی هستند.",
    ),
    "unknown": ("Unknown command. /help lists them.", "دستور ناشناخته. /help را ببینید."),
    "status": ("Status", "وضعیت"),
    "halt": ("Emergency halt", "توقف اضطراری"),
    "halt_on_word": ("ON", "فعال"),
    "halt_off_word": ("off", "غیرفعال"),
    "running_bots": ("Running bots", "ربات‌های فعال"),
    "none": ("none", "هیچ"),
    "open_position": ("Open position", "پوزیشن باز"),
    "no_position": ("No open position.", "پوزیشن بازی وجود ندارد."),
    "accounts": ("Accounts", "حساب‌ها"),
    "positions": ("Open position", "پوزیشن باز"),
    "total": ("Total", "جمع"),
    "no_feed": ("no price feed — PnL unknown", "داده قیمت در دسترس نیست — سود/زیان نامعلوم"),
    "balances": ("Balances", "موجودی‌ها"),
    "no_accounts": ("No accounts.", "حسابی وجود ندارد."),
    "bots": ("Bots", "ربات‌ها"),
    "no_bots": ("No bots.", "رباتی وجود ندارد."),
    "paused": ("paused", "متوقف"),
    "non_usdt": ("not USDT — not traded", "غیر USDT — معامله نمی‌شود"),
}

MARK = {"INFO": "🟢", "WARNING": "🟠", "ERROR": "🔴", "CRITICAL": "🚨"}


def _i(language: str) -> int:
    return 1 if language == "fa" else 0


def t(key: str, language: str, **params: Any) -> str:
    return TEXT[key][_i(language)].format(**params)


def title(code: str, language: str) -> str:
    pair = TITLES.get(code) or TITLES[GENERIC]
    return pair[_i(language)]


def label(key: str, language: str) -> str:
    return LABELS[key][_i(language)]


def value(raw: Any, language: str) -> str:
    if isinstance(raw, list | tuple):
        return ", ".join(value(v, language) for v in raw)
    text = str(raw)
    pair = VALUES.get(text)
    return escape(pair[_i(language)] if pair else text)


def when(moment: datetime) -> str:
    return timezone.localtime(moment).strftime("%Y-%m-%d %H:%M:%S")


def _lines(context: dict[str, Any], language: str) -> list[str]:
    return [
        f"{label(key, language)}: <b>{value(context[key], language)}</b>"
        for key in LABELS
        if context.get(key) not in (None, "", [])
    ]


#: The four fan-out events. They are rendered by hand rather than through the
#: label table because a label per field turned one trade into a dozen lines —
#: symbol, side, market, leverage, order type, both percentages, the fan-out
#: timing and then a line per account — and the one number the operator opened
#: the message for, the money, was not among them. A chat is read on a phone
#: while something is happening; it gets the instrument, the levels, and what
#: it made or lost.
TRADE_CODES = frozenset({"trade_opened", "trade_amended", "trade_closed", "trade_reduced"})


def _num(raw: Any) -> str:
    """A stored ``str(Decimal)`` without its trailing zeros. ``0.5000`` → ``0.5``."""
    text = str(raw).strip()
    if "." not in text:
        return text
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def _signed(raw: Any) -> str:
    """Money with its sign shown — ``+12.34``, ``-3.1``.

    Zero keeps no sign: a flat trade is not a small gain, and ``+0`` reads like
    one at a glance, which is the glance this whole message is written for.
    """
    text = _num(raw)
    if text.startswith("-"):
        return text
    try:
        if Decimal(text) == 0:
            return text
    except InvalidOperation:
        return text
    return f"+{text}"


def _total(legs: list[dict[str, Any]]) -> Decimal | None:
    """The PnL of the legs **that are being shown**.

    Summed here, off the filtered list, rather than carried in the context as a
    figure somebody computed earlier: a hidden account's money must not reach a
    reader who cannot see the account, and a pre-computed total would contain
    it. Everything else on this platform filters its totals the same way.
    """
    found = [leg["pnl"] for leg in legs if leg.get("pnl") not in (None, "")]
    if not found:
        return None
    try:
        return sum((Decimal(str(one)) for one in found), Decimal(0))
    except (InvalidOperation, TypeError):
        return None


def _instrument(context: dict[str, Any], language: str) -> str:
    """``BTCUSDC short · futures 10×`` — the whole of what used to be six lines."""
    parts = [escape(str(context.get("symbol") or ""))]
    if context.get("side"):
        parts.append(value(context["side"], language))
    line = " ".join(part for part in parts if part)
    tail = []
    if context.get("market"):
        leverage = context.get("leverage")
        venue = value(context["market"], language)
        tail.append(f"{venue} {leverage}×" if leverage and str(leverage) != "1" else venue)
    if context.get("order_type") and str(context["order_type"]) != "market":
        # A market order is the default and says nothing; "limit" is news.
        tail.append(value(context["order_type"], language))
    if context.get("origin"):
        origin = value(context["origin"], language)
        bot = context.get("bot")
        tail.append(f"{origin} ({escape(str(bot))})" if bot else origin)
    return " · ".join([line, *tail]) if line else " · ".join(tail)


def _levels(context: dict[str, Any], language: str) -> str:
    parts = []
    if context.get("sl_pct"):
        parts.append(f"{t('sl_short', language)} {_num(context['sl_pct'])}%")
    if context.get("tp_pct"):
        parts.append(f"{t('tp_short', language)} {_num(context['tp_pct'])}%")
    if context.get("fraction"):
        # A scale-out's target is what is *left*, not what was taken off.
        share = Decimal(str(context["fraction"])) * 100
        parts.append(f"{_num(share)}% {t('left_open', language)}")
    return " · ".join(parts)


def _account_name(leg: dict[str, Any]) -> str:
    return escape(str(leg.get("account") or f"#{leg.get('account_id')}"))


def _trade_body(code: str, context: dict[str, Any], language: str) -> list[str]:
    legs: list[dict[str, Any]] = context.get("legs") or []
    ok = [leg for leg in legs if leg.get("ok")]
    failed = [leg for leg in legs if not leg.get("ok")]

    body = [line for line in (_instrument(context, language), _levels(context, language)) if line]

    total = _total(ok)
    if total is not None:
        # The headline of a close: one number, signed, before anything else
        # about how it got there.
        body.append(f"{label('pnl', language)}: <b>{_signed(total)}</b>")

    if legs:
        # Filled, closed, updated: the same count, and three different facts.
        wording = {
            "trade_closed": "accounts_closed",
            "trade_reduced": "accounts_closed",
            "trade_amended": "accounts_amended",
        }.get(code, "accounts_ok")
        summary = t(wording, language, ok=len(ok), total=len(legs))
        prices = {str(leg.get("price")) for leg in ok if leg.get("price") not in (None, "")}
        if len(prices) == 1 and total is None:
            # One fill price for the whole fan-out is the normal case and worth
            # one line; several means the accounts filled apart, and the panel
            # is where that is read leg by leg.
            summary += f" @ {escape(_num(prices.pop()))}"
        if ok and total is None:
            # The accounts by name, on the same line — *which* of them took the
            # trade is worth knowing; how much each one sized is what the panel
            # is for. A line per account is the clutter this replaced.
            summary += " — " + ", ".join(_account_name(leg) for leg in ok)
        body.append(f"✅ {summary}" if ok else summary)

    # Per-account money, and only that: whoever is reading wants to know which
    # account made what, not what size it held.
    for leg in ok:
        if leg.get("pnl") in (None, ""):
            continue
        body.append(f"• {_account_name(leg)} {_signed(leg['pnl'])}")

    # A failure is never summarised away. It is the one thing in a fan-out that
    # asks the operator to do something.
    for leg in failed:
        why = leg.get("error") or leg.get("error_code") or t("leg_failed", language)
        body.append(f"❌ {_account_name(leg)} — {escape(str(why))[:160]}")
    return body


def _legs(legs: list[dict[str, Any]], language: str) -> list[str]:
    ok = sum(1 for leg in legs if leg.get("ok"))
    lines = [t("accounts_ok", language, ok=ok, total=len(legs))]
    for leg in legs:
        name = escape(str(leg.get("account") or f"#{leg.get('account_id')}"))
        where = escape(str(leg.get("exchange") or ""))
        head = f"• {name}" + (f" ({where})" if where else "")
        if leg.get("ok"):
            qty, price = leg.get("qty"), leg.get("price")
            fill = " ".join(
                part
                for part in (
                    escape(str(qty)) if qty not in (None, "") else "",
                    f"@ {escape(str(price))}" if price not in (None, "") else "",
                )
                if part
            )
            lines.append(f"✅ {head}" + (f" — {fill}" if fill else ""))
        else:
            why = leg.get("error") or leg.get("error_code") or t("leg_failed", language)
            lines.append(f"❌ {head} — {escape(str(why))[:200]}")
    return lines


def render(
    *,
    code: str,
    level: str,
    timestamp: datetime,
    context: dict[str, Any],
    language: str,
    trade_id: int | None = None,
    repeats: int = 0,
) -> str:
    """One event as a Telegram message. ``context`` is already filtered."""
    head = f"{MARK.get(level, '•')} <b>{escape(title(code, language))}</b>"
    if trade_id:
        head += f" · {t('trade', language)} #{trade_id}"
    if code in TRADE_CODES:
        body = _trade_body(code, context, language)
    else:
        body = _lines(context, language)
        legs = context.get("legs")
        if legs:
            body += _legs(legs, language)
    if repeats:
        body.append(f"<i>{t('similar', language, n=repeats)}</i>")
    body.append(f"🕒 {when(timestamp)}")
    return "\n".join([head, *body])
