"""Tests for TabdealLiveBroker — primary-strategy direct Tabdeal execution.

No real network calls: TabdealFuturesClient is patched at its import location,
mirroring apps.copytrading.tests / apps.exchange.test_tabdeal's style.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.accounts.models import User
from apps.credentials.models import Exchange, ExchangeCredential
from apps.exchange.tabdeal_errors import TabdealAPIError, TabdealErrorInfo
from apps.execution.models import ExecutionLog, OrderRecord
from apps.strategies.models import Strategy


def _make_user(trading=True):
    return User.objects.create_user(username="owner", password="x", role=User.Role.ADMIN, is_trading_enabled=trading)


def _make_strategy(user, *, position_size_pct=20, leverage=5, global_stop_loss_pct=None):
    cred = ExchangeCredential(user=user, exchange=Exchange.TABDEAL, label="td", is_active=True)
    cred.set_api_credentials("key", "secret")
    cred.save()
    risk: dict = {"position_size_pct": position_size_pct, "leverage": leverage}
    if global_stop_loss_pct is not None:
        risk["global_stop_loss_pct"] = global_stop_loss_pct
    strat = Strategy.objects.create(
        user=user,
        credential=cred,
        name="tabdeal-primary",
        symbol="BTC",
        source="//x",
        validation_status="ok",
        live_config={"risk": risk},
    )
    return strat, cred


def _fake_client(usdt=1000.0, position=None, precision=(2, 3)):
    client = MagicMock()
    client.available_usdt.return_value = usdt
    client.symbol_precision.return_value = precision
    client.set_leverage.return_value = {}
    client.get_position.return_value = position
    return client


def _broker(strategy, symbol="BTC", leverage=None):
    from apps.transpiler.runtime.tabdeal_live_broker import TabdealLiveBroker

    return TabdealLiveBroker(credential=strategy.credential, strategy=strategy, symbol=symbol, leverage=leverage)


def _mock_run_sync():
    """Return a patch target and side_effect for _run_sync that handles mutex
    acquire (first call → mock mutex) and release (second call → no-op).
    """
    mock_mutex = AsyncMock()
    mock_mutex.release = AsyncMock(return_value=True)

    call_count = 0

    def _side_effect(coro_or_val):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_mutex
        return None

    return patch("apps.transpiler.runtime.tabdeal_live_broker._run_sync", side_effect=_side_effect), mock_mutex


# ----- existing tests (updated to mock mutex) -----


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_places_order_and_records(mock_alert):
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client(usdt=1000.0)
    client.place_market_order.return_value = {"orderId": 1, "status": "FILLED", "avgPrice": "100.0"}

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is not None
    assert rec.status == "filled"
    assert float(rec.size) == 10.0  # (1000 * 20% * 5) / 100
    order = OrderRecord.objects.get(strategy=strat)
    assert order.side == OrderRecord.Side.BUY
    assert ExecutionLog.objects.filter(strategy=strat, event="order.placed").exists()
    client.set_leverage.assert_called_once()
    mock_alert.assert_called_once()


@pytest.mark.django_db
def test_entry_blocked_when_trading_disabled():
    user = _make_user(trading=False)
    strat, _cred = _make_strategy(user)
    client = _fake_client(usdt=1000.0)

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is None
    assert OrderRecord.objects.count() == 0
    assert ExecutionLog.objects.filter(strategy=strat, event="order.blocked").exists()
    client.place_market_order.assert_not_called()


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_rejected_on_futures_not_active(mock_alert):
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client(usdt=1000.0)
    client.place_market_order.side_effect = TabdealAPIError(
        TabdealErrorInfo("1207", "Futures not active", "Call set-leverage once to activate")
    )

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is not None
    assert rec.status == "rejected"
    log = ExecutionLog.objects.get(strategy=strat, event="order.rejected")
    assert log.payload["error"] == "1207"


@pytest.mark.django_db
def test_compute_qty_sizing_math():
    user = _make_user()
    strat, _cred = _make_strategy(user, position_size_pct=10, leverage=2)
    client = _fake_client(usdt=500.0, precision=(2, 3))

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        broker = _broker(strat)
        qty = broker._compute_qty(client, 50.0)

    # 500 * 10% * 2 / 50 = 2.0
    assert qty == 2.0


@pytest.mark.django_db
def test_close_no_open_position_is_noop():
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client(usdt=1000.0, position=None)

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        broker = _broker(strat)
        rec = broker.close("o1", 100.0, 2)

    assert rec is None
    client.close_position.assert_not_called()


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_close_partial_qty_pct_forces_full_close_and_logs(mock_alert):
    user = _make_user()
    strat, _cred = _make_strategy(user)
    position = {"positionAmt": "1.0", "markPrice": "100.0"}
    client = _fake_client(usdt=1000.0, position=position)
    client.close_position.return_value = {"avgPrice": "105.0"}

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        broker = _broker(strat)
        broker._open_orders["o1"] = {"side": "long", "qty": 1.0}
        rec = broker.close("o1", 105.0, 2, qty_pct=0.5)

    assert rec is not None
    client.close_position.assert_called_once()
    assert ExecutionLog.objects.filter(strategy=strat, event="order.partial_close_unsupported").exists()


@pytest.mark.django_db
def test_exit_no_position_id_logs_and_noops():
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client(usdt=1000.0)
    client.get_open_position_id.return_value = None

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        broker = _broker(strat)
        result = broker.exit("o1", 100.0, 2, stop=90.0, limit=110.0)

    assert result is None
    client.set_position_sl_tp.assert_not_called()
    assert ExecutionLog.objects.filter(strategy=strat, event="order.sltp_no_position").exists()


@pytest.mark.django_db
def test_risk_gate_blocks_on_max_leverage():
    user = _make_user()
    strat, _cred = _make_strategy(user, leverage=999)  # exceeds default max_leverage=10
    client = _fake_client(usdt=1000.0)

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is None
    assert OrderRecord.objects.count() == 0
    assert ExecutionLog.objects.filter(strategy=strat, event="risk.blocked").exists()
    client.place_market_order.assert_not_called()


# ----- new tests: mutex -----


@pytest.mark.django_db
def test_entry_mutex_busy_returns_none():
    """Mutex acquisition fails → order not placed."""
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client(usdt=1000.0)

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), \
         patch("apps.transpiler.runtime.tabdeal_live_broker._run_sync", return_value=None):
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is None
    client.place_market_order.assert_not_called()
    assert ExecutionLog.objects.filter(strategy=strat, event="order.mutex_busy").exists()


# ----- new tests: auto SL attachment -----


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_auto_attaches_sl(mock_alert):
    """After fill, SL is attached at global_stop_loss_pct distance."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client(usdt=1000.0)
    client.place_market_order.return_value = {"orderId": 1, "status": "FILLED", "avgPrice": "50000.0"}
    client.get_open_position_id.return_value = 42

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 50000.0, 1)

    assert rec is not None
    client.set_position_sl_tp.assert_called_once_with(
        position_id=42, sl_price=45000.0, symbol="BTC_USDT"
    )
    assert ExecutionLog.objects.filter(strategy=strat, event="order.sltp_auto").exists()


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_auto_sl_short_position(mock_alert):
    """SL for short position is above entry price."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=5)
    client = _fake_client(usdt=1000.0)
    client.place_market_order.return_value = {"orderId": 1, "status": "FILLED", "avgPrice": "100.0"}
    client.get_open_position_id.return_value = 7

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "short", 100.0, 1)

    assert rec is not None
    # Short: SL above entry (100 * 1.05 = 105.0)
    client.set_position_sl_tp.assert_called_once_with(
        position_id=7, sl_price=105.0, symbol="BTC_USDT"
    )


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_sl_retry_exhaustion_closes_position(mock_alert):
    """If SL attachment fails after all retries, position is closed."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client(usdt=1000.0)
    client.place_market_order.return_value = {"orderId": 1, "status": "FILLED", "avgPrice": "100.0"}
    client.get_open_position_id.return_value = 42
    client.set_position_sl_tp.side_effect = TabdealAPIError(
        TabdealErrorInfo("5017", "SL error", "Retry")
    )
    client.close_position.return_value = {"avgPrice": "100.0"}

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), \
         patch("apps.transpiler.runtime.tabdeal_live_broker.time.sleep"), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is not None  # order was placed
    assert client.set_position_sl_tp.call_count == 3
    client.close_position.assert_called_once_with("BTC_USDT")
    assert ExecutionLog.objects.filter(strategy=strat, event="slattach.failed").exists()
    assert ExecutionLog.objects.filter(strategy=strat, event="naked_close_executed").exists()


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_sl_no_position_id_closes_naked(mock_alert):
    """If position ID can't be fetched, position is closed as naked."""
    user = _make_user()
    strat, _cred = _make_strategy(user, global_stop_loss_pct=10)
    client = _fake_client(usdt=1000.0)
    client.place_market_order.return_value = {"orderId": 1, "status": "FILLED", "avgPrice": "100.0"}
    client.get_open_position_id.return_value = None
    client.close_position.return_value = {"avgPrice": "100.0"}

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is not None
    client.set_position_sl_tp.assert_not_called()
    client.close_position.assert_called_once()
    assert ExecutionLog.objects.filter(strategy=strat, event="slattach.no_position").exists()


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_no_sl_pct_does_not_attach(mock_alert):
    """Without global_stop_loss_pct configured, no SL is auto-attached."""
    user = _make_user()
    strat, _cred = _make_strategy(user)  # no global_stop_loss_pct
    client = _fake_client(usdt=1000.0)
    client.place_market_order.return_value = {"orderId": 1, "status": "FILLED", "avgPrice": "100.0"}

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is not None
    client.set_position_sl_tp.assert_not_called()
    assert not ExecutionLog.objects.filter(strategy=strat, event="order.sltp_auto").exists()


# ----- new tests: risk gate persistence -----


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_risk_gate_persists_halt_state_via_strategy_id(mock_alert):
    """RiskManager with strategy_id persists halt to Redis across instances."""
    user = _make_user()
    strat, _cred = _make_strategy(user, leverage=999)
    client = _fake_client(usdt=1000.0)

    run_sync_patch, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch:
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is None
    assert ExecutionLog.objects.filter(strategy=strat, event="risk.blocked").exists()

    # Second broker instance — halt state should persist via Redis.
    run_sync_patch2, _ = _mock_run_sync()
    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client), run_sync_patch2:
        broker2 = _broker(strat)
        rec2 = broker2.entry("o2", "long", 100.0, 2)

    assert rec2 is None
    # The second attempt should also be blocked (same halt reason persisted).
    blocked_logs = ExecutionLog.objects.filter(strategy=strat, event="risk.blocked")
    assert blocked_logs.count() >= 2


# --- Phase 4: Pine header sizing reaches the live broker -------------------

def test_header_sizing_extracted_from_program():
    from apps.transpiler.engine import compile as pine_compile, header_sizing

    program = pine_compile(
        'strategy("pct", default_qty_type=strategy.percent_of_equity, default_qty_value=90)\n'
        'plot(close)\n'
    )
    assert header_sizing(program) == {"default_qty": 90.0, "qty_is_percent_of_equity": True}

    plain = pine_compile('strategy("plain")\nplot(close)\n')
    assert header_sizing(plain) == {}


def test_live_broker_uses_header_percent_not_risk_config():
    """A script declaring 90% of equity must trade at 90%, not the risk default of 20%."""
    from unittest import mock
    from apps.transpiler.runtime.tabdeal_live_broker import TabdealLiveBroker
    from apps.exchange.tabdeal_futures import SymbolFilters

    strategy = mock.Mock(live_config={"risk": {"position_size_pct": 20, "leverage": 1}})
    broker = TabdealLiveBroker(
        credential=mock.Mock(), strategy=strategy, symbol="BTC",
        default_qty=90.0, qty_is_percent_of_equity=True,
    )
    client = mock.Mock()
    client.available_usdt.return_value = 1000.0
    client.symbol_filters.return_value = SymbolFilters(symbol="BTC_USDT", step_size=0.0001,
                                                       qty_precision=4)
    # 90% of 1000 USDT at 100 = 9.0 units, not 20% (2.0).
    assert broker._compute_qty(client, 100.0) == pytest.approx(9.0)


def test_live_broker_explicit_pine_qty_wins():
    from unittest import mock
    from apps.transpiler.runtime.tabdeal_live_broker import TabdealLiveBroker
    from apps.exchange.tabdeal_futures import SymbolFilters

    strategy = mock.Mock(live_config={})
    broker = TabdealLiveBroker(credential=mock.Mock(), strategy=strategy, symbol="BTC",
                               default_qty=90.0, qty_is_percent_of_equity=True)
    client = mock.Mock()
    client.available_usdt.return_value = 1000.0
    client.symbol_filters.return_value = SymbolFilters(symbol="BTC_USDT", step_size=0.001,
                                                       qty_precision=3)
    assert broker._compute_qty(client, 100.0, explicit_qty=2.5) == pytest.approx(2.5)


def test_live_broker_floors_quantity_to_lot_step():
    from unittest import mock
    from apps.transpiler.runtime.tabdeal_live_broker import TabdealLiveBroker
    from apps.exchange.tabdeal_futures import SymbolFilters

    strategy = mock.Mock(live_config={"risk": {"position_size_pct": 100, "leverage": 1}})
    broker = TabdealLiveBroker(credential=mock.Mock(), strategy=strategy, symbol="BTC")
    client = mock.Mock()
    client.available_usdt.return_value = 1000.0
    client.symbol_filters.return_value = SymbolFilters(symbol="BTC_USDT", step_size=0.05,
                                                       qty_precision=2)
    # 1000/70 = 14.2857... -> floored onto the 0.05 grid, never rounded up.
    assert broker._compute_qty(client, 70.0) == pytest.approx(14.25)
