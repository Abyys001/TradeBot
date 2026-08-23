"""The downloadable receipt: one account, one period, as a PDF.

This is the only artefact of the platform that leaves it. A partner reads it
without the panel in front of them, so it has to be self-explanatory and it has
to be honest about three things the screen can leave implicit:

* **The bot traded, not a person.** Every entry, stop, target and close in the
  table below was routed automatically by TradeBot on the admin's single
  action, fanned out to this account among others. The wording says so rather
  than leaving the reader to assume a human placed each order.
* **A period result is not a lifetime result.** Legs are counted in the period
  they were *realised* in. Whatever the account is worth today, and what it has
  returned since it was connected, are printed under their own heading and
  never folded into the period's number.
* **Unknown is unknown.** A leg the exchange never priced prints an em dash and
  is counted in neither the wins nor the losses, exactly as it is on screen.

**No percentage appears anywhere in this document** — not a return, not a win
rate, not a share of the split. The statement answers "how much", in money, and
every ratio the panel shows is deliberately left on the panel: a percentage on
paper invites a reader to annualise it, compare it against an account whose
capital moved mid-period, or read a share of profit as a promise. Money is the
figure the recipient can check against their own balance, so money is the only
figure printed. Adding a column here means asking whether it is a percentage
before anything else.

Issued in **English or Persian**, chosen at download time — the recipient's
language, not the operator's. Everything the document says lives in
``statement_text.py``; this module is layout only, and it mirrors itself when
the language reads right-to-left: the mark moves to the right of the band,
every table's columns run the other way, and paragraphs are wrapped, shaped and
reordered before ReportLab is allowed near them.

Layout is ReportLab platypus so the trade table can flow over as many pages as
it needs; the header band, the mark and the page numbers are drawn on the
canvas underneath it. No image asset is embedded — the logo is the same
geometry as ``frontend/public/favicon.svg``, redrawn in vectors, so the two can
never drift apart into different logos.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from apps.accounts.statement_text import Language, language
from apps.core.money import ZERO, D

# The panel's own palette, so the paper and the screen are recognisably one
# product. Values mirror the favicon and the Tailwind theme.
INK = colors.HexColor("#0e121a")
INK_SOFT = colors.HexColor("#4a5262")
INK_FAINT = colors.HexColor("#8b93a3")
BRAND = colors.HexColor("#4660be")
BRAND_LIGHT = colors.HexColor("#7c9cff")
TEAL = colors.HexColor("#3bc9d8")
LONG = colors.HexColor("#1a7f5a")
SHORT = colors.HexColor("#b3312f")
LINE = colors.HexColor("#dfe3ea")
WASH = colors.HexColor("#f4f6fa")
TOTAL = colors.HexColor("#e8ecf6")

PAGE = A4
MARGIN = 14 * mm
HEADER_H = 26 * mm
FOOTER_H = 14 * mm
CONTENT_W = PAGE[0] - 2 * MARGIN

#: A statement is a document, not a paginator: the reader wants every trade in
#: the window. This only exists so a pathological window cannot try to render a
#: hundred thousand rows into one response.
ROW_LIMIT = 2000

TAGS = re.compile(r"</?[a-zA-Z][^>]*>")


def esc(value: Any) -> str:
    """Anything from the database into paragraph-safe text."""
    return (
        str("" if value is None else value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# --- numbers --------------------------------------------------------------
#
# Latin digits in both languages, deliberately: the recipient checks these
# against the exchange's own screen, which shows Latin digits, and the panel
# takes the same decision for the same reason (``composables/useFormat.ts``).


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return D(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def money(value, dp: int = 2, signed: bool = False) -> str:
    """A USD figure with thousands separators. ``None`` is an em dash, not 0."""
    amount = _dec(value)
    if amount is None:
        return "—"
    quant = amount.quantize(Decimal(1).scaleb(-dp))
    sign = "-" if quant < ZERO else ("+" if signed and quant > ZERO else "")
    return f"{sign}{abs(quant):,.{dp}f}"


def usd(value, signed: bool = False) -> str:
    text = money(value, 2, signed)
    return text if text == "—" else (text[0] + "$" + text[1:] if text[0] in "+-" else "$" + text)


def qty(value) -> str:
    """A size printed at the precision it actually has, never padded to eight."""
    amount = _dec(value)
    if amount is None:
        return "—"
    return format(amount.normalize(), "f")


def price(value) -> str:
    amount = _dec(value)
    if amount is None:
        return "—"
    dp = 2 if abs(amount) >= 100 else (4 if abs(amount) >= 1 else 6)
    return f"{amount.quantize(Decimal(1).scaleb(-dp)):,.{dp}f}"


def tone(value) -> colors.Color:
    amount = _dec(value)
    if amount is None or amount == ZERO:
        return INK
    return LONG if amount > ZERO else SHORT


# --- the mark -------------------------------------------------------------

def draw_logo(c, x: float, y: float, size: float) -> None:
    """The fan-out mark: one source, three destinations. Same geometry as
    ``frontend/public/favicon.svg`` — one action, many accounts."""
    s = size / 64.0
    c.saveState()
    c.translate(x, y + size)
    c.scale(s, -s)  # SVG's y-down space, so the path numbers are the file's

    c.setFillColor(INK)
    c.roundRect(0, 0, 64, 64, 14, stroke=0, fill=1)

    c.setLineWidth(3)
    c.setLineCap(1)
    for path, colour in (
        ([(20, 32), (33, 32), (33, 16), (44, 16)], BRAND),
        ([(20, 32), (44, 32)], BRAND_LIGHT),
        ([(20, 32), (33, 32), (33, 48), (44, 48)], BRAND),
    ):
        c.setStrokeColor(colour)
        p = c.beginPath()
        p.moveTo(*path[0])
        for point in path[1:]:
            p.lineTo(*point)
        c.drawPath(p, stroke=1, fill=0)

    for cx, cy, r, colour in (
        (20, 32, 6, BRAND_LIGHT),
        (45, 16, 4, BRAND_LIGHT),
        (45, 32, 4, TEAL),
        (45, 48, 4, BRAND_LIGHT),
    ):
        c.setFillColor(colour)
        c.circle(cx, cy, r, stroke=0, fill=1)
    c.restoreState()


# --- page furniture -------------------------------------------------------

class StatementDoc(BaseDocTemplate):
    """Draws the band, the mark and the page numbers under the flowables.

    Two passes: the first counts the pages so the footer can say "1 of 4"
    rather than "1", which is what makes a printed statement checkable.
    """

    def __init__(self, buffer, *, language: Language, meta: dict[str, str]):
        super().__init__(
            buffer,
            pagesize=PAGE,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN + HEADER_H,
            bottomMargin=MARGIN + FOOTER_H,
            title=meta["title"],
            author="TradeBot",
            subject=meta["subject"],
            creator="TradeBot",
            # ReportLab writes this straight into the catalogue as ``/Lang``,
            # which is what tells a screen reader how to pronounce the page.
            lang=language.code,
        )
        # Not ``self.lang``: ReportLab writes a document attribute of that
        # name into the PDF catalogue as ``/Lang``, and it must be a string.
        self.language = language
        self.meta = meta
        self.total_pages = 0
        frame = Frame(
            MARGIN,
            MARGIN + FOOTER_H,
            CONTENT_W,
            PAGE[1] - 2 * MARGIN - HEADER_H - FOOTER_H,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [PageTemplate(id="statement", frames=[frame], onPage=self._furniture)]
        )

    def build(self, story):  # noqa: A003 - platypus' own name
        """``story`` is a *factory*, called once per pass — not a list.

        Platypus flowables carry state across a build: one that has to move to
        the next page is marked ``_postponed``, and the mark is only cleared
        when it is finally drawn. Handing the same objects to the counting pass
        and then to the real one makes the second build treat that mark as "I
        already gave you a page and you still did not fit" and abort the whole
        document. So each pass gets its own flowables.
        """
        probe = StatementDoc(BytesIO(), language=self.language, meta=self.meta)
        probe.total_pages = -1  # suppress "of N" while counting
        BaseDocTemplate.build(probe, story())
        self.total_pages = probe.page
        BaseDocTemplate.build(self, story())

    def _furniture(self, c, doc) -> None:
        """The band and the footer, mirrored when the language is.

        ``near``/``far`` are the margin the eye starts at and the one it ends
        at, so the same code draws the identity block against the reader's own
        starting edge in both languages.
        """
        lang, meta = self.language, self.meta
        top = PAGE[1] - MARGIN
        near, far = (PAGE[0] - MARGIN, MARGIN) if lang.rtl else (MARGIN, PAGE[0] - MARGIN)
        text_near = c.drawRightString if lang.rtl else c.drawString
        text_far = c.drawString if lang.rtl else c.drawRightString
        logo_x = near - 15 * mm if lang.rtl else near
        title_x = near - 19 * mm if lang.rtl else near + 19 * mm

        c.saveState()
        draw_logo(c, logo_x, top - 15 * mm, 15 * mm)

        c.setFillColor(INK)
        c.setFont(lang.bold, 15)
        text_near(title_x, top - 6.5 * mm, meta["brand"])
        c.setFillColor(INK_FAINT)
        c.setFont(lang.regular, 7.4)
        text_near(title_x, top - 10.6 * mm, meta["tagline"])
        text_near(title_x, top - 14 * mm, meta["issued"])

        c.setFillColor(BRAND)
        c.setFont(lang.bold, 10)
        text_far(far, top - 6.5 * mm, meta["heading"])
        c.setFillColor(INK_SOFT)
        c.setFont(lang.regular, 8)
        text_far(far, top - 11 * mm, meta["account"])
        c.setFillColor(INK_FAINT)
        c.setFont(lang.regular, 7.4)
        text_far(far, top - 14.6 * mm, meta["period"])

        c.setStrokeColor(BRAND)
        c.setLineWidth(1.2)
        c.line(MARGIN, top - 19 * mm, PAGE[0] - MARGIN, top - 19 * mm)

        bottom = MARGIN + FOOTER_H
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(MARGIN, bottom, PAGE[0] - MARGIN, bottom)
        c.setFillColor(INK_FAINT)
        c.setFont(lang.regular, 6.8)
        text_near(near, bottom - 4.5 * mm, meta["footer"])
        text_near(near, bottom - 8 * mm, meta["ref"])
        page = (
            lang.t("page", page=doc.page)
            if self.total_pages <= 0
            else lang.t("page_of", page=doc.page, total=self.total_pages)
        )
        text_far(far, bottom - 4.5 * mm, lang.shape(page))
        c.restoreState()


# --- one language's paragraph styles --------------------------------------

class Sheet:
    """Every style the document uses, in one language's font and direction."""

    def __init__(self, lang: Language):
        self.lang = lang
        base = dict(fontName=lang.regular, fontSize=8.5, leading=11,
                    textColor=INK, alignment=lang.start)
        # Persian needs the extra leading: Vazirmatn's ascenders and the marks
        # above them collide at Helvetica's line height.
        if lang.rtl:
            base["leading"] = 13

        def style(name: str, **kw) -> ParagraphStyle:
            return ParagraphStyle(name, **{**base, **kw})

        # Spelled out rather than derived through ``parent``: every style here
        # sets the same attributes ``base`` does, so a parent's value would be
        # overridden by the base one every time and never take effect.
        lead = base["leading"]
        note = dict(textColor=INK_FAINT, fontSize=7.2, leading=lead - 1.5)
        cell = dict(fontSize=7.2, leading=lead - 2)
        head = dict(fontName=lang.bold, fontSize=7, leading=lead - 2, textColor=colors.white)

        self.body = style("body")
        self.muted = style("muted", textColor=INK_SOFT, fontSize=8, leading=lead - 0.5)
        self.note = style("note", **note)
        self.hint = style("hint", **note, alignment=lang.end)
        self.h1 = style("h1", fontName=lang.bold, fontSize=13, leading=16)
        self.h2 = style("h2", fontName=lang.bold, fontSize=9, leading=12, textColor=BRAND)
        self.cell = style("cell", **cell)
        self.cell_end = style("cell_end", **cell, alignment=lang.end)
        self.head = style("head", **head)
        self.head_end = style("head_end", **head, alignment=lang.end)
        self.big = style("big", fontName=lang.bold, fontSize=12, leading=14)
        self.label = style("label", fontName=lang.bold, fontSize=6.6,
                           leading=8.5, textColor=INK_FAINT)
        self.center = style("center", alignment=TA_CENTER, fontSize=8,
                            leading=lead, textColor=INK_SOFT)


# --- the document ---------------------------------------------------------

TRADE_COLS = [7, 23, 20, 17, 18, 20, 20, 19, 23]
OPEN_COLS = [7, 23, 22, 19, 20, 24, 24, 22, 21]
FAIL_COLS = [7, 25, 22, 20, 108]
CASH_COLS = [26, 24, 30, 32, 70]
PAIR_COLS = [46, 26, 26, 26, 40]
SPLIT_COLS = [110, 50]

STATUS = {"active": "status_active", "paused": "status_paused", "error": "status_error"}
SOURCE = {"manual": "source_manual", "detected": "source_detected"}


def _mm(widths: list[float]) -> list[float]:
    """Column widths in mm, rescaled to exactly fill the frame."""
    total = sum(widths)
    return [w / total * CONTENT_W for w in widths]


class Statement:
    """One account's windowed report, laid out in one language.

    Every method returns platypus flowables; nothing here touches the database
    or decides a number — the arithmetic is ``report.statement_report``'s and
    the words are ``statement_text``'s.
    """

    def __init__(self, data: dict[str, Any], lang: str | None = None):
        self.data = data
        self.lang = language(lang)
        self.sheet = Sheet(self.lang)

    # --- text -------------------------------------------------------------

    def t(self, key: str, **kwargs) -> str:
        return self.lang.t(key, **kwargs)

    def txt(self, text: Any, style: ParagraphStyle) -> Paragraph:
        """A short single-line string — a cell, a label, a tile value."""
        return Paragraph(esc(self.lang.shape(str(text))), style)

    def para(self, text: str, style: ParagraphStyle, width: float = CONTENT_W) -> Paragraph:
        """A paragraph that will wrap.

        Left-to-right is ReportLab's own job. Right-to-left is not: the visual
        order has to be produced here, and it has to be produced **per line**,
        because reordering the whole paragraph and then letting ReportLab break
        it puts the closing words on the opening line. So the text is wrapped
        against the same metrics ReportLab will use, then each line is shaped
        and reordered on its own. Inline emphasis is dropped on that path —
        rebuilding tag boundaries across a reordered line is a way to move a
        tag onto the wrong word, and the Persian copy carries its emphasis in
        its punctuation instead.
        """
        if not self.lang.rtl:
            return Paragraph(text, style)
        plain = TAGS.sub("", text)
        lines = self._wrap(plain, style, width)
        return Paragraph("<br/>".join(esc(self.lang.shape(line)) for line in lines), style)

    def _wrap(self, text: str, style: ParagraphStyle, width: float) -> list[str]:
        """Greedy line breaking against the font the paragraph will be set in."""
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and stringWidth(candidate, style.fontName, style.fontSize) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or [""]

    def when(self, value, *, time: bool = True, short: bool = False) -> str:
        """A date the way both languages read it: day, month name, year.

        The calendar stays Gregorian in Persian too — the exchange's own record
        is Gregorian, and a statement that cannot be lined up against it is not
        checkable. Only the month's name is translated.
        """
        # Some of the report is model instants and some is serializer output,
        # where the same field is already an ISO string. Both arrive here.
        if isinstance(value, str):
            value = parse_datetime(value)
        if value is None:
            return "—"
        local = timezone.localtime(value)
        year = local.year % 100 if short else local.year
        text = f"{local.day:02d} {self.lang.month(local.month)} {year}"
        return f"{text} {local:%H:%M}" if time else text

    # --- building blocks --------------------------------------------------

    def section(self, title: str, hint: str = "") -> Table:
        """A ruled section heading: the title, and one line saying what it means."""
        cells = [
            self.txt(title, self.sheet.h2),
            self.para(hint, self.sheet.hint, CONTENT_W * 0.5),
        ]
        widths = [CONTENT_W * 0.5, CONTENT_W * 0.5]
        if self.lang.rtl:
            cells.reverse()
        table = Table([cells], colWidths=widths)
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, BRAND),
                ]
            )
        )
        return table

    def facts(self, pairs: list[tuple[str, str]], columns: int = 3) -> Table:
        """A label/value grid — the identity and connection block."""
        rows: list[list[Any]] = []
        for index in range(0, len(pairs), columns):
            chunk = list(pairs[index : index + columns])
            chunk += [("", "")] * (columns - len(chunk))
            if self.lang.rtl:
                chunk.reverse()
            rows.append([self.txt(label, self.sheet.label) for label, _ in chunk])
            rows.append([self.txt(value or "—", self.sheet.body) for _, value in chunk])
        table = Table(rows, colWidths=[CONTENT_W / columns] * columns)
        # The gutter goes on the side the next column is on.
        sides = ("RIGHTPADDING", "LEFTPADDING")
        near, far = sides if self.lang.rtl else sides[::-1]
        style = [
            (near, (0, 0), (-1, -1), 0),
            (far, (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for index in range(len(rows)):
            style.append(("TOPPADDING", (0, index), (-1, index), 6 if index % 2 == 0 else 1))
        table.setStyle(TableStyle(style))
        return table

    def tiles(self, cells: list[tuple[str, str, str, colors.Color]]) -> Table:
        """The headline numbers, boxed. (label, value, sub, colour)."""
        row = []
        for label, value, sub, colour in cells:
            inner = Table(
                [
                    [self.txt(label, self.sheet.label)],
                    [self.txt(value, ParagraphStyle("v", parent=self.sheet.big, textColor=colour))],
                    [self.para(sub, self.sheet.note, CONTENT_W / len(cells) - 16)],
                ]
            )
            inner.setStyle(
                TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, 0), 7),
                        ("TOPPADDING", (0, 1), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -2), 1),
                        ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
                    ]
                )
            )
            row.append(inner)
        if self.lang.rtl:
            row.reverse()
        width = CONTENT_W / len(row)
        table = Table([row], colWidths=[width] * len(row))
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
                    ("BACKGROUND", (0, 0), (-1, -1), WASH),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return table

    def cell(self, text: Any, numeric: bool = False, colour: colors.Color | None = None,
             bold: bool = False) -> Paragraph:
        style = self.sheet.cell_end if numeric else self.sheet.cell
        if colour is not None or bold:
            style = ParagraphStyle(
                "c",
                parent=style,
                textColor=colour or style.textColor,
                fontName=self.lang.bold if bold else style.fontName,
            )
        return self.txt(text, style)

    def grid(self, header: list[str], body: list[list[Any]], widths: list[float],
             numeric: set[int] | None = None, zebra: bool = True) -> Table:
        """A data table with the brand header band and a repeating header row.

        Mirrored for a right-to-left language, columns and all: a Persian table
        whose first column sits on the left reads back-to-front, however
        correct each cell is on its own.
        """
        numeric = numeric or set()
        head = [
            self.txt(text, self.sheet.head_end if index in numeric else self.sheet.head)
            for index, text in enumerate(header)
        ]
        rows = [head, *body]
        if self.lang.rtl:
            rows = [list(reversed(row)) for row in rows]
            widths = list(reversed(widths))
        table = Table(rows, colWidths=widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ]
        if zebra:
            for index in range(1, len(body) + 1):
                if index % 2 == 0:
                    style.append(("BACKGROUND", (0, index), (-1, index), WASH))
        table.setStyle(TableStyle(style))
        return table

    def banner(self, cells: list[Paragraph], widths: list[float]) -> Table:
        """A summed row under a table: same columns, brand wash, boxed."""
        if self.lang.rtl:
            cells = list(reversed(cells))
            widths = list(reversed(widths))
        table = Table([cells], colWidths=widths)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), TOTAL),
                    ("BOX", (0, 0), (-1, -1), 0.6, BRAND),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def empty(self, message: str) -> Table:
        table = Table([[self.para(message, self.sheet.center, CONTENT_W - 20)]],
                      colWidths=[CONTENT_W])
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                    ("BACKGROUND", (0, 0), (-1, -1), WASH),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return table

    # --- the period -------------------------------------------------------

    def period_label(self) -> str:
        period = self.data["period"]
        start, end = period.get("start"), period.get("end")
        if start is None and end is None:
            return self.t("period_all")
        if start is None:
            return self.t("period_until", end=self.when(end, time=False))
        if end is None:
            return self.t("period_from", start=self.when(start, time=False))
        # ``end`` is exclusive; the reader thinks in whole days, so name the
        # last day that is actually inside the window rather than the boundary
        # after it.
        return self.t(
            "period_range",
            start=self.when(start, time=False),
            end=self.when(end - timedelta(seconds=1), time=False),
        )

    def side(self, row: dict) -> Paragraph:
        long = row["side"] == "long"
        return self.cell(
            self.t("leverage", side=self.t("side_long" if long else "side_short"),
                   leverage=row["leverage"]),
            colour=LONG if long else SHORT,
        )

    # --- the sections -----------------------------------------------------

    def identity(self) -> list[Any]:
        account = self.data["account"]
        testnet = account.get("testnet")
        exchange = str(account["exchange_label"])
        return [
            self.txt(account["label"], self.sheet.h1),
            Spacer(1, 3),
            self.para(
                self.t(
                    "account_line",
                    exchange=exchange + (self.t("testnet_suffix") if testnet else ""),
                    period=self.period_label(),
                ),
                self.sheet.muted,
            ),
            Spacer(1, 8),
            self.facts(
                [
                    (self.t("fact_exchange"),
                     exchange + (self.t("testnet_tag") if testnet else "")),
                    (self.t("fact_connected"), self.when(self.data["connected_at"])),
                    (self.t("fact_trading_since"), self.when(self.data["eligible_from"])),
                    (self.t("fact_state"),
                     self.t(STATUS.get(str(account["status"]), "status_active"))),
                    (self.t("fact_fingerprint"), account.get("key_fingerprint") or "—"),
                    (self.t("fact_asset"), self.data["ledger"]["asset"]),
                ]
            ),
            Spacer(1, 9),
            self.para(self.t("intro"), self.sheet.muted),
        ]

    def headline(self) -> list[Any]:
        trading = self.data["trading"]
        ledger = self.data["ledger"]
        realised = trading["realised_pnl"]
        factor = trading["profit_factor"]
        return [
            self.section(self.t("sec_result"), self.t("sec_result_hint")),
            Spacer(1, 6),
            self.tiles(
                [
                    (self.t("tile_pnl"), usd(realised, signed=True),
                     self.t("tile_pnl_sub", count=trading["scored"]), tone(realised)),
                    (self.t("tile_trades"), str(trading["scored"]),
                     self.t("tile_trades_sub", wins=trading["wins"],
                            losses=trading["losses"]), INK),
                    (self.t("tile_extremes"),
                     f"{usd(trading['best'], True)} / {usd(trading['worst'], True)}",
                     self.t("tile_extremes_sub"), INK),
                    (self.t("tile_average"), usd(trading["average_pnl"], signed=True),
                     self.t("tile_average_sub"), tone(trading["average_pnl"])),
                ]
            ),
            Spacer(1, 5),
            self.tiles(
                [
                    (self.t("tile_volume"), usd(trading["volume"]),
                     self.t("tile_volume_sub"), INK),
                    (self.t("tile_factor"), money(factor) if factor else "—",
                     self.t("tile_factor_sub"), INK),
                    (self.t("tile_cash"), usd(self.data["flows"]["net"], signed=True),
                     self.t("tile_cash_sub", count=self.data["flows"]["count"]), INK_SOFT),
                ]
            ),
            Spacer(1, 10),
            self.section(self.t("sec_whole"), self.t("sec_whole_hint")),
            Spacer(1, 6),
            self.tiles(
                [
                    (self.t("tile_balance"), usd(ledger["current_balance"]),
                     self.t("tile_balance_sub",
                            when=self.when(self.data["account"].get("last_balance_at"))), INK),
                    (self.t("tile_invested"), usd(ledger["net_invested"]),
                     self.t("tile_invested_sub", deposits=money(ledger["deposits"]),
                            withdrawals=money(ledger["withdrawals"])), INK),
                    (self.t("tile_since"), usd(ledger["pnl"], signed=True),
                     self.t("tile_since_sub"), tone(ledger["pnl"])),
                ]
            ),
        ]

    def trades(self) -> list[Any]:
        rows = self.data["closed"]
        trading = self.data["trading"]
        hint = self.t("sec_trades_hint", count=len(rows)) + (
            self.t("sec_trades_capped", limit=ROW_LIMIT) if len(rows) > ROW_LIMIT else ""
        )
        story: list[Any] = [self.section(self.t("sec_trades"), hint), Spacer(1, 5)]
        if not rows:
            story.append(self.empty(self.t("trades_empty")))
            return story

        body = []
        for index, row in enumerate(rows[:ROW_LIMIT], start=1):
            colour = tone(row["pnl"])
            body.append(
                [
                    self.cell(index, True),
                    self.cell(self.when(row["closed_at"], short=True)),
                    self.cell(row["symbol"], bold=True),
                    self.side(row),
                    self.cell(qty(row["qty"]), True),
                    self.cell(price(row["entry_price"]), True),
                    self.cell(price(row["exit_price"]), True),
                    self.cell(usd(row["margin"]), True),
                    self.cell(usd(row["pnl"], signed=True), True, colour, bold=True),
                ]
            )

        realised = sum((D(row["pnl"]) for row in rows if row["pnl"] is not None), ZERO)
        margin = sum((D(row["margin"]) for row in rows if row["margin"] is not None), ZERO)
        story += [
            self.grid(
                [self.t("col_index"), self.t("col_closed"), self.t("col_pair"),
                 self.t("col_direction"), self.t("col_size"), self.t("col_entry"),
                 self.t("col_exit"), self.t("col_margin"), self.t("col_pnl")],
                body,
                _mm(TRADE_COLS),
                numeric={0, 4, 5, 6, 7, 8},
            ),
            Spacer(1, 3),
            self.banner(
                [
                    self.cell(self.t("period_total"), bold=True),
                    self.cell(usd(margin), True),
                    self.cell(usd(realised, signed=True), True, tone(realised), bold=True),
                ],
                _mm([sum(TRADE_COLS[:7]), TRADE_COLS[7], TRADE_COLS[8]]),
            ),
        ]
        if trading["scored"] != len(rows):
            story += [
                Spacer(1, 3),
                self.para(
                    self.t("unpriced_note", count=len(rows) - trading["scored"]),
                    self.sheet.note,
                ),
            ]
        return story

    def open_positions(self) -> list[Any]:
        rows = self.data["open"]
        if not rows:
            return []
        body = [
            [
                self.cell(index, True),
                self.cell(self.when(row["opened_at"], short=True)),
                self.cell(row["symbol"], bold=True),
                self.side(row),
                self.cell(qty(row["qty"]), True),
                self.cell(price(row["entry_price"]), True),
                self.cell(price(row["stop_loss"]), True),
                self.cell(price(row["take_profit"]), True),
                self.cell(usd(row["margin"]), True),
            ]
            for index, row in enumerate(rows, start=1)
        ]
        return [
            self.section(self.t("sec_open"), self.t("sec_open_hint")),
            Spacer(1, 5),
            self.grid(
                [self.t("col_index"), self.t("col_opened"), self.t("col_pair"),
                 self.t("col_direction"), self.t("col_size"), self.t("col_entry"),
                 self.t("col_stop"), self.t("col_target"), self.t("col_margin")],
                body,
                _mm(OPEN_COLS),
                numeric={0, 4, 5, 6, 7, 8},
            ),
        ]

    def failures(self) -> list[Any]:
        rows = self.data["failed"]
        if not rows:
            return []
        body = [
            [
                self.cell(index, True),
                self.cell(self.when(row["opened_at"], short=True)),
                self.cell(row["symbol"], bold=True),
                self.side(row),
                self.cell(row["error"] or row["error_code"] or self.t("not_routed"),
                          colour=INK_SOFT),
            ]
            for index, row in enumerate(rows, start=1)
        ]
        return [
            self.section(self.t("sec_failed"), self.t("sec_failed_hint")),
            Spacer(1, 5),
            self.grid(
                [self.t("col_index"), self.t("col_when"), self.t("col_pair"),
                 self.t("col_direction"), self.t("col_reason")],
                body,
                _mm(FAIL_COLS),
                numeric={0},
            ),
            Spacer(1, 3),
            self.para(self.t("failed_note"), self.sheet.note),
        ]

    def pairs(self) -> list[Any]:
        rows = self.data["symbols"]
        if not rows:
            return []
        body = []
        for row in rows:
            losses = row["legs"] - row["wins"]
            body.append(
                [
                    self.cell(row["symbol"], bold=True),
                    self.cell(row["legs"], True),
                    self.cell(row["wins"], True, LONG),
                    self.cell(losses, True, SHORT if losses else INK),
                    self.cell(usd(row["pnl"], signed=True), True, tone(row["pnl"]), bold=True),
                ]
            )
        return [
            self.section(self.t("sec_pairs"), self.t("sec_pairs_hint")),
            Spacer(1, 5),
            self.grid(
                [self.t("col_pair"), self.t("col_trades"), self.t("col_in_profit"),
                 self.t("col_in_loss"), self.t("col_pnl")],
                body,
                _mm(PAIR_COLS),
                numeric={1, 2, 3, 4},
            ),
        ]

    def cash(self) -> list[Any]:
        movements = self.data["movements"]
        flows = self.data["flows"]
        story: list[Any] = [
            self.section(self.t("sec_cash"), self.t("sec_cash_hint")),
            Spacer(1, 5),
        ]
        if not movements:
            story.append(self.empty(self.t("cash_empty")))
            return story

        body = []
        for movement in movements:
            deposit = movement["kind"] == "deposit"
            amount = D(movement["amount"])
            source = movement.get("source")
            body.append(
                [
                    self.cell(self.when(movement["occurred_at"], time=False)),
                    self.cell(self.t("deposit" if deposit else "withdrawal"),
                              colour=LONG if deposit else SHORT, bold=True),
                    self.cell(usd(amount if deposit else -amount, signed=True), True,
                              LONG if deposit else SHORT),
                    self.cell(self.t(SOURCE[source]) if source in SOURCE
                              else (movement.get("source_label") or "—")),
                    self.cell(movement.get("note") or "—", colour=INK_SOFT),
                ]
            )
        body.append(
            [
                self.cell(self.t("net_movement"), bold=True),
                self.cell(""),
                self.cell(usd(flows["net"], signed=True), True, tone(flows["net"]), bold=True),
                self.cell(""),
                self.cell(self.t("flows_sub", deposits=money(flows["deposits"]),
                                 withdrawals=money(flows["withdrawals"])), colour=INK_SOFT),
            ]
        )
        table = self.grid(
            [self.t("col_date"), self.t("col_type"), self.t("col_amount"),
             self.t("col_recorded"), self.t("col_note")],
            body,
            _mm(CASH_COLS),
            numeric={2},
        )
        table.setStyle(TableStyle([("BACKGROUND", (0, len(body)), (-1, len(body)), TOTAL)]))
        story.append(table)
        return story

    def split(self) -> list[Any]:
        """Who the profit belongs to — in money only.

        The share each party is on is a percentage and stays off the paper; the
        amount is the part the recipient can check against their own balance.
        """
        ledger = self.data["ledger"]
        profit = _dec(ledger["pnl"])
        if profit is None or profit <= ZERO:
            return []
        body = [
            [
                self.cell(self.t(f"role_{role}"), bold=True),
                self.cell(usd(ledger["shares"][role], signed=True), True, LONG, bold=True),
            ]
            for role in ("investor", "trader", "programmer")
            if role in self.data["split"]
        ]
        if not body:
            return []
        return [
            self.section(self.t("sec_split"), self.t("sec_split_hint")),
            Spacer(1, 5),
            self.grid(
                [self.t("col_party"), self.t("col_amount")],
                body,
                _mm(SPLIT_COLS),
                numeric={1},
            ),
        ]

    def notes(self) -> list[Any]:
        story: list[Any] = [self.section(self.t("sec_notes")), Spacer(1, 5)]
        for index, text in enumerate(self.lang.copy["notes"], start=1):
            numbered = (
                f"{index}.  {text}"
                if self.lang.rtl
                else f"<b>{index}.</b>&nbsp;&nbsp;{text}"
            )
            story += [self.para(numbered, self.sheet.note), Spacer(1, 3)]
        return story

    # --- the whole document -----------------------------------------------

    def story(self) -> list[Any]:
        story: list[Any] = [*self.identity(), Spacer(1, 10), *self.headline(),
                            Spacer(1, 10), *self.trades()]
        for block in (self.open_positions(), self.failures(), self.pairs(),
                      self.cash(), self.split()):
            if block:
                # A heading is not a section. Left to fall where it lands it
                # ends the page alone and the table it names opens the next
                # one, which reads as an empty section followed by an unlabelled
                # table — so demand room for the heading plus its first rows.
                story += [Spacer(1, 10), CondPageBreak(64), *block]
        return [*story, Spacer(1, 12), KeepTogether(self.notes())]

    def meta(self) -> dict[str, str]:
        """The canvas furniture, pre-shaped — the canvas draws, it does not lay out."""
        issued = timezone.localtime()
        account = self.data["account"]
        period = self.period_label()
        shape = self.lang.shape
        return {
            "title": self.t("meta_title", label=account["label"]),
            "subject": self.t("meta_subject", label=account["label"], period=period),
            "brand": shape(self.t("brand")),
            "tagline": shape(self.t("tagline")),
            "heading": shape(self.t("doc_title")),
            "account": shape(str(account["label"])),
            "period": shape(period),
            "issued": shape(self.t("issued", when=self.when(issued))),
            "footer": shape(self.t("footer")),
            "ref": shape(self.t("ref", ref=f"{issued:%Y%m%d-%H%M}-A{account['id']}")),
        }

    def render(self) -> bytes:
        buffer = BytesIO()
        StatementDoc(buffer, language=self.lang, meta=self.meta()).build(self.story)
        return buffer.getvalue()


def build_statement_pdf(data: dict[str, Any], lang: str | None = None) -> bytes:
    """Render one account's windowed report as the PDF the panel downloads."""
    return Statement(data, lang).render()


def statement_filename(data: dict[str, Any], lang: str | None = None) -> str:
    """An ASCII filename that names the account, the period and the language.

    The language is in the name because both files are legitimate and an
    operator sending one to a partner should not have to open it to tell which
    of the two is which.
    """
    statement = Statement(data, lang)
    account = data["account"]
    slug = "".join(
        ch if ch.isalnum() else "-" for ch in str(account["label"])
    ).strip("-").lower() or f"account-{account['id']}"
    period = data["period"]
    local = timezone.localtime
    span = (
        f"{local(period['start']):%Y-%m-%d}-to-{local(period['end']):%Y-%m-%d}"
        if period.get("start") and period.get("end")
        else "all-time"
    )
    return f"tradebot-statement-{slug}-{span}-{statement.lang.code}.pdf"
