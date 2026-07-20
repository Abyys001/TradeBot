"""Incremental paper trading runner on live candle feed."""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from apps.dashboard.publish import publish_dashboard
from apps.exchange.candles import fetch_candles
from apps.exchange.subscriptions import register_strategy, unregister_strategy
from apps.strategies.models import Strategy, StrategyState
from apps.transpiler.engine import compile
from apps.transpiler.live.session_store import delete_session, load_session, restore_scalars, save_session
from apps.transpiler.live.sliding_window import SlidingWindow
from apps.transpiler.runtime import interpreter
from apps.transpiler.runtime.context import ExecutionContext
from apps.transpiler.runtime.order_router import WarmupBroker

from .broker import PaperBroker
from .models import PaperAccount


def window_max_size(strategy: Strategy) -> int:
    buffer = getattr(settings, "LIVE_WINDOW_BUFFER", 50)
    return strategy.warmup_bars + buffer


class PaperIncrementalRunner:
    def start(self, account: PaperAccount) -> None:
        strategy = account.strategy
        network = (strategy.live_config or {}).get("network", "mainnet")
        df = fetch_candles(strategy.symbol, strategy.timeframe, strategy.warmup_bars, network=network)
        if df.empty:
            raise ValueError("no candles for paper warmup")

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
        save_session(f"paper:{account.pk}", window=window, ctx=ctx, source=strategy.source)

        state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        state.last_bar_ts = int(df.iloc[-1]["ts"])
        state.save(update_fields=["last_bar_ts"])

        register_strategy(
            strategy.pk,
            symbol=strategy.symbol,
            bar=strategy.timeframe,
            network=network,
        )
        account.is_active = True
        account.save(update_fields=["is_active", "updated_at"])

    def stop(self, account: PaperAccount) -> None:
        strategy = account.strategy
        network = (strategy.live_config or {}).get("network", "mainnet")
        unregister_strategy(strategy.pk, symbol=strategy.symbol, bar=strategy.timeframe, network=network)
        delete_session(f"paper:{account.pk}")
        account.is_active = False
        account.save(update_fields=["is_active", "updated_at"])

    def on_closed_candle(self, account: PaperAccount, candle: dict) -> bool:
        strategy = account.strategy
        state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        ts = int(candle["ts"])
        if state.last_bar_ts is not None and ts <= state.last_bar_ts:
            return False

        session = load_session(f"paper:{account.pk}")
        if session is None:
            raise RuntimeError(f"no paper session for account {account.pk}")

        window = SlidingWindow.from_rows(window_max_size(strategy), session["window"])
        window.append_closed(candle)
        program = compile(strategy.source)
        live_config = strategy.live_config or {}
        from apps.risk.config import read_risk

        broker = PaperBroker(
            account,
            leverage=float(read_risk(live_config).get("leverage", 1)),
            initial_balance=float(account.balance),
            allow_pyramiding=bool(live_config.get("pyramiding")),
        )
        broker.strategy = strategy
        ctx = ExecutionContext(
            window.to_dataframe(),
            broker,
            header=program.header,
            chart_interval=strategy.timeframe,
            symbol=strategy.symbol,
            program=program,
        )
        ctx.scalars = restore_scalars(session)
        interpreter.run_bar(program, ctx, ctx.n - 1)
        broker.sync_account(float(candle["close"]))
        save_session(f"paper:{account.pk}", window=window, ctx=ctx, source=strategy.source)

        position = {}
        if broker.open_trades:
            t = next(iter(broker.open_trades.values()))
            mark = float(candle["close"])
            direction = 1.0 if t.side == "long" else -1.0
            unrealized = (mark - t.entry_price) * t.size * direction
            position = {
                "side": t.side,
                "size": str(t.size),
                "entry_price": str(t.entry_price),
                "entry_bar": t.entry_bar,
                "unrealized_pnl": str(round(unrealized, 8)),
            }
        state.position = position
        state.last_bar_ts = ts
        state.save(update_fields=["last_bar_ts", "position"])
        publish_dashboard(
            strategy.user_id,
            {"source": "paper", "strategy_id": strategy.pk, "equity": str(account.equity)},
        )
        return True
