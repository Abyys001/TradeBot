# Plan: Offline historical backtesting (download + dry-run Pine strategies)

## Context

User wants to: download multi-year OHLCV history for several coins from Hyperliquid,
store it locally, import a Pine strategy, and backtest it in **dry mode** (no exchange
API / credentials) computing PnL and stats — purely as a test.

**Most of this already exists and works:**
- `run_backtest(source, df)` compiles Pine + runs over a DataFrame with `SimBroker`,
  which fills at bar price, never touches the exchange, and returns
  `net_pnl / win_rate / max_drawdown / num_trades` + per-trade list.
  (`apps/transpiler/engine.py:33`, `apps/transpiler/runtime/order_router.py:56-116`)
- `Backtest` + `BacktestTrade` models and `run_backtest_task` persist results.
  (`apps/transpiler/models.py:4-46`, `apps/transpiler/tasks.py:65-103`)
- Pine source is stored + validated on `Strategy` (`compile()` validates).
  (`apps/strategies/models.py`, `apps/transpiler/tasks.py:46`)

**Gaps to fill (the actual work):**
1. `fetch_candles()` does a single recent window only — no multi-year paginated backfill.
   (`apps/exchange/candles.py:51`)
2. No candle persistence — nothing stores downloaded history for reuse.
3. No offline driver — backtest currently only runs via API with candles in the request body.

### Hard facts (not blockers, shape the result)
- Hyperliquid launched ~mid-2023 → **~2 years max history**, not 5. Downloader fetches
  *max available* per interval.
- `candleSnapshot` caps ~5000 rows/request → multi-year needs pagination by time window.
- HL retains limited fine-grain depth: **1m won't go back 2 years**; coarse intervals
  (1h/4h/1d) reach furthest. Downloader stops when the API returns no older rows.
- Coins validated against HL meta (`apps/exchange/hl_meta.py`); unknown symbols
  (e.g. ZEC if not a HL perp) are skipped with a warning, not fatal.

## Approach

### 1. Paginated history fetch — new `apps/exchange/history.py`
`fetch_candles_range(coin, interval, start_ms, end_ms, *, network) -> pd.DataFrame`
- Loop `Info.candles_snapshot` in windows (`<=5000` bars; window = `5000 * _INTERVAL_MS[interval]`),
  advancing `start_ms` past the last returned `ts` each iteration.
- Dedupe on `ts`, sort ascending. Stop when a window returns no new rows (= hit history floor).
- Small `time.sleep` between calls for rate-limit safety.
- Reuse `_normalize_rows`, `_INTERVAL_MS`, `normalize_coin`, `normalize_interval`, `network_url`
  from `candles.py` / `hl_constants.py` (no duplication).

### 2. Flat-file storage — new `apps/exchange/candle_store.py`
- Layout: `<CANDLE_DATA_DIR>/<COIN>/<interval>.parquet` (parquet via `pyarrow`).
- `save_candles(coin, interval, df)` — merge with existing file, dedupe on `ts`, sort (incremental backfill).
- `load_candles(coin, interval, start=None, end=None) -> df` — read + optional ts slice.
- `CANDLE_DATA_DIR` from settings, default `BASE_DIR/data/candles`.

### 3. CLI commands ("Both" — offline first)
- `apps/exchange/management/commands/download_history.py`
  args: `--coins BTC ETH SOL DOGE ...`, `--intervals 1m 5m 15m 1h 4h`,
  `--start YYYY-MM-DD` (default = earliest available), `--end`, `--network`.
  Validates coins vs HL meta → fetch each coin×interval via `fetch_candles_range` → `save_candles`.
  Prints per-file summary (rows, ts range). Skips unknown coins with a warning.
- `apps/strategies/management/commands/import_strategy.py`
  args: `--pine PATH`, `--name`, `--symbol`, `--timeframe`. Reads `.pine` file, runs `compile()`
  to validate, creates `Strategy` (`source`, `validation_status="ok"`).
- `apps/transpiler/management/commands/run_backtest_file.py`
  args: `--strategy-id N` (or `--pine PATH`), `--coin`, `--interval`, `--start/--end`, `--qty`, `--save`.
  `load_candles` → `run_backtest(source, df)` → print metrics table + trade count.
  `--save` writes `Backtest` + `BacktestTrade` rows. No credentials touched.

### 4. API path (reuse same code)
- Extract result-persistence from `run_backtest_task` into `_persist_backtest_result(bt, result)`.
- New task `run_backtest_stored_task(backtest_id, coin, interval, start, end)`: `load_candles` →
  `run_backtest` → `_persist_backtest_result` (shares helper).
- New view `POST /api/strategies/<id>/backtest_stored/` body `{coin, interval, start, end}` →
  create `Backtest(status=PENDING)` → enqueue task → 202 + backtest_id.
  (`apps/transpiler/views.py`, `apps/transpiler/urls.py`)

### 5. Wiring
- `requirements.txt`: add `pyarrow` (parquet). pandas/numpy already present.
- `config/settings/base.py`: add `CANDLE_DATA_DIR` (env, default `BASE_DIR/data/candles`).
- `.env.example`: document `CANDLE_DATA_DIR`. `.gitignore`: add `data/`.

## Files
- new: `apps/exchange/history.py`, `apps/exchange/candle_store.py`
- new commands: `apps/exchange/management/commands/download_history.py`,
  `apps/strategies/management/commands/import_strategy.py`,
  `apps/transpiler/management/commands/run_backtest_file.py`
- modify: `apps/transpiler/tasks.py` (extract helper + stored task),
  `apps/transpiler/views.py`, `apps/transpiler/urls.py`,
  `requirements.txt`, `config/settings/base.py`, `.env.example`, `.gitignore`
- tests: `apps/exchange/tests.py` (downloader pagination w/ mocked `candles_snapshot`;
  candle_store round-trip), `apps/transpiler/tests.py` (backtest-from-store)

## Verification
1. `python manage.py download_history --coins BTC ETH SOL DOGE --intervals 1h 4h --start 2024-01-01`
   → files under `data/candles/<COIN>/<interval>.parquet`, row counts + ranges printed; unknown coin warns.
2. Large pull check: add `--intervals 1m` → confirm pagination advances and 1m stops at HL history floor.
3. `python manage.py import_strategy --pine <file>.pine --name "Test" --symbol BTC --timeframe 1h`
   → `Strategy` created, `validation_status == "ok"`.
4. `python manage.py run_backtest_file --strategy-id <N> --coin BTC --interval 1h`
   → prints `net_pnl / win_rate / max_drawdown / num_trades` + trades; no API/credential calls.
   `--save` → `Backtest` + `BacktestTrade` rows exist.
5. Unit tests green: `pytest apps/exchange apps/transpiler`.
6. (Stack up) `POST /api/strategies/<id>/backtest_stored/` → 202; `GET /api/backtests/<id>/` shows metrics.
