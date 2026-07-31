"""Rebuild OHLCV candles from the raw trade ledger.

The ingest nodes record every trade to an append-only Parquet ledger, but only
the live resampler turns those into candles, and only for the last 24h of each
pass. After a long recording run you need the whole history materialized before
a strategy can seed its warmup window — that is what this command does.

Because it folds candles straight from trades, it can produce **any** fixed
timeframe, including the higher timeframes a `request.security` strategy needs.

Usage::

    python manage.py backfill_candles                       # all symbols, base TFs
    python manage.py backfill_candles --symbols BTC_USDT --timeframes 1m 1h 3h
    python manage.py backfill_candles --strategy-id 4       # exactly what it needs
    python manage.py backfill_candles --start 2026-07-01 --end 2026-07-11
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from django.core.management.base import BaseCommand, CommandError

from apps.exchange.candle_store import save_candles
from apps.exchange.ledger import available_range, read_trades
from apps.exchange.resampler import Resampler, ledger_symbol_to_coin
from apps.exchange.timeframes import BASE_TIMEFRAMES, FIXED_MS, is_fixed, tf_to_ms

_DAY_MS = 86_400_000


def _parse_day(value: str, *, end: bool = False) -> int:
    """`YYYY-MM-DD` or epoch-ms -> epoch ms (UTC)."""
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    try:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CommandError(f"cannot parse date {value!r}; use YYYY-MM-DD or epoch ms") from exc
    if end:
        dt += timedelta(days=1)
    return int(dt.timestamp() * 1000)


def strategy_timeframes(strategy_id: int) -> tuple[str, list[str]]:
    """`(ledger_symbol, timeframes)` a live strategy needs — chart TF plus its HTFs."""
    from apps.strategies.models import Strategy
    from apps.transpiler.engine import compile as pine_compile
    from apps.transpiler.runtime.timeframe import minutes_to_interval
    from apps.transpiler.runtime.tabdeal_broker import to_tabdeal_symbol

    try:
        strategy = Strategy.objects.get(pk=strategy_id)
    except Strategy.DoesNotExist as exc:
        raise CommandError(f"strategy {strategy_id} does not exist") from exc

    timeframes = [strategy.timeframe]
    if strategy.source.strip():
        try:
            program = pine_compile(strategy.source)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"strategy {strategy_id} does not compile: {exc}") from exc
        for minutes in getattr(program, "security_minutes", ()) or ():
            try:
                timeframes.append(minutes_to_interval(minutes))
            except Exception as exc:  # noqa: BLE001
                raise CommandError(
                    f"strategy {strategy_id} requests a {minutes}-minute timeframe, "
                    f"which is not on the supported ladder ({', '.join(FIXED_MS)})"
                ) from exc
    return to_tabdeal_symbol(strategy.symbol), list(dict.fromkeys(timeframes))


class Command(BaseCommand):
    help = "Rebuild candles for one or more timeframes from the raw trade ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols", nargs="*", default=None,
            help="Ledger symbols, e.g. BTC_USDT. Defaults to TABDEAL_INGEST_SYMBOLS.",
        )
        parser.add_argument(
            "--timeframes", nargs="*", default=None,
            help=f"Fixed timeframes to build. Defaults to {', '.join(BASE_TIMEFRAMES)}.",
        )
        parser.add_argument(
            "--strategy-id", type=int, default=None,
            help="Derive symbol and timeframes (chart + request.security HTFs) from a strategy.",
        )
        parser.add_argument("--start", default=None, help="YYYY-MM-DD or epoch ms. Default: ledger start.")
        parser.add_argument("--end", default=None, help="YYYY-MM-DD or epoch ms. Default: ledger end.")
        parser.add_argument(
            "--chunk-days", type=int, default=2,
            help="Days of trades held in memory per pass (default: 2).",
        )

    def handle(self, *args, **options):
        symbols, timeframes = self._resolve_targets(options)
        for tf in timeframes:
            if not is_fixed(tf):
                raise CommandError(
                    f"{tf!r} is not a fixed timeframe; calendar timeframes are not "
                    f"supported here. Choose from: {', '.join(FIXED_MS)}"
                )

        chunk_ms = max(int(options["chunk_days"]), 1) * _DAY_MS
        grand_total = 0

        for symbol in symbols:
            window = self._window_for(symbol, options)
            if window is None:
                self.stdout.write(self.style.WARNING(f"{symbol}: no ledger data, skipping"))
                continue
            start_ms, end_ms = window
            self.stdout.write(
                f"{symbol}: {_iso(start_ms)} -> {_iso(end_ms)} "
                f"({(end_ms - start_ms) / _DAY_MS:.1f} days), timeframes={', '.join(timeframes)}"
            )
            written = self._backfill_symbol(symbol, timeframes, start_ms, end_ms, chunk_ms)
            grand_total += sum(written.values())
            for tf in timeframes:
                count = written.get(tf, 0)
                style = self.style.SUCCESS if count else self.style.WARNING
                self.stdout.write(style(f"  {tf:>4}: {count} bars"))

        if not grand_total:
            raise CommandError("no candles were written — check that ingest has recorded trades")
        self.stdout.write(self.style.SUCCESS(f"done: {grand_total} bars written"))

    # -- internals ---------------------------------------------------------

    def _resolve_targets(self, options) -> tuple[list[str], list[str]]:
        if options["strategy_id"] is not None:
            symbol, timeframes = strategy_timeframes(options["strategy_id"])
            return [symbol], options["timeframes"] or timeframes

        from django.conf import settings

        symbols = options["symbols"] or list(
            getattr(settings, "TABDEAL_INGEST_SYMBOLS", ["BTC_USDT"])
        )
        return list(symbols), list(options["timeframes"] or BASE_TIMEFRAMES)

    def _window_for(self, symbol: str, options) -> tuple[int, int] | None:
        span = available_range(symbol)
        if span is None:
            return None
        start_ms = _parse_day(options["start"]) if options["start"] else span[0]
        end_ms = _parse_day(options["end"], end=True) if options["end"] else span[1]
        if end_ms <= start_ms:
            raise CommandError(f"{symbol}: end ({_iso(end_ms)}) is not after start ({_iso(start_ms)})")
        return start_ms, end_ms

    def _backfill_symbol(
        self,
        symbol: str,
        timeframes: list[str],
        start_ms: int,
        end_ms: int,
        chunk_ms: int,
    ) -> dict[str, int]:
        resampler = Resampler(symbol)
        coin = ledger_symbol_to_coin(symbol)
        written: dict[str, int] = {}

        for tf in timeframes:
            tf_ms = tf_to_ms(tf)
            # Snap the window to bucket edges so chunk seams never split a bar.
            cursor = (start_ms // tf_ms) * tf_ms
            frames: list[pd.DataFrame] = []
            while cursor < end_ms:
                # Read whole buckets: a chunk boundary mid-bar would emit two
                # partial bars for the same timestamp.
                stop = min(((cursor + chunk_ms) // tf_ms) * tf_ms, end_ms)
                if stop <= cursor:
                    stop = min(cursor + tf_ms, end_ms)
                trades = read_trades(symbol, cursor, stop)
                if not trades.empty:
                    bars = resampler.resample_fixed_tagged(trades, tf)
                    if bars:
                        frames.append(pd.DataFrame(bars))
                cursor = stop

            if not frames:
                continue
            df = pd.concat(frames, ignore_index=True)
            df = df.drop_duplicates(subset="ts", keep="last").sort_values("ts").reset_index(drop=True)
            # The final bucket is still forming unless the window ran past its end.
            last_ts = int(df["ts"].iloc[-1])
            if last_ts + tf_ms > end_ms:
                df = df.iloc[:-1]
            if df.empty:
                continue
            save_candles(coin, tf, df)
            written[tf] = len(df)
        return written


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
