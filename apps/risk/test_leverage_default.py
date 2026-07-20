"""Leverage resolves to one canonical default everywhere (no Tabdeal-5x/others-1x split)."""
from __future__ import annotations

from apps.risk.config import DEFAULT_LEVERAGE, read_risk
from apps.transpiler.runtime.tabdeal_live_broker import TabdealLiveBroker


class _FakeStrategy:
    def __init__(self, live_config):
        self.live_config = live_config


def test_canonical_default_is_one():
    assert DEFAULT_LEVERAGE == 1
    # read_risk itself applies no default — an unset key is absent.
    assert read_risk({}).get("leverage") is None


def test_unset_leverage_uses_canonical_default():
    broker = TabdealLiveBroker(credential=None, strategy=_FakeStrategy({}), symbol="BTC")
    assert broker._leverage == float(DEFAULT_LEVERAGE)


def test_nested_risk_leverage_wins():
    strat = _FakeStrategy({"risk": {"leverage": 7}})
    broker = TabdealLiveBroker(credential=None, strategy=strat, symbol="BTC")
    assert broker._leverage == 7.0


def test_legacy_toplevel_leverage_honoured():
    strat = _FakeStrategy({"leverage": 3})
    broker = TabdealLiveBroker(credential=None, strategy=strat, symbol="BTC")
    assert broker._leverage == 3.0
