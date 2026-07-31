"""Readiness math tests — no filesystem, coverage is monkeypatched.

``readiness`` reports two separate things: whether enough history has been
*recorded* (ledger coverage) and whether it has been *materialized* into candles.
Only the second lets a strategy start, so these tests stub the stored-candle
count to isolate the coverage math.
"""
from __future__ import annotations

from unittest import mock

import pytest

from apps.exchange import readiness as rd


@pytest.fixture(autouse=True)
def _no_stored_candles():
    """Default: nothing materialized. Tests that care override it explicitly."""
    with mock.patch.object(rd, "stored_bar_count", return_value=0):
        yield

_TF = "1m"
_TF_MS = 60_000


def _patch(cov_intervals, pct_fn):
    return (
        mock.patch.object(rd, "union_coverage", return_value=cov_intervals),
        mock.patch.object(rd.coverage, "coverage_pct", side_effect=pct_fn),
    )


def test_no_coverage_is_not_ready():
    with mock.patch.object(rd, "union_coverage", return_value=[]):
        out = rd.readiness("BTC_USDT", _TF, 200)
    assert out["ready"] is False
    assert out["clean_bars"] == 0
    assert out["recording_since"] is None


def test_fully_covered_history_is_recording_ready():
    latest = 300 * _TF_MS
    p_union, p_pct = _patch([[0, latest]], lambda *a, **k: 1.0)
    with p_union, p_pct:
        out = rd.readiness("BTC_USDT", _TF, 200)
    assert out["recording_ready"] is True
    assert out["clean_bars"] == 200  # capped at required
    assert out["eta_seconds"] == 0
    assert out["recording_since"] == "1970-01-01T00:00:00Z"
    # Recorded but not materialized: the strategy still cannot seed its warmup.
    assert out["ready"] is False
    assert out["needs_backfill"] is True


def test_ready_only_once_candles_are_stored():
    latest = 300 * _TF_MS
    p_union, p_pct = _patch([[0, latest]], lambda *a, **k: 1.0)
    with p_union, p_pct, mock.patch.object(rd, "stored_bar_count", return_value=200):
        out = rd.readiness("BTC_USDT", _TF, 200)
    assert out["recording_ready"] is True
    assert out["ready"] is True
    assert "needs_backfill" not in out


def test_partial_history_reports_eta():
    # Full coverage only for the most recent 143 buckets; older buckets are gappy.
    latest = 300 * _TF_MS
    last_bucket = (latest // _TF_MS - 1) * _TF_MS  # 299 * tf
    clean_floor = last_bucket - 142 * _TF_MS       # newest 143 buckets fully covered

    def pct(symbol, start, end):
        return 1.0 if start >= clean_floor else 0.5

    p_union, p_pct = _patch([[0, latest]], pct)
    with p_union, p_pct:
        out = rd.readiness("BTC_USDT", _TF, 200)
    assert out["ready"] is False
    assert out["recording_ready"] is False
    assert out["clean_bars"] == 143
    assert out["eta_seconds"] == (200 - 143) * 60


def test_calendar_tf_rejected():
    out = rd.readiness("BTC_USDT", "1w", 200)
    assert out["ready"] is False
    assert "error" in out
