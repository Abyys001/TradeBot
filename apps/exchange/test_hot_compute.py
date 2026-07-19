"""P2/P6 gate: Node B publishes the liveness heartbeat the watchdog consumes.

The watchdog (Node D) reads ``health:hot_compute:{strategy_id}``. Before this wiring
the key was never written, so the watchdog sat permanently in Tier 2. These assert the
producer writes the key the consumer expects, on every tick (not only on trades).
"""
from unittest.mock import MagicMock

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.exchange.hot_compute import HOT_HEARTBEAT_KEY, HotCompute


class HeartbeatProducerTests(SimpleTestCase):
    def test_beat_writes_key_the_watchdog_reads(self):
        from apps.watchdog.monitor import WatchdogMonitor

        # Producer and consumer must agree on the key format (invariant 12).
        self.assertEqual(HOT_HEARTBEAT_KEY, WatchdogMonitor.HEARTBEAT_KEY)

        hc = HotCompute.__new__(HotCompute)  # bypass DB-touching __init__
        strat = MagicMock()
        strat.pk = 4242
        hc._targets = {"BTC_USDT": [(strat, 60_000, "1m")]}

        key = HOT_HEARTBEAT_KEY.format(strategy_id=4242)
        cache.delete(key)
        hc._beat()

        beat = cache.get(key)
        self.assertIsNotNone(beat)
        self.assertIn("ts", beat)
        self.assertGreater(beat["ts"], 0)

    def test_beat_no_targets_is_noop(self):
        hc = HotCompute.__new__(HotCompute)
        hc._targets = {}
        hc._beat()  # must not raise
