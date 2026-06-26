# TradeBot

Hyperliquid automated-trading backend (perpetuals + spot).

- **Phase 1 — Secure Foundation:** Django + DRF + Channels, Celery + Redis,
  PostgreSQL, AES-256-GCM encrypted agent keys, Hyperliquid integration layer.
- **Phase 2 — Pine Script Transpiler:** compiles a curated Pine Script v5 subset
  to runnable Python and backtests / live-trades via the exchange layer.
- **Phase 3 — Live Engine:** REST warmup + HL WebSocket candles + incremental
  interpreter with Redis Pub/Sub fan-out.

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

| App | Responsibility |
|-----|----------------|
| `apps.accounts` | Custom `User` + per-user trading kill-switch |
| `apps.credentials` | Agent private key (AES-256-GCM) + master wallet address |
| `apps.strategies` | `Strategy` / `StrategyState` + `market_type` (perp/spot) |
| `apps.execution` | `OrderRecord`, `ExecutionLog` (append-only audit) |
| `apps.exchange` | HL client, candle feed, WS manager, Channels consumer |

## Credential security (multi-layer)

1. **App layer:** AES-256-GCM encryption for the **Agent private key only**.
   The master wallet private key is never stored. Agent keys can trade but
   cannot withdraw funds when configured correctly in the HL dashboard.
2. **At rest (infra):** enable PostgreSQL/disk encryption in production.
3. **In transit (infra):** TLS to Postgres (`sslmode=require` in prod settings)
   and HTTPS/HSTS for the API.

## Setup & Run (Docker — recommended)

Everything runs from a **single** [`docker-compose.yml`](docker-compose.yml) +
[`Dockerfile`](Dockerfile). Source code is volume-mounted; Python changes reload
automatically via [watchfiles](https://github.com/samuelcolvin/watchfiles) — no
rebuild needed for code edits.

```bash
cp .env.example .env
# Fill SECRET_KEY and CREDENTIAL_ENC_KEY:
python -c "import secrets;print(secrets.token_urlsafe(50))"
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

docker compose up --build          # foreground, hot reload (RELOAD=1)
# or
docker compose up -d --build       # detached
```

| Service | Port / role |
|---------|-------------|
| `frontend` | `:8080` — Vue dashboard (nginx → API/WS proxy) |
| `web` | `:8000` — API + WebSocket (Daphne) |
| `celery` | task worker |
| `celery-beat` | scheduler (health heartbeat) |
| `market-feed` | Hyperliquid candle WS → Redis Pub/Sub |
| `user-feed` | Hyperliquid private WS (orderUpdates/userFills) → `OrderRecord` sync |
| `candle-consumer` | Pub/Sub → Celery `process_live_bar_task` |
| `postgres` | `:5432` |
| `redis` | `:6379` |

Open **http://localhost:8080** for the dashboard UI.

### Backtest without exchange API key

You can download historical OHLCV, upload Pine Script, and run backtests **without** adding a Hyperliquid agent key:

1. **Historical Data** (`/data`) — download OHLCV, funding, and open-interest snapshots from the public Hyperliquid API (no API key). Requires the **Celery worker** and **Redis**:

```bash
docker compose up -d postgres redis web celery celery-beat frontend
```

Data is stored in **PostgreSQL** (canonical, queryable) and **Parquet** (fast backtest reads) under `data/` (persisted via the `marketdata` Docker volume). Jobs stuck in `pending` usually mean Celery is offline — check the red/green indicator in the header or the banner on the Data page. Use **Retry all stale** on the Data page after starting Celery, or `POST /api/history/downloads/retry-stale/`.

**Troubleshooting (فارسی):** اگر کارهای دانلود در وضعیت `pending` می‌مانند، worker سلری را اجرا کنید: `docker compose up -d celery celery-beat`. سپس از دکمه «تلاش مجدد همه» در صفحه داده تاریخی استفاده کنید. فید Hyperliquid قرمز فقط برای چارت لایو است و روی دانلود تاریخی تأثیری ندارد.

2. **Strategies** — upload `.pine` or create strategy; choose **No API — backtest only**
3. Open the strategy → **Backtest** tab → pick coin/timeframe → Run Backtest

After UI changes, rebuild the frontend container:

```bash
docker compose build frontend web
docker compose run --rm web python manage.py migrate
docker compose up -d
```

Create an admin user (once):

```bash
docker compose exec web python manage.py createsuperuser
```

**Production deploy** (no hot reload, Daphne instead of runserver):

```bash
RELOAD=0 docker compose up -d --build
```

Rebuild the image only when `requirements.txt` changes:

```bash
docker compose build --no-cache
```

### Local setup (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Generate keys (see above)

docker compose up -d postgres redis   # infra only
python manage.py migrate
python manage.py createsuperuser
```

If you change `requirements.txt`, rebuild the image:

```bash
docker compose build web
docker compose up -d
```

```bash
python manage.py runserver 0.0.0.0:8000
celery -A config worker --loglevel=info
celery -A config beat --loglevel=info
python manage.py run_market_feed
python manage.py run_user_feed
```

## Phase 1 verification

| # | Check | How | Status |
|---|-------|-----|--------|
| 1 | Env boots | `docker compose up -d` → migrate runs via entrypoint → `docker compose exec web manage.py check` | ✅ |
| 2 | Encryption round-trip + ciphertext at rest | `pytest apps/credentials` | ✅ |
| 3 | Celery health | start worker → `config.celery.ping.delay().get()` returns `pong` | ✅ |
| 4 | Channels fan-out | group_send → receive over Redis channel layer | ✅ |
| 5 | HL layer logic | `pytest apps/exchange` (mocked SDK) | ✅ |
| 6 | DRF smoke | POST credential → agent key write-only, encrypted at rest | ✅ |

Run all unit tests:

```bash
pytest
```

### Hyperliquid credential setup (manual)

1. Create an **Agent wallet** in the [Hyperliquid dashboard](https://app.hyperliquid.xyz/) — trade-only, no withdraw.
2. `POST /api/credentials/` with `wallet_address`, `agent_private_key`, `network` (`testnet` or `mainnet`).
3. `POST /api/credentials/<id>/verify/` — checks master wallet state on HL.

```
POST /api/credentials/
{
  "label": "my-agent",
  "wallet_address": "0x...",
  "agent_private_key": "0x...",
  "network": "testnet"
}
```

## API surface

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/api/credentials/` | List / create (agent key write-only) |
| POST | `/api/credentials/<id>/verify/` | Validate against Hyperliquid |
| GET/POST | `/api/strategies/` | Strategy CRUD (includes `timeframe`, `warmup_bars`) |
| POST | `/api/strategies/<id>/start/` | Seed candles, warmup, begin live execution |
| POST | `/api/strategies/<id>/stop/` | Stop live execution |
| GET | `/api/orders/`, `/api/logs/` | Read-only execution history |
| WS | `/ws/exchange/<credential_id>/` | Realtime exchange updates (owner only) |

---

# Phase 2 — Pine Script → Python transpiler

Pipeline (`apps/transpiler`): **source → Lark lex/parse → AST → semantic
analysis → bar-by-bar interpreter**. The AST is *interpreted* (never `exec`'d).
Indicators are computed vectorized (NumPy/pandas) and indexed per bar — the
"hybrid" model: fast indicators, correct `var`/`varip`/`[]`/order semantics.

| Module | Role |
|--------|------|
| `grammar/pine.lark` + `parser.py` | Lark LALR grammar (indentation-aware) → AST |
| `semantic.py` | scope tracking, type lattice, **RestrictionLayer** (rejects `plot`/`plotshape`/`bgcolor`/… at compile time) |
| `runtime/indicators.py` | `ta.sma/ema/rma/rsi/atr/macd/bb/stoch/...` + `barssince/valuewhen/cum` |
| `runtime/interpreter.py` | vectorize pass + bar loop |
| `runtime/order_router.py` | `SimBroker` (backtest) / `LiveBroker` (Hyperliquid EIP-712) |
| `engine.py` | `compile()`, `run_backtest()`, `run_live()` |

### Curated Pine v5 subset
`strategy(...)`, `var`/`varip`, `=`/`:=`, tuple assignment `[a,b,c] = ta.macd(...)`,
`if/else if/else`, `for`, user-defined functions `f(x) => ...`, `[]`,
arithmetic/logical/comparison/ternary, `input.*` (defaults only), `ta.*`, `math.*`,
`syminfo.*`, `nz`/`na`, `strategy.entry/close/exit`, `strategy.position_size/equity/openprofit`.
Backtests fill at next bar open with optional commission/slippage. Visual/drawing builtins are rejected.

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/strategies/<id>/validate/` | compile + semantic check (no run) |
| POST | `/api/strategies/<id>/backtest/` | enqueue backtest (Celery); body has `candles` |
| GET | `/api/backtests/<id>/` | status, metrics, trades |

### Phase 2 verification

| # | Check | Status |
|---|-------|--------|
| 1 | Parse → expected AST; syntax error reports line | ✅ |
| 2 | RestrictionLayer rejects `plot/plotshape/bgcolor` at compile time | ✅ |
| 3 | Semantic catches use-before-declare + type mismatch | ✅ |
| 4 | `ta.sma/ema/rma/rsi` parity vs pandas reference | ✅ |
| 5 | SMA-cross backtest → trades + metrics (`var` + `[]` + crossover) | ✅ |
| 6 | Live routing (mocked HL): order placed when enabled, **blocked by kill-switch** | ✅ |
| 7 | Celery `run_backtest_task` persists `Backtest` + trades | ✅ |

```bash
pytest apps/transpiler      # transpiler + live engine tests
pytest                      # full suite
```

---

# Phase 3 — Live data feed & incremental engine

When a strategy is started, the platform seeds historical candles via Hyperliquid
`candles_snapshot`, warms up interpreter state (no orders), then processes each
**closed** candle from the HL WebSocket feed via Redis Pub/Sub.

| Module | Role |
|--------|------|
| `apps/exchange/hl_client.py` | Agent signing, verify, emergency cancel/close |
| `apps/exchange/candles.py` | REST fetch + normalize OHLCV (`fetch_candles`) |
| `apps/exchange/subscriptions.py` | Redis registry + Pub/Sub publish |
| `apps/exchange/market_ws.py` | HL candlestick WS consumer |
| `apps/exchange/candle_consumer.py` | Pub/Sub → Celery fan-out |
| `manage.py run_market_feed` | Long-lived WS process |
| `manage.py consume_hl_candles` | Long-lived Pub/Sub consumer |
| `apps/transpiler/live/sliding_window.py` | Bounded OHLCV buffer |
| `apps/transpiler/live/session_store.py` | Redis persistence of window + scalar state |
| `apps/transpiler/live/runner.py` | `LiveIncrementalRunner`: seed, warmup, `on_closed_candle` |
| `runtime/interpreter.py` | `vectorize_pass`, `run_warmup`, `run_bar` (incremental) |
| `runtime/order_router.py` | `WarmupBroker` (no-op orders during seed) |

### Live flow

1. `POST /api/strategies/<id>/start/` → Celery seeds `warmup_bars` candles, replays
   history with `WarmupBroker`, saves session to Redis, registers WS subscription.
2. `run_market_feed` subscribes to HL `candle` channel per `(coin, interval)`.
3. On closed candle, feed `PUBLISH`es to Redis; `consume_hl_candles` enqueues tasks.
4. Worker appends candle, re-vectorizes, runs **one bar**, routes orders via
   `LiveBroker` → Hyperliquid (perp `market_open` / spot `order`).

### Environment

| Variable | Purpose |
|----------|---------|
| `HL_NETWORK` | `mainnet` or `testnet` (default: testnet) |
| `CREDENTIAL_ENC_KEY` | AES-256 master key for agent private keys |
| `HL_CANDLE_CHANNEL_PREFIX` | Redis Pub/Sub prefix (default: `hl:candles`) |

### Phase 3 verification

| # | Check | Status |
|---|-------|--------|
| 1 | `fetch_candles` normalizes HL snapshot | ✅ |
| 2 | `SlidingWindow` drops oldest at capacity | ✅ |
| 3 | Warmup builds `var` state without orders | ✅ |
| 4 | `run_bar` incremental path matches full replay | ✅ |
| 5 | Duplicate candle ts skipped (idempotent) | ✅ |
| 6 | `start_live` / `stop_live` tasks + Redis session | ✅ |
| 7 | Live order on new candle (mocked HL) | ✅ |

```bash
pytest apps/exchange apps/transpiler   # Phase 3 + prior phases
pytest                                   # full suite (34)
```

---

## Trading Framework

TradeBot is evolving into a full **algorithmic trading framework** on Hyperliquid:
data management → realistic backtests → strategy plugins → risk gates → paper → live → analytics → optimization.

See the living roadmap: [`docs/TRADING_FRAMEWORK_ROADMAP.md`](docs/TRADING_FRAMEWORK_ROADMAP.md)

| App | Responsibility |
|-----|----------------|
| `apps.risk` | Shared `RiskManager` (daily loss, drawdown, exposure, leverage caps) |
| `apps.paper` | Virtual accounts + `PaperBroker` on live candle feed |
| `apps.optimizer` | Grid search, walk-forward, Monte Carlo |
| `apps.pro` | Strategy versions, journal, marketplace, replay sessions |

---

## Out of scope (later phases)
Custom Pine functions, arrays/matrices/maps, tuples, `request.security`
multi-timeframe, full alert system, private WS fill reconciliation,
parameter optimization, frontend, CI/CD, KMS migration.
