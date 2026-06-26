# Historical Data Downloader — Multi-Type Extension

## Context

The platform already has a working OHLCV download→backtest pipeline:
`DownloadForm.vue` → `POST /api/history/downloads/` → `download_history_task`
(Celery) → `fetch_candles_range` (paginated) → `save_candles` (parquet,
dedup-merge) → backtester reads via `load_candles` → `run_backtest`.

User wants the **"Historical data" panel** (`/data` → `DataView.vue`) to
download **anything** in the spec: OHLCV (done), **funding rates**, **open
interest**, **trade history** — download once, backtest with them.

### Hard reality of the Hyperliquid public API (verified in SDK source)

| Data type | Backfillable? | Method | Plan |
|-----------|---------------|--------|------|
| OHLCV | ✅ yes | `Info.candles_snapshot` | exists |
| Funding rates | ✅ yes | `Info.funding_history(name, startTime, endTime)` | **add backfill** |
| Open interest | ❌ no history endpoint | `Info.meta_and_asset_ctxs()` = current snapshot only | **forward-poll only** (Celery beat appends snapshots over time) |
| Public trades | ❌ no history endpoint | WS `"trades"` realtime only | **out of scope** (cannot backfill without keys; not consumed by backtester) |

So "download once" applies fully to OHLCV + funding. OI is collect-going-forward.
Trades deferred — flagged in UI as unavailable, no fake promise.

### Storage decision: parquet, not new Postgres tables

Spec suggests Postgres tables. **Recommend reusing the existing parquet store
pattern** (`candle_store.py`): proven, `fcntl`-locked, dedup-merge, and — most
important — the backtester already reads parquet via `load_candles`. New
Postgres tables would be unconsumed dead weight. Parquet keeps the "download
once + backtest" loop closed today. Layout mirrors candles:
- `data/candles/<COIN>/<interval>.parquet` (exists)
- `data/funding/<COIN>.parquet` — cols `ts, funding_rate, premium`
- `data/open_interest/<COIN>.parquet` — cols `ts, open_interest`

`HistoryDownload` model already tracks jobs (status/progress JSON); extend it
with a `data_types` field. No raw-data DB tables.

---

## Changes

### Backend

**1. `apps/exchange/history.py` — add fetchers + retry/backoff**
- Add `fetch_funding_range(coin, start_ms, end_ms, *, network, sleep)`:
  paginate `Info.funding_history` by time windows (HL caps ~500 rows/call →
  advance `start` past newest `time` each loop, same floor-stop logic as
  `fetch_candles_range`). Return df cols `ts, funding_rate, premium` (map from
  `time`, `fundingRate`, `premium`).
- Add `fetch_open_interest_snapshot(coins, *, network)`: one
  `meta_and_asset_ctxs()` call → df rows `ts=now, coin, open_interest` (from
  `openInterest`). Snapshot, not range.
- **Harden** `fetch_candles_range` (and new fetchers): wrap each paginated call
  in a retry helper — N retries, exponential backoff on exception/rate-limit.
  Reuse existing `apps/exchange/hl_rate_limit.py` `@with_rate_limit` decorator
  (currently unused) rather than hand-rolling. This fixes the current
  "raises on first error → bulk download dies midway" gap.

**2. `apps/exchange/candle_store.py` — generalize storage**
- Extract the merge/lock/save core into a private `_save_parquet(path, df,
  columns, dedup_key)` and have `save_candles` call it.
- Add `save_funding(coin, df)` → `data/funding/<COIN>.parquet`, dedup `ts`.
- Add `save_open_interest(coin, df)` → `data/open_interest/<COIN>.parquet`,
  dedup `ts`.
- Add `load_funding(coin, start, end)`, `load_open_interest(coin, start, end)`
  (mirror `load_candles`) for the backtester to consume later.
- Extend `list_datasets()` to also scan funding/ and open_interest/ dirs so the
  panel's "stored datasets" table shows them (tag each row with a `kind`).

**3. `apps/exchange/history_download.py` — orchestrate by data type**
- `download_pair` currently does OHLCV only. Add `download_funding(coin, ...)`
  and `download_open_interest(coins, ...)` siblings returning the same progress
  dict shape (`key`, `status`, `bars`, `start_ts`, `end_ts`, `path`, `error`).
- `download_history(...)` gains `data_types: list[str]` param. Loop logic:
  - `"ohlcv"` → per coin×interval `download_pair` (key `BTC/1h`)
  - `"funding"` → per coin `download_funding` (key `BTC/funding`)
  - `"open_interest"` → single `download_open_interest(coins)` snapshot
    (key `BTC/oi`), status note "snapshot — enable scheduled collection for
    history"
- Keep `on_progress` callback unchanged.

**4. `apps/exchange/models.py` + migration**
- Add `data_types = JSONField(default=list)` to `HistoryDownload`
  (default `["ohlcv"]` for back-compat). New migration `0003_*`.

**5. `apps/exchange/serializers.py`** — add `data_types` to fields/read-only.

**6. `apps/exchange/views.py` `HistoryDownloadViewSet.create`**
- Read `data_types` from `request.data` (default `["ohlcv"]`); validate against
  `{"ohlcv","funding","open_interest"}` (reject `"trades"` with clear message).
- Require `intervals` only when `"ohlcv"` selected (funding/OI ignore intervals).
- Pass `data_types` into `HistoryDownload.objects.create(...)`.

**7. `apps/exchange/tasks.py` `download_history_task`**
- Pass `job.data_types` into `download_history(...)`. Progress/publish unchanged.

**8. Open-interest forward collection (the only way to get OI history)**
- New Celery beat task `exchange.collect_open_interest` in `apps/exchange/tasks.py`:
  calls `fetch_open_interest_snapshot` for a configured coin set, appends via
  `save_open_interest`. Register in `CELERY_BEAT_SCHEDULE`
  (`config/settings/base.py`) at e.g. hourly. Coin set from settings
  (`OI_COLLECT_COINS`, default `["BTC","ETH","SOL","HYPE"]`).

### Frontend

**9. `frontend/src/modules/data/DownloadForm.vue`**
- Add a **data-type multi-select** (chips like intervals): `OHLCV`, `Funding`,
  `Open Interest`, and a disabled `Trades (unavailable)` chip with tooltip.
- Disable/grey the interval picker when only funding/OI selected.
- Include `dataTypes` in the `startDownload` payload.

**10. `frontend/src/api/client.ts`** — add `dataTypes?: string[]` to the
download request type and `data_types` to `HistoryDownload` response interface.

**11. `frontend/src/stores/history.ts`** — thread `dataTypes` through
`startDownload`. Progress/WS handling already generic (keyed dict) — no change.

**12. `frontend/src/modules/data/DownloadJobsList.vue`** — show data-type in the
pair key label (keys already carry `/funding`, `/oi` suffixes).

**13. i18n** — add keys to `frontend/src/locales/en.json` + `fa.json`
(`data.dataTypes`, `data.tradesUnavailable`, funding/oi labels).

---

## Out of scope / explicitly deferred
- **Public trade history** — no HL public endpoint; UI shows it disabled. If
  needed later: forward-capture via WS `"trades"`, not a backfill.
- **Postgres market-data tables** — parquet chosen (backtester already consumes
  it). Revisit only if cross-asset SQL aggregation becomes a requirement.
- **Backtester using funding for perp PnL** — data will be available via
  `load_funding`; wiring it into `run_backtest` PnL is a separate follow-up.

---

## Verification

1. **Migrate**: `python manage.py migrate exchange`.
2. **Funding backfill (CLI smoke)**: shell →
   `from apps.exchange.history import fetch_funding_range` → fetch BTC last 30d →
   assert non-empty, cols `ts, funding_rate, premium`, ascending, deduped.
3. **OI snapshot**: `fetch_open_interest_snapshot(["BTC","ETH"])` → 2 rows,
   `open_interest` numeric.
4. **Panel end-to-end**: run app (Django + Celery worker + beat + Vite). Open
   `/data`, select BTC, check `OHLCV + Funding`, range last 60d, Start. Watch
   job rows reach `done`; confirm `data/candles/BTC/*.parquet` and
   `data/funding/BTC.parquet` exist; "stored datasets" table lists both.
5. **Retry path**: temporarily point network at a bad URL → confirm backoff
   retries then a clean `failed` progress entry (not a crash).
6. **Backtest consumes it**: run an existing backtest on BTC/1h over the
   downloaded range → completes, trades produced (proves OHLCV pipeline intact).
7. **Tests**: extend `apps/exchange/tests.py` — mock `Info.funding_history` /
   `meta_and_asset_ctxs`, assert fetcher pagination + save/load round-trip +
   `data_types` validation in the viewset. Run `pytest apps/exchange`.
