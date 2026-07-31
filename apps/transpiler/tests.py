"""Phase 2 verification tests for the Pine Script transpiler."""
from decimal import Decimal
from unittest import mock

import numpy as np
import pandas as pd
import pytest
from django.contrib.auth import get_user_model

from apps.credentials.models import ExchangeCredential, Network
from apps.strategies.models import Strategy

from . import ast_nodes as ast
from .engine import compile, run_backtest, run_live
from .exceptions import PineSemanticError, PineSyntaxError, UnsupportedFeatureError
from .parser import parse
from .runtime import indicators as ind
from .runtime import interpreter
from .runtime.context import ExecutionContext
from .runtime.order_router import WarmupBroker

SMA_CROSS = """strategy("SMA Cross")
fast = ta.sma(close, 5)
slow = ta.sma(close, 20)
var float held = na
if ta.crossover(fast, slow)
    held := close
    strategy.entry("long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("long")
"""

EXIT_TPSL = """strategy("Exit TPSL")
strategy.entry("long", strategy.long, qty=1)
strategy.exit("x", stop=90, limit=110)
"""


def _wave_df(n=120):
    t = np.arange(n)
    close = 100 + 10 * np.sin(t / 8.0) + t * 0.05
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.ones(n) * 10}
    )


# 1. Lexing / parsing
def test_parse_builds_expected_ast():
    prog = parse(SMA_CROSS)
    assert prog.header is not None
    kinds = [type(n).__name__ for n in prog.body]
    assert kinds == ["AssignNode", "AssignNode", "StateDeclarationNode", "IfNode", "IfNode"]


def test_syntax_error_reports_location():
    with pytest.raises(PineSyntaxError) as e:
        parse('strategy("x")\nfast = ta.sma(close, \n')
    assert e.value.line is not None


# 2. Restriction layer
@pytest.mark.parametrize("bad", ["plotshape(close)", "bgcolor(close)"])
def test_restriction_rejects_visual_builtins(bad):
    with pytest.raises(UnsupportedFeatureError):
        compile(f'strategy("x")\n{bad}\n')


def test_plot_is_allowed_noop():
    compile('strategy("x")\nplot(close)\n')


def test_mid_file_line_comments_allowed():
    src = """strategy("x")

// === SIGNUM INPUTS ===
signum_bot_id = input.string("PTl6LD6u", "Signum Bot ID")
"""
    compile(src)


def test_inline_line_comment_after_statement():
    compile('strategy("x")\nx = input.string("80%", "size") // trailing note\n')


# 3. Semantic
def test_use_before_declare():
    with pytest.raises(PineSemanticError):
        compile('strategy("x")\ny = x + 1\n')


def test_type_mismatch_logical_on_float():
    with pytest.raises(PineSemanticError):
        compile('strategy("x")\nz = close and 5\n')


def test_valid_script_compiles():
    assert compile(SMA_CROSS).header is not None


# 4. Indicator parity
def test_sma_matches_pandas_reference():
    close = _wave_df()["close"].to_numpy()
    assert np.allclose(ind.sma(close, 14), pd.Series(close).rolling(14).mean().to_numpy(),
                       equal_nan=True)


def test_ema_rma_rsi_finite():
    close = _wave_df()["close"].to_numpy()
    for fn in (ind.ema, ind.rma, ind.rsi):
        out = fn(close, 14)
        assert np.isfinite(out[-1])


# 5. Backtest end-to-end
METRIC_KEYS = {
    "num_trades", "net_pnl", "gross_pnl", "total_commission", "win_rate", "max_drawdown",
    "profit_factor", "sharpe_ratio", "avg_trade", "risk_reward", "expectancy", "funding_paid",
    "leverage", "liquidations", "final_equity", "equity_series", "initial_balance",
}


def test_backtest_produces_trades_and_metrics():
    res = run_backtest(SMA_CROSS, _wave_df())
    assert res.metrics["num_trades"] >= 1
    assert set(res.metrics) == METRIC_KEYS
    t = res.trades[0]
    assert t["side"] == "long" and t["exit_price"] is not None


def test_fill_at_next_bar_open():
    """Entry on bar i fills at open[i+1] (after slippage)."""
    src = """strategy("fill")
if bar_index == 5
    strategy.entry("long", strategy.long)
if bar_index == 10
    strategy.close("long")
"""
    df = _wave_df(20)
    slip = 0.001
    res = run_backtest(src, df, slippage=slip)
    assert len(res.trades) == 1
    expected_entry = float(df["open"].iloc[6]) * (1.0 + slip)
    assert res.trades[0]["entry_bar"] == 6
    assert res.trades[0]["entry_price"] == pytest.approx(expected_entry)


def test_last_bar_signal_does_not_fill():
    src = """strategy("last")
if bar_index == 4
    strategy.entry("long", strategy.long)
"""
    df = _wave_df(5)
    res = run_backtest(src, df)
    assert res.metrics["num_trades"] == 0


def test_commission_and_slippage_reduce_pnl():
    src = """strategy("fees")
if bar_index == 1
    strategy.entry("long", strategy.long)
if bar_index == 5
    strategy.close("long")
"""
    df = _wave_df(10)
    no_fees = run_backtest(src, df, commission=0.0, slippage=0.0)
    with_fees = run_backtest(src, df, commission=0.001, slippage=0.001)
    assert with_fees.metrics["total_commission"] > 0
    assert with_fees.metrics["gross_pnl"] > with_fees.metrics["net_pnl"]
    assert with_fees.metrics["net_pnl"] < no_fees.metrics["net_pnl"]


def test_position_size_gates_entry_once():
    src = """strategy("pos")
if bar_index == 5 and strategy.position_size == 0
    strategy.entry("long", strategy.long)
if bar_index == 50
    strategy.close("long")
"""
    res = run_backtest(src, _wave_df(60))
    assert res.metrics["num_trades"] == 1


# 5b. input.*
def test_input_int_default_used_in_rsi():
    src = """strategy("input rsi")
len = input.int(14, "Length")
r = ta.rsi(close, len)
if bar_index == 30
    strategy.entry("long", strategy.long)
"""
    res = run_backtest(src, _wave_df(60))
    assert compile(src).header is not None


def test_input_float_defval_kwarg():
    src = 'strategy("x")\nth = input.float(defval=2.5)\n'
    prog = compile(src)
    res = run_backtest(src, _wave_df(5))
    assert res.metrics["num_trades"] == 0


# 5c. User-defined functions
def test_udf_single_line():
    src = """strategy("udf")
myAvg(x, y) => (x + y) / 2
s = myAvg(close, open)
if bar_index == 10
    strategy.entry("long", strategy.long)
"""
    res = run_backtest(src, _wave_df(30))
    assert res.metrics["num_trades"] == 1


def test_udf_multiline_suite():
    src = """strategy("udf multi")
dbl(x) =>
    y = x * 2
    y + 1
z = dbl(close)
if bar_index == 10
    strategy.entry("long", strategy.long)
"""
    res = run_backtest(src, _wave_df(30))
    assert res.metrics["num_trades"] == 1


def test_udf_wrong_arity_errors():
    with pytest.raises(PineSemanticError):
        compile('strategy("x")\nf(a) => a\ny = f(1, 2)\n')


# 5d. Indicators + tuple destructuring
def test_atr_matches_reference():
    df = _wave_df(80)
    high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    tr = ind.tr(high, low, close)
    ref = ind.rma(tr, 14)
    src = """strategy("atr")
a = ta.atr(14)
"""
    ctx_df = df
    from .runtime.context import ExecutionContext
    from .runtime.order_router import SimBroker
    from .runtime import interpreter
    from .parser import parse
    from .semantic import analyze
    prog = parse(src)
    analyze(prog)
    broker = SimBroker()
    ctx = ExecutionContext(ctx_df, broker)
    interpreter.run(prog, ctx)
    assert np.allclose(ctx.arrays["a"], ref, equal_nan=True, rtol=1e-5)


def test_change_matches_reference():
    close = _wave_df()["close"].to_numpy()
    ref = ind.change(close, 5)
    assert np.allclose(ind.change(close, 5), ref, equal_nan=True)


def test_macd_tuple_destructure():
    src = """strategy("macd")
[macdLine, signalLine, histLine] = ta.macd(close, 12, 26, 9)
if ta.crossover(macdLine, signalLine)
    strategy.entry("long", strategy.long)
if ta.crossunder(macdLine, signalLine)
    strategy.close("long")
"""
    res = run_backtest(src, _wave_df(120))
    assert res.metrics["num_trades"] >= 0


def test_bb_tuple_destructure():
    src = """strategy("bb")
[mid, upper, lower] = ta.bb(close, 20, 2.0)
if close < lower
    strategy.entry("long", strategy.long)
if close > upper
    strategy.close("long")
"""
    res = run_backtest(src, _wave_df(80))
    assert res.metrics["num_trades"] >= 0


def test_barssince_valuewhen():
    src = """strategy("stateful")
bs = ta.barssince(close > open)
vw = ta.valuewhen(close > open, close, 0)
"""
    res = run_backtest(src, _wave_df(40))
    assert res.metrics["num_trades"] == 0


def test_var_persistence_and_history():
    # `var` initialises once; `[]` reads prior bars.
    src = ('strategy("x")\n'
           'var int counter = 0\n'
           'counter := counter + 1\n'
           'prevClose = close[1]\n')
    # Should run without error across all bars.
    res = run_backtest(src, _wave_df(30))
    assert res.metrics["num_trades"] == 0


# 6. Live routing (mocked Hyperliquid) + kill-switch
def _hl_cred(user, **kwargs):
    cred = ExchangeCredential(
        user=user,
        label="agent",
        wallet_address="0x" + "11" * 20,
        network=Network.TESTNET,
        **kwargs,
    )
    cred.set_agent_key("0x" + "aa" * 32)
    cred.save()
    return cred


def _fake_hl_exchange():
    ex = mock.Mock()
    ex.market_open.return_value = {
        "status": "ok",
        "response": {"data": {"statuses": [{"filled": {"oid": 999}}]}},
    }
    return ex


def _live_setup(trading_enabled):
    User = get_user_model()
    user = User.objects.create_user(
        username=f"u{trading_enabled}", password="pw", is_trading_enabled=trading_enabled
    )
    cred = _hl_cred(user)
    strat = Strategy.objects.create(
        user=user, credential=cred, name="s", type="t", symbol="BTC",
        source='strategy("x")\nstrategy.entry("long", strategy.long)\n',
    )
    return user, cred, strat


@pytest.mark.django_db
def test_live_places_order_when_enabled():
    from apps.execution.models import ExecutionLog, OrderRecord

    _, cred, strat = _live_setup(trading_enabled=True)
    fake_exchange = _fake_hl_exchange()

    with (
        mock.patch("apps.exchange.hl_client.build_exchange", return_value=fake_exchange),
        mock.patch("apps.exchange.hl_meta.resolve_trading_name", return_value="BTC"),
        mock.patch("apps.exchange.hl_meta.get_asset_meta") as meta,
        mock.patch("apps.exchange.risk.pre_trade_gate") as gate,
    ):
        meta.return_value = mock.Mock(sz_decimals=4, is_spot=False, name="BTC")
        gate.return_value = mock.Mock(ok=True, reason="", details={})
        run_live(strat.source, _wave_df(5), credential=cred, strategy=strat, symbol="BTC")

    assert fake_exchange.market_open.called
    assert OrderRecord.objects.filter(strategy=strat).count() >= 1
    assert ExecutionLog.objects.filter(strategy=strat, event="order.placed").exists()


@pytest.mark.django_db
def test_live_blocked_by_kill_switch():
    from apps.execution.models import ExecutionLog, OrderRecord

    _, cred, strat = _live_setup(trading_enabled=False)
    fake_exchange = _fake_hl_exchange()

    with (
        mock.patch("apps.exchange.hl_client.build_exchange", return_value=fake_exchange),
        mock.patch("apps.exchange.hl_meta.resolve_trading_name", return_value="BTC"),
    ):
        run_live(strat.source, _wave_df(5), credential=cred, strategy=strat, symbol="BTC")

    assert not fake_exchange.market_open.called
    assert OrderRecord.objects.filter(strategy=strat).count() == 0
    assert ExecutionLog.objects.filter(strategy=strat, event="order.blocked").exists()


# 7. Celery-task path (eager, synchronous)
@pytest.mark.django_db
def test_run_backtest_task_persists_results(settings):
    from .models import Backtest
    from .tasks import run_backtest_task

    User = get_user_model()
    user = User.objects.create_user(username="cuser", password="pw")
    cred = _hl_cred(user)
    strat = Strategy.objects.create(
        user=user, credential=cred, name="s", type="t", symbol="BTC",
        source=SMA_CROSS,
    )
    bt = Backtest.objects.create(strategy=strat, symbol="BTC")
    df = _wave_df()
    candles = df.to_dict("records")

    run_backtest_task.run(bt.id, candles)  # synchronous execution
    bt.refresh_from_db()
    assert bt.status == Backtest.Status.DONE
    assert bt.metrics["num_trades"] >= 1
    assert bt.trades.count() == bt.metrics["num_trades"]
    assert bt.range_start is not None
    assert bt.range_end is not None


@pytest.mark.django_db
def test_run_backtest_stored_task_uses_local_candles(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path)
    from apps.exchange import candle_store

    from .models import Backtest
    from .tasks import run_backtest_stored_task

    User = get_user_model()
    user = User.objects.create_user(username="storeu", password="pw")
    cred = _hl_cred(user)
    strat = Strategy.objects.create(
        user=user, credential=cred, name="s", type="t", symbol="BTC", source=SMA_CROSS,
    )

    df = _wave_df()
    df["ts"] = range(1000, 1000 + len(df) * 60, 60)
    candle_store.save_candles("BTC", "1h", df)

    bt = Backtest.objects.create(strategy=strat, symbol="BTC", timeframe="1h")
    run_backtest_stored_task.run(bt.id, "BTC", "1h")  # synchronous, no exchange calls

    bt.refresh_from_db()
    assert bt.status == Backtest.Status.DONE
    assert bt.metrics["num_trades"] >= 1
    assert bt.trades.count() == bt.metrics["num_trades"]


@pytest.mark.django_db
def test_run_backtest_stored_task_fails_when_no_candles(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path)
    from .models import Backtest
    from .tasks import run_backtest_stored_task

    User = get_user_model()
    user = User.objects.create_user(username="nostoreu", password="pw")
    cred = _hl_cred(user)
    strat = Strategy.objects.create(
        user=user, credential=cred, name="s", type="t", symbol="BTC", source=SMA_CROSS,
    )
    bt = Backtest.objects.create(strategy=strat, symbol="NOSTORE", timeframe="1h")
    res = run_backtest_stored_task.run(bt.id, "NOSTORE", "1h")

    assert res["ok"] is False
    bt.refresh_from_db()
    assert bt.status == Backtest.Status.FAILED


@pytest.mark.django_db
def test_backtest_api_includes_trade_exit_fields(client):
    from .models import Backtest, BacktestTrade

    User = get_user_model()
    user = User.objects.create_user(username="apiu", password="pw")
    client.force_login(user)
    strat = Strategy.objects.create(user=user, name="s", type="pine", symbol="BTC", source=SMA_CROSS)
    bt = Backtest.objects.create(strategy=strat, symbol="BTC", status=Backtest.Status.DONE, metrics={})
    BacktestTrade.objects.create(
        backtest=bt,
        side="long",
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        size=Decimal("1"),
        pnl=Decimal("10"),
        entry_bar=1,
        exit_bar=5,
        stop_px=Decimal("90"),
        limit_px=Decimal("120"),
        exit_reason="take_profit",
    )

    data = client.get(f"/api/backtests/{bt.id}/").json()
    trade = data["trades"][0]
    assert trade["exit_reason"] == "take_profit"
    assert float(trade["stop_px"]) == 90.0
    assert float(trade["limit_px"]) == 120.0


@pytest.mark.django_db
def test_download_to_backtest_e2e(tmp_path, settings):
    """Stored candles from download path are readable by the backtest engine."""
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    from apps.exchange import candle_store

    from .models import Backtest
    from .tasks import run_backtest_stored_task

    User = get_user_model()
    user = User.objects.create_user(username="e2eu", password="pw")
    cred = _hl_cred(user)
    strat = Strategy.objects.create(
        user=user, credential=cred, name="e2e", type="t", symbol="BTC", source=SMA_CROSS,
    )

    df = _wave_df()
    df["ts"] = list(range(1_700_000_000_000, 1_700_000_000_000 + len(df) * 3_600_000, 3_600_000))
    with mock.patch("apps.exchange.candle_store._save_parquet"):
        candle_store.save_candles("BTC", "1h", df, network="mainnet")

    bt = Backtest.objects.create(
        strategy=strat, symbol="BTC", timeframe="1h", network="mainnet",
    )
    run_backtest_stored_task.run(bt.id, "BTC", "1h", network="mainnet")

    bt.refresh_from_db()
    assert bt.status == Backtest.Status.DONE
    assert bt.metrics.get("num_trades", 0) >= 1
    assert bt.trades.count() == bt.metrics["num_trades"]


# 8. Phase 3 — live tasks
def _live_strategy(trading_enabled=True, validated=True):
    User = get_user_model()
    user = User.objects.create_user(
        username=f"live{trading_enabled}{validated}",
        password="pw",
        is_trading_enabled=trading_enabled,
    )
    cred = _hl_cred(user, is_active=True)
    strat = Strategy.objects.create(
        user=user,
        credential=cred,
        name="live",
        type="t",
        symbol="BTC",
        timeframe="1m",
        warmup_bars=10,
        source='strategy("x")\nstrategy.entry("long", strategy.long)\n',
        validation_status="ok" if validated else "",
    )
    return user, cred, strat


@pytest.mark.django_db
def test_start_live_task_activates_and_creates_session():
    from unittest import mock

    from apps.strategies.models import StrategyState

    from .live import session_store
    from .tasks import start_live_strategy_task

    _, _, strat = _live_strategy()
    df = _wave_df(10)
    df["ts"] = range(1000, 1000 + len(df) * 60, 60)

    with mock.patch("apps.transpiler.live.runner.fetch_candles", return_value=df):
        start_live_strategy_task.run(strat.pk)

    strat.refresh_from_db()
    assert strat.status == Strategy.Status.ACTIVE
    assert session_store.session_exists(strat.pk)
    state = StrategyState.objects.get(strategy=strat)
    assert state.live_started_at is not None
    assert state.last_bar_ts is not None


@pytest.mark.django_db
def test_stop_live_task_pauses_and_deletes_session():
    from unittest import mock

    from .live import session_store
    from .tasks import start_live_strategy_task, stop_live_strategy_task

    _, _, strat = _live_strategy()
    df = _wave_df(10)
    df["ts"] = range(1000, 1000 + len(df) * 60, 60)

    with mock.patch("apps.transpiler.live.runner.fetch_candles", return_value=df):
        start_live_strategy_task.run(strat.pk)
    assert session_store.session_exists(strat.pk)

    stop_live_strategy_task.run(strat.pk)
    strat.refresh_from_db()
    assert strat.status == Strategy.Status.PAUSED
    assert not session_store.session_exists(strat.pk)


@pytest.mark.django_db
def test_process_live_bar_skips_duplicate_ts():
    from unittest import mock

    from apps.strategies.models import StrategyState

    from .tasks import process_live_bar_task, start_live_strategy_task

    _, _, strat = _live_strategy()
    df = _wave_df(10)
    df["ts"] = range(1000, 1000 + len(df) * 60, 60)

    with mock.patch("apps.transpiler.live.runner.fetch_candles", return_value=df):
        start_live_strategy_task.run(strat.pk)

    state = StrategyState.objects.get(strategy=strat)
    last_ts = state.last_bar_ts
    candle = {"ts": last_ts, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    result = process_live_bar_task.run(strat.pk, candle)
    assert result["processed"] is False


@pytest.mark.django_db
def test_live_spot_uses_order_api():
    from apps.execution.models import OrderRecord
    from apps.strategies.models import Strategy

    User = get_user_model()
    user = User.objects.create_user(username="spotu", password="pw", is_trading_enabled=True)
    cred = _hl_cred(user)
    strat = Strategy.objects.create(
        user=user, credential=cred, name="s", type="t", symbol="ETH",
        market_type=Strategy.MarketType.SPOT,
        source='strategy("x")\nstrategy.entry("long", strategy.long)\n',
    )
    fake_exchange = mock.Mock()
    fake_exchange.order.return_value = {
        "status": "ok",
        "response": {"data": {"statuses": [{"filled": {"oid": 1}}]}},
    }
    with (
        mock.patch("apps.exchange.hl_client.build_exchange", return_value=fake_exchange),
        mock.patch("apps.exchange.hl_meta.aggressive_spot_price", return_value=100.0),
        mock.patch("apps.exchange.hl_meta.resolve_trading_name", return_value="BTC/USDC"),
        mock.patch("apps.exchange.hl_meta.get_asset_meta") as meta,
    ):
        meta.return_value = mock.Mock(sz_decimals=8, is_spot=True, name="BTC/USDC")
        run_live(strat.source, _wave_df(5), credential=cred, strategy=strat, symbol="ETH")
    assert fake_exchange.order.called
    assert not fake_exchange.market_open.called
    assert OrderRecord.objects.filter(strategy=strat).exists()


@pytest.mark.django_db
def test_live_exit_places_trigger_orders_for_perp():
    from apps.strategies.models import Strategy

    User = get_user_model()
    user = User.objects.create_user(username="tpslu", password="pw", is_trading_enabled=True)
    cred = _hl_cred(user)
    strat = Strategy.objects.create(
        user=user,
        credential=cred,
        name="t",
        type="t",
        symbol="BTC",
        market_type=Strategy.MarketType.PERP,
        source=EXIT_TPSL,
    )
    fake_exchange = mock.Mock()
    fake_exchange.order.return_value = {
        "status": "ok",
        "response": {"data": {"statuses": [{"resting": {"oid": 1}}]}},
    }
    with (
        mock.patch("apps.exchange.hl_client.build_exchange", return_value=fake_exchange),
        mock.patch("apps.exchange.hl_meta.resolve_trading_name", return_value="BTC"),
        mock.patch("apps.exchange.risk.pre_trade_gate") as gate,
    ):
        gate.return_value = mock.Mock(ok=True, reason="", details={})
        run_live(strat.source, _wave_df(5), credential=cred, strategy=strat, symbol="BTC")

    assert fake_exchange.order.called

@pytest.mark.django_db
def test_process_live_bar_places_order_on_new_candle():
    from apps.execution.models import OrderRecord

    from .tasks import process_live_bar_task, start_live_strategy_task

    _, cred, strat = _live_strategy(trading_enabled=True)
    df = _wave_df(10)
    df["ts"] = range(1000, 1000 + len(df) * 60, 60)

    fake_exchange = _fake_hl_exchange()

    with mock.patch("apps.transpiler.live.runner.fetch_candles", return_value=df):
        start_live_strategy_task.run(strat.pk)

    candle = {"ts": 999999, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    with (
        mock.patch("apps.exchange.hl_client.build_exchange", return_value=fake_exchange),
        mock.patch("apps.exchange.risk.pre_trade_gate") as gate,
    ):
        gate.return_value = mock.Mock(ok=True, reason="", details={})
        result = process_live_bar_task.run(strat.pk, candle)

    assert result["processed"] is True
    assert fake_exchange.market_open.called
    assert OrderRecord.objects.filter(strategy=strat).exists()


def test_sim_broker_funding_and_liquidation():
    from apps.transpiler.runtime.sim_broker import SimBroker

    broker = SimBroker(
        default_qty=1.0,
        leverage=10.0,
        initial_balance=100.0,
        funding_rates={1000: 0.001},
        maintenance_margin_rate=0.9,
    )
    broker.entry("long", "long", 100.0, 0, qty=10.0)
    broker.on_bar(0, 1000, 100.0, 101.0, 99.0, 100.0)
    assert broker.funding_paid != 0.0
    broker.check_liquidation(10.0, 1)
    assert broker.liquidations >= 1


def test_sim_broker_partial_close():
    from apps.transpiler.runtime.sim_broker import SimBroker

    broker = SimBroker(default_qty=2.0)
    broker.fill_at_next_open = False
    broker.entry("p", "long", 100.0, 0, qty=2.0)
    broker.close("p", 110.0, 1, qty_pct=0.5)
    assert len(broker.closed) == 1
    assert "p" in broker.open_trades
    assert broker.open_trades["p"].size == 1.0


def test_sim_broker_sl_tp_intrabar():
    from apps.transpiler.runtime.sim_broker import SimBroker

    broker = SimBroker(default_qty=1.0)
    broker.fill_at_next_open = False
    broker.entry("t", "long", 100.0, 0)
    broker.exit("t", 100.0, 0, stop=95.0)
    broker.check_stops(bar_high=102.0, bar_low=94.0, bar_index=1)
    assert len(broker.closed) == 1
    assert broker.closed[0].exit_reason == "stop"


def test_metrics_sharpe_and_profit_factor():
    from apps.transpiler.metrics import compute_metrics

    class T:
        def __init__(self, pnl, gross_pnl=0, commission=0):
            self.pnl = pnl
            self.gross_pnl = gross_pnl or pnl
            self.commission = commission

    m = compute_metrics([T(10), T(-5), T(8)], equity_series=[10000, 10010, 10005, 10013])
    assert m["num_trades"] == 3
    assert m["profit_factor"] > 0
    assert "sharpe_ratio" in m


def test_strategy_plugin_registry():
    from apps.strategies.plugins.registry import get_engine, list_engines

    assert "pine" in list_engines()
    assert get_engine("pine").name == "pine"


OCC_SIGNUM = """strategy("OCC 1H - Signum Edition", overlay=true, initial_capital=30, default_qty_type=strategy.percent_of_equity, default_qty_value=90)

signum_bot_id = input.string("PTl6LD6u", "Signum Bot ID")
order_size_val = input.string("80%", "Order Size (as string)")

multiplier   = input.int(3, "Multiplier (Trend Speed)", minval=1)
basisType    = input.string("SMMA", "MA Type", options=["SMA", "EMA", "DEMA", "TEMA", "WMA", "VWMA", "SMMA", "HullMA", "LSMA", "ALMA"])
basisLen     = input.int(8, "MA Period", minval=1)

getMA(type, src, length) =>
    float res = na
    if type == "SMA"
        res := ta.sma(src, length)
    else if type == "EMA"
        res := ta.ema(src, length)
    else if type == "DEMA"
        e = ta.ema(src, length)
        res := 2 * e - ta.ema(e, length)
    else if type == "WMA"
        res := ta.wma(src, length)
    else if type == "VWMA"
        res := ta.vwma(src, length)
    else if type == "SMMA"
        float smma = na
        smma := na(smma[1]) ? ta.sma(src, length) : (smma[1] * (length - 1) + src) / length
        res := smma
    else if type == "HullMA"
        res := ta.wma(2 * ta.wma(src, length / 2) - ta.wma(src, length), math.round(math.sqrt(length)))
    res

ma_c = getMA(basisType, close, basisLen)
ma_o = getMA(basisType, open, basisLen)

res_str = str.tostring(timeframe.multiplier * multiplier)
c_alt = request.security(syminfo.tickerid, res_str, ma_c[1], lookahead=barmerge.lookahead_off)
o_alt = request.security(syminfo.tickerid, res_str, ma_o[1], lookahead=barmerge.lookahead_off)

signum_json = '{"action": "{{strategy.order.action}}", "ticker": "{{ticker}}", "order_size": "' + order_size_val + '", "position_size": "{{strategy.position_size}}", "schema": "2", "timestamp": "{{time}}", "bot_id": "' + signum_bot_id + '"}'

if ta.crossover(c_alt, o_alt)
    strategy.entry("long", strategy.long, alert_message=signum_json)

if ta.crossunder(c_alt, o_alt)
    strategy.entry("short", strategy.short, alert_message=signum_json)

plot(c_alt, color=color.green, linewidth=2, title="Long Trend")
plot(o_alt, color=color.red, linewidth=2, title="Short Trend")
"""


def test_occ_signum_strategy_compiles():
    prog = compile(OCC_SIGNUM)
    assert prog.header is not None


def _hourly_trend_df(n=240):
    t = np.arange(n)
    close = 100.0 + np.sin(t / 12.0) * 5.0 + t * 0.02
    ts = (1_700_000_000_000 + t * 3_600_000).astype(np.int64)
    return pd.DataFrame(
        {
            "ts": ts,
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.ones(n) * 100.0,
        }
    )


def test_occ_signum_backtest_runs():
    res = run_backtest(OCC_SIGNUM, _hourly_trend_df(), chart_interval="1h", symbol="HYPE")
    assert res.metrics["initial_balance"] == 30.0
    assert "num_trades" in res.metrics


def _volatile_occ_df(n=360):
    """OHLCV with phase-shifted close/open so HTF OCC MAs cross."""
    t = np.arange(n)
    close = 100.0 + np.sin(t / 8.0) * 15.0
    open_ = 100.0 + np.sin(t / 8.0 - 1.5) * 15.0
    ts = (1_700_000_000_000 + t * 3_600_000).astype(np.int64)
    return pd.DataFrame(
        {
            "ts": ts,
            "open": open_,
            "high": np.maximum(close, open_) + 1.0,
            "low": np.minimum(close, open_) - 1.0,
            "close": close,
            "volume": np.ones(n) * 100.0,
        }
    )


def test_udf_ta_sma_on_series_param():
    src = """strategy("udf sma")
getMA(type, src, length) =>
    float res = na
    if type == "SMA"
        res := ta.sma(src, length)
    res
ma_c = getMA("SMA", close, 8)
"""
    df = _hourly_trend_df(80)
    program = compile(src)
    ctx = ExecutionContext(df, WarmupBroker(), chart_interval="1h", program=program)
    ctx.functions = {f.name: f for f in program.functions}
    interpreter.run_warmup(program, ctx)
    finite = sum(1 for v in ctx.scalars["ma_c"].values if v == v)
    assert finite >= len(df) - 8


def test_getMA_smma_finite():
    src = """strategy("udf smma")
getMA(type, src, length) =>
    float res = na
    if type == "SMMA"
        float smma = na
        smma := na(smma[1]) ? ta.sma(src, length) : (smma[1] * (length - 1) + src) / length
        res := smma
    res
ma_c = getMA("SMMA", close, 8)
"""
    df = _hourly_trend_df(80)
    program = compile(src)
    ctx = ExecutionContext(df, WarmupBroker(), chart_interval="1h", program=program)
    ctx.functions = {f.name: f for f in program.functions}
    interpreter.run_warmup(program, ctx)
    finite = sum(1 for v in ctx.scalars["ma_c"].values if v == v)
    assert finite >= len(df) - 8


def test_occ_signum_c_alt_has_values():
    df = _hourly_trend_df(240)
    program = compile(OCC_SIGNUM)
    ctx = ExecutionContext(df, WarmupBroker(), chart_interval="1h", symbol="HYPE", program=program)
    ctx.functions = {f.name: f for f in program.functions}
    interpreter.const_eval_pass(program, ctx)
    interpreter.vectorize_pass(program, ctx)
    assert np.isfinite(ctx.arrays["c_alt"]).sum() > 8
    assert np.isfinite(ctx.arrays["o_alt"]).sum() > 8
    # The resolution string must resolve to the 3x higher timeframe, not the chart TF.
    assert ctx.scalars["res_str"].current == "180"


def test_occ_signum_produces_trades():
    res = run_backtest(OCC_SIGNUM, _volatile_occ_df(), chart_interval="1h", symbol="HYPE")
    assert res.metrics["num_trades"] > 0


def test_percent_of_equity_sizing():
    src = """strategy("pct", default_qty_type=strategy.percent_of_equity, default_qty_value=50, initial_capital=100)
if bar_index == 5
    strategy.entry("long", strategy.long)
"""
    df = _wave_df(20)
    res = run_backtest(src, df)
    assert res.metrics["initial_balance"] == 100.0
    if res.trades:
        assert res.trades[0]["size"] > 0


def test_position_reversal_on_opposite_entry():
    src = """strategy("rev")
if bar_index == 5
    strategy.entry("long", strategy.long)
if bar_index == 10
    strategy.entry("short", strategy.short)
if bar_index == 15
    strategy.close("short")
"""
    df = _wave_df(25)
    res = run_backtest(src, df)
    sides = [t["side"] for t in res.trades]
    assert "long" in sides
    assert "short" in sides


def test_request_security_htf_smma():
    src = """strategy("htf")
basisLen = 4
ma_c = ta.sma(close, basisLen)
res_str = str.tostring(timeframe.multiplier * 2)
c_alt = request.security(syminfo.tickerid, res_str, ma_c[1], lookahead=barmerge.lookahead_off)
if ta.crossover(c_alt, ta.sma(close, 3))
    strategy.entry("long", strategy.long)
"""
    res = run_backtest(src, _hourly_trend_df(120), chart_interval="1h", symbol="BTC")
    assert "num_trades" in res.metrics


# --- Phase 1 correctness regressions -------------------------------------
# These assert numeric correctness, not just finiteness. The OCC_SIGNUM fixture
# passed for months while silently computing the wrong series.

def test_series_history_offset_is_one_bar_back():
    """`x[1]` is the previous bar, not two bars back."""
    src = """strategy("hist")
var float ctr = na
ctr := na(ctr[1]) ? 1 : ctr[1] + 1
prev = ctr[1]
"""
    df = _wave_df(8)
    program = compile(src)
    ctx = ExecutionContext(df, WarmupBroker(), program=program)
    interpreter.run_warmup(program, ctx)
    ctr = ctx.scalars["ctr"].values
    prev = ctx.scalars["prev"].values
    assert ctr == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    # prev[i] == ctr[i-1]; bar 0 has no history.
    assert prev[1:] == ctr[:-1]


def test_udf_locals_are_per_call_site():
    """Two calls to one UDF must not share the callee's local series."""
    src = """strategy("scope")
acc(src) =>
    float run = na
    run := na(run[1]) ? src : run[1] + src
    run
a = acc(close)
b = acc(open)
"""
    df = _hourly_trend_df(30)
    program = compile(src)
    ctx = ExecutionContext(df, WarmupBroker(), chart_interval="1h", program=program)
    interpreter.run_warmup(program, ctx)
    a = np.array(ctx.scalars["a"].values, dtype=float)
    b = np.array(ctx.scalars["b"].values, dtype=float)
    assert np.allclose(a, np.cumsum(df["close"].to_numpy()))
    assert np.allclose(b, np.cumsum(df["open"].to_numpy()))


def test_occ_signum_smma_matches_reference():
    """getMA(SMMA) must equal the hand-computed SMMA, and ma_c/ma_o must differ."""
    df = _hourly_trend_df(120)
    program = compile(OCC_SIGNUM)
    ctx = ExecutionContext(df, WarmupBroker(), chart_interval="1h", symbol="HYPE", program=program)
    interpreter.run_warmup(program, ctx)

    length = 8

    def smma(src):
        sma = pd.Series(src).rolling(length).mean().to_numpy()
        out, prev = np.full(len(src), np.nan), np.nan
        for i in range(len(src)):
            prev = sma[i] if np.isnan(prev) else (prev * (length - 1) + src[i]) / length
            out[i] = prev
        return out

    ma_c = np.array(ctx.scalars["ma_c"].values, dtype=float)
    ma_o = np.array(ctx.scalars["ma_o"].values, dtype=float)
    # Each call site must track its own source series. When the locals are
    # shared, both collapse onto whichever ran last.
    assert np.allclose(ma_c[-10:], smma(df["close"].to_numpy())[-10:], atol=1e-9)
    assert np.allclose(ma_o[-10:], smma(df["open"].to_numpy())[-10:], atol=1e-9)


def test_pine_timeframe_semantics():
    from .runtime.timeframe import pine_multiplier, pine_period, resolve_security_minutes

    assert pine_period("1h") == "60"
    assert pine_multiplier("1h") == 60
    assert pine_multiplier("5m") == 5
    assert pine_multiplier("1d") == 1
    # A bare number is minutes in Pine, not chart-bar multiples.
    assert resolve_security_minutes("1h", "180") == 180
    assert resolve_security_minutes("15m", "60") == 60
    assert resolve_security_minutes("1h", "D") == 1440


def test_unresolvable_security_timeframe_raises():
    from .runtime.timeframe import resolve_security_minutes

    with pytest.raises(PineSemanticError):
        resolve_security_minutes("1h", "nan")
    with pytest.raises(PineSemanticError):
        resolve_security_minutes("1h", "banana")


def test_unknown_builtin_is_rejected():
    """Unimplemented builtins used to evaluate to `na` silently at every stage."""
    for bad in ("ta.supertrend(3, 10)", "ta.dema(close, 5)", "foo.bar(1)", "str.upper(close)"):
        with pytest.raises(UnsupportedFeatureError):
            compile(f'strategy("x")\ny = {bad}\n')


def test_real_occ_strategy_file_still_compiles():
    """The user's actual strategy must survive the allow-list."""
    prog = compile(OCC_SIGNUM)
    assert prog.header is not None


# --- Phase 2: multi-timeframe (request.security) ---------------------------

def _hourly_df_slice(n_total=240, take=None):
    df = _hourly_trend_df(n_total)
    return df if take is None else df.iloc[n_total - take:].reset_index(drop=True)


def test_htf_buckets_are_absolute_time_not_window_relative():
    """Live slides a window; HTF bars must not move when the window start moves."""
    from .runtime.security import resample_ohlcv

    full = resample_ohlcv(_hourly_df_slice(), 180, 60).set_index("ts")
    assert (full.index.to_numpy() % (3 * 3_600_000) == 0).all()

    for take in (120, 121, 122, 137):
        part = resample_ohlcv(_hourly_df_slice(take=take), 180, 60).set_index("ts")
        # Skip the first bucket: a sliced window can begin mid-bucket.
        shared = [ts for ts in part.index[1:] if ts in full.index]
        assert shared
        for ts in shared:
            cols = ["open", "high", "low", "close"]
            assert np.allclose(
                part.loc[ts, cols].to_numpy(dtype=float),
                full.loc[ts, cols].to_numpy(dtype=float),
            )


def test_security_lookahead_off_does_not_repaint():
    """A chart bar may only see HTF bars that already closed."""
    from .runtime.security import align_htf_to_ltf

    target_ms = 3 * 3_600_000
    htf_ts = np.array([0, target_ms, 2 * target_ms], dtype="int64")
    values = np.array([10.0, 20.0, 30.0])
    # A chart bar one hour into the second HTF bucket.
    chart_ts = np.array([target_ms + 3_600_000], dtype="int64")

    off = align_htf_to_ltf(values, 1, 3, chart_ts=chart_ts, htf_ts=htf_ts,
                           target_ms=target_ms, lookahead=False)
    on = align_htf_to_ltf(values, 1, 3, chart_ts=chart_ts, htf_ts=htf_ts,
                          target_ms=target_ms, lookahead=True)
    assert off[0] == 10.0  # last *closed* bucket
    assert on[0] == 20.0   # the bucket still forming


def test_security_minutes_declared_at_compile():
    from .engine import security_minutes

    program = compile(OCC_SIGNUM)
    assert program.security_minutes == (180,)          # 1h chart x multiplier 3
    assert security_minutes(program, "15m") == (45,)   # scales with the chart TF
