"""Risk manager tests: persistence, gates, and sizing."""
from unittest.mock import patch

from django.test import TestCase

from apps.risk.config import RiskConfig, parse_risk_config
from apps.risk.gates import (
    check_daily_loss,
    check_drawdown,
    check_leverage,
    check_max_exposure,
    check_max_open_trades,
)
from apps.risk.manager import RiskManager
from apps.risk.sizing import size_from_risk


class RiskGatesTestCase(TestCase):
    """Pure-function risk gate tests."""

    def test_max_open_trades_pass(self):
        self.assertTrue(check_max_open_trades(2, 3).ok)

    def test_max_open_trades_fail(self):
        self.assertFalse(check_max_open_trades(3, 3).ok)

    def test_max_exposure_pass(self):
        self.assertTrue(check_max_exposure(40.0, 50.0).ok)

    def test_max_exposure_fail(self):
        self.assertFalse(check_max_exposure(60.0, 50.0).ok)

    def test_daily_loss_pass(self):
        self.assertTrue(check_daily_loss(-3.0, 5.0).ok)

    def test_daily_loss_fail(self):
        self.assertFalse(check_daily_loss(-6.0, 5.0).ok)

    def test_drawdown_pass(self):
        self.assertTrue(check_drawdown(10.0, 15.0).ok)

    def test_drawdown_fail(self):
        self.assertFalse(check_drawdown(20.0, 15.0).ok)

    def test_leverage_pass(self):
        self.assertTrue(check_leverage(5.0, 10.0).ok)

    def test_leverage_fail(self):
        self.assertFalse(check_leverage(15.0, 10.0).ok)

    def test_none_limits_always_pass(self):
        self.assertTrue(check_max_open_trades(100, None).ok)
        self.assertTrue(check_max_exposure(100.0, None).ok)
        self.assertTrue(check_daily_loss(-50.0, None).ok)
        self.assertTrue(check_drawdown(50.0, None).ok)
        self.assertTrue(check_leverage(100.0, None).ok)


class RiskManagerTestCase(TestCase):
    """RiskManager with Redis persistence (mocked)."""

    @patch("apps.risk.manager.cache")
    def test_halt_persists_to_redis(self, mock_cache):
        mock_cache.get.return_value = None
        rm = RiskManager(
            config=RiskConfig(max_daily_loss_pct=5.0),
            initial_balance=10000.0,
            strategy_id=42,
        )
        # Simulate a big loss.
        rm.update_equity(9000.0)  # -10% daily loss
        self.assertTrue(rm.halted)
        self.assertEqual(rm.halt_reason, "max_daily_loss")
        mock_cache.set.assert_called()

    @patch("apps.risk.manager.cache")
    def test_loads_from_redis(self, mock_cache):
        import json
        state = {
            "peak_equity": 15000.0,
            "daily_start_equity": 12000.0,
            "daily_pnl": -500.0,
            "halted": True,
            "halt_reason": "max_daily_loss",
        }
        mock_cache.get.return_value = json.dumps(state)
        rm = RiskManager(strategy_id=42)
        self.assertTrue(rm.halted)
        self.assertEqual(rm.halt_reason, "max_daily_loss")
        self.assertEqual(rm.peak_equity, 15000.0)

    def test_pre_trade_blocked_when_halted(self):
        rm = RiskManager(strategy_id=None)
        rm.halted = True
        rm.halt_reason = "max_daily_loss"
        decision = rm.pre_trade(equity=10000, open_trades=0, exposure_pct=0.0)
        self.assertFalse(decision.ok)

    def test_new_day_resets_daily_pnl(self):
        rm = RiskManager(strategy_id=None)
        rm.update_equity(10000.0, new_day=True)
        self.assertEqual(rm.daily_pnl, 0.0)


class RiskConfigTestCase(TestCase):
    def test_from_dict_empty(self):
        cfg = RiskConfig.from_dict({})
        self.assertEqual(cfg.max_leverage, 10.0)

    def test_from_dict_custom(self):
        cfg = RiskConfig.from_dict({"max_leverage": 20.0, "max_daily_loss_pct": 3.0})
        self.assertEqual(cfg.max_leverage, 20.0)
        self.assertEqual(cfg.max_daily_loss_pct, 3.0)

    def test_parse_risk_config(self):
        cfg = parse_risk_config({"risk": {"max_open_trades": 5}})
        self.assertEqual(cfg.max_open_trades, 5)


class SizingTestCase(TestCase):
    def test_fixed_risk_usd(self):
        cfg = RiskConfig(fixed_risk_usd=100.0)
        size = size_from_risk(cfg, equity=10000, entry_price=50.0, stop_distance=10.0)
        self.assertAlmostEqual(size, 10.0)

    def test_risk_per_trade_pct_with_stop(self):
        cfg = RiskConfig(risk_per_trade_pct=1.0)
        size = size_from_risk(cfg, equity=10000, entry_price=50.0, stop_distance=10.0)
        # risk_usd = 10000 * 0.01 = 100, size = 100 / 10 = 10
        self.assertAlmostEqual(size, 10.0)

    def test_risk_per_trade_pct_no_stop(self):
        cfg = RiskConfig(risk_per_trade_pct=1.0)
        size = size_from_risk(cfg, equity=10000, entry_price=50.0, stop_distance=None)
        # notional = 100 * 1.0 leverage = 100, size = 100 / 50 = 2
        self.assertAlmostEqual(size, 2.0)

    def test_fallback_returns_1(self):
        cfg = RiskConfig(risk_per_trade_pct=None, fixed_risk_usd=None)
        size = size_from_risk(cfg, equity=10000, entry_price=50.0)
        self.assertEqual(size, 1.0)
