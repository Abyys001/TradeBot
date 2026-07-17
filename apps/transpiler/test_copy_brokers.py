"""Tests for the copy-trading brokers (signal capture + Tabdeal symbol mapping)."""
from .runtime.signal_capture_broker import SignalCaptureBroker
from .runtime.tabdeal_broker import to_tabdeal_symbol


def test_to_tabdeal_symbol_variants():
    assert to_tabdeal_symbol("BTC") == "BTC_USDT"
    assert to_tabdeal_symbol("BTCUSDT") == "BTC_USDT"
    assert to_tabdeal_symbol("btc_usdt") == "BTC_USDT"
    assert to_tabdeal_symbol("ETHUSD") == "ETH_USDT"


def test_capture_broker_records_entry_and_close():
    b = SignalCaptureBroker()
    b.entry("o1", "long", 100.0, 5, qty=1, alert_message="{...}")
    b.close("o1", 110.0, 6, reason="signal")
    assert b.has_actions()
    assert [a["type"] for a in b.actions] == ["entry", "close"]
    entry = b.actions[0]
    assert entry["direction"] == "long" and entry["price"] == 100.0
    assert entry["alert_message"] == "{...}"
    assert b.actions[1]["reason"] == "signal"


def test_capture_broker_short_and_exit():
    b = SignalCaptureBroker()
    b.entry("o2", "short", 50.0, 1)
    b.exit("o2", 50.0, 2, stop=55.0, limit=45.0)
    assert b.actions[0]["direction"] == "short"
    ex = b.actions[1]
    assert ex["type"] == "exit" and ex["stop"] == 55.0 and ex["limit"] == 45.0


def test_capture_broker_metrics_empty():
    b = SignalCaptureBroker()
    assert b.metrics() == {} and b.trades() == []
