"""Tests for the risk management layer (config, gates, sizing, manager)."""
from apps.risk import gates
from apps.risk.config import RiskConfig, parse_risk_config
from apps.risk.manager import RiskManager
from apps.risk.sizing import size_from_risk


# --- config ---------------------------------------------------------------

def test_risk_config_defaults():
    cfg = RiskConfig()
    assert cfg.risk_per_trade_pct == 1.0
    assert cfg.max_daily_loss_pct == 5.0
    assert cfg.max_drawdown_pct == 15.0
    assert cfg.max_open_trades == 3
    assert cfg.max_exposure_pct == 50.0
    assert cfg.max_leverage == 10.0


def test_parse_risk_config_from_live_config():
    cfg = parse_risk_config({"risk": {"max_leverage": 3, "max_open_trades": 1}})
    assert cfg.max_leverage == 3
    assert cfg.max_open_trades == 1


def test_parse_risk_config_empty():
    assert parse_risk_config(None).max_leverage == 10.0
    assert parse_risk_config({}).max_open_trades == 3


# --- gates ----------------------------------------------------------------

def test_check_max_open_trades_blocks_at_limit():
    assert gates.check_max_open_trades(3, 3).ok is False
    assert gates.check_max_open_trades(2, 3).ok is True
    assert gates.check_max_open_trades(99, None).ok is True


def test_check_max_exposure():
    assert gates.check_max_exposure(60.0, 50.0).ok is False
    assert gates.check_max_exposure(40.0, 50.0).ok is True


def test_check_daily_loss_uses_absolute_limit():
    assert gates.check_daily_loss(-6.0, 5.0).ok is False
    assert gates.check_daily_loss(-4.0, 5.0).ok is True
    # positive pnl never trips
    assert gates.check_daily_loss(10.0, 5.0).ok is True


def test_check_drawdown():
    assert gates.check_drawdown(20.0, 15.0).ok is False
    assert gates.check_drawdown(10.0, 15.0).ok is True


def test_check_leverage():
    assert gates.check_leverage(12.0, 10.0).ok is False
    assert gates.check_leverage(5.0, 10.0).ok is True


# --- sizing ---------------------------------------------------------------

def test_size_from_fixed_risk_usd():
    cfg = RiskConfig(fixed_risk_usd=100.0, risk_per_trade_pct=None)
    # risk $100 over a $10 stop distance -> 10 units
    assert size_from_risk(cfg, equity=10_000, entry_price=50, stop_distance=10) == 10.0


def test_size_from_pct_risk_with_stop():
    cfg = RiskConfig(risk_per_trade_pct=1.0, fixed_risk_usd=None)
    # 1% of 10k = $100 risk over $5 stop -> 20 units
    assert size_from_risk(cfg, equity=10_000, entry_price=50, stop_distance=5) == 20.0


def test_size_from_pct_risk_without_stop_uses_notional_cap():
    cfg = RiskConfig(risk_per_trade_pct=1.0, fixed_risk_usd=None)
    # 1% of 10k = $100 * leverage 2 = $200 notional / price 50 = 4 units
    assert size_from_risk(cfg, equity=10_000, entry_price=50, leverage=2.0) == 4.0


def test_size_fallback_when_no_config():
    cfg = RiskConfig(risk_per_trade_pct=None, fixed_risk_usd=None)
    assert size_from_risk(cfg, equity=10_000, entry_price=50) == 1.0


# --- manager --------------------------------------------------------------

def test_manager_halts_on_drawdown():
    mgr = RiskManager(RiskConfig(max_drawdown_pct=10.0, max_daily_loss_pct=99.0), initial_balance=10_000)
    mgr.update_equity(8_000)  # 20% drawdown
    assert mgr.halted is True
    assert mgr.halt_reason == "max_drawdown"
    # pre_trade refuses once halted
    assert mgr.pre_trade(equity=8_000, open_trades=0, exposure_pct=0).ok is False


def test_manager_halts_on_daily_loss():
    mgr = RiskManager(RiskConfig(max_daily_loss_pct=5.0, max_drawdown_pct=99.0), initial_balance=10_000)
    mgr.update_equity(9_000)  # -10% on the day
    assert mgr.halted is True
    assert mgr.halt_reason == "max_daily_loss"


def test_manager_pre_trade_rejects_leverage():
    mgr = RiskManager(RiskConfig(max_leverage=5.0), initial_balance=10_000)
    decision = mgr.pre_trade(equity=10_000, open_trades=0, exposure_pct=0, leverage=10.0)
    assert decision.ok is False
    assert decision.reason == "max_leverage"


def test_manager_pre_trade_rejects_open_trades():
    mgr = RiskManager(RiskConfig(max_open_trades=2), initial_balance=10_000)
    assert mgr.pre_trade(equity=10_000, open_trades=2, exposure_pct=0).ok is False


def test_manager_allows_healthy_trade():
    mgr = RiskManager(RiskConfig(), initial_balance=10_000)
    assert mgr.pre_trade(equity=10_000, open_trades=0, exposure_pct=10, leverage=2).ok is True
    assert mgr.halted is False
