# Bot mode

A bot is a **signal source, not a second execution path.** A Pine Script v5
strategy decides "I should be long"; everything after that — sizing (§5), the
fan-out and its per-leg deadline (§4), account isolation, the
`NEVER_SENT_CODES` reconciliation, the §7 halt, per-account history — is the
same code the admin's manual button already goes through. If a change to
`apps/bots/` ever adds a second order path it is wrong regardless of what it
does.

The decisions behind every rule here are Q20–Q27 in `docs/decisions.md`, plus
Q30 in `questions.md`. They are cited by number throughout, and the argument for
each is settled.

- `docs/bot-mode.md` — the eleven-phase plan and why each phase exists.
- `docs/bot-plan.md` — the execution plan under it: file manifest, settings, the
  test per item.
- This file — how to use what was built.

---

## 1. The subset

The engine implements a **deliberate subset** of Pine v5 (Q24). Anything outside
it is refused **by name, line and column** at upload time. Nothing is parsed and
quietly ignored — a script that loads and does not do what it says is worse than
a script that will not load.

`apps/pine/subset.py` is the whole registry, as data. What follows is a summary;
that file is the authority, and `/api/bots/validate/` will tell you about any
specific script.

### Accepted

| | |
|---|---|
| **Series** | `open` `high` `low` `close` `volume` `hl2` `hlc3` `ohlc4` `hlcc4` `time` `bar_index`, and `[n]` on any of them |
| **`ta.`** | `sma` `ema` `rma` `wma` `vwma` `hma` `stdev` `variance` `rsi` `atr` `tr` `macd` `bb` `bbw` `stoch` `cci` `mom` `roc` `crossover` `crossunder` `cross` `change` `highest` `lowest` `highestbars` `lowestbars` `barssince` `valuewhen` `cum` `sum` `percentile_linear_interpolation` `linreg` `rising` `falling` `pivothigh` `pivotlow` |
| **`math.`** | `abs` `max` `min` `pow` `sqrt` `log` `log10` `exp` `round` `floor` `ceil` `sign` `avg` `sum` `random`, `pi`, `e` |
| **`str.`** | `tostring` `tonumber` `format` `length` `contains` |
| **`input.`** | `int` `float` `bool` `string` `source` `timeframe` |
| **`strategy.`** | `entry` `close` `close_all` `exit`, and the read-only `position_size` `position_avg_price` `opentrades` `equity` `netprofit` `long` `short` |
| **`barstate.`** | `isfirst` `islast` `isconfirmed` `isnew` `ishistory` `isrealtime` |
| **Bare** | `nz` `na` `fixnan` `timestamp` `dayofweek` `hour` `minute` `second` `year` `month` `dayofmonth` `max` `min` `abs` |
| **Recorded, never executed** | `plot` `plotshape` `plotchar` `hline` `fill` `bgcolor` `alert` `alertcondition` |
| **Language** | `=` and `:=`, `var` / `varip`, type annotations, tuple declarations, `if` / `else if` / `else` (statement **and** expression), `switch`, `for` / `for…in` / `while` with `break` and `continue`, user functions (with default parameters), `+= -= *= /= %=`, named arguments, multi-line calls, `\` continuation |
| **User types** | `type Name` with typed fields and defaults; `Name.new(...)` / `Name.copy(...)`; `obj.field` and `obj.field := v`; `var` persists an object; objects are held **by reference** |
| **Methods** | `method f(T self, ...) =>` on any type, called `obj.f(...)`, overloaded by receiver type |
| **Enums** | `enum Name` with members and optional `= "title"`; `Name.member`; usable as a `switch` subject |

### Rejected, each with its own message

`request.security` and multi-timeframe · `array` `matrix` `map` · `line` `label`
`box` `table` `polyline` · `strategy.risk.*` · `strategy.order` `strategy.cancel`
`strategy.cancel_all` · `pyramiding` · `calc_on_every_tick` ·
`calc_on_order_fills` · `process_orders_on_close` ·
`import` `export` · `strategy.exit`'s `loss` `profit` `stop` `limit`
`trail_points` `trail_offset` `trail_price`.

Plus the semantic checks: no `//@version=5`, an `indicator()` instead of a
`strategy()`, `strategy()` not first, an order inside a loop **or a method**, an
unbounded `while`, recursion (through functions *or* methods), `expr[n]` on
something that keeps no history (an object field included — assign it first), a
type declared on an unknown field type, a duplicate type or method, an unknown
field or enum member where the type is known, a script over the size or
complexity limits, and an unknown name (which suggests the nearest one it knows).

### Three things that are accepted *and reported*

They raise a warning at upload, shown next to the editor. None is ever silent.

1. **A size argument.** `qty`, `qty_percent`, `default_qty_value` and friends are
   parsed and ignored — the platform sizes every leg at 99% of that account's
   own balance (Q20, spec §5). `StrategyIntent` has no quantity field at all.
2. **`varip`.** Treated as `var`. Its whole purpose is surviving an intrabar
   recalculation and this platform evaluates on bar close only (Q23).
3. **A `ta.*` call the runtime cannot hoist** — one inside a user function or a
   loop. See §3 below.

---

## 2. Writing a strategy

```pine
//@version=5
strategy("Trend and pullback", overlay = true)

trendLen = input.int(200, "Trend length", minval = 20, maxval = 500)
riskPct  = input.float(1.5, "Stop %",     minval = 0.1, maxval = 20)

trend = ta.ema(close, trendLen)
r     = ta.rsi(close, 14)

if strategy.position_size == 0 and close > trend and r < 40
    strategy.entry("L", strategy.long)
    strategy.exit("L-x", "L", loss_pct = riskPct, profit_pct = riskPct * 2)

if strategy.position_size > 0 and close < trend
    strategy.close("L")
```

Four things differ from TradingView and all four are deliberate:

**`strategy.position_size` is a direction, not a quantity** — `1`, `-1` or `0`.
Q20 means no single quantity is true across every account, so the platform will
not invent one. `strategy.position_avg_price`, `equity`, `netprofit` and
`opentrades` are supplied by the driver from the *exchange's* answer, not from a
private simulation inside the script.

**Percent exits are spelled `loss_pct` / `profit_pct`** (Q30). Pine's `loss=` is
in ticks; accepting it as percent would silently retune every stop.

**Levels come from the bot unless the script overrides them** (Q21). Leverage and
SL/TP are bot-level settings; a percent `strategy.exit` wins for that trade.
Leverage a script cannot set at all.

**Every bar is a closed bar** (Q23). `barstate.isconfirmed` is always true,
`calc_on_every_tick=true` is a validation error rather than a setting, and a bar
is only read once `now >= open + interval + BOT_BAR_CONFIRM_LAG_MS`.

### Checking one without the panel

```bash
cd backend
python manage.py pine_check path/to/strategy.pine        # errors, or nothing
python manage.py pine_check path/to/strategy.pine --ast  # the parse tree
```

`pine_check` and `POST /api/bots/validate/` call the same function, so the
command and the panel cannot disagree about whether a script is fine.

---

## 3. What the runtime does that TradingView does not

**Every registered `ta.*` call site advances on every bar.** An indicator inside
an `if` that only runs on some days converges to a different series than the same
indicator outside it — TradingView warns about this and leaves the behaviour
undefined; the failure is silent and permanent. The runtime sweeps every site the
bar did not reach at end of bar and advances it, evaluating its arguments in the
global scope.

Sites inside a **user function or a loop** cannot be swept that way — their
arguments only exist inside their own scope. Those are warned about at upload
(`ta_not_hoisted`) and any that could not be advanced are reported on the run.
Never silent, in either direction.

**Per-call-site state is keyed on the call path**, so `f(close)` and `f(high)`
calling the same `ta.sma` inside `f` are two indicators with two converged
states — not one fed two interleaved series.

**`ta.rsi(close, 14)[1]` works.** Each site keeps its own output history.
`expr[n]` on anything that keeps no history — an arithmetic expression, a member,
a user function's result — is a validation error rather than a quiet `na`.

---

## 4. Backtesting

```bash
python manage.py pine_backtest path/to/strategy.pine \
    --symbol BTCUSDT --interval 1h --from 2025-01-01 --to 2025-06-01
```

The report prints its **assumptions above its metrics**, always, because a
backtest whose fill model is optimistic is worse than no backtest — it produces a
number people act on.

| Assumption | Default |
|---|---|
| Entry fills at | the **next** bar's open |
| Slippage | `BOT_BACKTEST_SLIPPAGE_BPS`, applied against the trade |
| Fee | `BOT_BACKTEST_FEE_BPS`, charged on **both** sides |
| A bar that touches both the stop and the target | assumed **stopped out** |
| Warm-up | `max(indicator lookback) × BOT_WARMUP_MULTIPLIER`, and a window with too little of it says so |

It also reports an **intent digest** — a SHA-256 over the decision sequence
(side, levels, bar time, symbol; not plots, not reason strings). That digest is
the whole claim that a backtest predicts anything: the live loop computes it the
same way from the same function, and a mismatch is a divergence rather than a
difference of opinion between two implementations.

---

## 5. The promotion path

```
draft ──▶ paper ──▶ live
  │         │         │
  └─────────┴─────────┴──▶ stopped ──▶ paper
```

`stopped → live` is **not an edge**, and the database enforces it. Every one of
Q25's triggers means something was wrong; the way back to real money runs through
paper, where the same conditions can be watched without capital behind them.

`GET /api/bots/bots/<id>/promotion/` returns the Phase 7 gate with this bot's own
measurements filled in — soak days, divergences, restarts survived, feed gaps,
price drift, halt drills, the Q25 drills, whether the risk limits were set
deliberately, and the adapter acknowledgement. `POST …/start/ {"state":"live"}`
returns **409 with the gate attached** while any row is unmet. It is not a
confirmation dialog; it is a gate that knows the numbers.

One row cannot be measured from inside and is carried as an explicit human
acknowledgement: **no exchange adapter has been run against a live exchange or a
testnet yet** (`docs/adapters.md`). A bot is a bad first thing to discover that
with.

---

## 6. When a bot stops itself

Seven triggers (Q25). **None of them auto-resumes** — a bot that stopped itself
is restarted by a person who has read why.

| Trigger | Limit |
|---|---|
| Consecutive losses | `BOT_MAX_CONSECUTIVE_LOSSES` |
| Drawdown from this bot's own peak | `BOT_MAX_DRAWDOWN_PCT` |
| Trades per hour | `BOT_MAX_TRADES_PER_HOUR` |
| No confirmed bar for N× the timeframe | `BOT_NO_BAR_TIMEOUT_MULTIPLE` |
| An unrepairable feed gap | **any** — not configurable |
| A runtime error in the script | **any** — not configurable |
| The exchange and the record still disagree after `BOT_RECONCILE_PASSES_BEFORE_STOP` passes | — |

The two that are not numbers are not numbers on purpose: a setting there would be
a setting for how much silent disagreement with the market is acceptable.

The **§7 halt is the exception that is not a stop** for the bot's own gate —
under it a bot pauses and resumes when the halt clears. But turning the halt on,
or pressing close-all, **stops every running bot** (Q22): a halt that flattens
positions while a bot is still evaluating is a halt that re-enters ninety seconds
later, which is not a halt. Clearing the halt does not restart them.

---

## 7. Contention with the admin, and with other bots

Q22, first claim wins:

- A bot **skips** an account that is already in a trade and reports it as **"sat
  out"** — never as a failure. One account being busy is not a reason to keep the
  other nine flat.
- A manual entry into an account a bot is holding is **refused, naming the bot**
  (409 `bot_holds_position`).
- The admin outranks a bot: close-all and Stop-all win, always.
- An account whose last entry is **unconfirmed** counts as possibly holding one.
  A failed leg is not proof that nothing happened.

**Only one bot runs at a time.** The panel's bots list shows several bots but
activates one: `POST /bots/bots/<id>/start/` stops every *other* `paper`/`live`
bot first (`StopReason.MANUAL`, naming the bot that took its slot) and only then
starts this one — after that bot's own transition and, for `live`, the
promotion gate have already passed, so a start that was going to be refused
anyway never takes down a bot that was working fine. The response's
`deactivated` field lists what it stopped, and its own `bot_state` broadcast
catches every open tab up immediately, not just the one that clicked. A restart
re-checks rather than trusting `Bot.state`: if more than one row is somehow
left `paper`/`live` — data from before this rule existed, or a crash mid-write
— `resume_all()` resumes only the most recently started one and stops the rest
outright, never resumes two at once.

**Which accounts a bot may reach is a per-account switch, off by default.**
`ConnectedAccount.bot_trading_enabled` (panel: the account row's "Bot trading"
toggle) gates every *new* bot entry the same way `manual_trading_enabled` gates
the admin's own ticket — see `eligible_accounts` in `apps/trading/services.py`.
The two are independent: an account can take the admin's own hand, a bot's,
both, or neither. Neither switch touches a trade the account already holds a
leg of — an amend or a close still resolves from the leg, so flipping either
mid-trade can never strand a live position. An account nobody opted in simply
does not appear in a bot's fan-out, and reads as **"sat out"** exactly like one
already holding a position (Q22) — never as a failure.

Hidden accounts (Q27) take part in every fan-out **identically** — nothing in
`apps/pine/` or `apps/bots/` may import `accounts.visibility` — and every bot
*read* surface filters them, the same as every manual one.

---

## 8. Runbook

### Starting the supervisor

By default it runs **inside the ASGI process**, alongside the fan-out it routes
through: a broker round trip plus worker prefetch spends most of the spec §4
per-leg budget before the first exchange call.

```bash
BOT_SUPERVISOR_IN_ASGI=false      # to separate it
docker compose --profile bots up -d
```

The loop is identical either way:

```
next confirmed bar → run_bar → intent → reconcile against the exchange
→ translate → risk gate → dispatch → persist → broadcast
```

Reconciling *before* the diff is the part that is easy to get wrong. The exchange
decides what is open, not this database.

### After a restart

A bot re-warms **from bars, never from a serialised snapshot** — a code change
silently invalidates a snapshot, and the bot would start with converged-looking
state belonging to a different implementation of the same indicator. Then it
reads every account's position from the exchange, then it settles any action
recorded as dispatched whose result is unknown, and only then does it evaluate a
bar. A disagreement is retried once and then stops the bot.

### Diagnosing

| Symptom | Where to look |
|---|---|
| A script will not upload | `POST /api/bots/validate/`, or `manage.py pine_check` — the error names the construct, line and column |
| A bot stopped overnight | `BotRun.stop_reason` / `stop_detail`, and the persistent `bot_stopped` notice in the panel |
| Live disagrees with the backtest | the intent digest on the run against the one on the report; `BotRun.divergences` |
| A signal never fires | check the upload warnings for `ta_not_hoisted`, and `Runtime.advance_failures` on the run |
| The panel says "no price feed" | the bot's feed is the same public one the chart uses — `MARKET_DATA_PIN`, and `docs/decisions.md` Q13 |

### What is kept (Q26)

Every intent and every action, **forever** — that is what accountability for
other people's capital means. Bars: all of them at 15m and above; at 1m and 5m
only the bars where a signal or a plot value changed, plus a rolling seven-day
full window. Trimming loses detail, never accountability.

---

## 9. Settings

Every one is `BOT_<KEY>` in the environment and lands in `settings.BOT`;
`GET /api/bots/policy/` renders the live values, including the two stops that
deliberately have no number.

| Key | What it decides |
|---|---|
| `MAX_SCRIPT_BYTES` `MAX_AST_NODES` `MAX_TA_CALL_SITES` `MAX_LOOP_ITERATIONS` `SERIES_DEPTH` | what a script may be |
| `BAR_BUDGET_MS` | how long one bar may take before the bot stops |
| `BAR_CONFIRM_LAG_MS` | how late after the close a bar is trusted (Q23) |
| `WARMUP_MULTIPLIER` `WARMUP_MIN_BARS` | how much history converges an indicator |
| `MAX_CLOCK_SKEW_MS` | a fast clock confirms bars that have not closed |
| `BACKTEST_SLIPPAGE_BPS` `BACKTEST_FEE_BPS` | the fill model, printed on every report |
| `MAX_PRICE_DRIFT_PCT` | a stale feed or a mis-mapped symbol, caught with one number |
| `MAX_ACCOUNTS` | the canary cap on how wide a bot may fan out |
| `MAX_CONSECUTIVE_LOSSES` `MAX_DRAWDOWN_PCT` `MAX_TRADES_PER_HOUR` `NO_BAR_TIMEOUT_MULTIPLE` | the four countable Q25 triggers |
| `RECONCILE_PASSES_BEFORE_STOP` | how many times a disagreement is retried |
| `SOAK_DAYS` `SOAK_MIN_RESTARTS` `SOAK_MIN_HALT_DRILLS` | the promotion gate |
| `SUPERVISOR_IN_ASGI` | where the loop runs |

A bot's `risk_config` may **tighten** any of the risk keys for itself. The
promotion gate can tell whether they were set deliberately or left at defaults.

---

## 10. Not done

- **No adapter has been run against a live exchange or a testnet.** This gates
  live bots exactly as it gates live manual trading.
- **Phase 7's 14-day soak is a calendar item**, not a code item. The gate
  measures it; nothing can shorten it.
- **Phase 10's checklist is human**: the testnet drill, the lawyer's re-read, the
  canary week at one account.
- **The `ta.*` golden values are Q29** — open. The indicator tests currently
  compare against oracles transcribed from the Pine reference, which pins the
  incremental implementations against the textbook formulas but cannot catch a
  misreading of the reference itself. See
  `backend/tests/fixtures/pine/golden/README.md` for the file format; the tests
  pick up an export the moment one is committed.
