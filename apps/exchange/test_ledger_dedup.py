"""Tests for ledger dedup idempotency — P0.12, invariant 3."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from django.test import TestCase, override_settings

from apps.exchange.ledger import (
    LedgerWriter, LEDGER_COLUMNS, read_trades, union_coverage, coverage_gaps,
)


class LedgerDedupTests(TestCase):
    """Verify writing the same trade_id twice is idempotent (§3.1, invariant 3)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch(
            "apps.exchange.ledger._data_root",
            return_value=Path(self._tmpdir),
        )
        self._patcher.start()
        self.writer = LedgerWriter(node_id="test-node")

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _trade(self, trade_id: str, ts: int, price: float = 100.0):
        return {
            "trade_id": trade_id,
            "ts": ts,
            "price": price,
            "qty": 1.0,
            "side": "buy",
            "raw": "{}",
        }

    def test_duplicate_trade_id_is_idempotent(self):
        """Writing the same trade_id twice should result in only one row."""
        trade = self._trade("dup-001", 1700000000000)
        self.writer.add("BTC_USDT", trade)
        self.writer.add("BTC_USDT", trade)  # duplicate
        self.writer.flush()

        df = read_trades("BTC_USDT", 0, 9999999999999)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["trade_id"], "dup-001")

    def test_different_trade_ids_both_appear(self):
        self.writer.add("BTC_USDT", self._trade("id-1", 1700000000000))
        self.writer.add("BTC_USDT", self._trade("id-2", 1700000001000))
        self.writer.flush()

        df = read_trades("BTC_USDT", 0, 9999999999999)
        self.assertEqual(len(df), 2)

    def test_flush_multiple_times_idempotent(self):
        """Flushing the same buffer twice should not create duplicates."""
        trade = self._trade("multi-flush", 1700000000000)
        self.writer.add("BTC_USDT", trade)
        self.writer.flush()
        # Flush again with empty buffer — should not affect existing data
        self.writer.flush()

        df = read_trades("BTC_USDT", 0, 9999999999999)
        self.assertEqual(len(df), 1)

    def test_read_trades_dedupes_across_nodes(self):
        """read_trades deduplicates by trade_id across different node partitions."""
        trade = self._trade("cross-node", 1700000000000)

        w1 = LedgerWriter(node_id="node-1")
        w2 = LedgerWriter(node_id="node-2")

        # Patch both writers to use our temp dir
        with patch("apps.exchange.ledger._data_root", return_value=Path(self._tmpdir)):
            w1.add("BTC_USDT", trade)
            w1.flush()
            w2.add("BTC_USDT", trade)  # same trade, different node
            w2.flush()

        df = read_trades("BTC_USDT", 0, 9999999999999)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["trade_id"], "cross-node")

    def test_coverage_union_merge(self):
        """Two nodes covering the same window → single merged interval."""
        base = 1700000000000
        trade1 = self._trade("cov-1", base)
        trade2 = self._trade("cov-2", base + 5000)

        with patch("apps.exchange.ledger._data_root", return_value=Path(self._tmpdir)):
            w1 = LedgerWriter(node_id="node-1")
            w1.add("BTC_USDT", trade1)
            w1.flush()

            w2 = LedgerWriter(node_id="node-2")
            w2.add("BTC_USDT", trade2)
            w2.flush()

        cov = union_coverage("BTC_USDT")
        # Both nodes have overlapping intervals → union should be merged
        self.assertTrue(len(cov) >= 1)
        # Total coverage span should be at least 5000ms
        span = max(iv[1] for iv in cov) - min(iv[0] for iv in cov)
        self.assertGreaterEqual(span, 5000)

    def test_coverage_gap_detection(self):
        """Uncovered window is reported as a gap."""
        # Write a trade but query a far-away window
        self.writer.add("BTC_USDT", self._trade("gap-test", 1700000000000))
        self.writer.flush()

        # Query a window far in the future — should be a gap
        gaps = coverage_gaps("BTC_USDT", 1700099999000, 1700100000000)
        self.assertTrue(len(gaps) > 0)
        self.assertEqual(gaps[0][0], 1700099999000)
        self.assertEqual(gaps[0][1], 1700100000000)

    def test_sorted_by_ts(self):
        """Trades are always returned sorted by timestamp."""
        self.writer.add("BTC_USDT", self._trade("z-last", 1700000005000))
        self.writer.add("BTC_USDT", self._trade("a-first", 1700000000000))
        self.writer.add("BTC_USDT", self._trade("m-mid", 1700000002500))
        self.writer.flush()

        df = read_trades("BTC_USDT", 0, 9999999999999)
        self.assertEqual(list(df["trade_id"]), ["a-first", "m-mid", "z-last"])
