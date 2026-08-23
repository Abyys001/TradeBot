# Bot mode — the execution plan

> The layer below [`bot-mode.md`](bot-mode.md): what to create, in what order,
> and the test that proves each piece.

**Status:** nothing here is built. Phase 0 is closed.
**Audience:** whoever implements it, human or agent.
**Why:** `bot-mode.md` argues the design; this plan is what gets ticked off. They
are separate files because they change at different rates — the argument is
settled, the worklist is not.

---

## 0. How to use this

**Q20–Q27 are answered and binding.** They live in
[`decisions.md`](decisions.md), answered 2026-08-23. Cite the number; never
re-open the argument. `bot-mode.md` holds the reasoning behind each; this plan
holds only the consequence.

Everything downstream of `StrategyIntent` **already exists** and is not to be
forked: `route_open` / `route_amend` / `route_close`
(`backend/apps/trading/services.py:413`, `:602`, `:679`), the fan-out and its
per-leg deadline (`apps/engine/fanout.py`), sizing (`apps/trading/sizing.py`),
the halt (`apps/trading/killswitch.py`). A bot is a signal source. If a diff in
this project ever adds a second order path, it is wrong regardless of what it
does.

Three cross-cutting rules apply to every phase below and are not repeated in each:

- **`Decimal` for price, quantity, balance.** No floats cross into
  `StrategyIntent` or out of the risk gate.
- **Nothing in `apps/pine/` or `apps/bots/` imports `accounts.visibility`** —
  the same prohibition `apps/engine/` is under (Q27). Every bot *read* surface
  filters, and gets a case in `tests/test_account_access.py`.
- **Tests go in `backend/tests/test_*.py`.** See §1.2 — this one has already
  bitten this repo once.

---

## 1. Corrections to the roadmap

`bot-mode.md` was written before anyone read the tree it lands in. Eight of its
suggestions conflict with what is actually here. Each correction below is
grep-checkable at the cited line.

### 1.1 Two packages, not one — `apps/pine/` stays pure

`bot-mode.md` puts `feed.py`, `backtest.py`, `translate.py` and `riskgate.py`
inside `apps/pine/`, alongside the lexer and runtime. But Phase 1 and Phase 2
both open with "no I/O, no Django" — and `feed.py` awaits WebSockets,
`backtest.py` reads the ORM, `translate.py` calls `services.route_*`. Put them
in one package and that promise is gone by Phase 3, along with the ability to
test the runtime without a database.

The split:

| Package | Holds | May import |
|---|---|---|
| `backend/apps/pine/` | lexer, parser, AST, validator, series, `ta`, runtime, `StrategyIntent` | stdlib only — **not** `django.*`, **not** `apps.*` |
| `backend/apps/bots/` | feed, backtest, report, translator, risk gate, supervisor, models, views, WebSocket events | everything |

`apps/pine/` importing nothing from Django is a rule with a test
(`test_pine_imports_no_django`, walking the package's imports). It is what makes
the runtime the same object in backtest and live, which is the entire argument
of Phase 4.

Only `apps.pine` and `apps.bots` join `INSTALLED_APPS` — `apps.engine` and
`apps.exchanges` are plain packages and are not registered, because a package
earns a slot only when it has models or management commands.

### 1.2 The proposed test location would never run — and this repo already proves it

`bot-mode.md:231` and `:337` put tests and fixtures under
`backend/apps/pine/tests/`. `backend/pyproject.toml:4` sets
`testpaths = ["tests"]`.

This is not hypothetical. `backend/apps/logging/tests/` exists and holds **36
tests that the default `pytest` run does not collect** — including
`test_facets_serve_every_level_and_category_the_backend_writes`
(`apps/logging/tests/test_api.py:88`), which `bot-mode.md` Phase 6 names as the
thing that will catch a missing log category. It will not. It has not run in
months.

```
.venv/bin/python -m pytest --collect-only -q | grep -c apps/logging   # → 0
.venv/bin/python -m pytest apps/logging/tests --collect-only -q       # → 36
```

→ Pine tests go in `backend/tests/test_pine_*.py` and `test_bot_*.py`, flat,
like all 29 collected modules. **Separately and not part of bot mode:** the 36
orphaned tests are a live gap in the suite and want either a `testpaths` entry
or a move. Worth raising, not worth fixing inside this feature.

### 1.3 The corpus is this repo's first on-disk test data

There is no `fixtures/` directory and no `Path(__file__)` read anywhere in
`backend/tests/` today — every input is an inline literal or a module constant.
`backend/tests/fixtures/pine/` is a deliberate first, because a twenty-strategy
lexer corpus as inline triple-quoted strings is unreadable and undiffable.

Decided: the corpus is **authored in this repo**, not vendored from TradingView.
`accept/*.pine` covers the §1.3 subset; `reject/*.pine` carries one file per
rejected construct, each paired with the exact construct name, line and column
its error must report. No third-party scripts enter the tree.

### 1.4 `PineError` is the first error here to carry a span

House style is a subsystem-local base plus a lowercase snake_case `code` string:
`AdapterError` (`apps/exchanges/base.py:141`, `code=` keyword),
`SizingRejection` (`apps/trading/sizing.py:21`, positional `(reason, code)`).
There is no project-wide root exception and no error anywhere carries a location.

`PineError` keeps `code` and **adds `span`**, because §1.1 and §4 need line and
column to link a chart marker back to the line that drew it. Documented as an
extension of the existing pattern, in the class docstring, so the next reader
does not think it is a second convention.

### 1.5 `BOT` and `STRATEGY` log categories are a migration

`Category` is a `models.TextChoices` on `LogEntry`
(`apps/logging/models.py:11`), not a module constant. `bot-mode.md` lists this
as a wiring bullet; it is a schema change with a migration. And per §1.2, the
test that would have caught the half-done version does not currently run.

### 1.6 Frozen where it is a value, mutable where the engine accumulates

The split is consistent across the tree: `Capabilities`
(`apps/exchanges/base.py:43`), `OrderResult`, `Candle` are
`@dataclass(frozen=True, slots=True)`; `TradeIntent`
(`apps/engine/executor.py:39`) and `FanOutResult` (`apps/engine/fanout.py:96`)
are `slots=True` only, because the engine builds them up.

So: `Span`, `Token`, every AST node and `StrategyIntent` are frozen. `Series`,
the indicator state objects and the run context are not.

### 1.7 Management commands raise `CommandError`, never `sys.exit`

Progress goes to `self.stdout.write`, terminal state to `self.style.SUCCESS` /
`WARNING`, per-item failure to `self.stderr.write(self.style.ERROR(...))`.
`--dry-run` is the house preview flag. `pine_check` and `pine_backtest` follow
it.

### 1.8 `strategy.exit` is per *trade*, and the platform has one SL/TP per trade

Q21 lets a percent `strategy.exit` win over the bot's configured `sl_pct`. Note
what that means downstream: the platform's SL/TP is one pair per `Trade`,
identical across accounts (§5), so a script calling `strategy.exit` twice with
different percentages in one bar is not expressible. **Last call in the bar
wins, and the validator warns when a bar can reach two of them.** Decide it
here rather than in Phase 5, where it would look like a bug.

---

## 2. `settings.BOT`

Shaped like `settings.TRADING` (`config/settings.py:224`) and read the same way,
so `/api/bots/policy/` can mirror `trading/policy/`
(`apps/trading/views.py:140`) — the open decisions as live settings, visible in
the panel. `env_bool` (`config/settings.py:15`) for the flags.

| Key | Env | Default | First read in |
|---|---|---|---|
| `MAX_SCRIPT_BYTES` | `BOT_MAX_SCRIPT_BYTES` | 65536 | Phase 1 |
| `MAX_AST_NODES` | `BOT_MAX_AST_NODES` | 20000 | Phase 1 |
| `MAX_TA_CALL_SITES` | `BOT_MAX_TA_CALL_SITES` | 200 | Phase 1 |
| `MAX_LOOP_ITERATIONS` | `BOT_MAX_LOOP_ITERATIONS` | 10000 | Phase 1 + 2 |
| `SERIES_DEPTH` | `BOT_SERIES_DEPTH` | 5000 | Phase 2 |
| `BAR_BUDGET_MS` | `BOT_BAR_BUDGET_MS` | 250 | Phase 2 |
| `BAR_CONFIRM_LAG_MS` | `BOT_BAR_CONFIRM_LAG_MS` | 2000 | Phase 3 |
| `WARMUP_MULTIPLIER` | `BOT_WARMUP_MULTIPLIER` | 3 | Phase 3 |
| `WARMUP_MIN_BARS` | `BOT_WARMUP_MIN_BARS` | 300 | Phase 3 |
| `MAX_CLOCK_SKEW_MS` | `BOT_MAX_CLOCK_SKEW_MS` | 5000 | Phase 3 |
| `BACKTEST_SLIPPAGE_BPS` | `BOT_BACKTEST_SLIPPAGE_BPS` | 5 | Phase 4 |
| `BACKTEST_FEE_BPS` | `BOT_BACKTEST_FEE_BPS` | 5 | Phase 4 |
| `MAX_PRICE_DRIFT_PCT` | `BOT_MAX_PRICE_DRIFT_PCT` | 2 | Phase 5 |
| `MAX_ACCOUNTS` | `BOT_MAX_ACCOUNTS` | 0 (no cap) | Phase 5 |

**The Q25 auto-stop defaults.** Every one is per-bot configurable
(`Bot.risk_config` JSON); these are the fallbacks, and Phase 10 requires they be
set deliberately rather than left here.

| Key | Env | Default |
|---|---|---|
| `MAX_CONSECUTIVE_LOSSES` | `BOT_MAX_CONSECUTIVE_LOSSES` | 5 |
| `MAX_DRAWDOWN_PCT` | `BOT_MAX_DRAWDOWN_PCT` | 15 |
| `MAX_TRADES_PER_HOUR` | `BOT_MAX_TRADES_PER_HOUR` | 10 |
| `RECONCILE_PASSES_BEFORE_STOP` | `BOT_RECONCILE_PASSES_BEFORE_STOP` | 2 |
| `NO_BAR_TIMEOUT_MULTIPLE` | `BOT_NO_BAR_TIMEOUT_MULTIPLE` | 3 |

The remaining two Q25 triggers — an unrepairable feed gap and a script runtime
error — are **not numbers and not configurable**. Both are "any, the first one".
A setting there would be a setting for how much silent disagreement with the
market is acceptable, and the answer is none.

---

## 3. Phase 1 — the Pine front end

Source text → validated AST, or a precise error. Pure functions and frozen
dataclasses; no Django import anywhere in the package.

| File | Holds | Proven by |
|---|---|---|
| `apps/pine/errors.py` | `PineError(code, span)` + `PineSyntaxError` / `PineNameError` / `PineTypeError` / `PineUnsupported` / `PineRuntimeError` | every rejection test asserts `exc.value.code` and `exc.value.span` |
| `apps/pine/tokens.py` | `TokenKind`, `Span(line, col, end_line, end_col)`, `Token` | `test_pine_lexer.py` |
| `apps/pine/lexer.py` | column-stack INDENT/DEDENT; bracket depth suspends both newline-as-terminator and indentation; `\` continuation; `//` comments; int/float/string/bool/`#RRGGBB[AA]` literals | `test_pine_lexer.py` — corpus round-trip, and one test per literal form |
| `apps/pine/ast_nodes.py` | frozen node dataclasses, each with `span` and `call_id` | `test_pine_parser.py` |
| `apps/pine/parser.py` | recursive descent; full v5 precedence; right-assoc `?:`; `=` and `:=` as **distinct** nodes; `var`/`varip`; tuple declarations; named args; `if` as expression; `for`/`for…in`/`while`/`switch`; user functions | `test_pine_parser.py` |
| `apps/pine/subset.py` | the Q24 registry — one row per rejected construct carrying the message its error must produce | `test_pine_validate.py` parametrizes over the registry, so a new rejection cannot ship without its message |
| `apps/pine/validate.py` | subset enforcement + the `bot-mode.md` §1.4 semantic checks | `test_pine_validate.py` |
| `apps/pine/management/commands/pine_check.py` | `python manage.py pine_check <file> [--ast]` — prints the AST or the error, `CommandError` on failure | manual; the command is the Phase 8 editor's contract in miniature |
| `backend/tests/fixtures/pine/accept/*.pine` | ~20 authored strategies covering §1.3 | — |
| `backend/tests/fixtures/pine/reject/*.pine` | one per rejected construct + expected name/line/col | — |

**`call_id` is the load-bearing decision.** Derive it from the source span so it
survives a re-parse of unchanged source and changes when the line changes.
Phase 2 keys indicator state on it and Phase 4 links chart markers back through
it; getting it wrong is discovered in Phase 4, not Phase 1.

**Two additions to `bot-mode.md` §1.4's checklist**, both cheap here and
expensive later:

- The `strategy()` call's arguments are validated **by name** — `pyramiding`,
  `calc_on_every_tick`, `calc_on_order_fills`, `process_orders_on_close`
  rejected; `default_qty_type`, `default_qty_value`, `initial_capital` accepted
  and **reported as ignored** (Q20), never dropped in silence.
- `strategy.exit` argument shape is checked here, not in the runtime: percent
  arguments accepted, ticks/points rejected by name (Q21), and a bar that can
  reach two `strategy.exit` calls warns (§1.8).

**Done when:** the corpus parses; every rejection names construct, line and
column; `pytest backend/tests/test_pine_*.py` is green; `pine_check` prints an
AST for an accepted file and a located error for each rejected one.

---

## 4. Phase 2 — the Pine runtime

AST + bars → one `StrategyIntent` and a plot dict per bar. Still no I/O.

| File | Holds | Proven by |
|---|---|---|
| `apps/pine/series.py` | `Series` as a bounded ring buffer capped at `SERIES_DEPTH`; `na` as a first-class value — arithmetic on `na` yields `na`, comparison yields `false` | `test_pine_series.py` |
| `apps/pine/ta.py` | every §1.3 indicator as an incremental `update(x) -> value`, O(1) per bar, with TradingView's warm-up and `rma` seeding | `test_pine_ta.py` — golden values, see Q29 |
| `apps/pine/builtins.py` | `math.*`, `str.*`, `nz`/`na()`/`fixnan`, bar state, session/time | `test_pine_builtins.py` |
| `apps/pine/runtime.py` | `run_bar(bar)`, per-call-site state, `snapshot()`/`restore()`, the `BAR_BUDGET_MS` guard | `test_pine_runtime.py` |
| `apps/pine/intent.py` | `StrategyIntent`, frozen — no quantity, leverage, account or price field exists on it (Q20/Q21) | the type is the test |

**The three things that bite late**, all in §2.2 of `bot-mode.md` and all worth
a named test:

1. State is keyed on `(call_id, call_stack_path)`, not `call_id` — a `ta.*` call
   inside a user function invoked twice per bar is two logical call sites.
2. Every stateful call site **advances every bar**, including inside a branch
   that did not execute. Register them in one AST walk at load; tick them all,
   then evaluate. A strategy whose EMA only updates on days it is used is a
   different strategy.
3. `na` propagation. An indicator returning `na` compared with `>` gives
   `false`, not an error — so a warm-up bug looks exactly like a strategy that
   politely does not trade for a while.

**Determinism is a test, not an aspiration:** the same 10k bars twice, hashes
compared. No wall-clock reads; `math.random` only from a seeded generator whose
seed is recorded in the run.

**Done when:** golden tests pass for every indicator; determinism holds; 100k
bars run in under ~10s; dividing by zero raises `PineRuntimeError` naming the
line.

---

## 5. Phase 3 — the bar feed

A thin, strict layer over machinery that already exists — not a new data stack.
`public_sources.py` fetches candles, `public_stream.py` streams them,
`catalogue.ensure_history` (`apps/exchanges/catalogue.py:542`) downloads
history, `marketdata.get_candles` (`apps/exchanges/marketdata.py:323`) merges
stored and live.

**New:** `apps/bots/feed.py` (not `apps/pine/` — §1.1).

| Item | Rule |
|---|---|
| `BarFeed(symbol, interval, market)` | async-iterates **closed bars only**, exactly once each, in order |
| Bar identity | open time, UNIX seconds, as `public_sources` already returns |
| Confirmation | `now >= open_time + interval + BAR_CONFIRM_LAG_MS`. Exchanges emit the closing update late; reading on the clock roll gets a bar that is still moving |
| Source | WebSocket preferred, polling as fallback — exactly as the chart does. The bot knows which it is on and says so in the panel |
| Warm-up | `max(lookback) × WARMUP_MULTIPLIER`, floor `WARMUP_MIN_BARS`; replayed with `barstate.ishistory`, **every intent discarded** |
| Short history | the bot **refuses to start** and says how many bars it has against how many it needs. No unconverged EMA ever trades |
| Reconnect | re-fetch the window since the last seen bar, replay missing closed bars in order, then resume |
| Unrepairable gap | **stop the bot** (Q25). Never skip, never synthesise, never interpolate — `public_stream.py` already makes that promise for the chart |
| Clock | skew checked at start and hourly; over `MAX_CLOCK_SKEW_MS` refuses to start. UTC internally |

**Done when:** a 48-hour 1m BTCUSDT soak yields exactly 2,880 bars, each once,
in order, every reconnect repaired and logged — and a deliberate socket kill
mid-run recovers with no gap.

---

## 6. Phase 4 — backtest

Two jobs, and the second is the one that matters: it is the correctness harness
for Phases 1–3. Same runtime object, fed from storage instead of a socket.

**New:** `apps/bots/backtest.py`, `apps/bots/report.py`,
`apps/bots/management/commands/pine_backtest.py`.

The fill model, stated in every report because the numbers are meaningless
without it:

- entry at the **next bar's open**, never the signal bar's close;
- slippage `BACKTEST_SLIPPAGE_BPS`, fee `BACKTEST_FEE_BPS` per side, per-exchange override;
- SL/TP checked against following bars' high/low, and **when one bar touches
  both, the stop is assumed** — the only honest reading without tick data.

Metrics: net PnL, return %, max drawdown, Sharpe, win rate, profit factor,
average win/loss, expectancy, trade count, longest flat period, time in market,
average bars held, worst trade, consecutive losses. Equity curve and per-trade
table, both exportable. Every marker carries its `source_span` — that is what
the Phase 1 span plumbing was for.

**The determinism test is the deliverable.** Run N bars through `backtest.py`
and through the Phase 6 live loop fed the same bars from a fixture; assert the
intent sequences are byte-identical, forever. It is the whole argument that a
backtest predicts anything.

`python manage.py pine_backtest <file> --symbol --interval --from --to` prints
the summary, usable long before any UI exists.

---

## 7. Phase 5 — intent → action

**New:** `apps/bots/translate.py`, `apps/bots/riskgate.py`.

The translator diffs desired state against actual and emits the difference —
the table in `bot-mode.md` §5.1 is the specification. Four rules carry it:

- **A reversal is two actions, sequenced.** Close, confirm flat, then open.
  Concurrent on a netting venue gives a doubled or a cancelled order depending
  on arrival order.
- **Actual state comes from the exchange.** `services.reconcile_open_trade`
  (`apps/trading/services.py:548`) and `possync.sync_positions`
  (`apps/trading/possync.py:565`) run before the diff.
- **A failed leg is not proof nothing happened.** `accounts_in_open_trades`
  (`services.py:142`) already treats an unconfirmed leg as possibly holding —
  its docstring says why. The bot reports such an account as **"sat out"**, not
  as a failure (Q22), and never re-enters it.
- **Idempotency is a database constraint.** `(bot_run_id, bar_time,
  action_type)` persisted *before* dispatch, `UNIQUE`. Application logic alone
  does not survive a restart mid-fan-out.

The risk gate sits between the translator and `services.*`; every action passes
through and any refusal **stops the bot** (Q25). It carries all seven Q25
triggers, the optional per-bot UTC trading window, `MAX_ACCOUNTS`, a max
notional, and the price sanity check — bar close against the live ticker, more
than `MAX_PRICE_DRIFT_PCT` apart refuses and stops, which catches both a stale
feed and a mis-mapped symbol.

`killswitch.is_on()` (`apps/trading/killswitch.py:66`) is **reused, not
re-read** — no second path to the halt. Under the halt the bot pauses; it does
not error.

`dry_run` on every bot: evaluate, log the action it would have taken, route
nothing. That is Phase 7's shadow mode and it costs one branch.

---

## 8. Phase 6 — supervisor, persistence, recovery

**New app:** `apps/bots/` — models, migrations, supervisor, views, serializers.

Data model per `bot-mode.md` §6.1. `StrategyVersion` is immutable; editing makes
a version. `BotAction.idempotency_key` is `UNIQUE` at the database level.
`Trade` gains a nullable `bot_run` FK so §8 history can say which trades a bot
made, and the manual path is unchanged when it is null.

| Item | Rule |
|---|---|
| One `asyncio` task per bot | in the ASGI process, alongside the fan-out — `route_*` is async and a broker hop would spend the §4 budget |
| Isolation | one bot's exception, slow script or dead feed touches no other. Per-task supervision; never `gather` without `return_exceptions=True` |
| Loop | next confirmed bar → `run_bar` → intent → reconcile → translate → risk gate → dispatch → persist → broadcast |
| Lifecycle | a real state machine: `draft → paper → live`; any state `→ stopped`; `stopped → paper` only. **`stopped → live` is not a transition** — a test per illegal edge |
| Recovery | re-warm from bars, never from serialised indicator state (a deploy silently invalidates it); read positions from the exchange; reconcile any dispatched-but-unknown `BotAction` through `confirm_open` (`apps/engine/executor.py:931`) first |
| Disagreement | retry once; still disagreeing → **stop and notify**. Auto-correcting a disagreement nobody understands is how a recovery becomes a liquidation |

### Wiring into what exists

- **Stop-all stops every bot** — in `killswitch.set_stop_all(True)`
  (`killswitch.py:91`) and in the panel's flatten path. Q22 calls this the most
  important of the eight. Pinned by `test_stop_all_stops_every_running_bot` and
  `test_a_stopped_bot_does_not_re_enter_after_a_flatten`.
- `BOT` and `STRATEGY` added to `Category` — **with a migration** (§1.5) and a
  facets test that actually runs.
- `bot.bar` / `bot.intent` / `bot.action` / `bot.state` / `bot.stopped` on the
  existing `"trading"` group (`apps/trading/consumers.py:20`). Same staff-only,
  same-origin gate; hidden-account filtering on any per-account payload.
- `/api/bots/` — CRUD, `validate`, `backtest`, `start`, `stop`, `runs`, `bars`,
  `policy`. Async views like `order_views.py` where they route; DRF where they
  only read.
- A `bots` compose service alongside `possync`, or the supervisor inside the
  ASGI process — decide when Phase 6 starts, and record which in this file.

---

## 9. Phase 7 — paper, shadow, and the soak

Shadow mode is a `dry_run` bot on the **live** feed, routing nothing, running
alongside the admin's manual trading. Paper mode is the same bot routed to paper
accounts through `apps/exchanges/paper.py` and `./run.sh demo`.

**Divergence tracking is the point:** compare shadow-mode actions against a
backtest over the same bars. They must be identical. Any difference is a Phase 3
or Phase 6 bug, and it is free to find here.

### The gate — measured, not asserted

Phase 8's promotion flow **reads this table** and refuses while any row is
unmet, so each row needs a number the system itself records.

| Requirement | Threshold | Where the number comes from |
|---|---|---|
| Continuous paper/shadow runtime | 14 days | `BotRun.started_at` |
| Unexplained backtest/live divergences | 0 | divergence tracker |
| Process restarts survived cleanly | ≥ 3, one unplanned | recovery log entries |
| Feed gaps handled | 100% | feed gap counters |
| Reconciliation drift events | 0 unexplained | `BotAction` results |
| Kill-switch drills passed | ≥ 2 | halt log entries |
| Every Q25 auto-stop fired in a drill | all 7 | `BotRun.stop_reason` |

Fourteen days is not round-number thinking: it crosses a weekend, a funding
cycle, an exchange maintenance window, and at least one bad-liquidity hour.

---

## 10. Phase 8 — the panel

House rules unchanged: Nuxt 3, Pinia, Tailwind, every string through
`useI18n()`, English complete before Persian starts, RTL-capable from the first
commit, `reference/skills/frontend-design.SKILL.md` for the visual work.

| Surface | Notes |
|---|---|
| Strategies list | versions, validation status, which bots use them |
| Editor | CodeMirror 6 + Pine mode; inline errors from `validate` using Phase 1's line/col; Q20 ignored-`qty` and Q24 unsupported warnings shown, never hidden |
| Backtest view | equity curve, trade table, metrics, annotated chart. Marker → source line, line → its markers. The payoff for carrying spans through four phases |
| Bot list | state, symbol, timeframe, live PnL, next-bar countdown, last signal, feed source, per-bot stop |
| Bot detail | live chart with the strategy's own plots, signal log, action log with the resulting fan-out legs, risk-gate state, and why it stopped |
| Promotion | `draft → paper` one click; `paper → live` renders §9's gate with the system's own measurements and refuses while a row is unmet — a gate that knows the numbers, not a confirmation dialog |

Reuse `composables/useChartAdapter.ts`; do not add a second charting path. Every
new read surface filters hidden accounts, with its own case in
`tests/test_account_access.py` (Q27) — that file is the checklist.

---

## 11. Phase 9 — observability and ops

`system_log()` under `BOT`/`STRATEGY` for: bot started, warm-up complete, bar
evaluated (debug), intent produced, action dispatched, action result, risk-gate
refusal, feed gap, reconnect, stopped and why.

Numbers worth having: bars evaluated, evaluation ms p50/p99, feed lag, actions
dispatched, fan-out ms per bot action, refusals by reason, auto-stops by
trigger, divergence count.

**Alerts must leave the panel.** Telegram or email, because the panel is not
open at 03:00 and Q25's entire premise is that nobody is watching: bot
auto-stopped, feed gap unrepaired, reconciliation drift, risk-gate refusal, any
bot exception.

Docs: `docs/bots.md` — how to write a strategy for this platform, the subset,
the promotion path, and a runbook (a bot stopped; the feed gapped; the exchange
and the database disagree; flatten everything now).
`docs/spec/conformance.md` gains a bot-mode section, clause → where → the test,
lifted from the tables above.

---

## 12. Phase 10 — the go-live gate

Before any bot routes to a real account:

- [ ] §9's gate fully met, measurements recorded.
- [ ] A backtest over ≥ 2 years or ≥ 500 trades, whichever is more, and the
      admin has read the report's stated fill assumptions.
- [ ] **`docs/adapters.md`'s blocker cleared for the exchanges involved** — no
      adapter has been run against a live exchange or testnet yet, and a bot is
      a bad first thing to discover that with.
- [ ] Canary: one account, smallest balance, one week, `MAX_ACCOUNTS = 1`.
- [ ] Q25 limits set deliberately for this strategy, not left at §2's defaults.
- [ ] The runbook walked by whoever is on call, flatten drill included, on the
      real deployment.
- [ ] The §11 legal note re-read. Automating discretionary trading of other
      people's capital is a different activity from mirroring a human's trades.
      `questions.md` records the activity as signed off by a lawyer; that
      sign-off predates bot mode.

---

## 13. Order of work

Critical path is `1 → 2 → 4`: Phase 4 is what proves Phases 1–2 are right, and
everything after is plumbing that should not be built on an unproven runtime.

```
Phase 1 (front end) ──→ Phase 2 (runtime) ──→ Phase 4 (backtest)
                                                    │
Phase 3 (feed) ─────────────────────────────────────┤
                                                    ▼
                           Phase 5 (translate) ──→ Phase 6 (supervisor)
                                                    │
                                               Phase 7 (soak, 14 days)
                                                    │
                           Phase 8 (UI) ────────────┤
                           Phase 9 (ops) ───────────┤
                                                    ▼
                                              Phase 10 (go live)
```

Phase 3 is independent of 1 and 2 and can be built in parallel by a second pair
of hands; so can 8 and 9 alongside 6 and 7. Phase 10 waits for all of them.

**Start at** `backend/apps/pine/tokens.py`. Nothing above it needs a decision
that has not been taken — except Q29, which blocks only Phase 2's golden
fixtures and not its implementation.
