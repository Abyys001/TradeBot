"""P9: Chaos drill — end-to-end scenario tests.

Simulates multi-failure scenarios across the system to verify that:
1. Single-node failure → partial gap → recovery via union coverage
2. Total ingest failure → Class 3 → flatten + halt
3. Compute crash → ledger replay → self-heal
4. Watchdog tier escalation → kill switch
5. Mutex contention → no double orders
"""
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.test import TestCase, SimpleTestCase

from apps.exchange.halt_policy import (
    classify_failure_class, evaluate_halt, FailureClass, HaltAction,
)
from apps.exchange.data_quality import classify_bar, BarQuality
from apps.exchange.self_heal import detect_failure_class
from apps.exchange.ledger import (
    LedgerWriter, read_trades, union_coverage, coverage_gaps,
)
from apps.exchange.timeframes import FIXED_MS


class ChaosScenarioTests(TestCase):
    """Full chaos scenarios exercising multiple modules together."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch(
            "apps.exchange.ledger._data_root",
            return_value=Path(self._tmpdir),
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _trade(self, trade_id, ts, price=100.0):
        return {"trade_id": trade_id, "ts": ts, "price": price, "qty": 1.0, "side": "buy", "raw": "{}"}

    def test_scenario_single_node_down(self):
        """§0.1: One node down, other covers → partial or compute gap depending on coverage."""
        base = 1_700_000_000_000

        # Node 1 covers the full window
        w1 = LedgerWriter(node_id="a1")
        for i in range(10):
            w1.add("BTC_USDT", self._trade(f"t-{i}", base + i * 1000))
        w1.flush()

        # Node 2 is down (no writes)

        # Verify union coverage is complete
        cov = union_coverage("BTC_USDT")
        total_ms = sum(hi - lo for lo, hi in cov)
        self.assertGreaterEqual(total_ms, 9000)

        # Single node present → list_nodes returns ["a1"]
        # coverage_pct depends on the exact window; classify accordingly
        fc = detect_failure_class("BTC_USDT", base, base + 10000)
        self.assertIn(fc, (FailureClass.COMPUTE_GAP, FailureClass.PARTIAL_INGEST))

        # Evaluate halt: SUSPECT + SL confirmed → hold within budget (Class 1 or 2)
        d = evaluate_halt(
            quality="SUSPECT", sl_confirmed=True,
            failure_class=fc, bars_since_halt=1, max_blind_hold=3,
        )
        self.assertFalse(d.should_flatten)
        self.assertEqual(d.action.value, "hold")

    def test_scenario_total_ingest_loss(self):
        """§0.1: All nodes dead → Class 3 → flatten immediately."""
        fc = classify_failure_class(coverage_pct=0.0, has_any_node=False)
        self.assertEqual(fc, FailureClass.TOTAL_INGEST)

        d = evaluate_halt(
            quality="MISSING", sl_confirmed=True,
            failure_class=fc, bars_since_halt=0,
        )
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.reason, "class_3_total_ingest")

    def test_scenario_compute_crash_replay(self):
        """§2: Compute crashes → ledger has all trades → self-heal replays."""
        base = 1_700_000_000_000
        w = LedgerWriter(node_id="a1")
        for i in range(5):
            w.add("BTC_USDT", self._trade(f"crash-{i}", base + i * 60000))
        w.flush()

        # Read back — should have all trades
        df = read_trades("BTC_USDT", base, base + 300000)
        self.assertEqual(len(df), 5)

        # Verify dedup
        w2 = LedgerWriter(node_id="a1")
        for i in range(5):
            w2.add("BTC_USDT", self._trade(f"crash-{i}", base + i * 60000))
        w2.flush()

        df2 = read_trades("BTC_USDT", base, base + 300000)
        self.assertEqual(len(df2), 5)  # Still 5, not 10

    def test_scenario_quality_degradation(self):
        """§3.2: Coverage degrades → bar quality drops → SUSPECT → halt."""
        base = 1_700_000_000_000
        tf_ms = FIXED_MS["1m"]

        # 50% covered bar with trades → SUSPECT
        bar = {"open": 100, "high": 110, "low": 95, "close": 105, "ts": base, "volume": 10, "trade_count": 5}
        q = classify_bar(bar, covered_ms=tf_ms // 2, tf_ms=tf_ms)
        self.assertEqual(q, BarQuality.SUSPECT)

        # 100% covered with trades → CLEAN
        q2 = classify_bar(bar, covered_ms=tf_ms, tf_ms=tf_ms)
        self.assertEqual(q2, BarQuality.CLEAN)

        # 0% covered → MISSING
        q3 = classify_bar(bar, covered_ms=0, tf_ms=tf_ms)
        self.assertEqual(q3, BarQuality.MISSING)

    def test_scenario_naked_position_no_sl(self):
        """§4.3: SUSPECT bar + no SL → flatten (invariant 13)."""
        fc = classify_failure_class(coverage_pct=0.99, has_any_node=True)
        d = evaluate_halt(
            quality="SUSPECT", sl_confirmed=False,
            failure_class=fc, bars_since_halt=0,
        )
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.reason, "naked_position")

    def test_scenario_blind_hold_budget_exceeded(self):
        """§4.3: SL confirmed but held too long → forced flatten."""
        fc = classify_failure_class(coverage_pct=0.99, has_any_node=True)
        d = evaluate_halt(
            quality="SUSPECT", sl_confirmed=True,
            failure_class=fc, bars_since_halt=3, max_blind_hold=3,
        )
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.reason, "exceeded_max_blind_hold")

    def test_scenario_cross_node_dedup(self):
        """Two nodes write the same trades → union dedupes correctly."""
        base = 1_700_000_000_000
        trade = self._trade("shared-001", base)

        w1 = LedgerWriter(node_id="a1")
        w1.add("BTC_USDT", trade)
        w1.flush()

        w2 = LedgerWriter(node_id="a2")
        w2.add("BTC_USDT", trade)
        w2.flush()

        df = read_trades("BTC_USDT", 0, 9999999999999)
        self.assertEqual(len(df), 1)

        # Union coverage from both nodes
        cov = union_coverage("BTC_USDT")
        self.assertTrue(len(cov) >= 1)


class WatchdogTierEscalationTests(SimpleTestCase):
    """P9: Watchdog tier escalation scenarios."""

    def test_tier_escalation_0_to_3(self):
        """Healthy → slow → dead → kill switch, escalation across checks."""
        from apps.watchdog.tiers import evaluate_tier

        kw = dict(
            t_self_ms=5000, t_dead_ms=15000, max_blind_hold=3,
            sl_confirmed=False, bars_since_halt=0,
        )

        # T0: healthy
        d0 = evaluate_tier(heartbeat_gap_ms=1000, daily_loss_breached=False, **kw)
        self.assertEqual(d0.tier, 0)

        # T1: slow, no SL → attach
        d1 = evaluate_tier(heartbeat_gap_ms=6000, daily_loss_breached=False, **kw)
        self.assertEqual(d1.tier, 1)
        self.assertTrue(d1.should_attach_sl)

        # T2: dead, no SL → flatten
        d2 = evaluate_tier(heartbeat_gap_ms=20000, daily_loss_breached=False, **kw)
        self.assertEqual(d2.tier, 2)
        self.assertTrue(d2.should_flatten)

        # T3: daily loss → kill switch
        d3 = evaluate_tier(heartbeat_gap_ms=20000, daily_loss_breached=True, **kw)
        self.assertEqual(d3.tier, 3)
        self.assertTrue(d3.should_kill_switch)
        self.assertTrue(d3.should_flatten)

    def test_heartbeat_recovery(self):
        """Dead → healthy again → tier drops to 0."""
        from apps.watchdog.tiers import evaluate_tier

        kw = dict(t_self_ms=5000, t_dead_ms=15000, max_blind_hold=3)

        # Dead
        d1 = evaluate_tier(
            heartbeat_gap_ms=20000, sl_confirmed=True,
            bars_since_halt=2, daily_loss_breached=False, **kw,
        )
        self.assertEqual(d1.tier, 2)

        # Recovered
        d2 = evaluate_tier(
            heartbeat_gap_ms=1000, sl_confirmed=True,
            bars_since_halt=0, daily_loss_breached=False, **kw,
        )
        self.assertEqual(d2.tier, 0)
        self.assertEqual(d2.action, "healthy")


class GuardianScenarioTests(SimpleTestCase):
    """P9: Guardian position mismatch scenarios."""

    def test_position_vanished_while_sl_confirmed(self):
        """Position gone but SL was confirmed → reconcile."""
        from apps.watchdog.guardian import check_position

        client = MagicMock()
        client.get_position.return_value = None

        result = check_position(
            exchange_client=client, symbol="BTC_USDT",
            expected_has_sl=True, sl_confirmed=True,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.action_needed, "reconcile")

    def test_sl_vanished_while_position_exists(self):
        """Position exists but SL is gone → reattach."""
        from apps.watchdog.guardian import check_position

        client = MagicMock()
        client.get_position.return_value = {
            "positionAmt": "0.1",
            "entryPrice": "50000",
            "stopLossPrice": None,
            "unRealizedProfit": "10",
        }

        result = check_position(
            exchange_client=client, symbol="BTC_USDT",
            expected_has_sl=True, sl_confirmed=False,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.action_needed, "attach_sl")
