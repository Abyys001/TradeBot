# Backtest — Implementation Plan

Sidebar link + Pine Script v6 strategy backtesting + Hyperliquid public data download +
saved results + comparison. The plan to execute later, this file is the contract.

---

## 1. What we are building

A new panel destination, `/backtest`, that lets the admin:

1. Paste a **Pine Script v6 strategy** (a `.pine` file).
2. **Download the data first** — a distinct, gated step with its own progress bar.
   Data comes from **Hyperliquid public data** only (no credentials, spec §13
   discipline: real exchange data, no invented series).
3. Run the backtest: the Pine script is **translated to Python** and executed
   bar-by-bar against the downloaded candles.
4. See **why every trade happened**: for each open *and* close, the exact logic
   (which `strategy.entry` / `strategy.exit` fired, the triggering condition
   rendered in Pine text with resolved indicator values at that bar).
5. **Save every run** and revisit it later.
6. **Compare runs** — the part the brief calls out as most important.

Everything below is grounded in the existing repo:
- Pine v6 ground truth is already vendored at **`pinescriptv6_docs/`** (official
  manual restructured for LLMs; `LLM_MANIFEST.md` is the entry map, the
  `strategy` semantics live in `reference/functions/strategy.md`). The user's own
  complete Pine v6 document, when supplied, is committed to the same directory.
- Hyperliquid public candles already exist on the backend
  (`apps/exchanges/public_sources.py::HyperliquidPublicSource`), but backtesting
  needs **more than 500 bars and a range**, so the backtest app gets its own
  paginated fetcher that speaks to `https://api.hyperliquid.xyz/info` directly.
- Panel conventions: Django 5 + DRF, no broker worker in this deployment
  (threads, per `apps/exchanges/catalogue.py` precedent), Decimal everywhere for
  money, staff-gated writes, bilingual i18n (English first, Persian second),
  RTL-capable.

## 2. Architecture overview

```
Admin browser (Nuxt)                      Django backend (new app: apps/backtest/)
────────────────────                      ───────────────────────────────────────
/backtest  ── script (.pine) ───────────▶ pine/lexer.py ─ parser ─ AST ─ compiler
             symbol/interval/range ─────▶ data/download.py ── Hyperliquid public
             ▶ Run button ─────────────▶  engine.py (bar loop) + runtime.py
             ▶ progress poll (GET)      ─▶ Decision trace: every order event
             ▶ result                    │    + condition text + value snapshot
             results list / detail /     │  models: BacktestDataset, BacktestRun,
             compare (equity overlay)  ◀─┤           BacktestTrade, BacktestDecision
                                        └─ stored in PostgreSQL
```

The Pine toolchain and the engine are pure Python and **exchange-free**: they
never touch adapters, credentials, or accounts. The only outbound call in the
whole feature is the public Hyperliquid data download.

## 3. Ground truth to read first (executor checklist)

- `pinescriptv6_docs/LLM_MANIFEST.md` — where each Pine concept lives.
- `pinescriptv6_docs/pine_script_execution_model.md` — bar-by-bar execution,
  series, `var`, `varip`, `barstate`, realtime vs history. **This is the model
  the compiler must reproduce.**
- `pinescriptv6_docs/reference/functions/strategy.md` — exact `strategy.*`
  semantics (fills, `pyramiding`, `process_orders_on_close`, commission,
  slippage, exit precedence when stop+limit cross the same bar).
- `pinescriptv6_docs/reference/functions/ta.md` — exact indicator formulas
  (sma, ema/rma, rsi, macd, atr, bb, stoch, crossover/crossunder…).
- `pinescriptv6_docs/reference/keywords.md`, `operators.md`, `types.md` — the
  language surface the parser must accept.
- `backend/apps/exchanges/public_sources.py` (HyperliquidPublicSource) —
  request/response shapes of `candleSnapshot` to reuse.
- `backend/apps/trading/models.py::StoredCandle` / `MarketDataSync` — the stored
  bar + progress-row pattern to mirror.
- `backend/apps/exchanges/catalogue.py` — the thread + progress precedent the
  data download and backtest run jobs follow.
- `frontend/composables/useNavigation.ts`, `frontend/components/app/Sidebar.vue`,
  `frontend/components/app/MobileNav.vue` — one nav definition drives both rails.
- `frontend/stores/`, `frontend/composables/useApi.ts` — store + API client
  conventions.
- `frontend/utils/icons.ts` — inline icon set; a new glyph is added here.

## 4. Backend — new Django app `apps/backtest/`

Register in `config/settings.py::INSTALLED_APPS`. All views staff-gated on write
(like every other write in the panel). No credentials, no accounts, no adapters.

### 4.1 Models (`models.py`)

- **`BacktestDataset`** — one downloaded series.
  `name`, `exchange="hyperliquid"`, `symbol` (e.g. `BTCUSDT`, quote USDT),
  `interval` (1m/5m/15m/1h/4h/1d — Hyperliquid's native set), `start_time`,
  `end_time`, `bar_count`, `status` (pending/running/done/failed),
  `progress` (bars written), `detail`, `error`, `candles` **JSONField**
  (list of `[t, o, h, l, c, v]` — numbers stored as strings where they are money,
  decoded to `Decimal` on load), `created_at`.
  One row per (symbol, interval, range); a rerun reuses it.

- **`BacktestRun`** — one executed backtest.
  `name` (auto: script name + dataset + datetime), `dataset` FK,
  `script_source` (the pasted Pine), `script_name` (from `strategy(title=)`),
  `status` (queued/running/done/failed), `error`, `params` (JSON — the
  `strategy(...)` settings: initial_capital, commission, slippage, pyramiding…),
  `metrics` (JSON — §4.4), `equity_curve` (JSON — per-bar time + equity +
  drawdown + position marker), `version` (script content hash — a rerun of an
  unchanged script on a changed dataset is the comparison dimension),
  `created_at`, `duration_ms`.

- **`BacktestTrade`** — one closed position.
  `run` FK, `entry_time`, `exit_time`, `side`, `qty`, `entry_price`, `exit_price`,
  `pnl`, `pnl_pct`, `exit_reason` (see §4.5), `bars_held`.

- **`BacktestDecision`** — the *why*, one row per order event.
  `run` FK, `trade` FK (nullable for cancelled/expired orders), `bar_time`,
  `action` (entry/exit/close_all/reverse/cancel), `order_id` (Pine id),
  `side`, `price`, `size`, `reason` (decompiled Pine condition text + resolved
  values), `context` (JSON snapshot — the script's named series at that bar).
  This is what the UI renders as the decision trace.

### 4.2 The Pine Script v6 toolchain (`pine/`)

Pipeline: **lexer → parser (AST) → compiler → Python**, executed by `engine.py`.

- `pine/lexer.py` — tokeniser for the v6 surface: identifiers, numbers, strings,
  comments (`//`), all operators (`:=` **reassignment is a distinct token**, `? :`,
  `[]`, `.`, comparison/arithmetic), keywords. Token set driven by the vendored
  `reference/keywords.md` / `operators.md`.
- `pine/ast_nodes.py` — the AST: script, strategy header call, declarations
  (`x = …`, `var x = …`, `varip`), reassignment (`:=`), `if/else`, `switch`,
  `for` / `for…in` (phase 2), function declarations (`f(a,b) => …`), ternary,
  calls, series indexing `x[n]`, member access (`barstate.isconfirmed`),
  literals.
- `pine/parser.py` — recursive-descent parser producing the AST. Clear
  `NotSupportedError` with the offending line/column for anything out of scope
  (see the MVP boundary in §6) — a strategy must **fail loudly with a line
  number**, never be silently mis-compiled. That is the accuracy bar.
- `pine/compiler.py` — the heart. Walks the AST and emits a Python module that
  reproduces Pine's execution model exactly:
  - The script body becomes a **bar loop** (earliest → latest bar). Every Pine
    variable compiles to a per-bar series object (`runtime.Series`) indexed by
    the loop's bar counter. This mirrors `pine_script_execution_model.md`.
  - `var` / `varip` initialise once before the loop (varip: intra-bar, MVP
    treats it as var and notes the restriction).
  - `x := y` writes `series_x[bar] = y`.
  - History `x[n]` → `series_x[bar - n]` with bounds → `na`.
  - `if/else`, `switch`, ternary, `and/or/not` → Python control flow. The
    compiler tracks the **condition stack** so each `strategy.entry/exit` inside
    an `if` knows its triggering condition (feeds §4.5).
  - Every `strategy.entry/exit/close/order` call is rewritten into an engine
    call wrapped with the decision snapshot (§4.5).
  - Generated Python is emitted under a **whitelist-only runtime** (see §7): the
    only callable names in scope are our builtins — `import` and friends cannot
    exist because the compiler never emits them.
- `pine/runtime.py` — the whitelisted builtin library:
  - series helpers: `na`, `nz`, `fixnan`, `bar_index`, `time`, `open/high/low/
    close/volume`, `barstate.isconfirmed`, `barmerge`.
  - `ta.*`: sma, ema, rma, rsi, macd, atr, atrWilder, trueRange, bb, stdev,
    stoch, crossover, crossunder, highest, lowest, hhv, llv, vwap, … each
    implemented from the vendored `reference/functions/ta.md` formulas, reading
    the accumulated series up to the current bar (Pine semantics exactly).
  - `math.*`: round, floor, ceil, abs, max, min, pow, sqrt, exp, log, sign,
    pi… per the reference.
  - `strategy.*` → forwarded to `engine.py`'s state machine (§4.3).
  - display/no-op calls for backtesting: `plot`, `bgcolor`, `alert`, `box.new`
    etc. compile to debug hooks (their values land in the decision `context`),
    never to UI.
  - `request.security`, `array.*`, `matrix.*`, `map.*`, `type`/`method`,
    `dynamic*` → phase 2; the parser refuses them clearly in the MVP.
- `pine/decompiler.py` — renders an AST expression back to Pine text, with
  series values substituted: `ta.crossover(ta.rsi(close,14),30)` →
  `"rsi(close,14) crossed above 30 (rsi(14) = 31.2)"`. Powers the decision
  `reason` strings.

### 4.3 Backtest engine (`engine.py`)

A bar-loop simulator with Pine's fill semantics, all money in **Decimal**:

- State: cash, position (side, qty, avg price), equity = cash + mark of open
  position, trade ledger, order queue.
- `strategy(initial_capital=, default_qty_type=, default_qty_value=, currency=,
  pyramiding=, commission_type=, commission_value=, commission_on=, slippage=,
  process_orders_on_close=)` parsed from the script header and applied.
- Fills: default entries fill on the **next bar's open**; with
  `process_orders_on_close=true` they fill on the signal bar's close. `stop`/
  `limit` exits fire intra-bar when the bar's range crosses the level; the
  precedence rule when stop **and** limit are both hit in one bar is taken from
  the vendored `reference/functions/strategy.md` — verified against the doc,
  never guessed.
- `pyramiding` (default 0: max one entry per direction), `strategy.close`,
  `strategy.close_all`, `strategy.exit(from_entry=, stop=, limit=, trail_price=,
  trail_offset=, time=)`, `strategy.order`, `strategy.cancel`, `strategy.
  position_size`, `strategy.position_avg_price`, `strategy.open_*`, `strategy.
  equity`, `strategy.netprofit` — the surface a real strategy uses.
- Commission (percent or fixed, on open/close/all) and slippage applied at fill.
- **Equity curve** sampled every bar with the drawdown and a marker at each
  order event (for the chart's trade dots).
- **Metrics** (Pine strategy-report parity, all computed in Decimal): net profit
  % and absolute, gross profit, gross loss, profit factor, win rate, max
  drawdown (absolute and %), Sharpe, Sortino, total closed trades, wins/losses/
  break-even, largest win/loss, average win/loss, max consecutive wins/losses,
  exposure %, buy-and-hold comparison on the same bars, longest flat period.
  Stored in `BacktestRun.metrics`.

### 4.4 Execution model for the run

Same pattern as `catalogue.start_sync`: a **thread** (no Celery worker in this
deployment) that runs the pipeline and writes progress into the row. The API
polls status; a thread that dies records `error` and leaves the run inspectable.
`duration_ms` recorded so slow strategies are visible.

### 4.5 The decision trace — "what logic opened, what logic closed"

The brief's accuracy requirement. Three layers:

1. **Per order event**, the compiler's rewritten call tells the engine: the Pine
   order id, the action, and the **decompiled condition** from the enclosing
   `if` (via the condition stack), e.g. for
   `if ta.crossover(ta.rsi(close, 14), 30) and close > ta.sma(close, 20)`
   the reason reads
   `crossover(rsi(close,14),30) and close > sma(close,20)  →  rsi(14)=31.2, sma(20)=61,240.5, close=61,300.1`.
2. **Exit reasons** are the Pine semantics: `take profit`, `stop loss`, `close`,
   `close all`, `reverse`, `time exit` (from `strategy.exit(time=)`), `signal
   exit`, `SL/TP amended` — recorded on the trade and in the decision row.
3. **Context snapshot**: at every order bar the runtime captures the script's
   named series (`rsi`, `sma`, `ema`…) — name → value — into `BacktestDecision.
   context`. The UI renders it as a per-trade "signals at signal bar" strip, so
   the admin can see the state the strategy was looking at, not just the
   conclusion.

The same data is what makes comparison meaningful later.

### 4.6 Data download (`data/download.py`)

- Hyperliquid public `candleSnapshot` (`https://api.hyperliquid.xyz/info`,
  `req: {coin, interval, startTime, endTime}`), **pinned to Hyperliquid** — no
  provider fallback here: a backtest dataset must come from exactly the venue
  named on the screen.
- Paginated walk backwards from `endTime` (the endpoint caps a single response;
  the existing `HyperliquidPublicSource` returns ≤500), deduped, ascending,
  gap-checked. A small delay between pages to respect the public endpoint's
  rate limits.
- Symbols from the Hyperliquid perps universe (via the same `metaAndAssetCtxs`
  call the source already uses); canonical symbol `BTCUSDT`-style with quote
  `USDT`.
- Progress row mirrors `MarketDataSync`: phase (resolving / downloading / done),
  bars written, bar count target, percent. The frontend bar polls it.
- No credentials anywhere. Stored as `BacktestDataset.candles` (Decimal strings).

### 4.7 API (`urls.py` / `views.py`, prefix `/backtest/`)

- `POST /backtest/datasets/` — start a download (symbol, interval, range).
- `GET /backtest/datasets/` — list; `GET /backtest/datasets/<id>/` — status +
  bar count + a few sample bars (never the whole payload in the list).
- `POST /backtest/datasets/<id>/delete/` — discard (staff).
- `POST /backtest/runs/` — create: `dataset_id` + `script` (the .pine text).
  Validates/compiles first; returns the run id or a compile error with
  line/column (a strategy that fails to compile must never start a run).
- `GET /backtest/runs/` — saved runs, summary rows (name, script, dataset,
  bars, trades, net %, win rate, max DD, profit factor, Sharpe, date) — the
  compare/table payload.
- `GET /backtest/runs/<id>/` — full result: metrics, equity curve, trades,
  decisions.
- `POST /backtest/runs/<id>/delete/` — discard (staff).
- `POST /backtest/compare/` — takes a list of run ids, returns the shared
  metric matrix + equity curves normalised to a common axis for overlay. (Or
  the frontend assembles it from individual run payloads — decide at build:
  one call is fewer round trips, so prefer the endpoint.)

Hidden-account invariants do not apply (no accounts involved), but the "no new
read surface leaks" rule does: dataset/run payloads contain no account, balance
or position data — nothing to filter.

### 4.8 Security — sandboxing (do not skip, this is the order-routing repo)

Compiled Python is executed server-side; the strategy is untrusted input. Even
staff-only, the invariant is "the script can trade nothing outside its own
ledger". Hard rules, pinned by tests:

- The compiler is the only path to names: generated code references **only**
  `runtime` builtins and its own variables. No `import`, no `__builtins__`,
  no attribute/member access on non-runtime objects beyond what the compiler
  emits. A lexer/parser test asserts rejected constructs.
- Execution in a **subprocess** with `resource` limits (CPU seconds, address
  space), a wall-clock timeout (configurable; `BACKTEST_TIMEOUT_SECONDS`),
  and no network/FS reachable (the process inherits nothing; the runtime
  provides no IO). A runaway strategy fails the run with a timeout error, not
  the server.
- AST-level allow-listing in the compiler: only registered builtin names can
  be called; anything else is a compile error with line/column.
- No shell, no eval of user string as code (`eval`/`exec` of the *compiled*
  output only, which the compiler produced from a validated AST).
- Tests: a malicious script attempting `import os`, `__import__`, attribute
  probing, `open()`, infinite loop, and memory churn must all fail cleanly
  (see `tests/test_pine_security.py` in §4.9).

### 4.9 Testing

`apps/backtest/tests/`, run with `cd backend && .venv/bin/python -m pytest`,
`ruff` clean:

- `test_lexer.py` / `test_parser.py` — token and AST snapshots; every rejected
  construct has a line/column assertion.
- `test_compiler.py` — translate known strategies, execute, compare series
  values against hand-computed reference values (sma, ema, rsi on a synthetic
  candle series with known answers).
- `test_engine.py` — deterministic mini-strategies with known outcomes:
  a crossover entry that must be filled at next bar's open; SL vs TP firing in
  the same bar (precedence from the doc); pyramiding=0 blocking a second entry;
  commission/slippage arithmetic in Decimal.
- `test_decision_trace.py` — the reason strings and context snapshots are
  present and correct for a script with two entries and a `strategy.exit`.
- `test_download.py` — mocked Hyperliquid responses: pagination walk across
  multiple `candleSnapshot` pages, gap detection, dedupe.
- `test_api.py` — staff gating, compile-error rejection (400 with line/col),
  run lifecycle (queued→running→done), delete.
- `test_pine_security.py` — §4.8 table.
- `test_accuracy_fixture.py` — golden pair: a strategy backtested by the
  vendored Pine docs' example outputs (where the manual gives numbers) vs our
  engine; and a CSV/JSON fixture of an expected equity curve that must match.

## 5. Frontend

### 5.1 Navigation + i18n

- `composables/useNavigation.ts`: add
  `{ name: 'backtest', path: localePath('/backtest'), icon: 'backtest',
  label: t('nav.backtest'), primary: false }`. `primary: false` puts it in the
  mobile drawer and on the desktop rail (same mechanism both rails already use).
  `Sidebar.vue` and `MobileNav.vue` need **no changes** — they render from the
  list.
- `utils/icons.ts`: add a `backtest` glyph (a flask / beaker is the honest
  metaphor: an experiment against history) and `compare` (two curves) drawn on
  the same 24-grid at 1.6 stroke so it matches the set's optical weight.
- `i18n/locales/en.json` first, then `fa.json`: `nav.backtest` plus the full
  page vocabulary (sections below). Every string through i18n from day one;
  RTL-capable layouts.

### 5.2 Routes and page structure

- `pages/backtest.vue` — the landing page: composer + data bar + run + status.
- `pages/backtest/results.vue` — saved runs table (the compare picker lives
  here).
- `pages/backtest/results/[id].vue` — one run: metrics, equity chart with trade
  markers, trades table, decision trace.
- `pages/backtest/compare.vue` — the comparison view, `?runs=1,2,3` (state in
  the URL so it survives refresh and is linkable).
- Tabs (`Segmented`) across the top: **Run · Results · Compare** mirroring the
  three jobs, and the Results page rows are the comparison source.

### 5.3 Components (`components/backtest/`)

- `BacktestComposer.vue` — left: the Pine editor (monospace `<textarea>` with
  line numbers + the compile/validation status chip; keep it dependency-free
  like the rest of the panel — no editor library unless one is already a dep).
  Right: run configuration (dataset picker, initial capital, qty type/value —
  surfaced from the strategy header but editable before run). A green **Run
  backtest** that is disabled until a dataset is downloaded and the script
  compiles.
- `BacktestDataBar.vue` — the brief's download bar. Symbol (from the
  Hyperliquid universe), interval, range (start/end or "last N bars"), a
  **Download from Hyperliquid** button, and a progress bar (phase + bars
  written + percent) polled from the dataset row. On done, shows bar count +
  time span and enables the run. "Refetch" refreshes the dataset.
- `BacktestResultList.vue` — the table of saved runs (metrics columns), sorted
  newest first, searchable/filterable by script and dataset. Row checkboxes
  feed the compare set; "Open" goes to the detail; delete (staff).
- `BacktestResultDetail.vue` — metric grid (reuse `Stat`/`Card` components),
  the equity curve chart, and tabs: **Trades** (table) and **Decisions**
  (timeline, below).
- `BacktestTradesTable.vue` — entry time, side, qty, entry/exit price, pnl,
  pnl %, exit reason, bars held. A row click opens the decision strip for that
  trade.
- `BacktestDecisionPanel.vue` — the trace: for each trade, the entry card
  (the decompiled reason + context snapshot chips like `rsi(14)=31.2`) and the
  exit card (reason: take profit / stop loss / signal close…). Rendered as a
  small timeline so open→close logic reads top-to-bottom. This is the accuracy
  feature the brief demands — give it real visual weight.
- `BacktestEquityChart.vue` — the equity curve. **Reuse Lightweight Charts**
  (already the panel's chart engine): one series for equity, one per trade as
  a marker (green win / red loss dot at the close), optionally drawdown as a
  second series. The one piece of shared chart code stays behind
  `useChartAdapter` semantics; this is not the candlestick chart, so a small
  dedicated adapter function in the composable (or a light wrapper) is fine —
  do not bend the trading chart to this.
- `BacktestCompare.vue` — see §5.5.
- `BacktestEmptyState.vue` — the "no runs yet" invitation, in the panel's
  existing `Empty` styling: tell the admin to run their first backtest, don't
  show a blank grid.

### 5.4 Stores and API

- `stores/backtests.ts` — Pinia: current script text, composer form state,
  active dataset, runs list cache, `compareSelection: number[]`
  (persisted to `sessionStorage`; survives tab switches, and the URL `?runs=`
  is the shareable/refresh-safe copy).
- `composables/useApi.ts` (or a `useBacktestApi` composable): `datasets()`,
  `startDownload()`, `dataset(id)`, `deleteDataset(id)`, `runs()`,
  `run(id)`, `createRun()`, `deleteRun(id)`, `compare(ids)`. Same-origin,
  CSRF header on POSTs, exactly like the existing client.

### 5.5 The comparison view — designed, not bolted on

The brief flags comparison as the important part, so it earns the design work.
The winning pattern for comparing backtests is **one metric grid + one shared
equity chart**, because a table alone can't show *where* in time one strategy
won and another lost.

- **Selection** happens in `results.vue` (checkboxes on rows, a persistent
  `compareSelection` in the store, a floating "Compare N" button). The compare
  route opens with `?runs=…`.
- **Metric matrix**: one row per metric, one column per run, each run assigned
  a colour from a fixed palette; the **best value per metric row is
  highlighted** (and where direction is ambiguous — e.g. exposure — the "best"
  is defined explicitly in the header). Two or three runs side by side is the
  sweet spot; more than five columns is capped.
- **Overlaid equity curves**: all selected runs on one Lightweight Charts
  instance, normalised so each curve starts at the same baseline (each run's
  equity ÷ initial capital × 100 — this is display-only math, done in the
  frontend as a ratio, never money), with the run colour, a legend, and the
  trade markers per run drawn on its own curve. Crosshair reads both curves.
- **Below**: the compared runs' trade lists aligned by bar time when the
  datasets are the same (same symbol/interval/range) — a "who traded when"
  view that shows a divergence the numbers hide. Only offered when the datasets
  match; otherwise a note says the runs aren't directly comparable.
- **Highlighting a win is precise**: for each metric the winner cell gets the
  brand accent; ties and non-directional metrics get none. The comparison is a
  tool for the admin's judgement, not a "best run" verdict.

### 5.6 Design direction (from the frontend-design skill)

The panel is a dark trading terminal; the backtest page is its *lab*. The single
signature element: **the equity curve is also a trade log** — markers on the
curve at every open/close, win/loss colour-coded, so a run's whole story is
legible at a glance before a single table row is read. Everything else stays
quiet and disciplined on the existing tokens (`bg-panel`, `line`, `brand`,
`ink-muted`, `signal`): metrics as a dense grid (existing `Stat`), trades as a
table, the decision timeline as the one deliberately typographic element (the
`num` and `display` faces, Pine condition text in monospace). Motion only where
it explains (the download bar's progress, the compare legend's focus). English
copy first, sentence case, verbs that say what the button does ("Download from
Hyperliquid", "Run backtest") — the vocabulary the admin already knows.

## 6. Execution phases (in order, each with an acceptance bar)

- **Phase 0 — Vendor ground truth.** Ensure the user's complete Pine v6 doc and
  the vendored manual agree; commit any supplied doc into `pinescriptv6_docs/`.
  *Accept:* `LLM_MANIFEST.md` maps everything the compiler needs.
- **Phase 1 — Backend scaffold + data download.** App, models, download job
  against Hyperliquid public candles, dataset API, progress bar contract.
  *Accept:* a 5m BTCUSDT range downloads into a dataset row with the right bar
  count; download tests green with mocked pagination.
- **Phase 2 — Pine toolchain MVP.** Lexer, parser, compiler for the MVP surface
  (§4.2), runtime with `ta.*`/`math.*`/series, `NotSupportedError` with line/
  column. *Accept:* a hand-written "SMA crossover" strategy compiles, runs, and
  its indicator values match a hand-computed reference.
- **Phase 3 — Engine + decision trace.** Fills, commission, slippage, pyramiding,
  equity curve, metrics, the reason/decompiler + context snapshots.
  *Accept:* engine tests above; a known strategy's decision rows read as
  expected.
- **Phase 4 — Run API + persistence.** Run lifecycle, result payloads, compare
  endpoint, staff gating, security sandbox (§4.8). *Accept:* API + security
  tests green; a run survives restart and loads back.
- **Phase 5 — Frontend run page.** Nav + icon + i18n, composer, data bar, run +
  status flow, store + API client. *Accept:* end-to-end in the panel: paste →
  download → run → done, with the compile-error chip surfacing line/col.
- **Phase 6 — Results + compare.** Results table, detail page (metrics + equity
  + trades + decisions), compare view. *Accept:* the full loop works in the
  browser; compare overlays two runs correctly.
- **Phase 7 — Hardening and polish.** Accuracy fixture vs Pine docs' examples,
  `ruff` clean, full pytest, Nuxt build + `nuxt typecheck` clean, Persian
  translations, empty/error/offline states, keyboard focus + reduced motion,
  responsive down to the mobile drawer. *Accept:* the whole suite green; the
  panel's documented invariants untouched.

Phase 0–1 unblock the data story; phases 2–3 are the accuracy core and can run
in parallel with frontend phase 5; comparison (6) depends on everything above.

## 7. Repo invariants this feature must respect

- **Money in Decimal, never float** (§ "Money"): engine, metrics, dataset load
  all Decimal; JSON stores money as strings.
- **Staff-gated writes**; reads need auth, same as the rest of the panel.
- **Real data only**: dataset comes from Hyperliquid public and is labelled;
  no synthetic bars, no provider fallback for backtest data. A download that
  fails leaves the row failed with the exchange's error, never a 200 with made-up
  bars.
- **No credentials**: the backtest app never touches adapters, API keys, or
  accounts. Nothing here imports `apps.engine` or `apps.exchanges.hyperliquid`
  (the adapter); the only outbound call is the public info endpoint.
- **No new read-surface leaks**: dataset/run payloads carry no account or
  balance data, so the hidden-account filter has nothing to do — but if any
  payload is ever extended to reference accounts, it must be filtered per
  `apps/accounts/visibility.py` and tested in `test_hidden_accounts.py`.
- **i18n bilingual**: English first, Persian second, RTL-capable.
- **Spec discipline**: anything that contradicts the platform spec gets recorded
  in `docs/spec/` and `questions.md`, not silently.

## 8. Risks and open questions (append to `questions.md` as resolved)

- **Fill-model fidelity** is the accuracy risk: Pine's intra-bar stop/limit
  precedence and next-bar-open entries are documented in the vendored manual —
  pin each rule to the doc with a test, and mark in the UI which mode the run
  used (`process_orders_on_close`, `calc_on_every_tick` unsupported → noted).
- **`varip` / `calc_on_every_tick` / realtime bars** have no meaning on closed
  candles; the MVP runs on confirmed bars and says so on the run detail.
- **Pine float vs repo Decimal**: Pine computes in floats; the repo rule is
  Decimal. Engine money is Decimal; indicator arithmetic may be float only where
  it cannot reach a fill, then rounded to the tick before any order is taken.
  Decide the boundary during Phase 3 and record it.
- **`request.security` (HTF) and Pine arrays** — phase 2; the MVP must fail
  clearly, not mis-compile.
- **Backtest data range vs the chart's downloaded year**: the backtest fetches
  its own Hyperliquid range (independent of the panel's `StoredCandle` store) —
  confirm that is the desired boundary rather than reusing the catalogue.

## 9. Key files to touch (executor index)

Backend: `backend/apps/backtest/{models,views,urls}.py`,
`pine/{lexer,parser,ast_nodes,compiler,runtime,decompiler}.py`,
`engine.py`, `data/download.py`, `tests/*`, `config/settings.py` (app),
`.env.example` / `config/settings.py` (`BACKTEST_TIMEOUT_SECONDS`,
`BACKTEST_DATA_*`).

Frontend: `composables/useNavigation.ts`, `utils/icons.ts`,
`i18n/locales/{en,fa}.json`, `pages/backtest.vue`,
`pages/backtest/{results,compare}.vue`, `pages/backtest/results/[id].vue`,
`components/backtest/*`, `stores/backtests.ts`,
`composables/useBacktestApi.ts`.
