# Bot mode — full roadmap

> Define a strategy in Pine Script; the platform trades it across every connected
> account, through the routing path that already exists.

**Status:** planning. Nothing in this document is built yet. Phase 0 is closed.
**Audience:** whoever implements it, human or agent.
**Companion docs:** [`bot-plan.md`](bot-plan.md) — the execution plan: file
manifest, settings keys, and the eight places this roadmap's suggestions
conflict with the repo they land in. Also `docs/spec/platform-spec.md`,
`docs/decisions.md`, `CLAUDE.md`.

---

## 0. The shape of the thing

### 0.1 The one-sentence design

**Bot mode is a signal source, not a second execution path.**

A running bot produces exactly the calls the admin's own button produces —
`route_open`, `route_amend`, `route_close` — and everything downstream is reused
untouched: per-account sizing (§5), the fan-out and its deadline (§4), account
isolation, `NEVER_SENT_CODES` reconciliation, the kill switch (§7), per-account
history (§8), failure notifications.

```
Pine source  ─parse→  AST  ─run→  Pine runtime          ← new
                                       │
                                   StrategyIntent        ← new (declarative)
                                       │
                              intent → action translator ← new
                                       │
                              route_open / route_amend / route_close
                                       │
                     ┌─────────────────┴─────────────────┐   EXISTING —
                     │        fan-out (spec §4)          │   do not fork,
                     │   N adapters, N accounts, N legs  │   do not bypass
                     └───────────────────────────────────┘
```

If you ever find yourself writing a second `place_order` call path "just for the
bot", stop. That fork is how the bot ends up with different sizing, a kill
switch that does not stop it, and legs that never get reconciled. Every property
this platform has fought for lives in `apps/engine/` and `apps/trading/services.py`,
and the bot gets them for free **only** by going through the front door.

### 0.2 What actually changes about the risk

Today a human presses the button. Every clause in the spec — the deadline, the
isolation, the halt — is about making *one deliberate action* land correctly
across N accounts.

A bot removes the human from the loop. Three things follow, and they shape every
gate in this plan:

1. **A bug repeats.** A misread indicator does not cost one bad trade; it costs
   one bad trade per bar, forever, at 99% of every partner's balance.
2. **Nobody is watching at 03:00.** Failure handling that assumes the admin sees
   a notification and acts is not sufficient. The bot must be able to stop
   itself.
3. **The blast radius is the whole book.** One strategy, N accounts, all
   identical direction and leverage, all in at once. There is no diversification
   anywhere in this system by design (spec §5) — that is fine when a human chose
   the trade, and it is a compounding factor when a script did.

So: the bot **fails closed** at every ambiguity, it has its **own halt** on top
of the platform-wide one, and it does not touch real capital until it has run
green in paper for a fixed calendar period. These are not optional polish; they
are Phase 7 gates.

### 0.3 The eleven phases

| # | Phase | Rough size | Blocks |
|---|---|---|---|
| 0 | Decisions (Q20–Q27) — **closed**, `docs/decisions.md` | done | everything |
| 1 | Pine front end — lexer, parser, AST, validator | 1–2 wk | 2 |
| 2 | Pine runtime — series, `ta`, `strategy.*` → intents | 2–3 wk | 4, 5 |
| 3 | Bar feed — confirmed bars, warm-up, gap repair | 1 wk | 4, 6 |
| 4 | Backtest — replay, report, annotations | 1–2 wk | 7 |
| 5 | Intent translator + bot risk gate | 1 wk | 6 |
| 6 | Bot supervisor, persistence, crash recovery | 1–2 wk | 7 |
| 7 | Paper + shadow mode (spec §9 for bots) | 1 wk build, **2 wk soak** | 10 |
| 8 | Panel UI — editor, bot list, live detail, report | 2 wk | — |
| 9 | Observability, alerts, runbook | 3–4 d | 10 |
| 10 | Go-live gate | checklist | real money |

Sizes assume the existing codebase's standard of finish (tests that pin
behaviour, docstrings that say why). They are estimates, not commitments.

---

## Phase 0 — Decisions ✅ Closed

**All eight are answered and binding.** They were taken on 2026-08-23 the way
Q1–Q19 were taken, and they live in
[`docs/decisions.md`](decisions.md) — Q20–Q27 — with the full reasoning and the
setting or module that implements each. Cite them by number; the argument is
settled and is not repeated here.

| # | Decision |
|---|---|
| **Q20** | **The platform decides size; the script decides direction and timing.** `qty`, `strategy.percent_of_equity`, `default_qty_value`/`_type` are parsed and then ignored **with a warning at upload time**, never silently. `StrategyIntent` carries no quantity field at all, so there is nowhere for a script's `qty` to travel to. |
| **Q21** | **Leverage and SL/TP are bot-level settings**, exactly as the order ticket carries them. A percent `strategy.exit` wins for that trade, converted to the Q5a basis and validated against the liquidation distance. `strategy.exit` in ticks or points is rejected at validation — the conversion needs symbol rules the script cannot see. |
| **Q22** | **First claim wins; the admin outranks a bot.** A bot skips an account already in an open trade and reports it "sat out", not failed. A manual entry into an account a bot holds is refused, naming the bot, with a one-click "stop the bot and take the trade". **`close-all` and Stop-all stop every running bot** — the most important line of the eight. |
| **Q23** | **Confirmed bars only.** The bot evaluates once, on bar close. `calc_on_every_tick=true` is a **validation error, not a setting** — there is no configuration in which v1 evaluates intrabar. |
| **Q24** | **The v1 subset is §1.3 below**, and the validator rejects everything else **by name, line and column**. Nothing outside the subset is ever silently ignored — the same rule Q13 took for prices. |
| **Q25** | **Seven auto-stop triggers, none of them auto-resume.** Consecutive losses, own-peak drawdown, unrepairable feed gap, script runtime error, state disagreement after two reconcile passes, trades per rolling hour, and time with no confirmed bar. A bot that stopped itself is restarted by a person who has read why. |
| **Q26** | **Every intent and action forever** — that is the audit trail and it is small. Bars: all of them at 15m and above; at 1m and 5m only where a signal or plot value changed, plus a rolling 7-day window. |
| **Q27** | **Unchanged for bots.** They fan out to hidden accounts identically; nothing in `apps/pine/` or `apps/bots/` may import `accounts.visibility`. Every bot *read* surface filters, with its own case in `tests/test_account_access.py`. |

One question is open, and it blocks only Phase 2's golden fixtures rather than
its implementation: **Q29 — where the `ta.*` reference values come from.** See
[`questions.md`](../questions.md).

---

## Phase 1 — The Pine front end

**Goal:** turn Pine source text into a validated AST, or into a precise error.
No I/O, no market data, no Django. Pure functions and dataclasses.

**New package:** `backend/apps/pine/` — and it stays **pure**: no `django.*`
import, no `apps.*` import, anywhere in it. Everything with I/O (feed,
backtest, translator, risk gate, supervisor) lives in `apps/bots/` instead of
here, so the runtime is the same object in backtest and live. See
[`bot-plan.md`](bot-plan.md) §1.1.

```
backend/apps/pine/
    __init__.py
    errors.py        PineError hierarchy: syntax, name, type, runtime, unsupported
    tokens.py        token kinds
    lexer.py         whitespace-sensitive → INDENT/DEDENT
    ast_nodes.py     node dataclasses, every node carries id + source span
    parser.py        recursive descent, Pine v5 precedence
    validate.py      subset enforcement, semantic checks
    tests/
```

### 1.1 Lexer

Pine is whitespace-significant inside function bodies and `if`/`for` blocks, but
brackets suspend it and `\` continues a line.

- [ ] Emit `INDENT`/`DEDENT` from a column stack, the way Python's tokenizer does.
- [ ] Track bracket depth; inside `(`/`[`/`{`, newlines are not statement
      terminators and indentation is not significant.
- [ ] Handle `\` line continuation.
- [ ] Comments: `//` to end of line. There are no block comments in Pine.
- [ ] Literals: int, float, string (single and double quote), `true`/`false`,
      colour literals `#RRGGBB` and `#RRGGBBAA`.
- [ ] **Every token carries `(line, col, end_line, end_col)`.** Error messages
      that point at a character are the difference between a usable editor and
      a frustrating one, and the annotations in Phase 4/8 need spans to link a
      chart marker back to the line that drew it.

**Done when:** the lexer round-trips a corpus of ~20 strategies without
crashing, and every rejection names a line and column. The corpus is authored
in this repo under `backend/tests/fixtures/pine/`, not vendored from
TradingView — see [`bot-plan.md`](bot-plan.md) §1.3.

### 1.2 Parser and AST

- [ ] Full v5 precedence, lowest to highest: `?:` → `or` → `and` → `==` `!=` →
      `<` `>` `<=` `>=` → `+` `-` → `*` `/` `%` → unary `+` `-` `not` →
      history `[]` → call/member access.
- [ ] Right-associative `?:`. `a ? b : c ? d : e` parses as `a ? b : (c ? d : e)`.
- [ ] `=` declaration vs `:=` reassignment are different nodes. Conflating them
      is a real bug source: `x = 1` inside an `if` creates a *new local*, while
      `x := 1` mutates the outer one.
- [ ] `var` and `varip` qualifiers on declarations.
- [ ] Tuple declarations: `[macdLine, signalLine, hist] = ta.macd(...)`.
- [ ] Named arguments in calls, mixed with positional.
- [ ] `if` / `else if` / `else` as **expressions** as well as statements — Pine
      allows `x = if cond \n 1 \n else \n 2`.
- [ ] `for i = 0 to 10 by 2`, `for ... in`, `while`, `break`, `continue`.
- [ ] User-defined functions: `f(a, b) => a + b`, and multi-line bodies.
- [ ] **Every AST node gets a stable, unique `call_id`.** This is the load-bearing
      decision of the whole design and §2.2 explains why. Derive it from the
      source span so it survives a re-parse of unchanged source, and changes when
      the line changes — which is exactly the behaviour you want when someone
      edits a running strategy.

### 1.3 The v1 subset (Q24)

**Accepted:**

| Area | In v1 |
|---|---|
| Declaration | `//@version=5`, `strategy(title, overlay, ...)` |
| Variables | `=`, `:=`, `var`, `varip`, tuples |
| Control flow | `if`/`else if`/`else`, `for`, `for...in`, `while`, `break`, `continue`, `switch` |
| Functions | user-defined, single- and multi-line; parameters may carry a default (`f(a, b = 3) =>`) |
| Types | `type Name` with typed fields and per-field defaults; `Name.new(...)`, `Name.copy(...)`, `obj.field` read, `obj.field := v` write; `var` persists one object and its fields; assigned **by reference** |
| Methods | `method f(T this, ...) =>` on any built-in or user type; called `obj.f(...)`; dispatched and overloaded by receiver type |
| Enums | `enum Name` with named members and optional `= "title"`; `Name.member`, equality by identity, usable as a `switch` subject |
| Built-in series | `open` `high` `low` `close` `volume` `hl2` `hlc3` `ohlc4` `hlcc4` `time` `bar_index` |
| `ta.*` | `sma ema rma wma vwma hma stdev variance rsi atr tr macd bb bbw stoch cci mom roc crossover crossunder cross change highest lowest highestbars lowestbars barssince valuewhen cum sum percentile_linear_interpolation linreg rising falling pivothigh pivotlow` |
| `math.*` | `abs max min pow sqrt log log10 exp round floor ceil sign avg sum random` |
| `str.*` | `tostring tonumber format length contains` |
| Nulls | `na`, `nz`, `na()`, `fixnan` |
| Inputs | `input.int float bool string source timeframe` — become bot parameters |
| Orders | `strategy.entry`, `strategy.close`, `strategy.close_all`, `strategy.exit` (percent only, Q21) |
| Strategy state | `strategy.position_size`, `.position_avg_price`, `.opentrades`, `.equity`, `.netprofit` |
| Bar state | `barstate.isfirst`, `.islast`, `.isconfirmed`, `.isnew`, `.ishistory`, `.isrealtime` |
| Visual | `plot`, `plotshape`, `plotchar`, `hline`, `fill`, `bgcolor`, `alert`, `alertcondition` — recorded, never executed |
| Session/time | `timestamp`, `time`, `dayofweek`, `hour`, `minute`, `year`, `month`, `dayofmonth` |

**Rejected in v1, by name, at validation:**

| Construct | Why | Error message must say |
|---|---|---|
| `request.security()` | multi-timeframe is its own project, and its lookahead semantics are the #1 backtest/live divergence | "multi-timeframe is not supported yet" |
| `array.*`, `matrix.*`, `map.*` | collection types need a whole runtime value model | "collections are not supported yet" |
| `line.*`, `label.*`, `box.*`, `table.*`, `polyline.*` | drawing objects, no execution effect, large surface | "drawing objects are not supported" |
| `strategy.order`, `strategy.cancel`, `strategy.cancel_all` | raw order primitives do not map to §5 sizing | "use strategy.entry / strategy.close" |
| `pyramiding > 0` | contradicts one-open-trade-per-account and 99% margin | "pyramiding is not supported — the platform commits 99% on the first entry" |
| `calc_on_every_tick=true` | Q23 | "this platform evaluates on bar close only" |
| `calc_on_order_fills`, `process_orders_on_close` | fill-model semantics that do not exist here | name the parameter |
| `import` / libraries | resolution, versioning, trust | "libraries are not supported" |
| `obj.field[n]` (object-field history) | per-field history needs a series per field; same call as `(a+b)[n]` | "assign this to a variable first" |
| `varip` **used in live mode** | its whole point is surviving intrabar recalculation, which Q23 removed | warn, treat as `var` |
| `strategy.risk.*` | overlaps the bot risk gate (Q25) confusingly | "configure risk limits on the bot, not in the script" |

### 1.4 Validation pass

Beyond the subset, catch what the runtime cannot:

- [ ] `//@version=5` present. v4 and v6 rejected explicitly by version number.
- [ ] Exactly one `strategy()` call, first statement. An `indicator()` script is
      rejected with "this is an indicator, not a strategy" — a friendly and
      common mistake.
- [ ] Undefined names, at parse time, with a "did you mean" on close matches.
- [ ] Order calls inside `for`/`while` bodies → rejected. A loop that fires N
      entries per bar is the classic runaway, and Q20 means every one of them is
      99% of the account.
- [ ] Unbounded `while` → rejected. Bounded `while` gets an iteration cap
      (`BOT_MAX_LOOP_ITERATIONS`, default 10,000) enforced at runtime too.
- [ ] Recursion in user functions → rejected.
- [ ] Every `input.*` reachable, with a default, and a stable name for the
      parameter UI in Phase 8.
- [ ] Script size cap and complexity cap (node count, `ta.*` call-site count) so
      one pathological script cannot starve the event loop.

**Phase 1 done when:** twenty real strategies parse; every rejection names the
construct, the line, and the column; `pytest backend/tests/test_pine_*.py` is
green (**not** `apps/pine/tests` — `testpaths` would never collect it; see
[`bot-plan.md`](bot-plan.md) §1.2);
there is a `manage.py pine_check <file>` command that prints the AST or the
error.

---

## Phase 2 — The Pine runtime

**Goal:** given an AST and a stream of bars, produce, for each bar, a
`StrategyIntent` and a set of plot values. Still no I/O — the runtime is fed
bars and returns results, so it is identical in backtest and live.

**New modules:** `apps/pine/runtime.py`, `apps/pine/series.py`, `apps/pine/ta.py`,
`apps/pine/builtins.py`, `apps/pine/intent.py`

### 2.1 The series model

Every Pine expression is a *series*: a value per bar, with `[n]` reaching back.

- [ ] `Series` is a bounded ring buffer, not a growing list. Cap at
      `BOT_SERIES_DEPTH` (default 5,000 bars). A bot running for a year on 1m
      bars must not grow without bound.
- [ ] `na` is a first-class value, not `None` and not `NaN`-by-accident.
      Arithmetic on `na` yields `na`; comparison with `na` yields `false`.
      Getting this wrong produces indicators that are silently correct for 200
      bars and then wrong once, which is the worst failure mode available.
- [ ] **`Decimal` for anything that touches price, quantity, or money**, per the
      project-wide invariant. `float` is acceptable inside an indicator's
      internal accumulator where the alternative is unusably slow — but the
      value that crosses into `StrategyIntent` is `Decimal`, converted once, at
      a named boundary, with a comment saying so.

### 2.2 Per-call-site state — the load-bearing idea

`ta.ema(close, 20)` is stateful. Two calls to `ta.ema` on different lines are two
different EMAs; the *same* call on line 12 evaluated on bar 500 and bar 501 is
one EMA advancing.

- [ ] Every stateful builtin is an object keyed by the AST node's `call_id`,
      stored in a per-run dict.
- [ ] Indicators are **incremental**: `ema.update(value) -> value`, O(1) per bar.
      Never recompute a window from scratch per bar; that turns a 100k-bar
      backtest from seconds into an afternoon.
- [ ] A call site inside a user function called twice per bar is **two logical
      call sites**. Key on `(call_id, call_stack_path)`, not `call_id` alone.
      This one bites late and hard.
- [ ] A call site inside an `if` that does not execute on some bars must still
      **advance** — Pine evaluates every `ta.*` call every bar regardless of
      branch, and a strategy whose EMA only updates on days it is used is a
      different strategy. Walk the AST once at load and register every stateful
      call site; tick them all each bar, then evaluate the expression tree.

### 2.3 The `ta` library

Implement each as a small stateful class with `update(x) -> value`, in
`apps/pine/ta.py`. The full v1 list is in §1.3.

- [ ] Warm-up semantics exactly matching TradingView: `ta.sma(close, 20)` is `na`
      for the first 19 bars, and `ta.rma`-based indicators (`rsi`, `atr`) use
      TradingView's specific seeding — a simple average for the first period,
      then the recursive form. Get this wrong and your RSI is off by a few
      tenths forever, which is enough to flip a `crossover`.
- [ ] Each indicator gets a **golden test** against values exported from
      TradingView for a fixed BTCUSDT 1h window, to 8 decimal places. Put the
      fixture in `backend/tests/fixtures/pine/golden/`. This is the only way to
      know you are right, and it will find bugs. **Where those reference values
      come from is Q29, still open** — it blocks the fixture, not the
      implementation.

### 2.4 The execution model

- [ ] One `run_bar(bar)` call per confirmed bar: set built-in series, tick every
      stateful call site, walk the statement list, collect orders and plots.
- [ ] `barstate.*` computed from the feed's position, not guessed.
- [ ] **Snapshot/restore hooks now, even though Q23 says confirmed-only.** Give
      the runtime `snapshot()` and `restore(snap)`. Backtest does not need it;
      crash recovery in Phase 6 does; intrabar in v2 needs it. Building it in
      later means touching every stateful object.
- [ ] Deterministic: same bars in, same intents out, every time. No wall-clock
      reads, no RNG unless `math.random` is called (and then from a seeded
      generator recorded in the run). Pin this with a test that runs the same
      10k bars twice and compares hashes.
- [ ] A runtime error (division by zero, `BOT_MAX_LOOP_ITERATIONS` exceeded, cap
      breached) raises `PineRuntimeError` carrying the source span, and the bot
      auto-stops per Q25.
- [ ] Per-bar wall-clock budget (`BOT_BAR_BUDGET_MS`, default 250). The runtime
      shares the event loop with the fan-out; a script that spends two seconds
      per bar is a latency incident. Over budget → stop the bot, name the script.

### 2.5 The output contract

```python
@dataclass(frozen=True, slots=True)
class StrategyIntent:
    """What the strategy wants to be true after this bar. Declarative."""
    bar_time: int                    # UNIX seconds, bar OPEN time
    symbol: str
    desired_side: Side | None        # None == flat
    sl_pct: Decimal | None           # from strategy.exit, else None → bot config
    tp_pct: Decimal | None
    reason: str                      # "entry: L" / "close: exit long" — for the log
    source_span: Span                # which line asked, for the chart annotation
    plots: dict[str, Decimal | None] # plot()/plotshape() values, for annotations
    alerts: list[str]
```

Note what is **not** here: quantity, leverage, account, price. Q20 and Q21 put
those on the platform side. The intent says "be long" or "be flat" and nothing
about how much.

**Phase 2 done when:** golden tests pass for every indicator; a determinism test
passes; a 100k-bar run completes in under ~10 seconds; a script that divides by
zero produces an error naming the line.

---

## Phase 3 — The bar feed

**Goal:** a reliable stream of *confirmed* bars, with warm-up history, that never
silently skips one.

Most of this exists. `apps/exchanges/public_sources.py` fetches candles,
`public_stream.py` streams them, `catalogue.ensure_history` downloads and stores
history, `marketdata.get_candles` merges stored and live. Phase 3 is a thin,
strict layer on top — not a new data stack.

**New module:** `apps/pine/feed.py`

### 3.1 `BarFeed`

- [ ] `async for bar in BarFeed(symbol, interval, market)` yields **only closed
      bars**, exactly once each, in order.
- [ ] Bar identity is its **open time in UNIX seconds**, matching what
      `public_sources` already returns. Write down, in the docstring, that a bar
      is confirmed when `now >= open_time + interval` **plus**
      `BOT_BAR_CONFIRM_LAG_MS` (default 2,000). Exchanges emit the closing update
      slightly late, and reading a bar the instant the clock rolls over gets you
      a bar that is still moving.
- [ ] Prefer the WebSocket stream; fall back to polling exactly as the chart
      already does. The bot must know which one it is on and say so.

### 3.2 Warm-up

- [ ] Before the first live bar, load `max(indicator lookback) × 3`, minimum 300
      bars, from `marketdata.get_candles` / stored history.
- [ ] Replay them through the runtime with `barstate.ishistory = true`, and
      **discard every intent produced**. Warm-up converges indicators; it does
      not trade.
- [ ] If history is short (new listing), the bot **refuses to start** and says
      how many bars it has versus how many it needs. It does not start with an
      unconverged EMA.
- [ ] Log the warm-up: bars loaded, source, first and last timestamp, and the
      converged value of each top-level indicator. When live and backtest
      disagree later, this is the first thing you will want.

### 3.3 Gaps, reconnects, and the clock

This is where live diverges from backtest, so it gets the strictness.

- [ ] After a reconnect, **re-fetch the window** since the last bar the bot saw
      and replay any missing closed bars in order before resuming the stream.
- [ ] A gap that cannot be repaired (exchange has no data for that window) →
      **stop the bot** (Q25). Do not skip and carry on: the strategy's state
      machine now disagrees with the market.
- [ ] Never synthesise, hold, or interpolate a bar. `public_stream.py` already
      makes this promise for the chart; the bot inherits it.
- [ ] Check clock skew against the exchange at bot start and hourly. The adapters
      already sync (`_sync_clock`). More than `BOT_MAX_CLOCK_SKEW_MS` (default
      5,000) → refuse to start. A bot whose clock is a minute fast confirms bars
      that have not closed.
- [ ] Everything in UTC internally; the panel does the local-time rendering.

**Phase 3 done when:** a 48-hour soak on 1m BTCUSDT yields exactly 2,880 bars,
each once, in order, with every reconnect repaired and logged — and a deliberate
kill of the socket mid-run recovers without a gap.

---

## Phase 4 — Backtest

**Goal:** run a strategy over stored history and produce a report. Two purposes,
and the second is the important one:

1. The admin needs to see whether a strategy is worth running.
2. **It is the correctness harness for Phases 1–3.** Live mode and backtest mode
   feed the same runtime; if they ever produce different intents on the same
   bars, something is broken. Backtest is how you find out cheaply.

**New modules:** `apps/pine/backtest.py`, `apps/pine/report.py`

- [ ] Pull bars from stored history via `catalogue`/`marketdata`; kick off
      `ensure_history` and report progress when the window is not downloaded.
- [ ] Fill model, stated explicitly in the report because it determines whether
      the numbers mean anything:
      - entry at the **next bar's open**, never the signal bar's close
      - configurable slippage in basis points, default 5
      - taker fee per side, default 5 bps, per-exchange override
      - SL and TP checked against the following bars' high/low; **when both are
        touched in one bar, assume the stop** — the pessimistic assumption is
        the only honest one without tick data, and say so in the report
- [ ] Metrics: net PnL, return %, max drawdown, Sharpe, win rate, profit factor,
      average win/loss, expectancy, trade count, longest flat period, time in
      market, average bars held, worst trade, consecutive losses.
- [ ] Equity curve and per-trade table, both exportable.
- [ ] **Annotations**: every marker carries the `source_span` of the line that
      produced it, so the chart in Phase 8 can highlight the code that fired.
      This is what the `call_id`/span plumbing in Phase 1 was for.
- [ ] `manage.py pine_backtest <file> --symbol --interval --from --to` printing a
      summary — usable long before the UI exists.
- [ ] **Determinism test:** run N bars through `backtest.py` and through the
      Phase 6 live loop fed the same bars from a fixture; assert the intent
      sequences are byte-identical. Keep this test green forever. It is the whole
      argument that a backtest predicts anything.

**Report must state its own limits.** Print, at the top of every report: the fill
assumptions, the fee assumption, "SL assumed on ambiguous bars", the bar count,
the date range, and that a backtest is a description of the past. Not a
disclaimer for its own sake — a reader who does not know the fill model cannot
interpret the Sharpe.

---

## Phase 5 — Intent → action

**Goal:** turn a declarative intent into the imperative calls that already exist,
and refuse the ones that should not happen.

**New modules:** `apps/pine/translate.py`, `apps/pine/riskgate.py`

### 5.1 The translator

Pine says "I should be long." The platform's API says `route_open(...)`. The
translator diffs desired state against actual state and emits the difference.

| Desired | Actual (from `Trade`, verified against exchange) | Action |
|---|---|---|
| flat | flat | nothing |
| long | flat | `route_open(side=long, ...)` |
| flat | long | `route_close(trade)` |
| long | long, same SL/TP | nothing |
| long | long, different SL/TP | `route_amend(trade, sl_pct, tp_pct)` |
| long | **short** | `route_close(trade)` → confirm flat → `route_open(long)` |
| long | long on *some* accounts | leave it; the sat-out accounts join the next trade (spec §6) |

Non-obvious parts:

- [ ] **A reversal is two actions, sequenced, never concurrent.** Close, wait for
      the close to confirm flat, then open. Firing both at once on an exchange
      that nets positions gives you a doubled or a cancelled order depending on
      arrival order.
- [ ] **Actual state comes from the exchange, not the database.** `CLAUDE.md` is
      explicit: the exchange decides what is open. Use
      `services.reconcile_open_trade` / `possync.sync_positions` before diffing.
- [ ] **A leg that failed is not proof nothing happened.** Reuse
      `NEVER_SENT_CODES` — the bot must treat an unconfirmed leg as possibly
      holding a position, exactly as the manual path does, or it will "re-enter"
      into an account that is already in.
- [ ] **Idempotency.** Key every action on `(bot_run_id, bar_time, action_type)`
      and persist it *before* dispatch. On restart, an action already recorded is
      never re-sent. Without this, a restart during a fan-out double-enters.
- [ ] One intent per bar produces at most one entry. Enforce it in the
      translator, not just by convention.

### 5.2 The bot risk gate

Sits between the translator and `services.*`. Every action passes through; any
refusal stops the bot and notifies (Q25).

- [ ] All Q25 conditions.
- [ ] Trading window: optional per-bot allowed hours/days, UTC.
- [ ] Max notional per bot across all accounts.
- [ ] Sanity check on price: the intent's bar close versus the current ticker.
      More than `BOT_MAX_PRICE_DRIFT_PCT` (default 2%) apart → refuse and stop.
      This catches a stale feed and a fat-fingered symbol mapping.
- [ ] `killswitch.is_on()` → the bot does not route, and pauses rather than
      erroring. Reuse the existing switch; do not add a second read path.
- [ ] **Dry-run flag** on every bot: evaluates, logs the action it *would* take,
      routes nothing. This is Phase 7's shadow mode and it costs one `if`.

---

## Phase 6 — The supervisor, persistence, and recovery

**Goal:** bots that run, survive restarts, and can be stopped.

### 6.1 Data model — `apps/bots/models.py`

```
Strategy            name, description, created_at, created_by
StrategyVersion     strategy FK, version, source, parsed_ok, validation_errors,
                    inputs_schema, created_at
                    → immutable. Editing makes a new version.
Bot                 strategy_version FK, symbol, interval, market, leverage,
                    sl_pct, tp_pct, input_values (JSON), state
                    (draft|paper|live|stopped), dry_run, risk config (JSON),
                    created_at, created_by
BotRun              bot FK, started_at, stopped_at, stop_reason, warmup_bars,
                    feed_source, peak_equity
BotBar              run FK, bar_time, ohlcv, plots (JSON), intent (JSON)
                    → retention per Q26
BotAction           run FK, bar_time, action_type, idempotency_key (unique),
                    dispatched_at, trade FK (nullable), result (JSON)
                    → forever. This is the audit trail.
```

- [ ] `Trade` gets a nullable `bot_run` FK, so history (§8) can say which trades
      a bot made and the manual path is unchanged when it is null.
- [ ] `BotAction.idempotency_key` is `UNIQUE`. The database enforces §5.1's
      idempotency; application logic alone will not survive a race.

### 6.2 The supervisor

- [ ] One `asyncio` task per running bot, in the same process as the fan-out
      engine — the bot's actions go through `services.route_*`, which is async.
- [ ] The loop: await next confirmed bar → `run_bar` → intent → reconcile actual
      state → translate → risk gate → dispatch → persist → broadcast.
- [ ] **Isolation between bots is the same promise as isolation between
      accounts.** One bot's exception, one bot's slow script, one bot's stopped
      feed must not touch another. Per-task supervision, exceptions caught at the
      task boundary, never `gather` without `return_exceptions=True`.
- [ ] Bots start on process start from `Bot.state`, and their first act is
      warm-up and reconciliation, not trading.
- [ ] Bot lifecycle is a **state machine** with explicit transitions:
      `draft → paper → live`, any state `→ stopped`, `stopped → paper` only.
      `stopped → live` directly is not a transition. Write it as a real state
      machine with a test per illegal transition.

### 6.3 Restart and recovery

The hard part. On process start, for every bot in `paper` or `live`:

- [ ] Re-warm the runtime from history. **Do not** attempt to serialise and
      restore indicator state across a deploy — a code change silently
      invalidates it. Re-warming from bars is slower and always correct.
- [ ] Read actual position state from the exchange, per account.
- [ ] Read `BotAction` for the current bar. If an action is recorded as
      dispatched but its result is unknown, **reconcile it** through the existing
      `confirm_open` path before doing anything else.
- [ ] If reconciled state disagrees with what the strategy expects, do **not**
      correct it automatically on the first pass. Retry once; if it still
      disagrees, stop the bot and notify (Q25). Auto-correcting a disagreement
      you do not understand is how a recovery turns into a liquidation.
- [ ] Log the whole recovery as one structured entry: bars re-warmed, positions
      found, actions reconciled, decision taken.

### 6.4 Wiring into what exists

- [ ] **Stop-all stops every bot.** In `killswitch.set_stop_all(True)` and in the
      panel's flatten path. Test: `test_stop_all_stops_every_running_bot`, and
      `test_a_stopped_bot_does_not_re_enter_after_a_flatten`.
- [ ] New log categories `BOT` and `STRATEGY` in `apps.logging` — and add them to
      the facets endpoint, since `test_facets_serve_every_level_and_category_the_backend_writes`
      already exists to catch exactly that omission.
- [ ] New WebSocket events on the existing `"trading"` group: `bot.bar`,
      `bot.intent`, `bot.action`, `bot.state`, `bot.stopped`. Same staff-only,
      same-origin gate. Same hidden-account filtering on any per-account payload.
- [ ] New endpoints under `/api/bots/`: CRUD, `validate`, `backtest`, `start`,
      `stop`, `runs`, `bars`. Async views like `order_views.py` where they route;
      DRF where they only read.
- [ ] New settings under `settings.BOT`, mirroring `settings.TRADING`'s shape,
      surfaced on a `/api/bots/policy/` endpoint the way `trading/policy/` does.

---

## Phase 7 — Paper and shadow, then the soak

Spec §9 requires a demo mode. For bots it is not a nicety — it is the only
evidence that any of this works.

- [ ] **Shadow mode:** a bot with `dry_run=true` attached to the *live* feed,
      routing nothing, logging every action it would have taken. Run alongside
      the admin's manual trading. Costs nothing, catches everything.
- [ ] **Paper mode:** the same bot routed to paper accounts through the existing
      `paper.py` adapter and `./run.sh demo`.
- [ ] **Divergence tracking:** for the same period, compare shadow-mode actions
      to what a backtest over those same bars produces. They should be
      identical. Any difference is a bug in Phase 3 or Phase 6, and finding it
      here costs nothing.

**The gate — do not shorten it:**

| Requirement | Threshold |
|---|---|
| Continuous paper/shadow runtime | **14 days**, minimum |
| Unexplained backtest/live divergences | 0 |
| Process restarts survived cleanly | ≥ 3, at least one unplanned |
| Feed gaps handled (repaired or clean stop) | 100% |
| Reconciliation drift events | 0 unexplained |
| Kill-switch drills passed | ≥ 2 |
| Every Q25 auto-stop | fired at least once, deliberately, in a drill |

Fourteen days is not arbitrary: it is long enough to cross a weekend, a funding
cycle, an exchange maintenance window, and at least one bad-liquidity hour.

---

## Phase 8 — The panel

Standard house rules: Nuxt 3, Pinia, Tailwind, every string through `useI18n()`,
English complete first and Persian second, RTL-capable from the start,
`reference/skills/frontend-design.SKILL.md` for the visual work.

- [ ] **Strategies list** — versions, validation status, which bots use them.
- [ ] **Editor** — CodeMirror 6 with a Pine mode; errors inline from the
      `validate` endpoint with the line/column Phase 1 produces; the ignored-and-
      unsupported warnings (Q20, Q24) shown clearly, never hidden.
- [ ] **Backtest view** — equity curve, trade table, metrics, and the chart with
      annotations. Clicking a marker highlights the source line. Clicking a line
      highlights its markers. This is the payoff for carrying spans through four
      phases.
- [ ] **Bot list** — state, symbol, timeframe, live PnL, next bar countdown,
      last signal, feed source, per-bot stop button.
- [ ] **Bot detail** — the live chart with the strategy's own plots drawn on it,
      the signal log, the action log with the resulting fan-out legs, the risk-
      gate state, and the reason it stopped if it stopped.
- [ ] **Promotion flow** — `draft → paper` is one click; `paper → live` shows the
      Phase 7 gate as an actual checklist with the system's own measurements
      filled in, and refuses while any row is unmet. Not a confirmation dialog —
      a gate that knows the numbers.
- [ ] Reuse the existing chart adapter (`useChartAdapter.ts`) rather than adding a
      second charting path.
- [ ] Every new read surface filters hidden accounts, with its own case in
      `tests/test_account_access.py` (Q27).

---

## Phase 9 — Observability and ops

- [ ] Structured `system_log()` entries under `BOT`/`STRATEGY` for: bot started,
      warm-up complete, bar evaluated (debug), intent produced, action dispatched,
      action result, risk gate refusal, feed gap, reconnect, bot stopped and why.
- [ ] Metrics worth a number: bars evaluated, evaluation ms p50/p99, feed lag,
      actions dispatched, fan-out ms per bot action, refusals by reason, auto-stops
      by trigger, live-vs-backtest divergence count.
- [ ] Alerts, out-of-band (Telegram or email — not only the panel, because the
      panel is not open at 03:00): bot auto-stopped, feed gap unrepaired,
      reconciliation drift, risk-gate refusal, any bot exception.
- [ ] `docs/bots.md`: how to write a strategy for this platform, the subset, the
      promotion path, and a runbook — what to do when a bot stops, when the feed
      gaps, when the exchange and the database disagree, and how to flatten
      everything fast.
- [ ] `docs/spec/conformance.md` gains a bot-mode section, clause by clause, with
      the test that proves each row. Same standard as the rest of the table.

---

## Phase 10 — The go-live gate

Before any bot routes to a real account:

- [ ] Phase 7 gate fully met, with its measurements recorded.
- [ ] The strategy has a backtest over ≥ 2 years or ≥ 500 trades, whichever is
      more, and the admin has read the report's stated fill assumptions.
- [ ] `docs/adapters.md` blocker cleared for the exchanges involved — **no
      adapter has been run against a live exchange yet**, and a bot is a bad
      first thing to discover that with.
- [ ] Canary: one account, smallest balance, for one week, before the fan-out
      goes wide. `BOT_MAX_ACCOUNTS` capped to 1 to enforce it.
- [ ] Q25 limits reviewed and set deliberately for this strategy, not left at
      defaults.
- [ ] The runbook has been walked by whoever is on call, including the flatten
      drill, on the real deployment.
- [ ] Confirm the existing legal sign-off (`docs/decisions.md`, 2026-08-23)
      covers **automated** trading. It was given for this platform; automating
      discretionary trading of other people's capital is a different activity
      from mirroring a human's trades, so it is one question to the same lawyer,
      not a fresh review.

---

## The traps

Collected in one place, because each of these has sunk someone else's build.

1. **Repainting.** Any decision made on an unconfirmed bar can reverse before the
   bar closes. Q23 removes this in v1; if intrabar comes back in v2, it comes
   back with snapshot/restore and a divergence test, or not at all.
2. **Look-ahead.** A backtest that fills at the signal bar's close has seen the
   future. Next bar's open, always.
3. **The 99% contention.** Two bots, or a bot and the admin, both wanting the
   same account. Q22 decides it; the translator enforces it; a test pins it.
4. **Quantization.** Pine thinks in fractional units; exchanges have `qty_step`
   and `min_notional`. `sizing.py` already floors correctly — the bot must not
   round anywhere itself.
5. **The unconfirmed leg.** A failed leg may hold a position.
   `NEVER_SENT_CODES` exists for this and the bot must respect the same
   asymmetry, or it will re-enter into an account that is already in.
6. **Restart mid-fan-out.** Solved only by the unique `idempotency_key`, written
   before dispatch.
7. **`na` propagation.** An indicator that returns `na` compared with `>` returns
   `false`, not an error. A warm-up bug therefore looks like a strategy that
   simply does not trade for a while — silent, and easy to ship.
8. **`ta.rma` seeding.** TradingView's RSI and ATR use a specific first-period
   seed. An off-by-a-fraction indicator flips crossovers at the margin, and the
   margin is where all the trades are.
9. **Call sites inside conditionals.** Stateful builtins must advance every bar
   regardless of branch. §2.2.
10. **Clock skew.** A fast clock confirms bars that have not closed. Check at
    start and hourly.
11. **Timezone.** Pine's session and `dayofweek` functions are exchange-timezone
    aware. UTC internally, convert only at the edges, and state the assumption
    in the report.
12. **Silent unsupported constructs.** A script that loads but ignores a line is
    a script that lies. Reject by name.
13. **The event loop.** The runtime shares a process with a fan-out that has a
    per-leg deadline. A slow script is a latency incident for every account.
    `BOT_BAR_BUDGET_MS`.
14. **Over-fitting.** Not an engineering problem, but the one most likely to lose
    the money. A strategy tuned until the backtest looks good is a strategy tuned
    to the past. Walk-forward validation and out-of-sample periods belong in the
    report; the tool should make honest evaluation the easy path.

---

## Suggested build order

The dependency graph allows some parallelism, but the critical path is
`0 → 1 → 2 → 4`, because Phase 4 is what proves Phases 1–2 are right, and
everything after that is plumbing you should not build on an unproven runtime.

```
Q20–Q27 ✅ ─┬──────────────────────────────────────────────────────────┐
           │                                                          │
     Phase 1 (front end) ──→ Phase 2 (runtime) ──→ Phase 4 (backtest) │
           │                                             │            │
     Phase 3 (feed) ─────────────────────────────────────┤            │
                                                         ▼            │
                                Phase 5 (translate) ──→ Phase 6 (supervisor)
                                                         │            │
                                                    Phase 7 (paper, 2wk soak)
                                                         │            │
                                Phase 8 (UI) ────────────┤◄───────────┘
                                Phase 9 (ops) ───────────┤
                                                         ▼
                                                   Phase 10 (go live)
```

Phases 8 and 9 can run alongside 6 and 7 if there is a second pair of hands.
Phase 10 waits for all of them.

**First actual task:** `backend/apps/pine/tokens.py`. Q20–Q27 are answered, so
nothing on the path to it needs a decision that has not been taken. Work from
[`bot-plan.md`](bot-plan.md), which names every file and the test that proves
it; read its §1 first.
