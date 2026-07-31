"""Ledger -> candles backfill (the step that makes a long recording run usable)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.exchange import ledger
from apps.exchange.candle_store import load_candles
from apps.exchange.models import Candle

_HOUR_MS = 3_600_000
_START = 1_700_000_000_000 // _HOUR_MS * _HOUR_MS  # snap to an hour edge


@pytest.fixture
def ledger_root(tmp_path, settings):
    """A ledger holding 12h of one-trade-per-minute data for BTC_USDT."""
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    node = tmp_path / "ledger" / "BTC_USDT" / "n1"
    node.mkdir(parents=True)

    minutes = 12 * 60
    ts = _START + np.arange(minutes, dtype="int64") * 60_000
    price = 100.0 + np.sin(np.arange(minutes) / 30.0) * 5.0
    pd.DataFrame(
        {
            "trade_id": [f"t{i}" for i in range(minutes)],
            "ts": ts,
            "price": price,
            "qty": np.ones(minutes),
            "side": ["buy"] * minutes,
            "raw": [""] * minutes,
        }
    ).to_parquet(node / "20231114.parquet", index=False)

    (node / "_coverage.json").write_text(
        json.dumps({"intervals": [[int(ts[0]), int(ts[-1]) + 60_000]]})
    )
    return tmp_path


@pytest.mark.django_db
def test_backfill_writes_candles_for_requested_timeframes(ledger_root):
    assert load_candles("BTC", "1h").empty  # nothing stored yet

    call_command("backfill_candles", "--symbols", "BTC_USDT", "--timeframes", "1m", "1h", "3h")

    for tf, expected_ms in (("1m", 60_000), ("1h", _HOUR_MS), ("3h", 3 * _HOUR_MS)):
        df = load_candles("BTC", tf)
        assert not df.empty, f"{tf} was not written"
        gaps = np.diff(df["ts"].to_numpy())
        assert (gaps == expected_ms).all(), f"{tf} bars are not evenly spaced"
        # Buckets sit on absolute-time edges, so HTF bars line up with LTF bars.
        assert (df["ts"].to_numpy() % expected_ms == 0).all()


@pytest.mark.django_db
def test_backfill_is_idempotent(ledger_root):
    call_command("backfill_candles", "--symbols", "BTC_USDT", "--timeframes", "1h")
    first = load_candles("BTC", "1h")
    call_command("backfill_candles", "--symbols", "BTC_USDT", "--timeframes", "1h")
    second = load_candles("BTC", "1h")

    pd.testing.assert_frame_equal(first, second)
    assert Candle.objects.filter(asset="BTC", timeframe="1h").count() == len(first)


@pytest.mark.django_db
def test_backfill_records_bar_quality(ledger_root):
    call_command("backfill_candles", "--symbols", "BTC_USDT", "--timeframes", "1h")
    qualities = set(Candle.objects.filter(timeframe="1h").values_list("quality", flat=True))
    assert qualities <= {"CLEAN", "FLAT", "SUSPECT", "MISSING"}
    assert "CLEAN" in qualities
    assert all(c > 0 for c in Candle.objects.filter(timeframe="1h").values_list("trade_count", flat=True))


@pytest.mark.django_db
def test_backfill_rejects_calendar_timeframe(ledger_root):
    with pytest.raises(CommandError, match="not a fixed timeframe"):
        call_command("backfill_candles", "--symbols", "BTC_USDT", "--timeframes", "1w")


@pytest.mark.django_db
def test_backfill_without_ledger_data_fails_loudly(tmp_path, settings):
    settings.CANDLE_DATA_DIR = str(tmp_path / "candles")
    with pytest.raises(CommandError, match="no candles were written"):
        call_command("backfill_candles", "--symbols", "ETH_USDT", "--timeframes", "1h")


def test_available_range_reports_ledger_span(ledger_root):
    span = ledger.available_range("BTC_USDT")
    assert span is not None
    first, last = span
    assert first == _START
    assert last - first == 12 * _HOUR_MS
    assert ledger.available_range("NOPE_USDT") is None


@pytest.mark.django_db
def test_readiness_is_not_green_until_candles_are_stored(ledger_root):
    """Recorded trades alone must not report ready — warmup reads stored candles."""
    from apps.exchange.readiness import readiness

    before = readiness("BTC_USDT", "1h", required_bars=6)
    assert before["clean_bars"] >= 6      # trades are recorded
    assert before["stored_bars"] == 0     # but nothing is materialized
    assert before["ready"] is False
    assert before["needs_backfill"] is True
    assert "backfill_candles" in before["hint"]

    call_command("backfill_candles", "--symbols", "BTC_USDT", "--timeframes", "1h")

    after = readiness("BTC_USDT", "1h", required_bars=6)
    assert after["stored_bars"] >= 6
    assert after["ready"] is True
    assert "needs_backfill" not in after
