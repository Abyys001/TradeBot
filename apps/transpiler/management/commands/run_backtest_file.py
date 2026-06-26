"""Backtest a Pine strategy over locally stored candle history (dry mode).

No exchange API or credentials are touched — candles come from local parquet
files written by ``download_history``.

Example:
    python manage.py run_backtest_file --strategy-id 1 --coin BTC --interval 1h
    python manage.py run_backtest_file --pine strat.pine --coin BTC --interval 1h --save
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.exchange.candle_store import load_candles
from apps.transpiler.engine import run_backtest


def _to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


class Command(BaseCommand):
    help = "Backtest a Pine strategy over stored candle history (no exchange calls)."

    def add_arguments(self, parser):
        parser.add_argument("--strategy-id", type=int, default=None)
        parser.add_argument("--pine", default=None, help="Path to a .pine file (alt to --strategy-id)")
        parser.add_argument("--coin", required=True)
        parser.add_argument("--interval", required=True)
        parser.add_argument("--start", default=None, help="YYYY-MM-DD")
        parser.add_argument("--end", default=None, help="YYYY-MM-DD")
        parser.add_argument("--qty", type=float, default=1.0)
        parser.add_argument("--save", action="store_true", help="Persist Backtest + trades")

    def handle(self, *args, **opts):
        source, strategy = self._resolve_source(opts)

        start = _to_ms(opts["start"]) if opts["start"] else None
        end = _to_ms(opts["end"]) if opts["end"] else None

        df = load_candles(opts["coin"], opts["interval"], start, end)
        if df.empty:
            raise CommandError(
                f"no stored candles for {opts['coin']}/{opts['interval']}; "
                f"run download_history first"
            )

        result = run_backtest(source, df, default_qty=opts["qty"])

        m = result.metrics
        self.stdout.write(self.style.SUCCESS(f"--- backtest {opts['coin']}/{opts['interval']} ({len(df)} bars) ---"))
        self.stdout.write(f"net_pnl      : {m.get('net_pnl')}")
        self.stdout.write(f"win_rate     : {m.get('win_rate')}")
        self.stdout.write(f"max_drawdown : {m.get('max_drawdown')}")
        self.stdout.write(f"num_trades   : {m.get('num_trades')}")

        if opts["save"]:
            self._save(strategy, opts, df, result)

    def _resolve_source(self, opts):
        if opts["pine"]:
            path = Path(opts["pine"])
            if not path.exists():
                raise CommandError(f"file not found: {path}")
            return path.read_text(), None
        if opts["strategy_id"]:
            from apps.strategies.models import Strategy

            try:
                strategy = Strategy.objects.get(pk=opts["strategy_id"])
            except Strategy.DoesNotExist as exc:
                raise CommandError(f"no Strategy<{opts['strategy_id']}>") from exc
            return strategy.source, strategy
        raise CommandError("provide --strategy-id or --pine")

    def _save(self, strategy, opts, df, result):
        from apps.transpiler.models import Backtest, BacktestTrade

        if strategy is None:
            raise CommandError("--save requires --strategy-id (need a Strategy to attach to)")

        bt = Backtest.objects.create(
            strategy=strategy,
            status=Backtest.Status.DONE,
            symbol=opts["coin"],
            timeframe=opts["interval"],
            range_start=datetime.fromtimestamp(int(df["ts"].min()) / 1000, tz=timezone.utc),
            range_end=datetime.fromtimestamp(int(df["ts"].max()) / 1000, tz=timezone.utc),
            metrics=result.metrics,
        )
        BacktestTrade.objects.bulk_create(
            [
                BacktestTrade(
                    backtest=bt,
                    side=t["side"],
                    entry_price=Decimal(str(t["entry_price"])),
                    exit_price=Decimal(str(t["exit_price"])) if t["exit_price"] is not None else None,
                    size=Decimal(str(t["size"])),
                    pnl=Decimal(str(t["pnl"])),
                    entry_bar=t["entry_bar"],
                    exit_bar=t["exit_bar"],
                )
                for t in result.trades
            ]
        )
        self.stdout.write(self.style.SUCCESS(f"saved Backtest<{bt.id}> with {len(result.trades)} trades"))
