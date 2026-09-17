"""A TradingView export, read back in as the two files a parity fixture is.

The Strategy Tester's **List of Trades** is the only machine-readable record of
what TradingView did, and it is written for a spreadsheet rather than for us:
one row per fill leg, the money columns named after the account currency, and
every timestamp in whatever timezone the *chart* happened to be set to — which
the file does not say. A parity fixture that guesses that offset wrong is a
fixture that disagrees with the engine on every bar and blames the engine.

So the offset is **derived, not asked for**: `process_orders_on_close` fills at
the signal bar's close, so the right offset is the one where every price in the
export is a bar's close. A wrong offset matches almost nothing, which is what
makes the derivation safe to trust — and `chart_offset` refuses rather than
picks when two of them are close.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

#: Every offset a TradingView timezone can have, in seconds. Quarter-hour steps
#: because Kathmandu (+05:45) and Chatham (+12:45) are on the list.
_CANDIDATES = tuple(range(-12 * 3600, 14 * 3600 + 1, 15 * 60))

#: TradingView names its money columns after the account currency ("Price USDC",
#: "Net PnL USDT"), so they are matched by prefix. The rest are fixed.
_EXACT = {"trade": "Trade number", "type": "Type", "when": "Date and time", "signal": "Signal"}
_PREFIX = {"price": "Price", "qty": "Size (qty)", "pnl": "Net PnL"}


class TradingViewImportError(Exception):
    """The export is not the shape this reads."""


@dataclass(frozen=True, slots=True)
class Trade:
    """One TradingView trade: a scale-out slice is its own trade, as it lists it."""

    trade: int
    side: str
    signal: str
    entry_time: int
    entry_price: Decimal
    qty: Decimal
    pnl: Decimal
    #: Absent while the trade is still open at the end of the export.
    exit_time: int | None = None
    exit_price: Decimal | None = None


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "").replace(" ", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise TradingViewImportError(f"cannot read {text!r} as a number") from exc


def _seconds(text: str) -> int:
    """A chart-clock timestamp as seconds. Not UTC yet — see ``shift``."""
    try:
        return int(
            datetime.strptime(text.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp()
        )
    except ValueError as exc:
        raise TradingViewImportError(f"cannot read {text!r} as a date") from exc


def _columns(header: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, name in _EXACT.items():
        if name not in header:
            raise TradingViewImportError(
                f"no {name!r} column — this is not a List of Trades export"
            )
        found[key] = name
    for key, prefix in _PREFIX.items():
        match = [name for name in header if name.startswith(prefix)]
        if not match:
            raise TradingViewImportError(
                f"no {prefix!r} column — this is not a List of Trades export"
            )
        found[key] = match[0]
    return found


def parse(text: str) -> list[Trade]:
    """The export's two rows per trade, folded into one. Times are chart-clock."""
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        raise TradingViewImportError("the export has no rows")
    column = _columns(list(rows[0].keys()))
    entries: dict[int, dict] = {}
    exits: dict[int, dict] = {}
    for row in rows:
        number = int(_decimal(row[column["trade"]]))
        kind = row[column["type"]].strip().lower()
        if kind.startswith("entry"):
            entries[number] = row
        elif kind.startswith("exit"):
            exits[number] = row
        else:
            raise TradingViewImportError(f"trade {number}: unexpected Type {row[column['type']]!r}")
    out: list[Trade] = []
    for number in sorted(entries):
        entry = entries[number]
        exit_row = exits.get(number, {})
        side = entry[column["type"]].strip().lower().removeprefix("entry").strip()
        if side not in ("long", "short"):
            raise TradingViewImportError(f"trade {number}: unexpected side {side!r}")
        # The still-open trade prints "Open" where its exit would be, and an
        # em dash for the price. It is kept: it carries the entry TradingView
        # made, which is as much a claim about the engine as a closed one.
        closed = exit_row and exit_row[column["when"]].strip().lower() != "open"
        out.append(
            Trade(
                trade=number,
                side=side,
                signal=(exit_row or entry)[column["signal"]].strip(),
                entry_time=_seconds(entry[column["when"]]),
                entry_price=_decimal(entry[column["price"]]),
                qty=_decimal(entry[column["qty"]]),
                pnl=_decimal(entry[column["pnl"]]),
                exit_time=_seconds(exit_row[column["when"]]) if closed else None,
                exit_price=_decimal(exit_row[column["price"]]) if closed else None,
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class CandleRow:
    """One bar out of a chart-data export. UTC seconds, Decimal prices."""

    time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


#: What TradingView's "Export chart data" calls its columns, and the spellings
#: every other exporter uses. Matched case-insensitively, so a file that says
#: ``Open`` and one that says ``open`` are the same file.
_CANDLE_COLUMNS = {
    "time": ("time", "date", "datetime", "timestamp", "date and time", "open time"),
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close", "price"),
    "volume": ("volume", "vol"),
}

#: The timestamp formats seen in the wild. TradingView writes ISO 8601 with an
#: offset; a re-saved spreadsheet often drops the ``T`` or the zone.
_TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def _candle_time(text: str) -> int:
    """A bar's open time as UTC seconds, from a stamp or an epoch.

    A stamp with no zone is read as UTC rather than as local time. That is a
    decision and not a default: a bar read an hour out lines up with the wrong
    candle everywhere, and the engine takes the blame — so the importer's
    contract is "UTC, or say so in the file", and ``--tz`` shifts a chart-clock
    export on the way past.
    """
    text = text.strip()
    if not text:
        raise TradingViewImportError("a row has no timestamp")
    if text.lstrip("-").isdigit():
        value = int(text)
        # Milliseconds, as TradingView's own JSON and most exchanges use.
        return value // 1000 if value > 10_000_000_000 else value
    normalised = text.replace("Z", "+0000").replace("z", "+0000")
    # ``%z`` in 3.11 accepts ``+03:30``; older-style ``+0330`` is accepted too,
    # so both spellings of the same offset land on the same second.
    for fmt in _TIME_FORMATS:
        try:
            when = datetime.strptime(normalised, fmt)
        except ValueError:
            continue
        return int((when if when.tzinfo else when.replace(tzinfo=UTC)).timestamp())
    raise TradingViewImportError(f"cannot read {text!r} as a date")


def parse_candles(text: str, *, offset: int = 0) -> list[CandleRow]:
    """A chart-data export as bars, oldest first, de-duplicated.

    **Why this exists.** Hyperliquid sells the latest 5000 bars and no more —
    104 days at 30m — so most of a year-long TradingView run happened on bars
    the venue will never serve again, and nothing this platform can write will
    fetch them. They are not lost, though: the chart they were exported from
    still has them, and this is the door they come back in through. Every bar
    it reads goes into the archive, which keeps them for good, so the window a
    parity run can cover grows by exactly what the operator exports.

    It **interprets nothing**. Prices are copied as written, into ``Decimal``,
    and any column that is not OHLCV — a plotted series, an indicator — is
    ignored rather than rounded, renamed or averaged.

    ``offset`` moves a chart-clock export to UTC, in seconds, the same
    correction ``shift`` makes for a trade list.
    """
    rows = list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        raise TradingViewImportError("the export has no rows")

    lookup = {name.strip().lower(): name for name in rows[0]}
    column: dict[str, str] = {}
    for key, spellings in _CANDLE_COLUMNS.items():
        match = next((lookup[s] for s in spellings if s in lookup), "")
        if not match and key != "volume":
            raise TradingViewImportError(
                f"no {key!r} column — this is not a chart-data export "
                f"(found {', '.join(sorted(lookup)) or 'nothing'})"
            )
        column[key] = match

    by_time: dict[int, CandleRow] = {}
    for row in rows:
        when = _candle_time(row[column["time"]]) + offset
        raw_volume = row.get(column["volume"], "") if column["volume"] else ""
        by_time[when] = CandleRow(
            time=when,
            open=_decimal(row[column["open"]]),
            high=_decimal(row[column["high"]]),
            low=_decimal(row[column["low"]]),
            close=_decimal(row[column["close"]]),
            # A chart-data export of an index has no volume column at all, and
            # a bar with no volume is still a bar. Zero, never invented.
            volume=_decimal(raw_volume) if raw_volume.strip() else Decimal(0),
        )
    return [by_time[key] for key in sorted(by_time)]


def shift(trades: list[Trade], offset: int) -> list[Trade]:
    """The same trades with their timestamps moved from chart clock to UTC."""
    return [
        Trade(
            trade=t.trade,
            side=t.side,
            signal=t.signal,
            entry_time=t.entry_time - offset,
            entry_price=t.entry_price,
            qty=t.qty,
            pnl=t.pnl,
            exit_time=None if t.exit_time is None else t.exit_time - offset,
            exit_price=t.exit_price,
        )
        for t in trades
    ]


def _fills(trades: list[Trade]) -> list[tuple[int, Decimal]]:
    fills = [(t.entry_time, t.entry_price) for t in trades]
    fills += [(t.exit_time, t.exit_price) for t in trades if t.exit_time is not None]
    return [(when, price) for when, price in fills if price is not None]


def chart_offset(trades: list[Trade], bars, *, tolerance: Decimal = Decimal("0.00002")) -> int:
    """The chart's UTC offset in seconds, read off the prices themselves.

    ``tolerance`` is relative, and wide enough to swallow the slippage ticks the
    export has already had applied to it. Raises rather than guesses when no
    offset explains the prices, or when two of them do.
    """
    closes = {bar.time: bar.close for bar in bars}
    fills = _fills(trades)
    if not fills:
        raise TradingViewImportError("the export has no priced fills to align")
    scores: list[tuple[int, int, int]] = []
    for offset in _CANDIDATES:
        seen = hit = 0
        for when, price in fills:
            close = closes.get(when - offset)
            if close is None:
                continue
            seen += 1
            if abs(price - close) <= tolerance * abs(close):
                hit += 1
        scores.append((hit, seen, offset))
    scores.sort(reverse=True)
    best, seen, offset = scores[0]
    if seen == 0 or best < seen * 0.9 or best < 4:
        raise TradingViewImportError(
            "no chart timezone explains these prices against these bars — are they "
            "the same symbol, interval and venue the strategy was tested on?"
        )
    runner_up = max((hit for hit, _, other in scores if other != offset), default=0)
    if runner_up > best * 0.5:
        raise TradingViewImportError("two chart timezones explain these prices equally — pass --tz")
    return offset


FIXTURE_HEADER = (
    "trade,side,signal,entry_time_utc,entry_price,exit_time_utc,exit_price,qty,pnl_usdc"
)


def _stamp(when: int | None) -> str:
    return "" if when is None else datetime.fromtimestamp(when, UTC).strftime("%Y-%m-%d %H:%M")


def fixture_csv(trades: list[Trade]) -> str:
    """The list as a parity fixture reads it: UTC, one row per trade."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FIXTURE_HEADER.split(","))
    for t in trades:
        writer.writerow(
            [
                t.trade,
                t.side,
                t.signal,
                _stamp(t.entry_time),
                t.entry_price,
                _stamp(t.exit_time),
                "" if t.exit_price is None else t.exit_price,
                t.qty,
                t.pnl,
            ]
        )
    return out.getvalue()


def bars_csv(bars) -> str:
    """The bars as served, in the column order every fixture here uses."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["time", "open", "high", "low", "close", "volume"])
    for bar in bars:
        writer.writerow([bar.time, bar.open, bar.high, bar.low, bar.close, bar.volume])
    return out.getvalue()
