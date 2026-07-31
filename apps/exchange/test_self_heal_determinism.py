"""Determinism test: self-heal produces identical bar state to continuous run."""
from __future__ import annotations

from django.test import SimpleTestCase
from unittest.mock import patch

from apps.exchange.aggregator import bucket_start, TradeAggregator
from apps.exchange.self_heal import rebuild_bars


def _make_trades(count: int, base_ts: int, interval_ms: int,
                 base_price: float = 50_000.0) -> list[dict]:
    trades = []
    for i in range(count):
        ts = base_ts + i * interval_ms
        price = base_price + (i % 10) * 100
        trades.append({"ts": ts, "price": price, "qty": 0.01})
    return trades


TF = 60_000  # 1 minute
BASE_TS = 1_800_000_000_000  # epoch anchor


class SelfHealDeterminismTests(SimpleTestCase):

    def test_continuous_vs_self_heal_determinism(self):
        trades = _make_trades(50, BASE_TS, 60_000)  # 50 trades, 1 min apart over ~49 min

        # Path A: continuous run through a single aggregator
        agg_a = TradeAggregator("BTC_USDT", TF)
        bars_a: list[dict] = []
        for t in trades:
            sealed = agg_a.add_trade(int(t["ts"]), float(t["price"]), float(t.get("qty", 0)))
            bars_a.extend(sealed)
        # Flush remaining open bar
        last_ts = int(trades[-1]["ts"])
        bars_a.extend(agg_a.flush(last_ts + TF + 1000))

        # Path B: first 25 trades, then simulate crash/restart with new aggregator
        agg_b = TradeAggregator("BTC_USDT", TF)
        bars_b_mid: list[dict] = []
        for t in trades[:25]:
            sealed = agg_b.add_trade(int(t["ts"]), float(t["price"]), float(t.get("qty", 0)))
            bars_b_mid.extend(sealed)

        # Simulate crash: create new aggregator for trades 25..49
        agg_b2 = TradeAggregator("BTC_USDT", TF)
        bars_b2: list[dict] = []
        for t in trades[25:]:
            sealed = agg_b2.add_trade(int(t["ts"]), float(t["price"]), float(t.get("qty", 0)))
            bars_b2.extend(sealed)
        bars_b2.extend(agg_b2.flush(last_ts + TF + 1000))

        # S2 bars = bars from second aggregator
        s2 = bars_b2

        # S1 bars = last N bars from continuous run matching the timespan of trades[25:]
        s1_start_ts = int(trades[25]["ts"])  # first trade in second half
        s1_start_bucket = bucket_start(s1_start_ts, TF)
        s1 = [b for b in bars_a if b["ts"] >= s1_start_bucket]

        self.assertEqual(len(s1), len(s2),
                         f"S1 has {len(s1)} bars, S2 has {len(s2)}")

        for i, (b1, b2) in enumerate(zip(s1, s2)):
            self.assertEqual(b1["ts"], b2["ts"], f"bar {i}: ts mismatch")
            self.assertEqual(b1["open"], b2["open"], f"bar {i}: open mismatch")
            self.assertEqual(b1["high"], b2["high"], f"bar {i}: high mismatch")
            self.assertEqual(b1["low"], b2["low"], f"bar {i}: low mismatch")
            self.assertEqual(b1["close"], b2["close"], f"bar {i}: close mismatch")

    @patch("apps.exchange.self_heal.coverage_pct", return_value=1.0)
    def test_rebuild_bars_matches_continuous(self, mock_cov):
        trades = _make_trades(50, BASE_TS, 60_000)

        # Continuous run (same as Path A above)
        agg = TradeAggregator("BTC_USDT", TF)
        bars_continuous: list[dict] = []
        for t in trades:
            sealed = agg.add_trade(int(t["ts"]), float(t["price"]), float(t.get("qty", 0)))
            bars_continuous.extend(sealed)
        last_ts = int(trades[-1]["ts"])
        bars_continuous.extend(agg.flush(last_ts + TF + 1000))

        # rebuild_bars from raw trades
        rebuilt = rebuild_bars(trades, TF, "BTC_USDT")

        # Strip quality field from rebuilt for comparison
        rebuilt_clean = [{k: v for k, v in b.items() if k != "quality"} for b in rebuilt]

        self.assertEqual(len(bars_continuous), len(rebuilt_clean))
        for i, (b1, b2) in enumerate(zip(bars_continuous, rebuilt_clean)):
            self.assertEqual(b1["ts"], b2["ts"], f"bar {i}: ts mismatch")
            self.assertEqual(b1["open"], b2["open"], f"bar {i}: open mismatch")
            self.assertEqual(b1["high"], b2["high"], f"bar {i}: high mismatch")
            self.assertEqual(b1["low"], b2["low"], f"bar {i}: low mismatch")
            self.assertEqual(b1["close"], b2["close"], f"bar {i}: close mismatch")
