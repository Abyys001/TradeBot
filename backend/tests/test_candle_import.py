"""The archive's other door: bars that no exchange will sell any more.

Hyperliquid serves the latest 5000 bars. At 30m that is 104 days, so 60 of the
86 trades in the admin's TradingView year happened on bars nothing can fetch —
recorded in `fixtures/pine/tradingview/mcg_t3_flow_perp/README.md` as the
reason most of that year is unverified rather than verified-correct. The chart
those trades were exported from still has the bars, and
``manage.py import_candles`` is how they get back in.

What is being tested is that it **copies**. An importer that resamples, fills
gaps, rounds to a tick or guesses a timezone would be putting invented bars in
the one table the whole platform treats as fact.
"""

from __future__ import annotations

from decimal import Decimal as D
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.bots import tvimport
from apps.exchanges import candlestore
from apps.exchanges.base import MarketType
from apps.trading.models import StoredCandle

CHART_DATA = """time,open,high,low,close,Volume,Plot
2026-01-01T00:00:00Z,100.5,101.25,99.75,101,1234.5,7
2026-01-01T00:30:00Z,101,102,100.5,101.5,2000,8
"""


def test_a_tradingview_chart_export_reads_as_bars():
    rows = tvimport.parse_candles(CHART_DATA)
    assert [row.time for row in rows] == [1767225600, 1767227400]
    assert rows[0].open == D("100.5")
    assert rows[0].high == D("101.25")
    assert rows[0].close == D("101")
    assert rows[0].volume == D("1234.5")


def test_prices_arrive_as_decimal_and_are_not_rounded_to_anybodys_tick():
    rows = tvimport.parse_candles(
        "time,open,high,low,close\n2026-01-01T00:00:00Z,1.000000001,2,0.5,1.7\n"
    )
    assert rows[0].open == D("1.000000001")


def test_a_column_that_is_not_ohlcv_is_ignored_rather_than_read_as_one():
    """A chart export carries every plotted series beside the bars."""
    rows = tvimport.parse_candles(CHART_DATA)
    assert not hasattr(rows[0], "Plot")
    assert rows[0].close == D("101")


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2026-01-01T00:00:00Z", 1767225600),
        ("2026-01-01T00:00:00+00:00", 1767225600),
        ("2026-01-01 00:00:00", 1767225600),
        ("2026-01-01 00:00", 1767225600),
        ("1767225600", 1767225600),
        ("1767225600000", 1767225600),  # milliseconds
        ("2026-01-01T03:30:00+03:30", 1767225600),
    ],
)
def test_every_stamp_these_exports_use_lands_on_the_same_second(stamp, expected):
    rows = tvimport.parse_candles(f"time,open,high,low,close\n{stamp},1,2,0.5,1.7\n")
    assert rows[0].time == expected


def test_a_chart_clock_export_is_shifted_rather_than_guessed_at():
    """A List of Trades export derives its offset from the prices; a bar file
    cannot, so the operator states it and the importer applies it."""
    rows = tvimport.parse_candles(CHART_DATA, offset=-3600)
    assert rows[0].time == 1767225600 - 3600


def test_a_volumeless_export_is_bars_with_no_volume_not_a_refusal():
    rows = tvimport.parse_candles("time,open,high,low,close\n2026-01-01T00:00:00Z,1,2,0.5,1.7\n")
    assert rows[0].volume == D(0)


def test_a_file_that_is_not_ohlcv_is_refused_by_name():
    with pytest.raises(tvimport.TradingViewImportError) as exc:
        tvimport.parse_candles("a,b\n1,2\n")
    assert "not a chart-data export" in str(exc.value)


def test_two_rows_for_one_bar_leave_one_bar():
    rows = tvimport.parse_candles(
        "time,open,high,low,close\n"
        "2026-01-01T00:00:00Z,1,2,0.5,1.7\n"
        "2026-01-01T00:00:00Z,1,2,0.5,1.9\n"
    )
    assert len(rows) == 1
    assert rows[0].close == D("1.9")


# --- the command, against the real archive ----------------------------------


@pytest.mark.django_db
def test_the_command_writes_the_bars_into_the_archive(tmp_path):
    path = tmp_path / "chart.csv"
    path.write_text(CHART_DATA)
    out = StringIO()

    call_command(
        "import_candles",
        str(path),
        "--symbol", "zecusdc",
        "--interval", "30m",
        "--exchange", "hyperliquid",
        stdout=out,
    )

    stored, exchange = candlestore.read_window(
        symbol="ZECUSDC", interval="30m", market=MarketType.FUTURES, limit=10
    )
    assert [candle.time for candle in stored] == [1767225600, 1767227400]
    assert exchange == "hyperliquid"
    assert stored[0].high == D("101.25")
    assert "2 new bar(s) archived" in out.getvalue()


@pytest.mark.django_db
def test_importing_the_same_file_twice_stores_it_once(tmp_path):
    """Settled history does not change — the archive's first rule."""
    path = tmp_path / "chart.csv"
    path.write_text(CHART_DATA)
    for _ in range(2):
        call_command(
            "import_candles", str(path),
            "--symbol", "ZECUSDC", "--interval", "30m", "--exchange", "hyperliquid",
            stdout=StringIO(),
        )
    assert StoredCandle.objects.count() == 2


@pytest.mark.django_db
def test_bars_off_the_intervals_grid_are_refused_rather_than_stored_beside_the_real_ones(
    tmp_path,
):
    """A bar at 00:07 would never match the one the venue serves at 00:00, so
    the archive would hold two of everything and every window would read double."""
    path = tmp_path / "chart.csv"
    path.write_text("time,open,high,low,close\n2026-01-01T00:07:00Z,1,2,0.5,1.7\n")
    with pytest.raises(CommandError) as exc:
        call_command(
            "import_candles", str(path),
            "--symbol", "ZECUSDC", "--interval", "30m", "--exchange", "hyperliquid",
            stdout=StringIO(),
        )
    assert "not on the 30m grid" in str(exc.value)
    assert StoredCandle.objects.count() == 0


@pytest.mark.django_db
def test_a_dry_run_reports_and_writes_nothing(tmp_path):
    path = tmp_path / "chart.csv"
    path.write_text(CHART_DATA)
    out = StringIO()
    call_command(
        "import_candles", str(path),
        "--symbol", "ZECUSDC", "--interval", "30m", "--exchange", "hyperliquid",
        "--dry-run", stdout=out,
    )
    assert StoredCandle.objects.count() == 0
    assert "nothing written" in out.getvalue()


@pytest.mark.django_db
def test_an_unknown_interval_is_refused_before_anything_is_read(tmp_path):
    path = tmp_path / "chart.csv"
    path.write_text(CHART_DATA)
    with pytest.raises(CommandError) as exc:
        call_command(
            "import_candles", str(path),
            "--symbol", "ZECUSDC", "--interval", "7m", "--exchange", "hyperliquid",
            stdout=StringIO(),
        )
    assert "not an interval" in str(exc.value)
