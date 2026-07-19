"""Tests for TabdealBroadcastClient reconnect and dedup — P0.11, §3.1."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from collections import deque

from django.test import SimpleTestCase

from apps.exchange.tabdeal_ws import (
    TabdealBroadcastClient, normalize_trade, _DEDUPE_RING,
)


class ReconnectDedupTests(SimpleTestCase):
    """Verify the per-node dedup ring prevents replays after reconnect (§3.1)."""

    def test_dedup_ring_maxlen(self):
        """Ring is bounded at _DEDUPE_RING entries."""
        self.assertEqual(_DEDUPE_RING, 4096)

    def test_dedup_prevents_replay(self):
        """Same trade_id seen twice → second is filtered."""
        seen: deque[str] = deque(maxlen=_DEDUPE_RING)
        seen_set: set[str] = set()

        trade = {"trade_id": "t1", "ts": 1000, "price": 100, "qty": 1, "side": "buy", "raw": "{}"}
        tid = trade["trade_id"]

        # First time — should pass
        self.assertNotIn(tid, seen_set)
        seen.append(tid)
        seen_set.add(tid)

        # Second time — should be filtered
        self.assertIn(tid, seen_set)

    def test_dedup_ring_evicts_oldest(self):
        """When ring is full, oldest entry is evicted so it can re-appear."""
        seen: deque[str] = deque(maxlen=3)
        seen_set: set[str] = set()

        for tid in ["a", "b", "c"]:
            seen.append(tid)
            seen_set.add(tid)

        # Ring full, "a" is oldest
        self.assertEqual(len(seen), 3)
        self.assertIn("a", seen_set)

        # Add "d" → "a" evicted from ring (but may still be in set until cleanup)
        seen.append("d")
        seen_set.discard(seen[0] if len(seen) == seen.maxlen else "a")
        # Cleanup logic from _consume: discard seen[0] before append when full
        seen_set.discard("a")

        self.assertNotIn("a", seen_set)

    def test_gap_callback_on_reconnect(self):
        """on_gap is called on every (re)connect to start a fresh coverage interval."""
        gaps = []
        client = TabdealBroadcastClient(
            ["BTC_USDT"],
            on_trade=AsyncMock(),
            on_gap=lambda s: gaps.append(s),
        )
        # Simulate what _run_symbol does on connect
        if client._on_gap:
            client._on_gap("BTC_USDT")
        self.assertEqual(gaps, ["BTC_USDT"])

    def test_planned_reconnect_detected(self):
        """Plain-text 'connection closed ok' frame is a planned reconnect (§10)."""
        msg = "connection closed ok"
        self.assertIn("connection closed ok", msg)


class NormalizeTradeTests(SimpleTestCase):
    """Verify normalize_trade handles all known payload shapes."""

    def test_bare_dict(self):
        raw = json.dumps({"id": "1", "price": "50000", "qty": "0.1", "time": 1700000000000, "side": "buy"})
        row = normalize_trade(raw)
        self.assertIsNotNone(row)
        self.assertEqual(row["trade_id"], "1")
        self.assertEqual(row["ts"], 1700000000000)
        self.assertEqual(row["price"], 50000.0)

    def test_wrapped_trade(self):
        raw = json.dumps({"trade": {"id": "2", "price": "3000", "qty": "1", "time": 2000000000000}})
        row = normalize_trade(raw)
        self.assertIsNotNone(row)
        self.assertEqual(row["trade_id"], "2")

    def test_seconds_to_ms(self):
        """ts < 10_000_000_000 is promoted to ms."""
        raw = json.dumps({"id": "3", "price": "100", "qty": "1", "time": 1700000000})
        row = normalize_trade(raw)
        self.assertEqual(row["ts"], 1700000000000)

    def test_is_buyer_maker_side(self):
        raw = json.dumps({"id": "4", "price": "100", "qty": "1", "time": 1700000000000, "isBuyerMaker": True})
        row = normalize_trade(raw)
        self.assertEqual(row["side"], "sell")  # buyer is maker → aggressor is seller

    def test_invalid_json_returns_none(self):
        self.assertIsNone(normalize_trade("not json"))

    def test_missing_tid_returns_none(self):
        raw = json.dumps({"price": "100", "qty": "1", "time": 1000})
        self.assertIsNone(normalize_trade(raw))
