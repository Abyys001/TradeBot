"""Tests for TabdealLiveBroker — primary-strategy direct Tabdeal execution.

No real network calls: TabdealFuturesClient is patched at its import location,
mirroring apps.copytrading.tests / apps.exchange.test_tabdeal's style.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.models import User
from apps.credentials.models import Exchange, ExchangeCredential
from apps.exchange.tabdeal_errors import TabdealAPIError, TabdealErrorInfo
from apps.execution.models import ExecutionLog, OrderRecord
from apps.strategies.models import Strategy


def _make_user(trading=True):
    return User.objects.create_user(username="owner", password="x", role=User.Role.ADMIN, is_trading_enabled=trading)


def _make_strategy(user, *, position_size_pct=20, leverage=5):
    cred = ExchangeCredential(user=user, exchange=Exchange.TABDEAL, label="td", is_active=True)
    cred.set_api_credentials("key", "secret")
    cred.save()
    strat = Strategy.objects.create(
        user=user,
        credential=cred,
        name="tabdeal-primary",
        symbol="BTC",
        source="//x",
        validation_status="ok",
        live_config={"risk": {"position_size_pct": position_size_pct, "leverage": leverage}},
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


@pytest.mark.django_db
@patch("apps.telegram.tasks.dispatch_telegram_alert.delay")
def test_entry_places_order_and_records(mock_alert):
    user = _make_user()
    strat, _cred = _make_strategy(user)
    client = _fake_client(usdt=1000.0)
    client.place_market_order.return_value = {"orderId": 1, "status": "FILLED", "avgPrice": "100.0"}

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
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

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
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

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
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

    with patch("apps.exchange.tabdeal_futures.TabdealFuturesClient", return_value=client):
        broker = _broker(strat)
        rec = broker.entry("o1", "long", 100.0, 1)

    assert rec is None
    assert OrderRecord.objects.count() == 0
    assert ExecutionLog.objects.filter(strategy=strat, event="risk.blocked").exists()
    client.place_market_order.assert_not_called()
