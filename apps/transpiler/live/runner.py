"""Incremental live strategy runner (Phase 3)."""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from apps.dashboard.publish import publish_dashboard
from apps.exchange.candles import fetch_candles
from apps.exchange.subscriptions import register_strategy, unregister_strategy
from apps.exchange.ws_manager import publish_update
from apps.strategies.models import Strategy, StrategyState

from ..engine import compile
from ..runtime import interpreter
from ..runtime.context import ExecutionContext
from ..runtime.order_router import LiveBroker, WarmupBroker
from .session_store import delete_session, load_session, restore_scalars, save_session
from .sliding_window import SlidingWindow


def window_max_size(strategy: Strategy) -> int:
    buffer = getattr(settings, "LIVE_WINDOW_BUFFER", 50)
    return strategy.warmup_bars + buffer


class LiveIncrementalRunner:
    """Seed historical candles, warmup interpreter state, then process live bars."""

    def seed_and_warmup(self, strategy: Strategy) -> None:
        df = fetch_candles(
            strategy.symbol,
            strategy.timeframe,
            strategy.warmup_bars,
            network=strategy.credential.network,
        )
        if df.empty:
            raise ValueError("no candles returned from exchange")

        window = SlidingWindow(window_max_size(strategy))
        window.load_df(df)

        program = compile(strategy.source)
        broker = WarmupBroker()
        ctx = ExecutionContext(
            window.to_dataframe(),
            broker,
            header=program.header,
            chart_interval=strategy.timeframe,
            symbol=strategy.symbol,
            program=program,
        )
        interpreter.run_warmup(program, ctx)

        save_session(strategy.pk, window=window, ctx=ctx, source=strategy.source)

        state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        state.live_started_at = timezone.now()
        state.last_bar_ts = int(df.iloc[-1]["ts"])
        state.live_error = ""
        state.save(update_fields=["live_started_at", "last_bar_ts", "live_error"])

        register_strategy(
            strategy.pk,
            symbol=strategy.symbol,
            bar=strategy.timeframe,
            network=strategy.credential.network,
        )

    def _backfill_gap(self, strategy: Strategy, state: StrategyState, ts: int) -> int:
        """Fetch missed candles when gap detected, replay them, return latest ts."""
        from apps.exchange.candles import fetch_candles

        gap_start = state.last_bar_ts + 1
        extra_bars = getattr(settings, "LIVE_BACKFILL_EXTRA", 50)
        df = fetch_candles(
            strategy.symbol,
            strategy.timeframe,
            extra_bars,
            before_ts=ts,
            network=strategy.credential.network,
        )
        if df.empty:
            return state.last_bar_ts
        missed = df[df["ts"] > gap_start]
        if missed.empty:
            return state.last_bar_ts
        for _, row in missed.iterrows():
            if not self._process_one(strategy, state, {
                "ts": row["ts"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("volume", 0),
            }):
                break
        return state.last_bar_ts

    def _process_one(self, strategy: Strategy, state: StrategyState, candle: dict) -> bool:
        """Process a single candle (internal, no gap check)."""
        from apps.execution.models import ExecutionLog

        ts = int(candle["ts"])
        ExecutionLog.objects.create(
            strategy=strategy,
            level=ExecutionLog.Level.DEBUG,
            event="bar.received",
            payload={
                "symbol": strategy.symbol,
                "timeframe": strategy.timeframe,
                "ts": ts,
                "close": candle["close"],
            },
        )

        session = load_session(strategy.pk)
        if session is None:
            raise RuntimeError(f"no live session for strategy {strategy.pk}")

        window = SlidingWindow.from_rows(window_max_size(strategy), session["window"])
        window.append_closed(candle)
        program = compile(strategy.source)
        broker = LiveBroker(
            credential=strategy.credential,
            strategy=strategy,
            symbol=strategy.symbol,
        )
        ctx = ExecutionContext(
            window.to_dataframe(),
            broker,
            header=program.header,
            chart_interval=strategy.timeframe,
            symbol=strategy.symbol,
            program=program,
        )
        ctx.scalars = restore_scalars(session)
        last_bar = ctx.n - 1
        interpreter.run_bar(program, ctx, last_bar)
        action = broker.last_action if hasattr(broker, "last_action") else "No Action"
        ExecutionLog.objects.create(
            strategy=strategy,
            level=ExecutionLog.Level.INFO,
            event="strategy.evaluated",
            payload={"name": strategy.name, "action": action},
        )
        save_session(strategy.pk, window=window, ctx=ctx, source=strategy.source)
        state.last_bar_ts = ts
        state.live_error = ""
        state.save(update_fields=["last_bar_ts", "live_error"])
        publish_update(
            strategy.credential_id,
            {
                "source": "live_bar",
                "strategy_id": strategy.pk,
                "ts": ts,
                "close": candle["close"],
            },
        )
        publish_dashboard(
            strategy.user_id,
            {
                "source": "candle_tick",
                "strategy_id": strategy.pk,
                "symbol": strategy.symbol,
                "timeframe": strategy.timeframe,
                "candle": {
                    "time": ts // 1000,
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "volume": candle.get("volume", 0),
                },
            },
        )
        if state.pnl is not None:
            publish_dashboard(
                strategy.user_id,
                {
                    "source": "pnl",
                    "strategy_id": strategy.pk,
                    "pnl": str(state.pnl),
                    "position": state.position,
                },
            )
        return True

    def on_closed_candle(self, strategy: Strategy, candle: dict) -> bool:
        """Process one closed candle. Returns True if processed, False if skipped."""
        state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        ts = int(candle["ts"])
        if state.last_bar_ts is not None and ts <= state.last_bar_ts:
            return False
        if state.last_bar_ts is not None and ts - state.last_bar_ts > 60000:
            self._backfill_gap(strategy, state, ts)
        return self._process_one(strategy, state, candle)

    @staticmethod
    def stop(strategy: Strategy) -> None:
        unregister_strategy(
            strategy.pk,
            symbol=strategy.symbol,
            bar=strategy.timeframe,
            network=strategy.credential.network,
        )
        delete_session(strategy.pk)
        state = getattr(strategy, "state", None)
        if state is None:
            try:
                state = StrategyState.objects.get(strategy=strategy)
            except StrategyState.DoesNotExist:
                state = None
        if state:
            state.live_started_at = None
            state.save(update_fields=["live_started_at"])
