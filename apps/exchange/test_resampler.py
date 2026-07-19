"""Tests for resampler — §3.2/§0.3: fixed and calendar TF resampling."""
import importlib
from pathlib import Path
import tempfile

from django.test import TestCase, override_settings

from apps.exchange.resampler import (
    resample_fixed, resample_calendar, calendar_bucket_start,
    _week_start, _month_start, _quarter_start,
)
from apps.exchange.timeframes import FIXED_MS

BASE = 1_700_000_000_000  # 2023-11-14 22:13:20 UTC


def _trade(ts, price=100.0, qty=1.0):
    import pandas as pd
    return pd.DataFrame([{"trade_id": str(ts), "ts": int(ts), "price": price, "qty": qty, "side": "buy", "raw": "{}"}])


class ResampleFixedTests(TestCase):
    def test_single_bar(self):
        trades = _trade(BASE + 5000, 100.0, 1.0)
        bars = resample_fixed(trades, "1m")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["ts"], (BASE // 60000) * 60000)
        self.assertEqual(bars[0]["open"], 100.0)
        self.assertEqual(bars[0]["trade_count"], 1)

    def test_multiple_trades_same_bar(self):
        import pandas as pd
        trades = pd.DataFrame([
            {"trade_id": "1", "ts": BASE, "price": 100, "qty": 1, "side": "buy", "raw": "{}"},
            {"trade_id": "2", "ts": BASE + 1000, "price": 105, "qty": 2, "side": "buy", "raw": "{}"},
            {"trade_id": "3", "ts": BASE + 2000, "price": 95, "qty": 1, "side": "sell", "raw": "{}"},
        ])
        bars = resample_fixed(trades, "1m")
        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertEqual(bar["open"], 100)
        self.assertEqual(bar["high"], 105)
        self.assertEqual(bar["low"], 95)
        self.assertEqual(bar["close"], 95)
        self.assertEqual(bar["volume"], 4)
        self.assertEqual(bar["trade_count"], 3)

    def test_two_bars(self):
        import pandas as pd
        tf_ms = FIXED_MS["1m"]
        trades = pd.DataFrame([
            {"trade_id": "1", "ts": BASE, "price": 100, "qty": 1, "side": "buy", "raw": "{}"},
            {"trade_id": "2", "ts": BASE + tf_ms + 1000, "price": 200, "qty": 1, "side": "buy", "raw": "{}"},
        ])
        bars = resample_fixed(trades, "1m")
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0]["open"], 100)
        self.assertEqual(bars[1]["open"], 200)

    def test_empty_trades(self):
        import pandas as pd
        trades = pd.DataFrame(columns=["trade_id", "ts", "price", "qty", "side", "raw"])
        bars = resample_fixed(trades, "1m")
        self.assertEqual(bars, [])


class CalendarBucketTests(TestCase):
    def test_week_start_is_monday(self):
        from datetime import datetime, timezone
        # BASE = 2023-11-14 22:13:20 UTC is a Tuesday
        monday_ts = _week_start(BASE)
        dt = datetime.fromtimestamp(monday_ts / 1000, tz=timezone.utc)
        self.assertEqual(dt.weekday(), 0)  # Monday
        self.assertEqual(dt.hour, 0)
        self.assertEqual(dt.minute, 0)

    def test_month_start(self):
        from datetime import datetime, timezone
        month_ts = _month_start(BASE)
        dt = datetime.fromtimestamp(month_ts / 1000, tz=timezone.utc)
        self.assertEqual(dt.day, 1)
        self.assertEqual(dt.hour, 0)

    def test_quarter_start(self):
        from datetime import datetime, timezone
        # Nov is in Q4 (Oct-Dec), so quarter start is Oct 1
        q_ts = _quarter_start(BASE)
        dt = datetime.fromtimestamp(q_ts / 1000, tz=timezone.utc)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 1)


class ResampleCalendarTests(TestCase):
    def test_weekly_bar(self):
        import pandas as pd
        trades = pd.DataFrame([
            {"trade_id": "1", "ts": BASE, "price": 100, "qty": 1, "side": "buy", "raw": "{}"},
            {"trade_id": "2", "ts": BASE + 86400000, "price": 200, "qty": 1, "side": "buy", "raw": "{}"},
        ])
        bars = resample_calendar(trades, "1w")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["open"], 100)
        self.assertEqual(bars[0]["close"], 200)
        self.assertEqual(bars[0]["high"], 200)
        self.assertEqual(bars[0]["low"], 100)

    def test_monthly_bar(self):
        import pandas as pd
        trades = pd.DataFrame([
            {"trade_id": "1", "ts": BASE, "price": 100, "qty": 1, "side": "buy", "raw": "{}"},
        ])
        bars = resample_calendar(trades, "1M")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["open"], 100)
