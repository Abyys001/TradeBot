"""Tests for halt policy — §4.3 (invariant 1, 13)."""
from django.test import SimpleTestCase

from apps.exchange.halt_policy import (
    HaltAction, FailureClass, HaltDecision,
    classify_failure_class, evaluate_halt,
)


class ClassifyFailureClassTests(SimpleTestCase):
    def test_compute_gap(self):
        result = classify_failure_class(coverage_pct=1.0, has_any_node=True)
        self.assertEqual(result, FailureClass.COMPUTE_GAP)

    def test_partial_ingest(self):
        result = classify_failure_class(coverage_pct=0.5, has_any_node=True)
        self.assertEqual(result, FailureClass.PARTIAL_INGEST)

    def test_total_ingest_no_nodes(self):
        result = classify_failure_class(coverage_pct=0.0, has_any_node=False)
        self.assertEqual(result, FailureClass.TOTAL_INGEST)

    def test_partial_ingest_zero_coverage(self):
        # Node alive but 0% coverage = partial (node reporting, just no data for this window)
        result = classify_failure_class(coverage_pct=0.0, has_any_node=True)
        self.assertEqual(result, FailureClass.PARTIAL_INGEST)


class EvaluateHaltTests(SimpleTestCase):
    def test_class3_always_flattens(self):
        d = evaluate_halt(
            quality="MISSING",
            sl_confirmed=True,
            failure_class=FailureClass.TOTAL_INGEST,
            bars_since_halt=0,
        )
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.reason, "class_3_total_ingest")

    def test_missing_always_flattens(self):
        d = evaluate_halt(
            quality="MISSING",
            sl_confirmed=True,
            failure_class=FailureClass.COMPUTE_GAP,
            bars_since_halt=0,
        )
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.reason, "bar_missing")

    def test_naked_position_flattens(self):
        d = evaluate_halt(
            quality="SUSPECT",
            sl_confirmed=False,
            failure_class=FailureClass.COMPUTE_GAP,
            bars_since_halt=0,
        )
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.reason, "naked_position")

    def test_sl_confirmed_within_budget_holds(self):
        d = evaluate_halt(
            quality="SUSPECT",
            sl_confirmed=True,
            failure_class=FailureClass.COMPUTE_GAP,
            bars_since_halt=1,
            max_blind_hold=3,
        )
        self.assertFalse(d.should_flatten)
        self.assertEqual(d.action, HaltAction.HOLD)
        self.assertEqual(d.eta_blind_hold, 2)

    def test_sl_exceeded_budget_flattens(self):
        d = evaluate_halt(
            quality="SUSPECT",
            sl_confirmed=True,
            failure_class=FailureClass.COMPUTE_GAP,
            bars_since_halt=3,
            max_blind_hold=3,
        )
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.reason, "exceeded_max_blind_hold")

    def test_eta_decreases(self):
        d1 = evaluate_halt(
            quality="SUSPECT", sl_confirmed=True,
            failure_class=FailureClass.COMPUTE_GAP,
            bars_since_halt=0, max_blind_hold=3,
        )
        d2 = evaluate_halt(
            quality="SUSPECT", sl_confirmed=True,
            failure_class=FailureClass.COMPUTE_GAP,
            bars_since_halt=2, max_blind_hold=3,
        )
        self.assertEqual(d1.eta_blind_hold, 3)
        self.assertEqual(d2.eta_blind_hold, 1)

    def test_decision_fields(self):
        d = evaluate_halt(
            quality="SUSPECT",
            sl_confirmed=True,
            failure_class=FailureClass.PARTIAL_INGEST,
            bars_since_halt=1,
        )
        self.assertEqual(d.failure_class, FailureClass.PARTIAL_INGEST)
        self.assertTrue(d.sl_confirmed)
        self.assertEqual(d.bars_since_halt, 1)
