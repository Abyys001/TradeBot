"""Offline tests for the Tabdeal broadcast trade normalizer (Master Plan §3.1)."""
from __future__ import annotations

import json

from django.test import SimpleTestCase

from apps.exchange.tabdeal_ws import normalize_trade


class NormalizeTradeTests(SimpleTestCase):
    def test_wrapped_rest_style(self):
        msg = json.dumps({"trade": {"id": 42, "price": "101.5", "qty": "0.3",
                                    "time": 1_700_000_000_000, "isBuyerMaker": False}})
        row = normalize_trade(msg)
        self.assertEqual(row["trade_id"], "42")
        self.assertEqual(row["ts"], 1_700_000_000_000)
        self.assertEqual(row["price"], 101.5)
        self.assertEqual(row["qty"], 0.3)
        self.assertEqual(row["side"], "buy")  # buyer not maker -> buy aggressor

    def test_binance_stream_aliases(self):
        msg = json.dumps({"t": 7, "p": "50000", "q": "1", "T": 1_700_000_001_000, "m": True})
        row = normalize_trade(msg)
        self.assertEqual(row["trade_id"], "7")
        self.assertEqual(row["side"], "sell")  # buyer is maker -> sell aggressor

    def test_explicit_side(self):
        msg = json.dumps({"trade": {"id": 1, "price": 1, "qty": 1, "time": 1_700_000_000_000, "side": "SELL"}})
        self.assertEqual(normalize_trade(msg)["side"], "sell")

    def test_seconds_promoted_to_ms(self):
        msg = json.dumps({"id": 1, "price": 1, "qty": 1, "time": 1_700_000_000})
        self.assertEqual(normalize_trade(msg)["ts"], 1_700_000_000_000)

    def test_non_trade_ignored(self):
        self.assertIsNone(normalize_trade("connection closed ok"))
        self.assertIsNone(normalize_trade(json.dumps({"error": "Invalid params"})))
        self.assertIsNone(normalize_trade("not json"))
        self.assertIsNone(normalize_trade(json.dumps({"trade": {"price": 1}})))  # no id/ts

    def test_raw_preserved(self):
        msg = json.dumps({"id": 1, "price": 1, "qty": 1, "time": 1_700_000_000_000})
        self.assertEqual(normalize_trade(msg)["raw"], msg)
