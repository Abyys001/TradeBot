# Parity & Execution Plan — TradingView as source of truth, Hyperliquid as execution

> **Goal.** Make the platform's backtests reproduce TradingView as closely as
> possible, and keep that guarantee all the way to live fills on Hyperliquid.
>
> **Audience.** An implementing agent (Claude Code) with the repo checked out,
> plus a human who owns a TradingView account (the exports in Part A can only be
> produced by a person).
>
> **Companion docs.** `docs/bot-mode.md`, `docs/bot-plan.md`, `docs/bots.md`,
> `docs/decisions.md`, `docs/spec/conformance.md`. Cite decisions by number; do
> not re-open them.

---

## 0. Ground rules (read before writing any code)

These are the existing invariants. Every task below stays inside them.

- [ ] **A bot is a signal source, not a second execution path.** Nothing here
      adds an order path. Everything below `StrategyIntent` is reused
      (`route_open/amend/close`, fan-out, `sizing.py`, `killswitch`). If a diff
      adds a second `place_order`, it is wrong regardless of what it does.
- [ ] **`apps/pine/` stays pure** — stdlib only, no `django.*`, no `apps.*`
      (`test_pine_imports_no_django`). All fixture I/O, TradingView import, and
      Hyperliquid fetching live in `apps/bots/`, `apps/exchanges/`, or tests —
      never in `apps/pine/`.
- [ ] **`Decimal` on the money path.** Prices, quantities, balances that cross
      into `StrategyIntent` or out of the risk gate are `Decimal`. Indicator/
      series math is a separate question — see **P6**.
- [ ] **TradingView is the oracle; fix the engine, never the fixture.** When a
      conformance test fails, the engine is wrong, not the exported truth.
- [ ] **Do not weaken the subset to pass a fixture.** If a strategy needs a
      rejected construct (`request.security`, `array/matrix/map`, pyramiding),
      that strategy is out of scope for v1 — record it, do not silently admit it.
- [ ] **Reuse the existing golden-fixture harness.** `backend/tests/fixtures/
      pine/golden/` and its `README.md` already exist (Q29). Extend the format
      and swap the oracle source; do not build a parallel one.

---

## 1. The design in one screen

**Two profiles of one engine.**

| Profile | Candles | Sizing | Slippage / fee | Funding | Used for |
|---|---|---|---|---|---|
| **Parity** | TradingView-exported | matches the TV strategy's Properties | matches TV (start at 0) | off | proving the engine equals TradingView |
| **Predictive** | Hyperliquid API | platform 99% × leverage (spec §5) | HL-calibrated | on | the go/no-go decision that predicts live |

**Three reconciliation layers**, each a standing test:

1. **TradingView Strategy Tester ≡ engine (parity profile)** on TV-exported
   candles. *Is the interpreter faithful?* — Part B, P3/P4/P5.
2. **Engine predictive backtest ≡ engine live loop**, both on the HL feed.
   *Is the runtime deterministic between backtest and live?* — the existing
   `divergence.digest_intents` test; P12 keeps it green under the predictive
   profile.
3. **Engine live loop ≡ actual Hyperliquid fills.** *What does reality cost?* —
   measured in paper/canary, folded back into the predictive profile (P9).

**One bridge:** HL API candles ≡ TradingView `HYPERLIQUID:` candles for the same
window (P7). If those agree, a TradingView backtest genuinely stands in for a
Hyperliquid one.

---

## PART A — What the human exports from TradingView

An agent cannot log into TradingView. A person does this once per fixture and
drops files into the repo; the agent (P1) provides an importer so the person's
job is only "export CSV, run the importer."

**Setup for every export**
- [ ] Chart the **`HYPERLIQUID:`** symbol you will actually trade (e.g.
      `HYPERLIQUID:BTCUSD`), not Binance/Coinbase/an index.
- [ ] Fix the timeframe and a fixed, recent date window (higher timeframes reach
      back further — see the ~5000-bar note in P10).
- [ ] Record your TradingView plan's export bar-count limit; a paid tier exports
      far more history and you will want it.

**A. Indicator exports** (feeds P3)
- [ ] For each `ta.*` in the subset, add a one-line `//@version=6 indicator(...)`
      that `plot()`s the function's output(s) with stable titles.
- [ ] **Export chart data** → CSV. It contains OHLCV **and** each plotted series
      on the same timestamps. Save the CSV plus the exact script text.

**B. Trade-list exports** (feeds P4)
- [ ] For each strategy you intend to run, load it on the `HYPERLIQUID:` chart,
      set the **Properties** (sizing, commission, slippage,
      `process_orders_on_close`, margin) to a config you write down.
- [ ] Strategy Tester → **List of Trades** → export CSV.
- [ ] Also **Export chart data** for the same window (the candles the trades ran
      on). Save: script text, the Properties you used, both CSVs.

**C. Fill edge-case exports** (feeds P5)
- [ ] Build or find a **small** candle window that hits one ambiguity, run the
      strategy on it, export the List of Trades + candles. One fixture per case:
      - bar touches **both** stop and target;
      - stop hit on the **same bar** the entry filled;
      - bar **gaps through** the stop;
      - `process_orders_on_close=true` entry then same-bar exit;
      - entry whose next-bar-open **gaps**.

**Where files go:** `backend/tests/fixtures/pine/tv/{indicators,tradelist,edge}/`
as raw CSVs + a small sidecar (script text, symbol, interval, properties). P1's
importer converts these into the golden JSON the tests read.

---

## PART B — Agent worklist

Build the harness first; it works against a schema and one sample fixture before
any real TradingView export exists, then goes green when the exports land.

### P1 — Fixture format + TradingView importer

**New:** `apps/bots/tv_import.py`,
`apps/bots/management/commands/tv_import.py`,
`backend/tests/fixtures/pine/tv/README.md`.

- [ ] Define the golden JSON the tests consume (Decimals as strings; `null` for
      `na`):
      ```json
      // indicators/<name>.json
      { "kind":"indicator", "symbol":"HYPERLIQUID:BTCUSD", "interval":"60",
        "pine_version":6, "exported_at":"…", "script":"…",
        "candles":[[t,"o","h","l","c","v"], …],
        "expected":{ "ema20":[null,null,"…"], … } }

      // tradelist/<name>.json  (edge cases share this shape)
      { "kind":"tradelist", "symbol":"…", "interval":"…", "pine_version":6,
        "properties":{ "initial_capital":"…","default_qty_type":"…",
          "default_qty_value":"…","commission_type":"…","commission_value":"…",
          "slippage":"…","process_orders_on_close":false,
          "margin_long":"…","margin_short":"…" },
        "script":"…", "candles":[[t,"o","h","l","c","v"], …],
        "trades":[ { "num":1,"side":"long","entry_time":…,"entry_price":"…",
          "exit_time":…,"exit_price":"…","qty":"…","pnl":"…",
          "reason_entry":"…","reason_exit":"…" }, … ] }
      ```
- [ ] `tv_import` converts TradingView's native CSV exports (chart data + List of
      Trades) into the above. It parses TV's column layout, aligns timestamps to
      UNIX seconds (the platform's bar identity — `feed_base.Candle.time`), and
      writes the JSON. It performs **no** interpretation: it copies numbers.
- [ ] A schema validator rejects a malformed fixture with a located message.
- [ ] Commit **one** hand-written sample of each kind so the harness is testable
      before real exports arrive.

**Done when:** `manage.py tv_import --kind indicator|tradelist|edge <csv…>`
produces a schema-valid fixture; `test_tv_fixture_schema` is green.

### P2 — Two assumption profiles

**Changed:** `apps/bots/backtest.py`, `apps/bots/report.py`,
`apps/bots/config.py`, `apps/bots/management/commands/pine_backtest.py`.

- [ ] Introduce an explicit `Profile` (`parity` | `predictive`) that selects the
      assumptions bundle: candle source, sizing rule, slippage/fee, funding
      on/off. Today `Assumptions` already carries most of this and the report
      labels the sizing line — formalize it into a named profile rather than a
      scatter of flags.
- [ ] `parity`: honour the fixture's `properties` verbatim (sizing type,
      commission, slippage, `process_orders_on_close`, margin). This is what
      makes a run comparable to TradingView.
- [ ] `predictive`: force platform sizing (spec §5), HL slippage/fee, funding on
      (P8). Ignore `default_qty_type` with the existing Q20 report line.
- [ ] `pine_backtest --profile parity|predictive`, default `predictive`. Every
      report header names the profile.

**Done when:** the same script + candles under the two profiles produce the two
documented sizings, and `test_profile_selects_assumptions` pins it.

### P3 — Indicator conformance (replaces the transcribed oracles, Q29)

**Changed:** the existing golden harness under `backend/tests/fixtures/pine/
golden/`; **new** tests `backend/tests/test_pine_indicator_parity.py`.

- [ ] Point the indicator oracle at the **TV-exported** fixtures from P1, not the
      values transcribed from `reference/pinescriptv6/`. Keep the old fixtures
      only as a secondary sanity check, clearly labelled non-authoritative.
- [ ] Harness: feed each fixture's `candles` to the runtime, read back the named
      series, compare bar-for-bar to `expected`.
- [ ] **Tolerance:** target is TradingView's float64 result. Use a relative
      epsilon `BOT_PARITY_EPS` (default `1e-8`); assert `na` where `expected` is
      `null`. Any bar over epsilon is a failure to investigate, not to widen.
- [ ] Coverage: every `ta.*` in the subset; ≥2 symbols incl. one thin/gappy;
      a fixture exercising `[n]` history; the time/session builtins with the
      chart timezone pinned.

**Done when:** every indicator fixture matches within `BOT_PARITY_EPS`;
`test_pine_indicator_parity` is green; Q29 is closed in `conformance.md`.

### P4 — Trade-list conformance (the strongest single oracle)

**New:** `backend/tests/test_pine_tradelist_parity.py`.

- [ ] For each `tradelist` fixture: run `backtest.py` under the **parity**
      profile on the fixture candles, Properties mirrored from the fixture.
- [ ] Assert, row-for-row: entry time, exit time, side, entry price (to the
      instrument tick), exit price (to tick), exit reason, and trade count.
      Assert PnL within a rounding tolerance once sizing matches.
- [ ] First pass with `slippage=0` and matched commission to isolate logic +
      fill timing; then a second fixture with matched slippage on.
- [ ] Cover the constructs you rely on: crossover; percent SL/TP
      `strategy.exit`; `qty_percent` scale-outs (TP1/TP2/TP3 on one bar → three
      closed trades, as TradingView lists them); reversal;
      `process_orders_on_close`.

**Done when:** every trade-list fixture matches to tick on prices and exactly on
bars/side/reason/count; `test_pine_tradelist_parity` is green.

### P5 — Fill edge cases (inherit TradingView's rule, don't reason about it)

**New:** `backend/tests/test_pine_fill_edge_cases.py`.

- [ ] One fixture per case from Part A/C. Each is a `tradelist` fixture with a
      tiny candle window and one/few trades.
- [ ] Assert the engine's trade matches TradingView's exported trade exactly.
- [ ] Where the engine's current assumption differs from TV (e.g. the
      both-touched bar, where the engine assumes the stop): **change the engine
      to match TradingView's exported result** for the configured settings, and
      note it in `report.Assumptions` so the report still states the rule.

**Done when:** every edge fixture matches; `test_pine_fill_edge_cases` is green;
`docs/bots.md`'s fill-model table reflects whatever TradingView actually does.

### P6 — Numeric model alignment (float64 vs Decimal on the series path)

Pine computes all series math in IEEE-754 double precision. If the runtime uses
`Decimal` for series, values will differ from TradingView in the low digits and
can flip a crossover exactly at equality.

- [ ] Inspect `apps/pine/runtime.py`: is the series/`ta.*` math `float` or
      `Decimal`?
- [ ] If it already mirrors Pine's float64, add a note and move on.
- [ ] If it is `Decimal`, and P3/P4 show divergences traceable to precision:
      make **series math** float64 to mirror Pine, and convert to `Decimal` only
      at the boundary where a value becomes a **price/level/size** that crosses
      into `StrategyIntent` or a fill. The money-path Decimal rule (Ground Rules)
      is unchanged; this is strictly about the indicator math above it.
- [ ] Keep determinism: no wall-clock, seeded RNG only, same bars twice → same
      digest.

**Done when:** P3/P4 pass within `BOT_PARITY_EPS` with the numeric model chosen,
and the determinism test still holds.

### P7 — Data-parity check (the bridge)

**New:** `apps/bots/management/commands/hl_tv_data_parity.py`,
`backend/tests/test_hl_tv_data_parity.py`.

- [ ] Command takes a TV-exported chart-data CSV and a symbol/interval/window,
      fetches the same window from `HyperliquidPublicSource.candles`, and diffs
      OHLCV bar-for-bar.
- [ ] Report per-field max/median deviation and any missing/extra bars. Both are
      Hyperliquid data through different pipelines (TV's feed vs HL's
      `candleSnapshot`), so small deviations are expected; characterise them.
- [ ] If deviations exceed a documented threshold, print the offending bars —
      this is a data issue to resolve or record, never to hide.

**Done when:** the command prints a signed parity report for a real window, and
the result is written into `conformance.md` (agreement level + any caveat).

### P8 — Funding in the predictive profile

HL perps pay funding; the report currently excludes it, which understates the
cost of any held position.

**Changed:** `apps/exchanges/public_sources.py` (extend `HyperliquidPublicSource`
with a funding-history fetch — HL `/info` `fundingHistory`), `apps/bots/
backtest.py`, `apps/bots/report.py`.

- [ ] Fetch funding history for the symbol/window (predictive profile only).
- [ ] Apply funding to the open position at each funding settlement inside the
      window (HL settles hourly); sign by side. Fold into equity and PnL.
- [ ] The report's assumptions line stops saying "does not include funding" for
      the predictive profile and states the funding total instead. Parity profile
      remains funding-off (TradingView does not model it).

**Done when:** a held-position fixture shows funding applied at the right
settlements; `test_predictive_backtest_applies_funding` is green.

### P9 — Slippage & fee calibration (layer 3)

**New:** `apps/bots/management/commands/hl_slippage_report.py`.

- [ ] From stored `BotAction` results (which carry the requested basis and the
      per-leg fill), compute realised slippage in bps: requested price
      (bar close / next open, per the fill model) vs actual HL fill, by side and
      by notional bucket.
- [ ] Print the distribution (median, p90) and the taker fee actually charged.
- [ ] Use the output to set `BOT_BACKTEST_SLIPPAGE_BPS` and `BOT_BACKTEST_FEE_BPS`
      for the **predictive** profile. This is the number that makes the
      predictive backtest match live cost; it is measured, never guessed.

**Done when:** the command runs against paper/canary `BotAction` data and its
output is what the predictive profile reads.

### P10 — History-depth honesty

HL's `candleSnapshot` serves only ~5000 bars/interval (`limited_history=True`).

- [ ] `pine_backtest` and the backtest API already report short warm-up; extend
      that so any request beyond HL's available depth says exactly how many bars
      exist vs were asked for, per interval, and never silently truncates.
- [ ] Surface the practical ceiling (1m ≈ 3.5d, 1h ≈ 7mo, 4h ≈ 2y) in
      `docs/bots.md` so timeframe choice is made with eyes open. Pair it with a
      hard out-of-sample split in the promotion workflow (overfitting risk is
      worse on a small sample).

**Done when:** an over-long window returns a clear coverage statement, pinned by
`test_backtest_reports_hl_history_ceiling`.

### P11 — Conformance CLI + parity report

**New:** `apps/bots/management/commands/pine_conformance.py`.

- [ ] Runs every P3/P4/P5 fixture and prints a single parity report: per fixture,
      pass/fail, worst indicator deviation, trade-list diffs if any.
- [ ] Exit non-zero on any failure so it can gate CI and be read from a terminal
      long before any UI.

**Done when:** `manage.py pine_conformance` summarises the whole suite and
returns the right exit code.

### P12 — Wire into CI and the existing divergence test (layer 2)

- [ ] Add P3/P4/P5/P11 to the test run (`backend/tests/test_*.py` — **not**
      `apps/*/tests`, per `bot-plan.md` §1.2).
- [ ] Confirm `divergence.digest_intents` (backtest vs live loop) runs under the
      **predictive** profile on a shared fixture and stays byte-identical. This
      is layer 2; do not fork it.
- [ ] Update `docs/spec/conformance.md`: Q29 closed, the two profiles, the three
      layers, and the data-parity result.

**Done when:** CI is green with the conformance suite included, and
`conformance.md` reflects the new state.

---

## 2. Acceptance criteria — the measurable definition of "as close as possible"

- **Indicators (parity):** every `ta.*` fixture matches TradingView within
  `BOT_PARITY_EPS` (default `1e-8` relative); `na` regions match exactly.
- **Trade list (parity):** for every strategy fixture — entry bar, exit bar,
  side, exit reason, and trade count match **exactly**; entry/exit prices match
  to the instrument tick; PnL within rounding once sizing matches.
- **Fill edge cases (parity):** each fixture's trade matches TradingView exactly;
  the engine's documented fill rules equal TradingView's observed behaviour.
- **Data parity (bridge):** HL API candles vs TradingView `HYPERLIQUID:` candles
  agree within the documented threshold over the check window, or the deviation
  is characterised in `conformance.md`.
- **Determinism (layer 2):** predictive backtest and live loop emit
  byte-identical intent sequences on the same bars.
- **Cost realism (layer 3):** predictive slippage/fee/funding come from measured
  HL fills, not defaults.

When all six hold, any residual gap between a TradingView chart and a live
Hyperliquid fill is attributable to data or execution — never to an unlocated
engine bug. That is the strongest form of "as close as possible" that is true.

---

## 3. Order of work

```
P1 ─▶ P2 ─▶ P3 ─▶ P4 ─▶ P5        (P6 pulled in if P3/P4 show precision drift)
                  │
       P7, P8, P9, P10  (independent; can run alongside P4/P5)
                  │
                 P11 ─▶ P12 (CI + conformance.md)
```

- **P1–P2 first** — nothing can be validated without the fixture format and the
  two profiles.
- **P3/P4/P5 need the human's Part-A exports.** Build the harnesses against the
  sample fixtures, then turn green as real exports land.
- **P6** is contingent: only act if precision divergence appears.
- **P7–P10** are independent workstreams; **P8/P9** feed the predictive profile.
- **P11/P12** close it out and make it a standing contract.

**First task:** P1 — the fixture format and `tv_import`. Everything downstream
reads what it produces.
