"""``python manage.py import_candles <chart-data.csv> --symbol ZECUSDC --interval 30m``.

The archive's other door. Every other way bars get in — the chart's poll, the
WebSocket, a backtest's download, a bot's feed — asks an exchange, and an
exchange answers only as far back as it feels like: Hyperliquid sells the
latest 5000 bars, which is 104 days at 30m, and its S3 archive publishes no
candles at all. So most of a TradingView year is on bars no request will ever
return, and the parity fixture says as much in writing: 60 of the admin's 86
trades predate any bar the venue still holds.

This is how those bars come back. TradingView's **Export chart data** writes
the OHLCV it drew, and this reads that file straight into
``exchanges.candlestore`` — the same table, the same rules, the same unique
key. Nothing downstream learns where a bar came from beyond its ``exchange``
label, so a backtest, a warm-up and a chart all deepen together.

**It copies; it does not interpret.** No resampling, no gap filling, no
rounding to anybody's tick. A row that is already stored is left alone, because
the archive's first rule is that settled history does not change.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.bots import tvimport
from apps.exchanges import candlestore
from apps.exchanges.base import MarketType
from apps.exchanges.feed_base import INTERVALS, Candle


def _offset(text: str) -> int:
    """``+03:30`` / ``-5`` / ``UTC`` as seconds. Same spelling as ``import_tradingview``."""
    text = text.strip().upper().removeprefix("UTC")
    if not text or text in ("+0", "0", "Z"):
        return 0
    sign = -1 if text.startswith("-") else 1
    hours, _, minutes = text.lstrip("+-").partition(":")
    try:
        return sign * (int(hours) * 3600 + int(minutes or 0) * 60)
    except ValueError as exc:
        raise CommandError(f"cannot read {text!r} as a UTC offset — try +03:30") from exc


class Command(BaseCommand):
    help = "Read an OHLCV CSV (TradingView chart data) into the candle archive."

    def add_arguments(self, parser) -> None:
        parser.add_argument("path", help="the CSV, as TradingView's Export chart data writes it")
        parser.add_argument(
            "--symbol", required=True, help="the pair on this platform, e.g. ZECUSDC"
        )
        parser.add_argument(
            "--interval", required=True, help="e.g. 30m — one the platform stores"
        )
        parser.add_argument("--market", default="futures", choices=[m.value for m in MarketType])
        parser.add_argument(
            "--exchange",
            default="",
            help="which venue these bars are, for provenance; defaults to the pinned feed",
        )
        parser.add_argument(
            "--tz",
            default="",
            help="the chart's UTC offset when the file is stamped in chart time",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="read and report, write nothing",
        )

    def handle(self, *args, **options) -> None:
        from apps.exchanges import marketdata

        source = Path(options["path"])
        if not source.exists():
            raise CommandError(f"{source} does not exist")

        interval = options["interval"]
        if interval not in INTERVALS:
            raise CommandError(
                f"{interval!r} is not an interval this platform stores — one of "
                f"{', '.join(sorted(INTERVALS))}"
            )

        exchange = options["exchange"] or marketdata.pinned_provider()
        if not exchange:
            raise CommandError(
                "no --exchange given and no market-data feed is pinned, so these bars "
                "would be stored with no provenance — pass --exchange"
            )

        try:
            rows = tvimport.parse_candles(
                source.read_text(encoding="utf-8-sig"), offset=_offset(options["tz"])
            )
        except tvimport.TradingViewImportError as exc:
            raise CommandError(str(exc)) from exc

        symbol = options["symbol"].upper()
        market = MarketType(options["market"])
        step = INTERVALS[interval]
        off_grid = [row.time for row in rows if row.time % step]
        if off_grid:
            # Not a warning. A bar whose open time is not on the interval's grid
            # will never match one the platform fetched, so the archive would
            # hold two of everything and every window would read double.
            raise CommandError(
                f"{len(off_grid)} bar(s) are not on the {interval} grid (first: "
                f"{off_grid[0]}) — check --tz and that the file really is {interval}"
            )

        self.stdout.write(
            f"{len(rows)} bars, {tvimport_span(rows)} — {symbol} {interval} on {exchange}"
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run: nothing written"))
            return

        written = candlestore.persist(
            exchange=exchange,
            symbol=symbol,
            market=market,
            interval=interval,
            candles=[
                Candle(
                    time=row.time,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                )
                for row in rows
            ],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{written} new bar(s) archived; {len(rows) - written} were already stored"
            )
        )


def tvimport_span(rows) -> str:
    from datetime import UTC, datetime

    def stamp(seconds: int) -> str:
        return datetime.fromtimestamp(seconds, tz=UTC).strftime("%Y-%m-%d %H:%M")

    return f"{stamp(rows[0].time)} → {stamp(rows[-1].time)} UTC"
