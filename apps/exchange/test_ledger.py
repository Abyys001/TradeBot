"""Offline tests for the append-only trade ledger (Master Plan §3.1, §0.1)."""
from __future__ import annotations

import importlib

from django.test import TestCase, override_settings


def _reload_ledger(tmp_candle_dir):
    """Point CANDLE_DATA_DIR at a temp dir and reload the module so paths rebind."""
    from apps.exchange import ledger as ledger_mod
    with override_settings(CANDLE_DATA_DIR=str(tmp_candle_dir / "candles")):
        importlib.reload(ledger_mod)
    return ledger_mod


def _trade(tid, ts, price=100.0, qty=1.0, side="buy"):
    return {"trade_id": str(tid), "ts": int(ts), "price": price, "qty": qty, "side": side, "raw": "{}"}


class LedgerTests(TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        from pathlib import Path
        self._override = override_settings(CANDLE_DATA_DIR=str(Path(self.tmp.name) / "candles"))
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.ledger = importlib.import_module("apps.exchange.ledger")

    def test_append_and_read(self):
        w = self.ledger.LedgerWriter(node_id="A1")
        for i in range(5):
            w.add("BTC_USDT", _trade(i, 1_700_000_000_000 + i * 1000))
        self.assertEqual(w.flush(), 5)
        df = self.ledger.read_trades("BTC_USDT", 0, 2_000_000_000_000)
        self.assertEqual(len(df), 5)
        self.assertTrue(df["ts"].is_monotonic_increasing)

    def test_dedup_same_node(self):
        w = self.ledger.LedgerWriter(node_id="A1")
        w.add("BTC_USDT", _trade(1, 1_700_000_000_000))
        w.flush()
        w.add("BTC_USDT", _trade(1, 1_700_000_000_000))  # duplicate id
        w.add("BTC_USDT", _trade(2, 1_700_000_001_000))
        w.flush()
        df = self.ledger.read_trades("BTC_USDT", 0, 2_000_000_000_000)
        self.assertEqual(len(df), 2)

    def test_cross_node_merge_union(self):
        # Node A1 has trades 1,2 ; Node A2 has 2,3 (overlap on id 2).
        base = 1_700_000_000_000
        a1 = self.ledger.LedgerWriter(node_id="A1")
        a1.add("BTC_USDT", _trade(1, base))
        a1.add("BTC_USDT", _trade(2, base + 1000))
        a1.flush()
        a2 = self.ledger.LedgerWriter(node_id="A2")
        a2.add("BTC_USDT", _trade(2, base + 1000))
        a2.add("BTC_USDT", _trade(3, base + 2000))
        a2.flush()
        df = self.ledger.read_trades("BTC_USDT", 0, 2_000_000_000_000)
        self.assertEqual(sorted(df["trade_id"].tolist()), ["1", "2", "3"])

    def test_coverage_and_gap(self):
        base = 1_700_000_000_000
        w = self.ledger.LedgerWriter(node_id="A1")
        w.add("BTC_USDT", _trade(1, base))
        w.add("BTC_USDT", _trade(2, base + 1000))
        w.flush()
        # simulate a socket drop, then resume 10s later
        w.mark_gap("BTC_USDT")
        w.add("BTC_USDT", _trade(3, base + 11_000))
        w.flush()
        cov = self.ledger.union_coverage("BTC_USDT")
        self.assertEqual(len(cov), 2)  # two intervals, gap between them
        gaps = self.ledger.coverage_gaps("BTC_USDT", base, base + 11_000)
        self.assertTrue(any(g[0] >= base + 1000 and g[1] <= base + 11_000 for g in gaps))

    def test_multi_day_range_read(self):
        # Trades spanning two UTC days land in separate day-files but read as one range.
        day1 = 1_700_000_000_000            # 2023-11-14
        day2 = day1 + 86_400_000 + 5_000    # next day
        w = self.ledger.LedgerWriter(node_id="A1")
        w.add("BTC_USDT", _trade(1, day1))
        w.add("BTC_USDT", _trade(2, day2))
        w.flush()
        df = self.ledger.read_trades("BTC_USDT", 0, 2_000_000_000_000)
        self.assertEqual(len(df), 2)

    def test_coverage_service_facade(self):
        from apps.exchange import coverage
        base = 1_700_000_000_000
        w = self.ledger.LedgerWriter(node_id="A1")
        w.add("BTC_USDT", _trade(1, base))
        w.add("BTC_USDT", _trade(2, base + 1000))
        w.flush()
        self.assertTrue(coverage.is_covered("BTC_USDT", base, base + 1000))
        self.assertAlmostEqual(coverage.coverage_pct("BTC_USDT", base, base + 1000), 1.0, places=3)
        # A window extending past the last trade is only partially covered.
        self.assertLess(coverage.coverage_pct("BTC_USDT", base, base + 100_000), 1.0)

    def test_gap_filled_by_second_node(self):
        # A1 drops during [base+1000, base+11000]; A2 covers it -> union has no gap.
        base = 1_700_000_000_000
        a1 = self.ledger.LedgerWriter(node_id="A1")
        a1.add("BTC_USDT", _trade(1, base))
        a1.flush()
        a1.mark_gap("BTC_USDT")
        a1.add("BTC_USDT", _trade(9, base + 11_000))
        a1.flush()
        a2 = self.ledger.LedgerWriter(node_id="A2")
        for i in range(0, 12):
            a2.add("BTC_USDT", _trade(100 + i, base + i * 1000))
        a2.flush()
        gaps = self.ledger.coverage_gaps("BTC_USDT", base, base + 11_000)
        self.assertEqual(gaps, [])
