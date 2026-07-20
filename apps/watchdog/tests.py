"""Tests for watchdog tiers — §6.2/6.3/6.4/6.5."""
from django.test import SimpleTestCase

from apps.watchdog.tiers import evaluate_tier


class EvaluateTierTests(SimpleTestCase):
    def _defaults(self, **kw):
        d = dict(
            heartbeat_gap_ms=0,
            t_self_ms=5000,
            t_dead_ms=15000,
            sl_confirmed=False,
            bars_since_halt=0,
            max_blind_hold=3,
            daily_loss_breached=False,
        )
        d.update(kw)
        return d

    def test_healthy(self):
        d = evaluate_tier(**self._defaults(heartbeat_gap_ms=1000))
        self.assertEqual(d.tier, 0)
        self.assertEqual(d.action, "healthy")

    def test_tier1_slow_no_sl(self):
        d = evaluate_tier(**self._defaults(heartbeat_gap_ms=6000, sl_confirmed=False))
        self.assertEqual(d.tier, 1)
        self.assertTrue(d.should_attach_sl)
        self.assertFalse(d.should_flatten)

    def test_tier1_slow_sl_attached(self):
        d = evaluate_tier(**self._defaults(heartbeat_gap_ms=6000, sl_confirmed=True))
        self.assertEqual(d.tier, 1)
        self.assertEqual(d.action, "monitor")
        self.assertFalse(d.should_flatten)

    def test_tier2_dead_naked(self):
        d = evaluate_tier(**self._defaults(heartbeat_gap_ms=20000, sl_confirmed=False))
        self.assertEqual(d.tier, 2)
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.action, "flatten_naked")

    def test_tier2_dead_sl_within_budget(self):
        d = evaluate_tier(**self._defaults(
            heartbeat_gap_ms=20000, sl_confirmed=True, bars_since_halt=1,
        ))
        self.assertEqual(d.tier, 2)
        self.assertFalse(d.should_flatten)
        self.assertEqual(d.action, "hold_protected")

    def test_tier2_dead_sl_exceeded(self):
        d = evaluate_tier(**self._defaults(
            heartbeat_gap_ms=20000, sl_confirmed=True, bars_since_halt=3, max_blind_hold=3,
        ))
        self.assertEqual(d.tier, 2)
        self.assertTrue(d.should_flatten)
        self.assertEqual(d.action, "flatten_exceeded")

    def test_tier3_daily_loss(self):
        d = evaluate_tier(**self._defaults(daily_loss_breached=True, heartbeat_gap_ms=0))
        self.assertEqual(d.tier, 3)
        self.assertTrue(d.should_kill_switch)
        self.assertTrue(d.should_flatten)

    def test_tier3_daily_loss_overrides_everything(self):
        """Daily loss breach wins even if heartbeat is healthy."""
        d = evaluate_tier(**self._defaults(daily_loss_breached=True, heartbeat_gap_ms=100))
        self.assertEqual(d.tier, 3)

    def test_boundary_t_self(self):
        d = evaluate_tier(**self._defaults(heartbeat_gap_ms=5000))
        self.assertEqual(d.tier, 1)

    def test_boundary_t_dead(self):
        d = evaluate_tier(**self._defaults(heartbeat_gap_ms=15000))
        self.assertEqual(d.tier, 2)
