"""Offline tests: trade aggregator + bar-quality model (Master Plan §3.2/§3.3, inv 1,2,4)."""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.exchange.aggregator import TradeAggregator, bucket_start
from apps.exchange.data_quality import (
    BarQuality, classify_bar, derive_quality, should_halt, worst,
)

TF = 60_000  # 1m
BASE = 1_700_000_000_000
B0 = bucket_start(BASE, TF)


class AggregatorTests(SimpleTestCase):
    def test_bucket_alignment_utc(self):
        self.assertEqual(bucket_start(B0 + 5_000, TF), B0)
        self.assertEqual(bucket_start(B0 + TF - 1, TF), B0)
        self.assertEqual(bucket_start(B0 + TF, TF), B0 + TF)

    def test_next_trade_seal_ohlcv(self):
        agg = TradeAggregator("BTC_USDT", TF)
        self.assertEqual(agg.add_trade(B0 + 1_000, 100, 1), [])   # opens bucket
        self.assertEqual(agg.add_trade(B0 + 2_000, 105, 1), [])   # high
        self.assertEqual(agg.add_trade(B0 + 3_000, 95, 1), [])    # low
        sealed = agg.add_trade(B0 + TF + 500, 101, 1)             # next bucket -> seal prev
        self.assertEqual(len(sealed), 1)
        bar = sealed[0]
        self.assertEqual(bar["ts"], B0)
        self.assertEqual((bar["open"], bar["high"], bar["low"], bar["close"]), (100, 105, 95, 95))
        self.assertEqual(bar["trade_count"], 3)
        self.assertEqual(bar["volume"], 3)

    def test_quiet_timeout_seal(self):
        agg = TradeAggregator("BTC_USDT", TF, grace_ms=750)
        agg.add_trade(B0 + 1_000, 100, 1)
        self.assertEqual(agg.flush(B0 + TF + 100), [])            # within grace
        sealed = agg.flush(B0 + TF + 800)                         # past grace
        self.assertEqual(len(sealed), 1)
        self.assertEqual(sealed[0]["ts"], B0)

    def test_flat_fill_bounded(self):
        agg = TradeAggregator("BTC_USDT", TF, max_flat_fill=5)
        agg.add_trade(B0 + 1_000, 100, 1)
        # jump 3 buckets ahead: seal real bar + 2 FLAT bars for the empty buckets between.
        sealed = agg.add_trade(B0 + 3 * TF + 1_000, 110, 1)
        self.assertEqual([b["ts"] for b in sealed], [B0, B0 + TF, B0 + 2 * TF])
        self.assertEqual(sealed[0]["trade_count"], 1)
        for flat in sealed[1:]:
            self.assertEqual(flat["trade_count"], 0)
            self.assertEqual(flat["open"], flat["close"], 100)  # carried forward

    def test_large_gap_not_flat_filled(self):
        agg = TradeAggregator("BTC_USDT", TF, max_flat_fill=5)
        agg.add_trade(B0 + 1_000, 100, 1)
        sealed = agg.add_trade(B0 + 100 * TF, 110, 1)  # huge jump
        self.assertEqual(len(sealed), 1)               # only the real bar; gap left for coverage
        self.assertEqual(sealed[0]["ts"], B0)

    def test_out_of_order_trade_dropped(self):
        agg = TradeAggregator("BTC_USDT", TF)
        agg.add_trade(B0 + TF + 1_000, 100, 1)     # opens bucket B0+TF
        sealed = agg.add_trade(B0 + 1_000, 999, 1)  # late trade for already-current-or-past bucket
        self.assertEqual(sealed, [])                # immutable — not mutated


class QualityModelTests(SimpleTestCase):
    def test_classify(self):
        clean = classify_bar({"trade_count": 3}, covered_ms=TF, tf_ms=TF)
        flat = classify_bar({"trade_count": 0}, covered_ms=TF, tf_ms=TF)
        suspect = classify_bar({"trade_count": 3}, covered_ms=TF // 2, tf_ms=TF)
        missing = classify_bar({"trade_count": 0}, covered_ms=0, tf_ms=TF)
        self.assertEqual((clean, flat, suspect, missing),
                         (BarQuality.CLEAN, BarQuality.FLAT, BarQuality.SUSPECT, BarQuality.MISSING))

    def test_worst_and_halt(self):
        self.assertEqual(worst(BarQuality.CLEAN, BarQuality.FLAT), BarQuality.FLAT)
        self.assertEqual(worst(BarQuality.FLAT, BarQuality.MISSING), BarQuality.MISSING)
        self.assertFalse(should_halt([BarQuality.CLEAN, BarQuality.FLAT]))  # FLAT never halts
        self.assertTrue(should_halt([BarQuality.CLEAN, BarQuality.SUSPECT]))
        self.assertTrue(should_halt([BarQuality.MISSING]))

    def test_derive_quality_flat_does_not_downgrade(self):
        self.assertEqual(derive_quality([BarQuality.CLEAN, BarQuality.FLAT]), BarQuality.CLEAN)
        self.assertEqual(derive_quality([BarQuality.FLAT, BarQuality.FLAT]), BarQuality.FLAT)
        self.assertEqual(derive_quality([BarQuality.CLEAN, BarQuality.SUSPECT]), BarQuality.SUSPECT)
        self.assertEqual(derive_quality([BarQuality.CLEAN, BarQuality.MISSING]), BarQuality.MISSING)
