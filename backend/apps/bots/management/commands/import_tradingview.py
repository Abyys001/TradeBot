"""``python manage.py import_tradingview <list_of_trades.csv> --symbol --interval``.

Turns one TradingView Strategy Tester export into a parity fixture: the list of
trades in UTC, and the bars the replay runs on, downloaded through the
platform's own loader so the archive keeps them. The venue serves a fixed depth
(Hyperliquid: the latest 5000 bars) and the archive does not, which is why the
download goes through ``load_bars`` rather than a fetch of its own — the second
export of the same pair reaches further back than the first.

The chart's timezone is derived from the prices, not asked for; ``--tz`` is
there for an export whose bars are not to hand.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.bots import tvimport
from apps.bots.backtest import load_bars
from apps.exchanges.base import MarketType


def _offset(text: str) -> int:
    """``+03:30`` / ``-5`` / ``UTC`` as seconds."""
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
    help = "Convert a TradingView List of Trades export into a parity fixture."

    def add_arguments(self, parser) -> None:
        parser.add_argument("path", help="the List of Trades CSV, as TradingView exports it")
        parser.add_argument(
            "--symbol", required=True, help="the pair on this platform, e.g. ZECUSDC"
        )
        parser.add_argument("--interval", default="30m")
        parser.add_argument("--market", default="futures", choices=[m.value for m in MarketType])
        parser.add_argument("--into", required=True, help="directory to write the fixture into")
        parser.add_argument(
            "--tz",
            default="",
            help="the chart's UTC offset, when it cannot be derived from the bars",
        )
        parser.add_argument(
            "--no-bars",
            action="store_true",
            help="convert the trade list only; requires --tz",
        )

    def handle(self, *args, **options) -> None:
        source = Path(options["path"])
        if not source.exists():
            raise CommandError(f"{source} does not exist")
        try:
            trades = tvimport.parse(source.read_text(encoding="utf-8-sig"))
        except tvimport.TradingViewImportError as exc:
            raise CommandError(str(exc)) from exc

        into = Path(options["into"])
        into.mkdir(parents=True, exist_ok=True)
        bars = []
        if not options["no_bars"]:
            first = min(t.entry_time for t in trades) - 3600 * 24
            last = max(t.exit_time or t.entry_time for t in trades)
            window = load_bars(
                symbol=options["symbol"],
                interval=options["interval"],
                market=MarketType(options["market"]),
                from_time=first,
                to_time=last,
                warmup=0,
                progress=lambda phase, done, detail: None,
            )
            bars = window.bars
            for note in window.notes:
                self.stdout.write(self.style.WARNING(f"  ! {note}"))

        if options["tz"]:
            offset = _offset(options["tz"])
        elif bars:
            try:
                offset = tvimport.chart_offset(trades, bars)
            except tvimport.TradingViewImportError as exc:
                raise CommandError(str(exc)) from exc
        else:
            raise CommandError("--no-bars needs --tz: nothing is left to derive the clock from")
        self.stdout.write(
            f"chart timezone: UTC{offset // 3600:+03d}:{abs(offset) % 3600 // 60:02d}"
        )

        (into / "list_of_trades.csv").write_text(
            tvimport.fixture_csv(tvimport.shift(trades, offset))
        )
        self.stdout.write(f"  {len(trades)} trades -> {into / 'list_of_trades.csv'}")
        if bars:
            name = f"bars_{options['symbol'].lower()}_{options['interval']}.csv"
            (into / name).write_text(tvimport.bars_csv(bars))
            covered = [t for t in trades if t.entry_time - offset >= bars[0].time]
            self.stdout.write(f"  {len(bars)} bars -> {into / name}")
            self.stdout.write(
                f"  {len(covered)} of {len(trades)} trades open inside the bars there are; "
                f"the rest need an export of the chart's own history."
            )
