# Algo Trader

Guidance for Claude Code in this repository.

## Commands

```bash
# Tests
pytest                                  # all
pytest apps/transpiler                  # one app
pytest apps/exchange/tests.py::TestName # one test
# Wrap noisy runs to compress output: rtk pytest apps/transpiler

# Django
python manage.py migrate
python manage.py createsuperuser
python manage.py check

# Docker (primary workflow)
cp .env.example .env          # fill SECRET_KEY and CREDENTIAL_ENC_KEY
docker compose up -d --build  # dev, hot-reload (RELOAD=1 default)
RELOAD=0 docker compose up -d --build   # production (no watchfiles)
docker compose exec web python manage.py migrate

# After UI changes the frontend image must be rebuilt
docker compose build frontend web && docker compose up -d

# Local (infra still in Docker)
docker compose up -d postgres redis
python manage.py runserver 0.0.0.0:8000
celery -A config worker --loglevel=info
celery -A config beat --loglevel=info
python manage.py run_market_feed     # long-lived HL candle WS
python manage.py run_user_feed       # long-lived HL private WS (fills/orders)
python manage.py consume_hl_candles  # Redis Pub/Sub → Celery fan-out

# Generate secrets
python -c "import secrets;print(secrets.token_urlsafe(50))"                            # SECRET_KEY
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # CREDENTIAL_ENC_KEY
```

## Settings & environment

| Settings module | When |
|---|---|
| `config.settings.dev` | Default — PostgreSQL + Redis via Docker |
| `config.settings.dev_sqlite` | SQLite + eager Celery, no Docker Postgres; disables daphne/channels |
| `config.settings.prod` | Production (TLS, no DEBUG) |

`pytest.ini` sets `DJANGO_SETTINGS_MODULE = config.settings.dev`.

| Variable | Purpose |
|---|---|
| `CREDENTIAL_ENC_KEY` | Base64-urlsafe 32-byte AES-256 master key for agent private keys |
| `HL_NETWORK` | `mainnet` or `testnet` (default `testnet`) |
| `HL_CANDLE_CHANNEL_PREFIX` | Redis Pub/Sub namespace (default `hl:candles`) |
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

**Services** (docker-compose): `web` (Daphne ASGI :8000) · `celery` ·
`celery-beat` · `market-feed` (HL candle WS → Redis Pub/Sub) · `user-feed`
(HL private WS → `OrderRecord` sync) · `candle-consumer` (Pub/Sub → Celery) ·
`frontend` (Vue dashboard behind nginx, :8080).

## App map

| App | Responsibility |
|---|---|
| `apps.accounts` | Custom `User` model + per-user trading kill-switch |
| `apps.credentials` | AES-256-GCM encrypted agent private key + `ExchangeCredential` |
| `apps.strategies` | `Strategy` / `StrategyState`, Pine upload, plugin registry |
| `apps.execution` | `OrderRecord`, `ExecutionLog` (append-only audit trail) |
| `apps.exchange` | HL REST/WS client, candle feed, market history, WS consumer |
| `apps.transpiler` | Pine Script v5 → Python (grammar → parser → semantic → interpreter → order router) |
| `apps.risk` | `RiskManager` gates: daily loss, drawdown, max open trades, exposure, leverage |
| `apps.paper` | Virtual accounts + `PaperBroker` (wraps `SimBroker`) on the live feed |
| `apps.optimizer` | Grid search, walk-forward, Monte Carlo |
| `apps.pro` | Strategy versioning, journal, marketplace, replay sessions |
| `apps.dashboard` | Health heartbeat, overview aggregates, WebSocket publish |
| `apps.integrations` | Signum webhook alert delivery |
| `apps.telegram` | Telegram alert integration |

## Data storage

- **PostgreSQL** — canonical market data, orders, backtests, strategies, credentials
- **Parquet** (`data/candles/`, `CANDLE_DATA_DIR`) — fast read path for backtesting
- **Redis** — Celery broker/results, Channels layer, live session state
  (`live:session:<id>`), candle Pub/Sub (`hl:candles:<coin>:<interval>`)

## Deeper detail — load on demand

- `tradebot-internals` skill — transpiler pipeline and supported Pine v5 subset,
  live feed flow, credential encryption format, plugin registry, beat schedule.
- `core` skill — workflow, coding standards, model routing, token budget.

## graphify

Knowledge graph at `graphify-out/`. For any codebase question run
`graphify query "<question>"` **before** grep or reading source
(`graphify path "<A>" "<B>"`, `graphify explain "<concept>"`). Read
`graphify-out/GRAPH_REPORT.md` only for broad architecture review. Run
`graphify update .` after modifying code. A PreToolUse hook enforces this.
