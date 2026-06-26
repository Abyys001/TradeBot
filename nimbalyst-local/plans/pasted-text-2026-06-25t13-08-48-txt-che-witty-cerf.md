# TradeBot — Full Feature Audit, Fixes & Completion Roadmap

## Context

User pasted an 8-phase roadmap for a pro Hyperliquid algo-trading framework and asked: "check all these features, make sure they work, are good quality, and work well." User then chose: **verify + fix existing + build missing**, verified via **run test suite + manual app QA + add missing tests + add CI**.

Surprise from exploration: the backend is **far more complete than expected** — effectively all 8 roadmap phases have working backend code, including Phase 4 (`apps/optimizer/`: grid, walk-forward, monte-carlo, portfolio) and Phase 8 (`apps/pro/`: versioning, journal, marketplace, replay). The real gaps are **quality, test coverage, and missing frontend** for the advanced phases — not missing core logic.

Goal: bring every roadmap feature to a verified, tested, usable state. No architecture rewrite — the foundations are sound.

## Current State (audit result)

Status legend: ✅ done & tested · 🟡 works but thin/untested · 🔴 backend-only, no UI · ⛔ stub

| Phase | Feature area | Backend | Frontend | Tests | Verdict |
|---|---|---|---|---|---|
| 1 | Data: downloader, incremental sync, validation, gap detect, Parquet+PG, multi-TF | ✅ | ✅ DataView | ✅ exchange (17) | Solid |
| 2 | Backtest: candle/fee/slippage/leverage/liquidation/funding sim, metrics | ✅ | ✅ | ✅ transpiler (44) | Solid; multi-asset only via loop |
| 2 | Strategy engine (plugin: Pine ✅, AI ⛔), indicators (30+) | ✅ | ✅ | ✅ | AI engine = `NotImplementedError` (expected) |
| 2 | Risk mgr: fixed/pct risk, daily loss, max DD, max trades/exposure, leverage | ✅ `apps/risk/` | partial (config form) | 🔴 **0 tests** | Untested |
| 2 | Paper trading | ✅ `apps/paper/` | ✅ paper module | 🔴 **0 tests** | Untested |
| 2 | Performance metrics (winrate, PF, Sharpe, DD, avg, R:R) | ✅ | ✅ MetricsCards | ✅ | Solid |
| 3 | HL integration: place/cancel/leverage, account monitor, order sync | ✅ | ✅ live module | 🟡 partial (no live integ tests) | Good; no native order-modify (cancel+reorder) |
| 3 | Order types: market/limit/stop/TP | ✅ (stop-limit ✗) | ✅ | 🟡 | Stop-limit not implemented |
| 3 | Position monitor: PnL, margin, funding | ✅ | ✅ PositionsPanel | 🟡 | Live liq-price queried not computed |
| 4 | Optimizer: grid, walk-forward, monte-carlo | ✅ `apps/optimizer/` | 🔴 **none** | 🔴 **0 tests** | API wired, no UI, untested |
| 5 | Portfolio: multi-asset backtest | 🟡 thin (no correlation/shared equity) | 🔴 **none** | 🔴 **0 tests** | Independent per-asset only |
| 5 | Portfolio metrics: exposure, correlation, portfolio DD/Sharpe | ⛔ missing | 🔴 | 🔴 | Not implemented |
| 6 | AI signal engine, market regime | ⛔ stub | 🔴 | 🔴 | Out of scope unless prioritized |
| 7 | Dashboard: equity curve, positions, trades, PnL, DD | ✅ | ✅ | 🔴 API untested | Good |
| 7 | Analytics: best/worst ✅, monthly 🟡, funding-cost UI ⛔, winrate-by-asset ⛔ | 🟡 | 🟡 AnalyticsView | 🔴 | Gaps |
| 7 | Visual backtest markers: entry/exit ✅, SL/TP ⛔ | 🟡 | 🟡 TradingChart | 🔴 | SL/TP not drawn |
| 8 | Versioning, journal, marketplace, replay | ✅ `apps/pro/` | 🔴 **none** | 🔴 **0 tests** | API wired, no UI; replay = no step endpoint |
| infra | Docker compose (7 svc) | ✅ | — | — | No web/worker healthchecks |
| infra | CI/CD | ⛔ | — | — | None |
| infra | Frontend unit tests | — | ⛔ **0 tests** | — | None |

**Apps with zero tests:** `optimizer`, `pro`, `paper`, `risk`, `execution`, `accounts`, `dashboard`, `strategies`.
**Only stub:** `apps/strategies/plugins/ai.py:15` (acceptable — Phase 6 future).

## Workstreams

Ordered for fast value. Each stream is independently shippable.

### A. Baseline verification (do first — establishes ground truth)
1. Run full backend suite: `pytest -q` (pytest.ini → `config.settings.dev`). Record pass/fail per module. Fix any reds before touching anything else.
2. Manual app QA via `docker-compose up`: login → create Pine strategy → validate → run backtest → view chart markers + metrics → start paper → check positions/PnL/WS live updates. Drive UI with Playwright MCP; screenshot each flow. Log every defect found into the tracker.

### B. Backend test coverage (close the 0-test apps)
Add `tests.py` per app following existing patterns in `apps/transpiler/tests.py` & `apps/exchange/tests.py` (pytest-django, mocked HL SDK):
- `apps/risk/` — gates: daily-loss halt, max-DD halt, max-trades/exposure/leverage rejects, sizing (fixed vs pct). Pure functions, high ROI.
- `apps/optimizer/` — `grid_search` ordering, `walk_forward` window math, `monte_carlo_equity` percentiles, `portfolio_backtest` aggregation. Use a tiny synthetic df.
- `apps/paper/` — virtual balance updates, sim fills, equity from broker.
- `apps/execution/` — `order_sync` fill aggregation / weighted avg, OrderRecord state transitions.
- `apps/pro/` — versioning increments, journal CRUD, marketplace publish/list, replay session create.
- `apps/dashboard/` — `/api/overview/`, `/api/analytics/`, `/api/markers/` (entry/exit + new SL/TP) endpoint contract tests.
- `apps/transpiler/live/session_store.py` — Redis save/load/restore round-trip (fakeredis).
- Kill switch + emergency stop path.

### C. Quality fixes to existing features
- **SL/TP chart markers**: extend `apps/dashboard/views.py` markers endpoint to emit stop/limit levels from `BacktestTrade`; render distinct shapes in `frontend/.../TradingChart.vue` (reuse existing marker pipeline at `TradingChart.vue:97-108`).
- **Analytics gaps** (`apps/dashboard/views.py` + `AnalyticsView.vue`): add monthly P&L bucketing, win-rate-by-asset aggregation, and surface `funding_paid` metric card (metric already computed in `metrics.py`, just hidden).
- **Portfolio depth** (`apps/optimizer/portfolio.py`): add shared-equity option + portfolio-level metrics (total exposure, correlation matrix of per-asset returns, portfolio DD/Sharpe). Reuse `apps/transpiler/metrics.py`.
- **Replay step** (`apps/pro/`): add `advance`/`step` endpoint so ReplaySession cursor moves bar-by-bar (currently only creates a row).
- **Hard HL-API features (all in scope, confirmed):**
  - **Stop-limit orders** — add as new order type alongside market/limit/stop/TP in `apps/transpiler/runtime/order_router.py` (live) + `sim_broker.py` (backtest); expose via Pine `strategy.exit`/entry params; round price/size via `hl_meta`.
  - **Live liquidation price** — compute live (notional, leverage, maintenance margin) rather than only reading HL margin summary; surface in `PositionsPanel.vue`. Reuse backtest formula in `sim_broker.py:176`.
  - **Move SL/TP post-entry** — allow modifying stop/take-profit on an open position via cancel+replace of reduce-only trigger orders (`order_router.py:381` `_place_perp_tpsl`); add strategy API + endpoint.
- **Remove AI engine entirely** (user: not wanted): delete `apps/strategies/plugins/ai.py`, drop AI from `plugins/registry.py`, remove any AI engine option in strategy create/configure UI and serializers/migrations as needed. After removal, no `NotImplementedError` remains in codebase.

### D. Build missing frontend (Phase 4/5/8 backend has no UI)
New views + router entries (`frontend/src/router/index.ts`) + `api/client.ts` helpers:
- **Optimizer view**: param-grid builder → POST `/api/optimize/grid`, walk-forward, monte-carlo; results table + equity distribution chart (reuse `EquityCurve.vue`, `display`-style charts).
- **Portfolio view**: multi-asset selection → portfolio backtest + metrics.
- **Pro/Journal**: trade journal list+create (reason/result/screenshot/tags); strategy version history + restore; replay player UI; marketplace browse/publish.
Wire into `AppLayout` nav.

### E. Frontend tests
Add Vitest + Vue Test Utils (currently zero). Cover: stores (`chart`, `strategy`, `backtest`), `useDashboardWebSocket` routing/reconnect, critical components (MetricsCards, TradingChart marker mapping, StrategyConfigurator validation).

### F. CI + infra
- `.github/workflows/ci.yml`: matrix → ruff/flake lint, `pytest`, frontend `npm ci && vitest && build`, docker build. Spin Postgres+Redis service containers for backend tests.
- Add healthchecks for `web`/`celery` in `docker-compose.yml`; optional resource limits.

## Sequencing (roadmap)

1. **Stream A** — verify, get green baseline, log defects. *(gate: nothing else until suite is green)*
2. **Stream B** + **Stream F (CI)** in parallel — lock in coverage so future work can't regress.
3. **Stream C** — quality fixes (each independently verifiable).
4. **Stream D** — frontend for advanced phases.
5. **Stream E** — frontend tests, fold into CI.
6. AI engine (Phase 6) **removed** per user — no work, just deletion in Stream C.

## Critical files

- Backend logic: `apps/optimizer/{grid,walk_forward,monte_carlo,portfolio}.py`, `apps/pro/{models,views}.py`, `apps/risk/{gates,manager,sizing,config}.py`, `apps/dashboard/views.py`, `apps/transpiler/metrics.py`, `apps/transpiler/live/session_store.py`.
- Frontend: `frontend/src/router/index.ts`, `frontend/src/api/client.ts`, `frontend/src/views/AnalyticsView.vue`, `frontend/src/modules/chart/TradingChart.vue`, `frontend/src/modules/backtest/{EquityCurve,MetricsCards}.vue`, `frontend/src/layouts/AppLayout.vue`.
- Infra: `docker-compose.yml`, new `.github/workflows/ci.yml`, new `frontend/vitest.config.ts`.
- URLs already wired: `config/urls.py` (optimizer + pro included).

## Verification

- **Per stream**: `pytest -q` stays green; new tests assert the specific behavior added.
- **Frontend**: `vitest run` green; `npm run build` succeeds.
- **End-to-end manual** (Playwright MCP on `docker-compose up`): backtest flow shows SL/TP markers; analytics shows monthly + per-asset + funding; optimizer grid returns ranked results in UI; portfolio view aggregates; journal entry persists; replay steps a bar. Screenshot each.
- **CI**: workflow passes on a test PR (lint + backend + frontend + build).
- Final: re-walk the audit matrix above — every 🔴/🟡/⛔ targeted this round flips to ✅.

## Decisions locked
- Stop-limit, live liquidation-price, post-entry move-SL/TP: **all in scope** (Stream C).
- AI engine (Phase 6): **removed entirely**, not built.
