"""§5 — the backtest must predict the live loop, and this is how that is a test.

A single function both sides call is what makes it a test rather than two
implementations agreeing by luck.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.bots import backtest, divergence
from apps.pine.intent import Side, StrategyIntent
from apps.pine.parser import parse
from apps.pine.runtime import Runtime
from tests import pine_corpus

D = Decimal
CROSS = (pine_corpus.ACCEPT / "01_sma_cross.pine").read_text()


def intent(side, *, bar_time=1, sl=None, tp=None, reason="", plots=None) -> StrategyIntent:
    return StrategyIntent(
        bar_time=bar_time,
        symbol="BTCUSDT",
        desired_side=side,
        sl_pct=D(sl) if sl else None,
        tp_pct=D(tp) if tp else None,
        reason=reason,
        source_span=None,
        plots=plots or {},
        alerts=(),
    )


# --- what goes into the digest ----------------------------------------------


def test_the_digest_is_stable_for_the_same_sequence():
    sequence = [intent(Side.LONG), intent(None, bar_time=2)]
    assert divergence.digest_intents(sequence) == divergence.digest_intents(sequence)


def test_a_different_side_changes_the_digest():
    assert divergence.digest_intents([intent(Side.LONG)]) != divergence.digest_intents(
        [intent(Side.SHORT)]
    )


def test_a_different_stop_changes_the_digest():
    assert divergence.digest_intents([intent(Side.LONG, sl="1")]) != divergence.digest_intents(
        [intent(Side.LONG, sl="2")]
    )


def test_a_different_bar_time_changes_the_digest():
    assert divergence.digest_intents(
        [intent(Side.LONG, bar_time=1)]
    ) != divergence.digest_intents([intent(Side.LONG, bar_time=2)])


def test_the_reason_string_is_not_part_of_the_decision():
    """It is output for a human; a reworded reason is not a changed strategy."""
    assert divergence.digest_intents([intent(Side.LONG, reason="a")]) == (
        divergence.digest_intents([intent(Side.LONG, reason="b")])
    )


def test_a_changed_plot_is_not_a_changed_strategy():
    assert divergence.digest_intents([intent(Side.LONG, plots={"x": "1"})]) == (
        divergence.digest_intents([intent(Side.LONG, plots={"x": "2"})])
    )


def test_an_empty_sequence_still_produces_a_digest():
    assert divergence.digest_intents([]) 


def test_compare_refuses_an_empty_digest_rather_than_calling_it_a_match():
    """Two runs that both produced nothing is not evidence of agreement."""
    assert divergence.compare("", "") is False


def test_compare_matches_identical_digests():
    digest = divergence.digest_intents([intent(Side.LONG)])
    assert divergence.compare(digest, digest) is True


def test_compare_rejects_different_digests():
    assert divergence.compare("a" * 64, "b" * 64) is False


# --- the actual claim -------------------------------------------------------


def test_the_backtest_and_a_bare_runtime_agree_on_the_same_bars():
    """Not two implementations: the backtest drives the *same* `Runtime`, and
    this pins that there is no second evaluation path hiding inside it."""
    bars = pine_corpus.bars(200)
    report = backtest.run(
        source=CROSS,
        symbol="BTCUSDT",
        interval="15m",
        from_time=bars[0].time,
        to_time=bars[-1].time,
        bars=bars,
    )

    runtime = Runtime(parse(CROSS), symbol="BTCUSDT")
    intents = []
    position = 0
    for candle in bars:
        runtime.sync_position(size_sign=position)
        result = runtime.run_bar(candle)
        intents.append(result.intent)
        position = {Side.LONG: 1, Side.SHORT: -1, None: 0}[result.intent.desired_side]

    assert report.intent_digest == divergence.digest_intents(intents)


def test_the_same_script_run_twice_never_diverges_from_itself():
    bars = pine_corpus.bars(300)
    kwargs = dict(
        source=CROSS, symbol="BTCUSDT", interval="15m",
        from_time=bars[0].time, to_time=bars[-1].time, bars=bars,
    )
    assert divergence.compare(
        backtest.run(**kwargs).intent_digest, backtest.run(**kwargs).intent_digest
    )


@pytest.mark.parametrize("path", pine_corpus.accepted(), ids=lambda p: p.name)
def test_every_fixture_is_reproducible(path):
    bars = pine_corpus.bars(150)
    kwargs = dict(
        source=path.read_text(), symbol="BTCUSDT", interval="15m",
        from_time=bars[0].time, to_time=bars[-1].time, bars=bars,
    )
    assert backtest.run(**kwargs).intent_digest == backtest.run(**kwargs).intent_digest


# --- the scale-out (Q33) ----------------------------------------------------


def test_a_script_that_never_scales_out_digests_exactly_as_it_did_before():
    """The fraction is written only when it is not a whole position, so adding
    the field did not invalidate the paper-run digests the promotion gate has
    already recorded. This is the digest, computed by hand from the fields the
    fingerprint carried before Q33."""
    import hashlib
    import json

    rows = [
        {"t": 1, "s": "BTCUSDT", "d": "long", "sl": None, "tp": None},
        {"t": 2, "s": "BTCUSDT", "d": None, "sl": None, "tp": None},
    ]
    expected = hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    rerun = [intent(Side.LONG, bar_time=1), intent(None, bar_time=2)]
    assert divergence.digest_intents(rerun) == expected


def test_two_runs_that_disagree_only_about_a_scale_out_are_a_divergence():
    """Without the fraction in the digest the side is identical on both sides
    of a TP1, and the two runs would have compared equal."""
    whole = intent(Side.LONG, bar_time=1)
    scaled = StrategyIntent(
        bar_time=1,
        symbol="BTCUSDT",
        desired_side=Side.LONG,
        position_fraction=D("0.6"),
    )
    assert not divergence.compare(
        divergence.digest_intents([whole]), divergence.digest_intents([scaled])
    )
