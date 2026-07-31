"""Exchange order filters — lot step, tick size, and minimum notional."""
from __future__ import annotations

import pytest

from apps.exchange.tabdeal_futures import SymbolFilters


def _filters(**kw) -> SymbolFilters:
    base = dict(symbol="BTC_USDT", qty_precision=3, price_precision=2,
                step_size=0.001, tick_size=0.01, min_qty=0.002, min_notional=5.0)
    base.update(kw)
    return SymbolFilters(**base)


def test_quantity_is_floored_to_the_lot_step_not_rounded():
    """Rounding up can exceed available margin; the exchange also rejects off-step sizes."""
    f = _filters(step_size=0.005)
    assert f.round_qty(0.0149) == 0.010
    assert f.round_qty(0.0199) == 0.015
    assert f.round_qty(0.02) == 0.020


def test_price_is_rounded_to_tick_size():
    f = _filters(tick_size=0.5, price_precision=1)
    assert f.round_price(100.24) == 100.0
    assert f.round_price(100.26) == 100.5


def test_reject_reason_flags_orders_the_exchange_would_bounce():
    f = _filters()
    assert f.reject_reason(0.0, 50_000) is not None
    assert "minQty" in f.reject_reason(0.001, 50_000)
    assert "minNotional" in f.reject_reason(0.002, 100)  # 0.2 USDT notional
    assert f.reject_reason(0.002, 50_000) is None        # 100 USDT notional


def test_max_qty_is_enforced_when_present():
    f = _filters(max_qty=1.0)
    assert "maxQty" in f.reject_reason(2.0, 50_000)


def test_filters_parsed_from_exchange_info_payload():
    from unittest import mock
    from apps.exchange.tabdeal_futures import TabdealFuturesClient

    payload = {"symbols": [{
        "symbol": "ETH_USDT", "pricePrecision": 2, "quantityPrecision": 3,
        "filters": [
            {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.02", "maxQty": "500"},
            {"filterType": "PRICE_FILTER", "tickSize": "0.05"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
        ],
    }]}
    client = TabdealFuturesClient.__new__(TabdealFuturesClient)
    with mock.patch.object(TabdealFuturesClient, "exchange_info", return_value=payload):
        f = client.symbol_filters("ETH_USDT")

    assert (f.step_size, f.min_qty, f.max_qty) == (0.01, 0.02, 500.0)
    assert f.tick_size == 0.05
    assert f.min_notional == 10.0


def test_unknown_symbol_falls_back_to_safe_defaults():
    from unittest import mock
    from apps.exchange.tabdeal_futures import TabdealFuturesClient

    client = TabdealFuturesClient.__new__(TabdealFuturesClient)
    with mock.patch.object(TabdealFuturesClient, "exchange_info", return_value={"symbols": []}):
        f = client.symbol_filters("NOPE_USDT")
    assert f.symbol == "NOPE_USDT"
    assert f.round_qty(1.23456) > 0
