# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
pytest

# Run a specific app's tests
pytest apps/transpiler
pytest apps/exchange apps/transpiler
pytest apps/credentials

# Run a single test file or test
pytest apps/exchange/tests.py::TestName

# Django management
python manage.py migrate
python manage.py createsuperuser
python manage.py check

# Docker (primary workflow)
cp .env.example .env          # fill SECRET_KEY and CREDENTIAL_ENC_KEY
docker compose up --build     # dev with hot-reload (RELOAD=1 default)
docker compose up -d --build  # detached
RELOAD=0 docker compose up -d --build  # production (no watchfiles)
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser

# After UI changes (frontend needs rebuild)
docker compose build frontend web
docker compose run --rm web python manage.py migrate
docker compose up -d

# Local (without Docker — infra still in Docker)
docker compose up -d postgres redis
python manage.py runserver 0.0.0.0:8000
celery -A config worker --loglevel=info
celery -A config beat --loglevel=info
python manage.py run_market_feed     # long-lived HL candle WS process
python manage.py run_user_feed       # long-lived HL private WS (fills/orders)
python manage.py consume_hl_candles  # long-lived Redis Pub/Sub → Celery fan-out

# Generate required secrets
python -c "import secrets;print(secrets.token_urlsafe(50))"          # SECRET_KEY
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # CREDENTIAL_ENC_KEY
```

## Settings & Environment

| Settings module | When to use |
|---|---|
| `config.settings.dev` | Default — PostgreSQL + Redis via Docker |
| `config.settings.dev_sqlite` | SQLite + eager Celery; no Docker Postgres needed. Disables daphne/channels. |
| `config.settings.prod` | Production (TLS, no DEBUG) |

`pytest.ini` sets `DJANGO_SETTINGS_MODULE = config.settings.dev`.

Key env vars beyond Django defaults:

| Variable | Purpose |
|---|---|
| `CREDENTIAL_ENC_KEY` | Base64-urlsafe 32-byte AES-256 master key for agent private keys |
| `HL_NETWORK` | `mainnet` or `testnet` (default: `testnet`) |
| `HL_CANDLE_CHANNEL_PREFIX` | Redis Pub/Sub namespace (default: `hl:candles`) |
| `HISTORY_SYNC_ASSETS` | Comma-separated coins for scheduled candle sync |
| `LIVE_WINDOW_BUFFER` | Sliding candle window size for live interpreter state |
| `TELEGRAM_ALERT_ENABLED` | Toggle Telegram alert delivery |

## Architecture

```
Client ─REST/WS─▶ Django (DRF) + Channels (ASGI/Daphne)
                        │ enqueue              │ publish
                        ▼                      ▼
                   Celery worker ◀─Redis─▶ (Pub/Sub + broker/cache)
                        │ hyperliquid-python-sdk (EIP-712 signing)
                        ▼
              Hyperliquid L1 (mainnet/testnet)     PostgreSQL
```

**Services** (docker-compose):
- `web` — Daphne ASGI on `:8000`
- `celery` — task worker
- `celery-beat` — periodic scheduler
- `market-feed` — HL candlestick WS → Redis Pub/Sub
- `user-feed` — HL private WS (orderUpdates/userFills) → `OrderRecord` sync
- `candle-consumer` — Pub/Sub → Celery `process_live_bar_task`
- `frontend` — Vue dashboard (nginx proxy) on `:8080`

## App Map

| App | Responsibility |
|---|---|
| `apps.accounts` | Custom `User` model + per-user trading kill-switch |
| `apps.credentials` | AES-256-GCM encrypted agent private key + `ExchangeCredential` model |
| `apps.strategies` | `Strategy` / `StrategyState` + Pine Script upload + plugin registry (`apps/strategies/plugins/`) |
| `apps.execution` | `OrderRecord`, `ExecutionLog` (append-only audit trail) |
| `apps.exchange` | HL REST/WS client, candle feed, market data history, WS Channels consumer |
| `apps.transpiler` | Pine Script v5 → Python: grammar → parser → semantic analysis → interpreter → order router |
| `apps.risk` | `RiskManager` gates: daily loss, drawdown, max open trades, exposure, leverage caps |
| `apps.paper` | Virtual accounts + `PaperBroker` (wraps `SimBroker`) running on live candle feed |
| `apps.optimizer` | Grid search, walk-forward, Monte Carlo optimization |
| `apps.pro` | Strategy versioning, journal, marketplace, replay sessions |
| `apps.dashboard` | Health heartbeat, overview aggregates, WebSocket publish |
| `apps.integrations` | Signum webhook alert delivery |
| `apps.telegram` | Telegram alert integration |

## Pine Script Transpiler (`apps/transpiler/`)

Pipeline: **source → Lark LALR parse → AST → semantic analysis → bar-by-bar interpreter**. The AST is interpreted, never `exec`'d.

| Module | Role |
|---|---|
| `grammar/pine.lark` + `parser.py` | LALR grammar (indentation-aware) → AST nodes (`ast_nodes.py`) |
| `semantic.py` | Scope tracking, type lattice, `RestrictionLayer` (rejects `plot`/`plotshape`/`bgcolor` etc. at compile time) |
| `runtime/indicators.py` | `ta.sma/ema/rma/rsi/atr/macd/bb/stoch` + `barssince/valuewhen/cum` (NumPy/pandas vectorized) |
| `runtime/interpreter.py` | `vectorize_pass` + bar loop; `run_warmup` / `run_bar` for live incremental path |
| `runtime/order_router.py` | `SimBroker` (backtest) / `WarmupBroker` (no-op seed) / `LiveBroker` (Hyperliquid EIP-712) |
| `runtime/sim_broker.py` | Fill-at-next-open simulation with commission/slippage |
| `engine.py` | `compile()`, `run_backtest()`, `run_live()` public API |
| `live/sliding_window.py` | Bounded OHLCV ring buffer |
| `live/session_store.py` | Redis persistence of window + scalar interpreter state between bars |
| `live/runner.py` | `LiveIncrementalRunner`: seed history, warmup, `on_closed_candle` |

**Curated Pine v5 subset:** `strategy(...)`, `var`/`varip`, `=`/`:=`, tuple `[a,b,c] = ta.macd(...)`, `if/else if/else`, `for`, user functions, `[]` history operator, `ta.*`, `math.*`, `syminfo.*`, `nz/na`, `strategy.entry/close/exit/position_size/equity/openprofit`. Visual/drawing builtins are rejected at the semantic layer.

## Live Feed Flow (Phase 3)

1. `POST /api/strategies/<id>/start/` → Celery seeds `warmup_bars` candles, replays with `WarmupBroker`, saves session to Redis, registers WS subscription.
2. `run_market_feed` subscribes to HL `candle` channel per `(coin, interval)`.
3. On closed candle, feed `PUBLISH`es to Redis channel; `consume_hl_candles` enqueues `process_live_bar_task`.
4. Worker appends candle, re-vectorizes, runs one bar, routes live orders via `LiveBroker` → Hyperliquid.

Duplicate candle timestamps are skipped (idempotent).

## Credential Security

Agent private keys are encrypted with AES-256-GCM (`apps/credentials/crypto.py`). Format on disk: `nonce(12) || ciphertext || tag(16)`. The master wallet private key is **never stored** — only the agent key, which can trade but cannot withdraw. `CREDENTIAL_ENC_KEY` must be set or Django will refuse to start.

## Data Storage

- **PostgreSQL:** canonical market data, orders, backtests, strategies, credentials
- **Parquet files** (`data/candles/`): fast read path for backtesting (`CANDLE_DATA_DIR`)
- **Redis:** Celery broker + result backend, Channels layer, live session state (`live:session:<id>`), candle Pub/Sub (`hl:candles:<coin>:<interval>`)

## Strategy Plugin System

`apps/strategies/plugins/` contains a plugin registry (`registry.py`) plus a Pine Script plugin (`pine.py`) and a base class (`base.py`). New strategy types register here.

## Celery Beat Schedule

| Task | Interval |
|---|---|
| `dashboard.health_heartbeat` | 5s |
| `execution.reconcile_orders` | 60s |
| `exchange.sync_active_accounts` | 30s |
| `exchange.collect_open_interest` | 1h |
| `exchange.sync_history_incremental` | `HISTORY_SYNC_INTERVAL_SECONDS` (default 1h) |
