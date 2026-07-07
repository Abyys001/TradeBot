# Plan: Make the Pine→executable translate engine accurate & able to run real TradingView strategies

## Context

The app already parses a curated Pine v5 subset (`apps/transpiler/parser.py` + `grammar/pine.lark`),
semantically checks it (`semantic.py`), and runs it bar-by-bar with a two-phase interpreter
(vectorize + bar loop) over a `SimBroker` (backtest) or `LiveBroker` (Hyperliquid). End-to-end
import→validate→backtest→trade is wired (views/tasks/management commands + frontend BacktestPanel).

**But the engine is neither accurate nor able to run most real TradingView strategies.** Audit found:

1. **Backtest fills have lookahead bias.** `_exec_order` fills at `ctx.close_price` — the *same* bar the
   signal fires on (`runtime/interpreter.py:335`, `runtime/order_router.py:69,78`). TradingView fills at
   the **next bar's open**. No commission/slippage either → optimistic, unrealistic PnL.
2. **`strategy.position_size / .equity / .openprofit` resolve to `NA` at runtime**
   (`runtime/interpreter.py:229-230`) despite being typed `float`. Strategies branching on position state
   silently misbehave.
3. **`input.*()` not accepted.** Grammar parses `input.int(...)` as a member_call (ns=`input`), but
   `semantic.py` only allows bare `input` → pasted scripts fail to compile. (`semantic.py:24` ALLOWED_PLAIN)
4. **No user-defined functions** (`f(x) => ...`). Not in grammar at all → published scripts fail to parse.
5. **~15 common indicators missing** (`runtime/indicators.py` REGISTRY has only sma/ema/rma/rsi/cross*/highest/lowest).
   No macd/bb/atr/stoch/vwap/change/mom/cci/stdev/barssince/valuewhen/etc. macd/bb/stoch return **tuples**,
   which the grammar can't destructure (`[a,b,c] = ta.macd(...)`).

**Goal (per user):** next-bar-open fills + commission/slippage; make strategy-state vars, `input.*`,
user-defined funcs, and common indicators work; keep live routing as-is (backtest-first — `LiveBroker`
market orders unchanged). Outcome: a copy-pasted TradingView strategy compiles, backtests with realistic
PnL across pairs/timeframes, and (for the supported subset) trades live.

## Approach

Five focused workstreams. Each ends with green tests. Order matters: fills first (accuracy), then
language/indicator breadth (coverage).

### 1. Realistic backtest fills — `runtime/order_router.py`, `runtime/interpreter.py`, `engine.py`

- **Next-bar-open fill.** In `_exec_order` (`interpreter.py:332`) stop passing `ctx.close_price`. Instead
  pass the fill reference the broker needs and let `SimBroker` queue the order, filling at the **next bar's
  open**. Cleanest: interpreter looks up `ctx.arrays["open"][i+1]` (the real next bar — deterministic, not
  lookahead since the order is "placed at bar i close, executed at i+1 open"); if `i+1 >= n`, the signal on
  the last bar does not fill (matches TV — no future bar). `finalize()` still marks-to-market remaining open
  positions at the last close.
- **Commission + slippage.** Add `commission` (fraction, e.g. 0.00045) and `slippage` (fraction of price)
  to `SimBroker.__init__`. Apply slippage to the fill price (worse for the side) and deduct commission on
  both entry and exit in `close()`'s PnL. Extend `metrics()` with `gross_pnl`, `total_commission`,
  `net_pnl` (after fees). Keep existing keys.
- **Plumb config.** `run_backtest(source, df, *, default_qty, commission, slippage)` (`engine.py:33`).
  Read defaults from the `strategy()` header kwargs when present (`commission_value`, `slippage`,
  `default_qty_value`/`qty`) via `program.header.args`; allow request/CLI override. Thread through
  `run_backtest_task` / `run_backtest_stored_task` (`tasks.py`) and the backtest views (optional body
  fields `commission`, `slippage`).
- Live path untouched (`LiveBroker` still market-fills on closed bar).

### 2. `strategy.*` runtime state — `runtime/order_router.py`, `runtime/interpreter.py`

- `SimBroker` tracks live position state: `position_size` (signed sum of open trade sizes), and given a
  current price, `open_profit` (unrealised) and `equity` (realised cum PnL + unrealised). Add
  `position_size()`, `open_profit(price)`, `equity(price)` accessors (live PnL uses `ctx.close_price`).
- `_scalar_builtin` ns==`strategy` (`interpreter.py:229`): resolve `position_size`/`equity`/`openprofit`
  from `ctx.broker` at the current bar price; keep `long`/`short` constants. Guard for brokers without the
  accessors (LiveBroker/WarmupBroker) → return `NA`.
- Vectorize pass must NOT precompute expressions referencing `strategy.*` (they're per-bar state): ensure
  `as_array` raises `NotVectorizable` for ns==`strategy` properties so they fall to scalar eval.

### 3. `input.*()` support — `semantic.py`, `runtime/interpreter.py`

- Grammar already produces `BuiltinFunctionNode(namespace="input", name="int|float|bool|string|source|...")`.
  Allow ns==`input` in `semantic.py` restriction/type passes; return type by suffix
  (`int`→int, `float`→float, `bool`→bool, `string`→string, default→float). Also keep bare `input(...)`.
- Evaluate to the **default value**: first positional arg, or `defval=` kwarg. Add handling in both
  `_vectorize_builtin` (return `np.full(n, default)`) and `_scalar_builtin` (return the constant). Title/
  `minval`/`maxval`/`group`/`tooltip` kwargs are ignored. (No UI param-editing this phase — defaults only.)

### 4. User-defined functions `f(x, y) => ...` — `grammar/pine.lark`, `parser.py`, `ast_nodes.py`, `semantic.py`, `runtime/interpreter.py`

- **Grammar**: add a function-def statement, single-line `NAME "(" [params] ")" "=>" expr` and multi-line
  `NAME "(" [params] ")" "=>" suite` (last expression is the return). `params: NAME ("," NAME)*`.
- **AST**: `FunctionDefNode(name, params, body)` (+ a `ReturnNode`/last-expr convention). Transformer
  builds it; `ProgramNode` collects defs.
- **Semantic**: register user functions in scope; analyze body with params declared; calls to a user
  function resolve as `CallNode`/`BuiltinFunctionNode(namespace=None, name=...)` with arity check.
- **Interpreter**: store defs on `ctx.functions`. Scalar eval of a call to a user function pushes a local
  scalar scope binding params to evaluated args, executes the body, returns the last expression. UDF calls
  are not vectorized (fall back to scalar via `NotVectorizable`). Keep recursion depth bounded.

### 5. Indicators + tuple destructuring — `runtime/indicators.py`, `grammar/pine.lark`, `parser.py`, `ast_nodes.py`, `semantic.py`, `runtime/interpreter.py`

- **Tuple-destructuring assignment** (needed for macd/bb/stoch): grammar rule
  `tuple_assignment: "[" NAME ("," NAME)* "]" "=" expr`. AST `TupleAssignNode(names, value)`. Interpreter
  evaluates the RHS (a multi-return builtin) to a tuple and binds each name (scalar buffers; vectorized
  arrays where pure). Semantic checks count matches the builtin's arity.
- **Single-return indicators** (add to REGISTRY + `_vectorize_builtin` dispatch + `_builtin_type` in
  semantic): `tr`/`atr`, `change`, `mom`, `roc`, `stdev`, `variance`, `cci`, `wma`, `hma`, `vwap`
  (uses volume+hlc3), `rising`, `falling`, `cross`. Most are vectorizable with pandas/numpy like the
  existing ones.
- **Multi-return**: `ta.macd(src,fast,slow,sig)`→(macd,signal,hist); `ta.bb(src,len,mult)`→(mid,upper,lower);
  `ta.stoch(...)`→ %K (and pair with sma for %D in scripts). Return tuples consumed by `TupleAssignNode`.
- **Stateful (condition-history) builtins**: `ta.barssince(cond)`, `ta.valuewhen(cond, src, n)`,
  `ta.cum(src)`. Implement as non-vectorizable scalar builtins that keep per-strategy state across bars in
  `ctx` (e.g. last-true bar index). They already run inside the bar loop via `_scalar_builtin`.
- Update the curated indicator list in README "Out of scope/supported" notes.

### Reuse (do not re-implement)
- `_normalize_rows`, `load_candles`/`save_candles`, `list_datasets` for data (already done).
- `SeriesBuffer`/`ExecutionContext` history + `as_array`/`eval_scalar` machinery — extend, don't replace.
- `_persist_backtest_result` (`tasks.py`) for storing metrics/trades — unchanged shape (extra metric keys
  flow through `Backtest.metrics` JSON automatically).
- Frontend `BacktestPanel.vue` / backtest store already call `backtest_stored` and poll — new metric keys
  (`gross_pnl`, `total_commission`) just need display rows in `BacktestResults.vue` (small add).

## Files
- modify: `apps/transpiler/grammar/pine.lark` (UDF def, tuple-assign), `apps/transpiler/parser.py`,
  `apps/transpiler/ast_nodes.py`, `apps/transpiler/semantic.py`,
  `apps/transpiler/runtime/interpreter.py`, `apps/transpiler/runtime/order_router.py`,
  `apps/transpiler/runtime/indicators.py`, `apps/transpiler/engine.py`, `apps/transpiler/tasks.py`,
  `apps/transpiler/views.py` (optional commission/slippage body fields)
- frontend (small): `frontend/src/modules/backtest/BacktestResults.vue` (show fee/gross rows)
- tests: `apps/transpiler/tests.py` (+ `apps/transpiler/live/tests.py` regression),
  add `apps/transpiler/runtime/` indicator parity tests

## Verification
1. **Fill model**: unit test — single entry on bar i, assert fill price == `open[i+1]` and PnL net of
   commission+slippage; last-bar signal does not fill. `test_incremental_sma_matches_full_replay` still green.
2. **strategy state**: script using `if strategy.position_size == 0` enters once then holds; assert trade
   count and that `strategy.position_size` reads nonzero while open.
3. **input**: `len = input.int(14, "Length")` + `ta.rsi(close, len)` compiles & backtests; default used.
4. **UDF**: `myAvg(x, y) => (x + y) / 2` then `s = myAvg(close, open)` compiles, backtests, matches manual.
5. **Indicators**: parity tests vs pandas/numpy reference for atr/change/stdev/wma/vwap; `[m,s,h]=ta.macd(close,12,26,9)`
   destructures and matches reference; `ta.barssince`/`valuewhen` correct on a hand-checked series.
6. **End-to-end (real script)**: import a representative published TradingView strategy via
   `manage.py import_strategy --pine <file>.pine ...` → `validation_status == ok`, then
   `manage.py run_backtest_file --strategy-id N --coin BTC --interval 1h --save` → realistic
   net_pnl/win_rate/max_drawdown + trades; no credential/API calls.
7. `pytest apps/transpiler` green; `ruff check` clean; `manage.py check` clean.
8. API smoke: `POST /api/strategies/<id>/backtest_stored/` (optional `commission`/`slippage`) → 202;
   `GET /api/backtests/<id>/` shows the extended metrics.

## Notes / out of scope (this phase)
- `request.security()` multi-timeframe, arrays/maps/matrices, `switch`/`while`, full alert system,
  parameter optimization, UI editing of `input.*` values (defaults only), live-execution fill/fee parity.
- macd/stoch tuple semantics target the common 3-/1-return forms; exotic overloads may still be rejected.
