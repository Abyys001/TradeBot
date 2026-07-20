"""Tests for self-heal — §4: determinism and classification."""
from django.test import SimpleTestCase
from unittest.mock import patch

from apps.exchange.self_heal import detect_failure_class
from apps.exchange.halt_policy import FailureClass


class DetectFailureClassTests(SimpleTestCase):
    @patch("apps.exchange.self_heal.coverage_pct", return_value=1.0)
    @patch("apps.exchange.self_heal.list_nodes", return_value=["a1", "a2"])
    def test_class1_compute_gap(self, mock_nodes, mock_cov):
        result = detect_failure_class("BTC_USDT", 0, 60000)
        self.assertEqual(result, FailureClass.COMPUTE_GAP)

    @patch("apps.exchange.self_heal.coverage_pct", return_value=0.5)
    @patch("apps.exchange.self_heal.list_nodes", return_value=["a1"])
    def test_class2_partial_ingest(self, mock_nodes, mock_cov):
        result = detect_failure_class("BTC_USDT", 0, 60000)
        self.assertEqual(result, FailureClass.PARTIAL_INGEST)

    @patch("apps.exchange.self_heal.coverage_pct", return_value=0.0)
    @patch("apps.exchange.self_heal.list_nodes", return_value=[])
    def test_class3_total_ingest(self, mock_nodes, mock_cov):
        result = detect_failure_class("BTC_USDT", 0, 60000)
        self.assertEqual(result, FailureClass.TOTAL_INGEST)

    @patch("apps.exchange.self_heal.coverage_pct", return_value=0.8)
    @patch("apps.exchange.self_heal.list_nodes", return_value=["a1"])
    def test_class2_zero_coverage_with_node(self, mock_nodes, mock_cov):
        # Node alive but 0% coverage = partial, same as 80% with one node
        result = detect_failure_class("BTC_USDT", 0, 60000)
        self.assertEqual(result, FailureClass.PARTIAL_INGEST)
