"""``python manage.py pine_backtest <file> --symbol --interval --from --to``.

Usable long before any UI exists, and it prints the fill assumptions before it
prints a single number — a reader who does not know the fill model cannot
interpret the Sharpe, so the model is not something to go looking for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.bots import backtest
from apps.bots.models import BacktestRun, Strategy, StrategyVersion
from apps.exchanges.base import MarketType


def _moment(text: str) -> int:
    """``2024-01-01`` or a raw UNIX second. UTC, like everything internal."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(text, pattern).replace(tzinfo=UTC).timestamp())
        except ValueError:
            continue
    raise CommandError(f"cannot read {text!r} as a date — use YYYY-MM-DD or a UNIX second")


class Command(BaseCommand):
    help = "Replay a Pine strategy over stored history and print the report."

    def add_arguments(self, parser) -> None:
        parser.add_argument("path", help="path to a .pine file")
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--interval", default="1h")
        parser.add_argument("--market", default="futures", choices=[m.value for m in MarketType])
        parser.add_argument("--from", dest="from_time", required=True)
        parser.add_argument("--to", dest="to_time", required=True)
        parser.add_argument("--leverage", type=int, default=1)
        parser.add_argument("--sl", dest="sl_pct", default=None)
        parser.add_argument("--tp", dest="tp_pct", default=None)
        parser.add_argument("--equity", default="10000")
        parser.add_argument(
            "--save",
            metavar="STRATEGY",
            default="",
            help="store the report against this strategy name, creating a version if needed",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="validate and report what would be run, without replaying",
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"no such file: {path}")
        source = path.read_text(encoding="utf-8")

        from_time = _moment(options["from_time"])
        to_time = _moment(options["to_time"])
        if to_time <= from_time:
            raise CommandError("--to must be after --from")

        if options["dry_run"]:
            self.stdout.write(
                f"would replay {path.name} on {options['symbol']} {options['interval']} "
                f"from {from_time} to {to_time}"
            )
            return

        try:
            report = backtest.run(
                source=source,
                symbol=options["symbol"],
                interval=options["interval"],
                market=MarketType(options["market"]),
                from_time=from_time,
                to_time=to_time,
                leverage=options["leverage"],
                sl_pct=_decimal(options["sl_pct"], "--sl"),
                tp_pct=_decimal(options["tp_pct"], "--tp"),
                initial_equity=_decimal(options["equity"], "--equity") or Decimal("10000"),
            )
        except backtest.BacktestError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("\n".join(report.summary_lines()))

        if report.warnings:
            for warning in report.warnings:
                self.stderr.write(self.style.WARNING(warning))

        if options["save"]:
            run = self._store(options["save"], source, report, options)
            self.stdout.write(self.style.SUCCESS(f"saved as backtest #{run.id}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"{report.metrics['trades']} trades replayed"))

    def _store(self, name: str, source: str, report, options) -> BacktestRun:
        strategy, _ = Strategy.objects.get_or_create(name=name)
        version = strategy.versions.filter(source=source).first()
        if version is None:
            latest = strategy.versions.order_by("-version").first()
            version = StrategyVersion.objects.create(
                strategy=strategy,
                version=(latest.version + 1) if latest else 1,
                source=source,
                parsed_ok=True,
            )
        return BacktestRun.objects.create(
            strategy_version=version,
            symbol=report.symbol,
            interval=report.interval,
            market=options["market"],
            from_time=report.from_time,
            to_time=report.to_time,
            bars=report.bars,
            trades=len(report.trades),
            metrics=report.as_dict()["metrics"],
            assumptions=report.assumptions.as_dict(),
            equity_curve=report.as_dict()["equity_curve"],
            trade_log=report.as_dict()["trades"],
            intent_digest=report.intent_digest,
        )


def _decimal(value, flag: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise CommandError(f"{flag} must be a number, got {value!r}") from exc
