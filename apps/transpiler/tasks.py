"""Celery tasks: source validation and backtest execution.

Registered via the Phase 1 `config.celery` autodiscovery. Backtests run off the
request cycle; progress is pushed to the strategy credential's Channels group
(`apps.exchange.ws_manager.publish_update`) so a UI can stream status.
"""
from __future__ import annotations

import logging
from decimal import Decimal

import pandas as pd
from celery import shared_task

logger = logging.getLogger(__name__)

from apps.dashboard.publish import publish_dashboard
from apps.exchange.ws_manager import publish_update

from .engine import compile, run_backtest
from .exceptions import PineError
from .models import Backtest, BacktestTrade


def _candles_to_df(candles: list[dict]) -> pd.DataFrame:
    """Normalise a list of OHLCV dicts into the frame the engine expects."""
    rows = []
    base_ts = 1_700_000_000_000
    for i, c in enumerate(candles):
        if "ts" in c:
            ts = int(c["ts"])
        elif "time" in c:
            ts = int(c["time"]) * 1000
        else:
            ts = base_ts + i * 3_600_000
        rows.append(
            {
                "ts": ts,
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("volume", 0.0)),
            }
        )
    return pd.DataFrame(rows)


def _notify(strategy, payload):
    cred_id = getattr(strategy, "credential_id", None)
    if cred_id:
        try:
            publish_update(cred_id, payload)
        except Exception:  # noqa: BLE001 — notification is best-effort
            pass
    user_id = getattr(strategy, "user_id", None)
    if user_id:
        try:
            publish_dashboard(user_id, payload)
        except Exception:  # noqa: BLE001
            pass


@shared_task(name="transpiler.validate_source")
def validate_source_task(strategy_id: int):
    """Compile + semantic-check a strategy's Pine source; store the result."""
    from apps.strategies.models import Strategy

    strategy = Strategy.objects.get(pk=strategy_id)
    try:
        compile(strategy.source)
    except PineError as exc:
        strategy.validation_status = "error"
        strategy.validation_error = str(exc)
        strategy.save(update_fields=["validation_status", "validation_error"])
        return {"ok": False, "error": str(exc)}
    strategy.validation_status = "ok"
    strategy.validation_error = ""
    strategy.save(update_fields=["validation_status", "validation_error"])
    return {"ok": True}


def _persist_backtest_result(bt, result):
    """Store metrics + trades for a completed backtest and notify listeners."""
    from datetime import datetime, timezone

    bt.metrics = result.metrics
    bt.status = Backtest.Status.DONE
    bt.save(update_fields=["metrics", "status"])

    def _ts_to_dt(ts_ms):
        if ts_ms:
            return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
        return None

    BacktestTrade.objects.bulk_create(
        [
            BacktestTrade(
                backtest=bt,
                side=t["side"],
                entry_price=Decimal(str(t["entry_price"])),
                exit_price=Decimal(str(t["exit_price"])) if t["exit_price"] is not None else None,
                size=Decimal(str(t["size"])),
                pnl=Decimal(str(t["pnl"])),
                gross_pnl=Decimal(str(t.get("gross_pnl", 0))),
                commission=Decimal(str(t.get("commission", 0))),
                entry_bar=t["entry_bar"],
                exit_bar=t["exit_bar"],
                stop_px=Decimal(str(t["stop_px"])) if t.get("stop_px") is not None else None,
                limit_px=Decimal(str(t["limit_px"])) if t.get("limit_px") is not None else None,
                exit_reason=t.get("exit_reason", ""),
                entry_time=_ts_to_dt(t.get("entry_time")),
                exit_time=_ts_to_dt(t.get("exit_time")),
            )
            for t in result.trades
        ]
    )
    _notify(bt.strategy, {"source": "backtest", "backtest_id": bt.id, "status": "done", "metrics": result.metrics})


@shared_task(name="transpiler.run_backtest")
def run_backtest_task(
    backtest_id: int,
    candles: list[dict],
    commission: float | None = None,
    slippage: float | None = None,
):
    """Run a backtest of the strategy's source over the supplied candles."""
    bt = Backtest.objects.select_related("strategy").get(pk=backtest_id)
    strategy = bt.strategy
    bt.status = Backtest.Status.RUNNING
    bt.save(update_fields=["status"])
    _notify(strategy, {"source": "backtest", "backtest_id": bt.id, "status": "running"})

    try:
        from datetime import datetime, timezone

        df = _candles_to_df(candles)
        if not df.empty:
            bt.range_start = datetime.fromtimestamp(int(df["ts"].min()) / 1000, tz=timezone.utc)
            bt.range_end = datetime.fromtimestamp(int(df["ts"].max()) / 1000, tz=timezone.utc)
            bt.save(update_fields=["range_start", "range_end"])
        result = run_backtest(
            strategy.source,
            df,
            commission=commission,
            slippage=slippage,
            chart_interval=bt.timeframe or "1h",
            symbol=bt.symbol or "",
        )
        _persist_backtest_result(bt, result)
    except Exception as exc:  # noqa: BLE001
        bt.status = Backtest.Status.FAILED
        bt.error = str(exc)
        bt.save(update_fields=["status", "error"])
        _notify(strategy, {"source": "backtest", "backtest_id": bt.id, "status": "failed", "error": str(exc)})
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "metrics": result.metrics}


@shared_task(bind=True, name="transpiler.run_backtest_stored")
def run_backtest_stored_task(
    self,
    backtest_id: int,
    coin: str,
    interval: str,
    start: int | None = None,
    end: int | None = None,
    *,
    network: str = "mainnet",
    commission: float | None = None,
    slippage: float | None = None,
    initial_balance: float = 10_000.0,
):
    """Run a backtest over stored candle history, auto-downloading if needed."""
    from datetime import datetime, timezone

    from apps.exchange.candle_store import load_candles, load_funding

    bt = Backtest.objects.select_related("strategy").get(pk=backtest_id)
    strategy = bt.strategy
    bt.status = Backtest.Status.RUNNING
    bt.initial_balance = initial_balance
    bt.save(update_fields=["status", "initial_balance"])
    _notify(strategy, {"source": "backtest", "backtest_id": bt.id, "status": "running"})

    try:
        def _progress(step, pct):
            try:
                self.update_state(state="PROGRESS", meta={"step": step, "pct": pct})
            except Exception:  # noqa: BLE001 — best-effort, fails gracefully in tests
                pass

        # Tabdeal-only: there is no candle backfill. Backtests run over locally
        # recorded history only; a range with no recorded data is an explicit error
        # (the frontend clamps range pickers to the recorded coverage window).
        _progress("loading_data", 20)
        df = load_candles(coin, interval, start, end, network=network)
        if df.empty:
            raise ValueError(
                f"no recorded candles for {coin}/{interval} in the requested range "
                f"(history begins when the recorder was switched on)"
            )
        funding_df = load_funding(coin, start, end, network=network)
        bt.range_start = datetime.fromtimestamp(int(df["ts"].min()) / 1000, tz=timezone.utc)
        bt.range_end = datetime.fromtimestamp(int(df["ts"].max()) / 1000, tz=timezone.utc)
        bt.save(update_fields=["range_start", "range_end"])

        _progress("running_backtest", 40)
        live_config = strategy.live_config or {}
        from apps.risk.config import read_risk

        result = run_backtest(
            strategy.source,
            df,
            commission=commission,
            slippage=slippage,
            leverage=read_risk(live_config).get("leverage"),
            initial_balance=initial_balance,
            funding_df=funding_df if not funding_df.empty else None,
            live_config=live_config,
            chart_interval=interval,
            symbol=coin,
        )

        _progress("saving", 90)
        _persist_backtest_result(bt, result)
    except Exception as exc:  # noqa: BLE001
        bt.status = Backtest.Status.FAILED
        bt.error = str(exc)
        bt.save(update_fields=["status", "error"])
        _notify(strategy, {"source": "backtest", "backtest_id": bt.id, "status": "failed", "error": str(exc)})
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "metrics": result.metrics}


def _recover_positions_if_any(strategy: Strategy) -> dict[str, object] | None:
    """Query the strategy's exchange for an open position and return recovered position/PnL, or None."""
    from apps.credentials.models import Exchange

    if strategy.credential is None:
        return None
    if strategy.credential.exchange == Exchange.TABDEAL:
        return _recover_tabdeal_position(strategy)
    # Tabdeal is the only supported live exchange; nothing to recover otherwise.
    return None


def _recover_tabdeal_position(strategy: Strategy) -> dict[str, object] | None:
    """Query Tabdeal for the strategy's own open position and return recovered position/PnL, or None."""
    from apps.exchange.tabdeal_futures import TabdealFuturesClient
    from apps.transpiler.runtime.tabdeal_broker import to_tabdeal_symbol

    try:
        client = TabdealFuturesClient(strategy.credential)
        pos = client.get_position(to_tabdeal_symbol(strategy.symbol))
        if pos is None:
            return None
        return {
            "position": float(pos.get("positionAmt", 0)),
            "entry_px": float(pos.get("entryPrice", 0)),
            "pnl": float(pos.get("unRealizedProfit", pos.get("unrealizedProfit", 0))),
        }
    except (TypeError, ValueError):
        return None
    except Exception:  # noqa: BLE001
        logger.exception("tabdeal position recovery failed")
        return None


@shared_task(name="transpiler.start_live_strategy")
def start_live_strategy_task(strategy_id: int):
    """Seed candles, warmup interpreter state, register WS subscription."""
    from apps.strategies.models import Strategy

    from .live.runner import LiveIncrementalRunner

    strategy = Strategy.objects.select_related("credential", "user").get(pk=strategy_id)
    runner = LiveIncrementalRunner()
    try:
        runner.seed_and_warmup(strategy)
    except Exception as exc:  # noqa: BLE001
        state = strategy.state if hasattr(strategy, "state") else None
        if state is None:
            from apps.strategies.models import StrategyState

            state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        state.live_error = str(exc)
        state.save(update_fields=["live_error"])
        _notify(strategy, {"source": "live", "status": "failed", "error": str(exc)})
        return {"ok": False, "error": str(exc)}

    recovered = _recover_positions_if_any(strategy)
    if recovered is not None:
        from apps.strategies.models import StrategyState

        state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        state.position = recovered["position"]
        state.entry_price = recovered["entry_px"]
        state.pnl = recovered["pnl"]
        state.save(update_fields=["position", "entry_price", "pnl"])

    strategy.status = Strategy.Status.ACTIVE
    strategy.save(update_fields=["status"])
    _notify(strategy, {"source": "live", "status": "started"})
    return {"ok": True}


@shared_task(name="transpiler.stop_live_strategy")
def stop_live_strategy_task(strategy_id: int):
    """Unregister subscription and clear live session."""
    from apps.strategies.models import Strategy

    from .live.runner import LiveIncrementalRunner

    strategy = Strategy.objects.select_related("credential").get(pk=strategy_id)
    LiveIncrementalRunner.stop(strategy)
    strategy.status = Strategy.Status.PAUSED
    strategy.save(update_fields=["status"])
    _notify(strategy, {"source": "live", "status": "stopped"})
    return {"ok": True}


@shared_task(name="transpiler.process_live_bar")
def process_live_bar_task(strategy_id: int, candle: dict):
    """Process one closed candle for an active live strategy."""
    from apps.strategies.models import Strategy

    from .live.runner import LiveIncrementalRunner

    strategy = Strategy.objects.select_related("credential", "user").get(pk=strategy_id)
    if strategy.status != Strategy.Status.ACTIVE:
        return {"ok": False, "skipped": "not active"}

    runner = LiveIncrementalRunner()
    try:
        processed = runner.on_closed_candle(strategy, candle)
    except Exception as exc:  # noqa: BLE001
        from apps.strategies.models import StrategyState

        state, _ = StrategyState.objects.get_or_create(strategy=strategy)
        state.live_error = str(exc)
        state.save(update_fields=["live_error"])
        _notify(strategy, {"source": "live", "status": "error", "error": str(exc)})
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "processed": processed}
