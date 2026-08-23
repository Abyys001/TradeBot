"""Every word the statement says, in both languages it says them in.

The statement is the one artefact of the platform that leaves it, and the
person it goes to may not read English. So the document is issued in the
language the operator picks at download time — not the language of whoever is
signed in — and this module holds both versions of every phrase side by side so
they cannot drift apart.

Three things the Persian side needs that the English side does not:

* **A font.** ReportLab's built-in Helvetica has no Arabic glyphs at all, so
  the Persian document is set in Vazirmatn (SIL OFL, vendored in ``fonts/``) —
  the same face the panel uses, so paper and screen are one product.
* **Shaping.** Arabic script is cursive: a letter's glyph depends on its
  neighbours. ReportLab does not do that join, so text is reshaped
  (``arabic_reshaper``) before it is drawn.
* **Bidirectional reordering.** ReportLab draws the string in the order it is
  given, so the visual order has to be produced here (``python-bidi``). It is
  applied per *line*, because reordering a whole paragraph and then letting
  ReportLab wrap it puts the last words on the first line — see
  ``statement.wrap_rtl``.

Deliberately *not* localised: digits and dates. The panel already fixes Latin
digits for money in Persian (``composables/useFormat.ts``) because the same
figures appear in Latin digits on the exchange's own screen, and a statement
that disagrees with the exchange is one nobody can check. For the same reason
the calendar stays Gregorian; only the month names are translated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).resolve().parent / "fonts"

#: Anything in the Arabic block, including the Persian letters and the
#: presentation forms the reshaper produces.
ARABIC = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")

DEFAULT_LANGUAGE = "en"


@lru_cache(maxsize=1)
def _register_persian_fonts() -> tuple[str, str]:
    """Embed Vazirmatn once per process. Returns (regular, bold) font names."""
    pdfmetrics.registerFont(TTFont("Vazirmatn", str(FONT_DIR / "Vazirmatn-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Vazirmatn-Bold", str(FONT_DIR / "Vazirmatn-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        "Vazirmatn", normal="Vazirmatn", bold="Vazirmatn-Bold",
        italic="Vazirmatn", boldItalic="Vazirmatn-Bold",
    )
    return "Vazirmatn", "Vazirmatn-Bold"


@dataclass(frozen=True)
class Language:
    """One language's fonts, direction and words."""

    code: str
    rtl: bool
    regular: str
    bold: str
    months: tuple[str, ...]
    copy: dict[str, Any]

    @property
    def start(self) -> int:
        """Alignment for text that reads from the margin the eye starts at."""
        return TA_RIGHT if self.rtl else TA_LEFT

    @property
    def end(self) -> int:
        return TA_LEFT if self.rtl else TA_RIGHT

    def t(self, key: str, **kwargs) -> str:
        """One phrase, with its placeholders filled in."""
        text = self.copy[key]
        return text.format(**kwargs) if kwargs else text

    def shape(self, text: str) -> str:
        """Logical text into the visual order ReportLab will draw verbatim.

        A string with no Arabic letter in it is returned untouched: running the
        bidi algorithm over ``+$1,234.00`` inside a right-to-left document
        moves the sign to the far end, which is a different number.
        """
        if not self.rtl or not text or not ARABIC.search(text):
            return text
        import arabic_reshaper
        from bidi import get_display

        return get_display(arabic_reshaper.reshape(text), base_dir="R")

    def month(self, index: int) -> str:
        """``index`` is 1-12, as ``datetime.month`` gives it."""
        return self.months[index - 1]


EN_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

FA_MONTHS = (
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
)


EN: dict[str, Any] = {
    # --- page furniture ---
    "brand": "TradeBot",
    "tagline": "Automated multi-account order routing",
    "doc_title": "TRADING STATEMENT",
    "issued": "Issued {when}",
    "footer": "Generated automatically by TradeBot · figures are the exchange's "
              "own fills · confidential to the account holder",
    "ref": "Reference {ref}",
    "page": "Page {page}",
    "page_of": "Page {page} of {total}",
    "meta_title": "TradeBot statement — {label}",
    "meta_subject": "Automated trading statement for {label} ({period})",

    # --- the period ---
    "period_all": "Since the account was connected",
    "period_until": "Up to {end}",
    "period_from": "From {start}",
    "period_range": "{start} — {end}",

    # --- identity ---
    "account_line": "{exchange} account · statement period: <b>{period}</b>",
    "testnet_suffix": " (testnet)",
    "testnet_tag": " · testnet",
    "fact_exchange": "EXCHANGE",
    "fact_connected": "CONNECTED TO THE BOT",
    "fact_trading_since": "TRADING SINCE",
    "fact_state": "CURRENT STATE",
    "fact_fingerprint": "KEY FINGERPRINT",
    "fact_asset": "DENOMINATED IN",
    "status_active": "Active",
    "status_paused": "Paused",
    "status_error": "Error",
    # --- headline ---
    "sec_result": "Result for this period",
    "sec_result_hint": "closed by the bot, realised in this window",
    "tile_pnl": "PROFIT / LOSS",
    "tile_pnl_sub": "across {count} priced trades",
    "tile_trades": "TRADES CLOSED",
    "tile_trades_sub": "{wins} in profit · {losses} in loss",
    "tile_extremes": "BEST / WORST",
    "tile_extremes_sub": "single trade in the period",
    "tile_average": "AVERAGE PER TRADE",
    "tile_average_sub": "mean realised result",
    "tile_volume": "VOLUME TRADED",
    "tile_volume_sub": "total position value routed",
    "tile_factor": "PROFIT FACTOR",
    "tile_factor_sub": "gross profit ÷ gross loss",
    "tile_cash": "CASH MOVED",
    "tile_cash_sub": "{count} transfers this period",
    "sec_whole": "The account as a whole",
    "sec_whole_hint": "not limited to this period",
    "tile_balance": "BALANCE NOW",
    "tile_balance_sub": "as of {when}",
    "tile_invested": "NET INVESTED",
    "tile_invested_sub": "{deposits} in · {withdrawals} out",
    "tile_since": "SINCE CONNECTED",
    "tile_since_sub": "balance less net invested",

    # --- trades ---
    "sec_trades": "Trades closed in this period",
    "sec_trades_hint": "{count} closed by the bot",
    "sec_trades_capped": " · newest {limit} shown",
    "trades_empty": "The bot closed no positions on this account in this period.",
    "col_index": "#",
    "col_closed": "Closed",
    "col_pair": "Pair",
    "col_direction": "Direction",
    "col_size": "Size",
    "col_entry": "Entry",
    "col_exit": "Exit",
    "col_margin": "Margin",
    "col_pnl": "Profit / loss",
    "side_long": "LONG",
    "side_short": "SHORT",
    "leverage": "{side} ×{leverage}",
    "period_total": "Period total — realised by the bot",
    "unpriced_note": "{count} of these closed without a price from the exchange "
                     "and are excluded from the total above.",

    # --- still open ---
    "sec_open": "Still open at the end of the period",
    "sec_open_hint": "no result yet — excluded from the total above",
    "col_opened": "Opened",
    "col_stop": "Stop loss",
    "col_target": "Take profit",

    # --- failures ---
    "sec_failed": "Orders the bot could not place",
    "sec_failed_hint": "recorded in full — nothing was traded on them",
    "col_when": "When",
    "col_reason": "What the exchange said",
    "not_routed": "not routed",
    "failed_note": "Each account is routed independently, so an order the "
                   "exchange refused here — most often because the account's "
                   "balance was below the exchange's minimum order size — did "
                   "not delay or affect any other account.",

    # --- by pair ---
    "sec_pairs": "Where the result came from",
    "sec_pairs_hint": "by trading pair, best first",
    "col_trades": "Trades",
    "col_in_profit": "In profit",
    "col_in_loss": "In loss",

    # --- cash ---
    "sec_cash": "Deposits and withdrawals in this period",
    "sec_cash_hint": "your own capital moving — never counted as profit",
    "cash_empty": "No deposit or withdrawal was recorded in this period.",
    "col_date": "Date",
    "col_type": "Type",
    "col_amount": "Amount",
    "col_recorded": "Recorded",
    "col_note": "Note",
    "deposit": "Deposit",
    "withdrawal": "Withdrawal",
    "net_movement": "Net movement",
    "flows_sub": "{deposits} in · {withdrawals} out",
    "source_manual": "Recorded by hand",
    "source_detected": "Accepted from a detection",

    # --- split ---
    "sec_split": "Profit split",
    "sec_split_hint": "applied to the return since the account was connected",
    "col_party": "Party",
    "role_investor": "Investor",
    "role_trader": "Trader",
    "role_programmer": "Programmer",
}


FA: dict[str, Any] = {
    # --- page furniture ---
    "brand": "TradeBot",
    "tagline": "مسیریابی خودکار سفارش روی چند حساب",
    "doc_title": "صورت‌حساب معاملات",
    "issued": "صادر شده در {when}",
    "footer": "این سند به‌صورت خودکار توسط TradeBot تولید شده است · ارقام برگرفته "
              "از معاملات ثبت‌شده در خودِ صرافی است · محرمانه و مخصوص دارنده حساب",
    "ref": "شناسه سند {ref}",
    "page": "صفحه {page}",
    "page_of": "صفحه {page} از {total}",
    "meta_title": "صورت‌حساب TradeBot — {label}",
    "meta_subject": "صورت‌حساب معاملات خودکار برای {label} ({period})",

    # --- the period ---
    "period_all": "از زمان اتصال حساب تاکنون",
    "period_until": "تا {end}",
    "period_from": "از {start}",
    "period_range": "{start} تا {end}",

    # --- identity ---
    "account_line": "حساب {exchange} · دوره صورت‌حساب: <b>{period}</b>",
    "testnet_suffix": " (شبکه آزمایشی)",
    "testnet_tag": " · شبکه آزمایشی",
    "fact_exchange": "صرافی",
    "fact_connected": "زمان اتصال به ربات",
    "fact_trading_since": "آغاز معامله",
    "fact_state": "وضعیت فعلی",
    "fact_fingerprint": "اثر انگشت کلید",
    "fact_asset": "واحد حساب",
    "status_active": "فعال",
    "status_paused": "متوقف‌شده",
    "status_error": "خطا",
    # --- headline ---
    "sec_result": "نتیجه این دوره",
    "sec_result_hint": "معاملاتی که ربات در این بازه بسته و تسویه کرده است",
    "tile_pnl": "سود / زیان",
    "tile_pnl_sub": "حاصل {count} معامله قیمت‌گذاری‌شده",
    "tile_trades": "معاملات بسته‌شده",
    "tile_trades_sub": "{wins} معامله با سود · {losses} معامله با زیان",
    "tile_extremes": "بهترین / بدترین",
    "tile_extremes_sub": "تک معامله در این دوره",
    "tile_average": "میانگین هر معامله",
    "tile_average_sub": "میانگین نتیجه تسویه‌شده",
    "tile_volume": "حجم معامله‌شده",
    "tile_volume_sub": "مجموع ارزش موقعیت‌های ارسال‌شده",
    "tile_factor": "ضریب سودآوری",
    "tile_factor_sub": "سود ناخالص ÷ زیان ناخالص",
    "tile_cash": "جابه‌جایی وجه",
    "tile_cash_sub": "{count} انتقال در این دوره",
    "sec_whole": "وضعیت کل حساب",
    "sec_whole_hint": "محدود به این دوره نیست",
    "tile_balance": "موجودی کنونی",
    "tile_balance_sub": "به تاریخ {when}",
    "tile_invested": "سرمایه خالص",
    "tile_invested_sub": "{deposits} واریز · {withdrawals} برداشت",
    "tile_since": "از زمان اتصال",
    "tile_since_sub": "موجودی منهای سرمایه خالص",

    # --- trades ---
    "sec_trades": "معاملات بسته‌شده در این دوره",
    "sec_trades_hint": "{count} معامله توسط ربات بسته شده است",
    "sec_trades_capped": " · {limit} مورد آخر نمایش داده شده",
    "trades_empty": "ربات در این دوره هیچ موقعیتی را روی این حساب نبسته است.",
    # Not "ردیف": the column is 7 units wide and holds Latin digits, so the
    # word wraps mid-letter. "#" is read the same in both languages.
    "col_index": "#",
    "col_closed": "زمان بستن",
    "col_pair": "جفت‌ارز",
    "col_direction": "جهت",
    "col_size": "حجم",
    "col_entry": "ورود",
    "col_exit": "خروج",
    "col_margin": "مارجین",
    "col_pnl": "سود / زیان",
    "side_long": "خرید",
    "side_short": "فروش",
    "leverage": "{side} ×{leverage}",
    "period_total": "جمع این دوره — تسویه‌شده توسط ربات",
    "unpriced_note": "{count} مورد از این معاملات بدون قیمت از سوی صرافی بسته "
                     "شده‌اند و در جمع بالا محاسبه نشده‌اند.",

    # --- still open ---
    "sec_open": "باز در پایان این دوره",
    "sec_open_hint": "هنوز نتیجه‌ای ندارند — در جمع بالا محاسبه نشده‌اند",
    "col_opened": "زمان باز شدن",
    "col_stop": "حد ضرر",
    "col_target": "حد سود",

    # --- failures ---
    "sec_failed": "سفارش‌هایی که ربات نتوانست ثبت کند",
    "sec_failed_hint": "کامل ثبت شده‌اند — هیچ معامله‌ای روی آن‌ها انجام نشده است",
    "col_when": "زمان",
    "col_reason": "پاسخ صرافی",
    "not_routed": "ارسال نشد",
    "failed_note": "هر حساب مستقل از بقیه اجرا می‌شود؛ بنابراین سفارشی که صرافی "
                   "اینجا رد کرده است — که بیشتر وقت‌ها به این دلیل است که "
                   "موجودی حساب از حداقل حجم سفارشِ صرافی کمتر بوده — هیچ تأخیر "
                   "یا اثری روی حساب‌های دیگر نداشته است.",

    # --- by pair ---
    "sec_pairs": "نتیجه از کجا آمده است",
    "sec_pairs_hint": "به تفکیک جفت‌ارز، سودده‌ترین در بالا",
    "col_trades": "معاملات",
    "col_in_profit": "با سود",
    "col_in_loss": "با زیان",

    # --- cash ---
    "sec_cash": "واریز و برداشت در این دوره",
    "sec_cash_hint": "جابه‌جایی سرمایه خودتان — هرگز سود به حساب نمی‌آید",
    "cash_empty": "در این دوره هیچ واریز یا برداشتی ثبت نشده است.",
    "col_date": "تاریخ",
    "col_type": "نوع",
    "col_amount": "مبلغ",
    "col_recorded": "نحوه ثبت",
    "col_note": "توضیح",
    "deposit": "واریز",
    "withdrawal": "برداشت",
    "net_movement": "خالص جابه‌جایی",
    "flows_sub": "{deposits} واریز · {withdrawals} برداشت",
    "source_manual": "ثبت دستی",
    "source_detected": "تأیید یک تشخیص خودکار",

    # --- split ---
    "sec_split": "تقسیم سود",
    "sec_split_hint": "بر مبنای بازده حساب از زمان اتصال محاسبه شده است",
    "col_party": "طرف",
    "role_investor": "سرمایه‌گذار",
    "role_trader": "معامله‌گر",
    "role_programmer": "برنامه‌نویس",
}


@lru_cache(maxsize=4)
def language(code: str | None) -> Language:
    """The requested language, or English when it is not one we issue."""
    if str(code or "").lower().startswith("fa"):
        regular, bold = _register_persian_fonts()
        return Language("fa", True, regular, bold, FA_MONTHS, FA)
    return Language("en", False, "Helvetica", "Helvetica-Bold", EN_MONTHS, EN)


#: What the API accepts. Anything else falls back to English rather than 400 —
#: a statement in the wrong language is recoverable, no statement is not.
LANGUAGES = ("en", "fa")
