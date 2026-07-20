"""Offline tests for the probe-suite control flow (Master Plan §7). No network."""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.exchange.tabdeal_probe import run_probes


class FakeClient:
    def __init__(self, *, fail_sl=False):
        self.closed = 0
        self.opened = 0
        self._fail_sl = fail_sl

    def server_time(self):
        import time
        return int(time.time() * 1000)

    def exchange_info(self, symbol=None):
        return {"symbols": [{"symbol": symbol, "filters": [
            {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
        ]}]}

    def symbol_precision(self, symbol):
        return 2, 3

    def verify_credentials(self):
        return True, "verified"

    def available_usdt(self):
        return 42.0

    def get_positions(self, symbol=None):
        if self.opened and not self.closed:
            return [{"symbol": symbol, "positionAmt": "0.001", "entryPrice": "50000"}]
        return []

    def get_position(self, symbol):
        pos = self.get_positions(symbol)
        return pos[0] if pos else None

    def set_leverage(self, symbol, leverage):
        return {"leverage": leverage}

    def place_market_order(self, *, symbol, side, quantity, client_order_id=None):
        self.opened += 1
        return {"orderId": 999}

    def get_open_position_id(self, symbol):
        return 7

    def set_position_sl_tp(self, *, position_id, sl_price=None, tp_price=None, symbol=None):
        if self._fail_sl:
            raise RuntimeError("sl rejected")
        return {}

    def user_trades(self, symbol, *, limit=50):
        return [{"id": 1, "price": "50000", "qty": "0.001", "realizedPnl": "0.1"}]

    def close_position(self, symbol):
        self.closed += 1
        return {}


class ProbeSuiteTests(SimpleTestCase):
    def test_read_only_runs_without_orders(self):
        c = FakeClient()
        results = run_probes(c, live_orders=False)
        names = {r.name for r in results}
        self.assertEqual(c.opened, 0)  # no orders sent
        self.assertIn("clock", names)
        self.assertIn("verify", names)
        self.assertNotIn("order_open", names)

    def test_live_orders_full_lifecycle_and_close(self):
        c = FakeClient()
        results = run_probes(c, live_orders=True, quantity=0.001)
        names = {r.name for r in results}
        self.assertIn("order_open", names)
        self.assertIn("delete_close", names)
        self.assertEqual(c.opened, 1)
        self.assertEqual(c.closed, 1)  # position always closed
        self.assertTrue(all(r.ok for r in results), [r.line() for r in results])

    def test_position_closed_even_when_sl_fails(self):
        c = FakeClient(fail_sl=True)
        results = run_probes(c, live_orders=True, quantity=0.001)
        # SL probe fails but the position is still closed in finally.
        self.assertEqual(c.closed, 1)
        sl = next(r for r in results if r.name == "sl_attach")
        self.assertFalse(sl.ok)
