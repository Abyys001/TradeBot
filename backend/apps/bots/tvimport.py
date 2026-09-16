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
