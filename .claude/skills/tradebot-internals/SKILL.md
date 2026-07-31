---
name: tradebot-internals
description: "Deep internals of this repo — Pine Script transpiler pipeline and supported v5 subset, live candle feed flow, credential encryption format, strategy plugin registry, and the Celery beat schedule. Load when working on the transpiler, the live feed, credentials, plugins, or scheduled tasks."
---

# TradeBot Internals

Extracted from `CLAUDE.md` so it loads only when relevant. For orientation
prefer `graphify query "<question>"` over reading source.

## Pine Script transpiler (`apps/transpiler/`)

Pipeline: **source → Lark LALR parse → AST → semantic analysis → bar-by-bar
interpreter**. The AST is interpreted, never `exec`'d.

| Module | Role |
|---|---|
| `grammar/pine.lark` + `parser.py` | LALR grammar (indentation-aware) → AST nodes (`ast_nodes.py`) |
| `semantic.py` | Scope tracking, type lattice, `RestrictionLayer` (rejects `plot`/`plotshape`/`bgcolor` etc. at compile time) |
| `runtime/indicators.py` | `ta.sma/ema/rma/rsi/atr/macd/bb/stoch` + `barssince/valuewhen/cum` (NumPy/pandas vectorized) |
| `runtime/interpreter.py` | `vectorize_pass` + bar loop; `run_warmup` / `run_bar` for the live incremental path |
| `runtime/order_router.py` | `SimBroker` (backtest) / `WarmupBroker` (no-op seed) / `LiveBroker` (Hyperliquid EIP-712) |
| `runtime/sim_broker.py` | Fill-at-next-open simulation with commission/slippage |
| `engine.py` | `compile()`, `run_backtest()`, `run_live()` public API |
| `live/sliding_window.py` | Bounded OHLCV ring buffer |
| `live/session_store.py` | Redis persistence of window + scalar interpreter state between bars |
| `live/runner.py` | `LiveIncrementalRunner`: seed history, warmup, `on_closed_candle` |

**Supported Pine v5 subset:** `strategy(...)`, `var`/`varip`, `=`/`:=`, tuple
`[a,b,c] = ta.macd(...)`, `if/else if/else`, `for`, user functions, `[]` history
operator, `ta.*`, `math.*`, `syminfo.*`, `nz/na`,
`strategy.entry/close/exit/position_size/equity/openprofit`.
Visual/drawing builtins are rejected at the semantic layer.

## Live feed flow (Phase 3)

1. `POST /api/strategies/<id>/start/` → Celery seeds `warmup_bars` candles,
   replays with `WarmupBroker`, saves session to Redis, registers the WS
   subscription.
2. `run_market_feed` subscribes to the HL `candle` channel per `(coin, interval)`.
3. On a closed candle the feed `PUBLISH`es to a Redis channel;
   `consume_hl_candles` enqueues `process_live_bar_task`.
4. The worker appends the candle, re-vectorizes, runs one bar, and routes live
   orders via `LiveBroker` → Hyperliquid.

Duplicate candle timestamps are skipped (idempotent).

## Credential security

Agent private keys are encrypted with AES-256-GCM (`apps/credentials/crypto.py`).
On-disk format: `nonce(12) || ciphertext || tag(16)`. The master wallet private
key is **never stored** — only the agent key, which can trade but cannot
withdraw. `CREDENTIAL_ENC_KEY` must be set or Django refuses to start.

## Strategy plugin system

`apps/strategies/plugins/` holds the registry (`registry.py`), a Pine Script
plugin (`pine.py`), and a base class (`base.py`). New strategy types register
here.

## Celery beat schedule

| Task | Interval |
|---|---|
| `dashboard.health_heartbeat` | 5s |
| `execution.reconcile_orders` | 60s |
| `exchange.sync_active_accounts` | 30s |
| `exchange.collect_open_interest` | 1h |
| `exchange.sync_history_incremental` | `HISTORY_SYNC_INTERVAL_SECONDS` (default 1h) |
