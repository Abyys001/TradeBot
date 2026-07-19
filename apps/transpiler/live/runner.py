"""Incremental live strategy runner (Phase 3)."""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from apps.credentials.models import Exchange
from apps.dashboard.publish import publish_dashboard
from apps.exchange.candles import fetch_candles
from apps.exchange.data_quality import BarQuality, should_halt
from apps.exchange.subscriptions import register_strategy, unregister_strategy
from apps.exchange.ws_manager import publish_update
from apps.strategies.models import Strategy, StrategyState

from ..engine import compile
from ..runtime import interpreter
from ..runtime.context import ExecutionContext
from ..runtime.order_router import LiveBroker, WarmupBroker
from ..runtime.signal_capture_broker import SignalCaptureBroker
from .session_store import delete_session, load_session, restore_scalars, save_session
from .sliding_window import SlidingWindow


def window_max_size(strategy: Strategy) -> int:
    buffer = getattr(settings, "LIVE_WINDOW_BUFFER", 50)
    return strategy.warmup_bars + buffer


def _halt_bars_key(strategy_id: int) -> str:
    """Cache key tracking consecutive halted bars (§4.3 blind-hold budget)."""
    return f"halt:bars:{strategy_id}"


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

    def _build_broker(self, strategy: Strategy):
        """Construct the broker for this strategy's live path.

        Copy-trading -> SignalCaptureBroker; Tabdeal credential -> TabdealLiveBroker
        (the Tabdeal-only live path); otherwise the legacy Hyperliquid LiveBroker.
        """
        if bool((strategy.live_config or {}).get("copy_trading")):
            return SignalCaptureBroker()
        if strategy.credential and strategy.credential.exchange == Exchange.TABDEAL:
            from ..runtime.tabdeal_live_broker import TabdealLiveBroker

            return TabdealLiveBroker(
                credential=strategy.credential,
                strategy=strategy,
                symbol=strategy.symbol,
            )
        return LiveBroker(
            credential=strategy.credential,
            strategy=strategy,
            symbol=strategy.symbol,
        )

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
        copy_mode = bool((strategy.live_config or {}).get("copy_trading"))
        broker = self._build_broker(strategy)
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
        if copy_mode and isinstance(broker, SignalCaptureBroker) and broker.has_actions():
            from apps.copytrading.tasks import fan_out_signal_task

            fan_out_signal_task.delay(strategy.pk, broker.actions)
        save_session(strategy.pk, window=window, ctx=ctx, source=strategy.source)
        state.last_bar_ts = ts
        state.live_error = ""
        state.save(update_fields=["last_bar_ts", "live_error"])
        # A clean bar resolved any prior halt — reset the blind-hold budget (§4.3).
        from django.core.cache import cache as _cache

        _cache.delete(_halt_bars_key(strategy.pk))
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
        """Process one closed candle. Returns True if processed, False if skipped.

        A bar whose quality is SUSPECT/MISSING halts the strategy (invariant 1): it is never
        fed to the interpreter. Recovery is handled by self-heal (P4), not here.
        """
        state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        ts = int(candle["ts"])
        if state.last_bar_ts is not None and ts <= state.last_bar_ts:
            return False
        if self._halt_if_suspect(strategy, state, candle):
            return False
        if state.last_bar_ts is not None and ts - state.last_bar_ts > 60000:
            self._backfill_gap(strategy, state, ts)
        return self._process_one(strategy, state, candle)

    def _halt_if_suspect(self, strategy: Strategy, state: StrategyState, candle: dict) -> bool:
        """If the bar's quality gates trading, apply the §4.3 policy and return True (skip).

        A SUSPECT/MISSING bar is never fed to the interpreter (invariant 1). Beyond
        skipping the bar, the open position must be handled: ``evaluate_halt`` decides
        HOLD (SL confirmed, within blind-hold budget) vs FLATTEN (naked / MISSING /
        Class-3 total-ingest / budget exceeded). The decision is logged and, on FLATTEN,
        the position is closed.
        """
        q = candle.get("quality")
        if q is None:
            return False
        try:
            quality = BarQuality(q)
        except ValueError:
            return False
        if not should_halt([quality]):
            return False

        from django.core.cache import cache
        from apps.exchange.halt_policy import evaluate_halt
        from apps.execution.models import ExecutionLog

        ts = int(candle["ts"])
        bars_key = _halt_bars_key(strategy.pk)
        bars_since_halt = int(cache.get(bars_key) or 0)
        failure_class = self._classify_failure(strategy, ts)
        # `sl_confirmed` is populated by P5 (SL-attach verification); until then it is
        # absent -> False -> a naked position flattens (fail closed, invariant 5/13).
        sl_confirmed = bool(getattr(state, "sl_confirmed", False))
        max_blind_hold = getattr(settings, "MAX_BLIND_HOLD", 3)

        decision = evaluate_halt(
            quality=quality.value,
            sl_confirmed=sl_confirmed,
            failure_class=failure_class,
            bars_since_halt=bars_since_halt,
            max_blind_hold=max_blind_hold,
        )
        cache.set(bars_key, bars_since_halt + 1, timeout=86400)

        state.live_error = (
            f"halted: {quality.value} bar at {ts} -> "
            f"{decision.action.value} ({decision.reason})"
        )
        state.save(update_fields=["live_error"])
        ExecutionLog.objects.create(
            strategy=strategy,
            level=ExecutionLog.Level.WARNING,
            event="bar.halt",
            payload={
                "ts": ts,
                "quality": quality.value,
                "symbol": strategy.symbol,
                "action": decision.action.value,
                "reason": decision.reason,
                "failure_class": decision.failure_class.value,
                "sl_confirmed": sl_confirmed,
                "bars_since_halt": bars_since_halt,
                "eta_blind_hold": decision.eta_blind_hold,
            },
        )
        if decision.should_flatten:
            self._flatten_on_halt(strategy, decision)
        return True

    def _classify_failure(self, strategy: Strategy, ts: int):
        """Classify the quality failure over this bar's window (§0.1).

        Fails closed to TOTAL_INGEST (forces FLATTEN) if the window cannot be
        evaluated — a gate that cannot run blocks/flattens (invariant 5).
        """
        from apps.exchange.halt_policy import FailureClass
        from apps.exchange.timeframes import is_fixed, tf_to_ms

        try:
            if not is_fixed(strategy.timeframe):
                return FailureClass.TOTAL_INGEST
            from apps.exchange.self_heal import detect_failure_class
            from apps.transpiler.runtime.tabdeal_broker import to_tabdeal_symbol

            tf_ms = tf_to_ms(strategy.timeframe)
            symbol = to_tabdeal_symbol(strategy.symbol)
            return detect_failure_class(symbol, ts, ts + tf_ms)
        except Exception:  # noqa: BLE001 — unresolvable gate -> fail closed
            return FailureClass.TOTAL_INGEST

    def _flatten_on_halt(self, strategy: Strategy, decision) -> None:
        """Close the open position when the halt policy decides FLATTEN (§4.3).

        NOTE (P5): ``TabdealLiveBroker.close`` currently honors the kill-switch, so a
        halt-flatten can be blocked when trading is disabled — a violation of invariant
        6 (risk/kill gates must never block an exit). P5 makes close/flatten bypass the
        kill-switch; until then the watchdog (Node D, P6) is the backstop.
        """
        from apps.execution.models import ExecutionLog

        if not (strategy.credential and strategy.credential.exchange == Exchange.TABDEAL):
            ExecutionLog.objects.create(
                strategy=strategy,
                level=ExecutionLog.Level.WARNING,
                event="bar.halt_flatten_skipped",
                payload={"reason": decision.reason, "note": "non-tabdeal path (deprecated)"},
            )
            return

        from ..runtime.tabdeal_live_broker import TabdealLiveBroker

        broker = TabdealLiveBroker(
            credential=strategy.credential,
            strategy=strategy,
            symbol=strategy.symbol,
        )
        try:
            rec = broker.close("halt", None, -1, reason=f"halt:{decision.reason}")
        except Exception as exc:  # noqa: BLE001
            ExecutionLog.objects.create(
                strategy=strategy,
                level=ExecutionLog.Level.ERROR,
                event="bar.halt_flatten_failed",
                payload={"reason": decision.reason, "error": type(exc).__name__},
            )
            return
        ExecutionLog.objects.create(
            strategy=strategy,
            level=ExecutionLog.Level.WARNING,
            event="bar.halt_flatten",
            payload={"reason": decision.reason, "closed": rec is not None},
        )

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
