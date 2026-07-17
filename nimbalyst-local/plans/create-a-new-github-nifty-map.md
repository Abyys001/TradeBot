# Live Trading Module — Setup Wizard + Live Command Center

## Context

The product spec calls for a polished, secure Live Trading experience split into two
states: a step-by-step **Setup Wizard** (pre-deployment onboarding) and a **Live Command
Center** (post-deployment monitoring terminal). Today the app has no `/live` route — only an
orphan `PositionsPanel.vue` component and a backtest-focused `StrategyDetailView`.

Exploration confirmed the **backend is already complete** for everything the spec needs:
- Encrypted Hyperliquid credentials (AES-256-GCM) — `apps/credentials/`, create + `verify/`
- Pine v5 transpiler + validation — `apps/transpiler/`, `POST /strategies/{id}/validate/`
- Live engine (seed/warmup/incremental bar runner) over Celery — `apps/transpiler/live/`
- WebSocket streaming of `candle_tick`, `pnl`, `log`, `health` — `useDashboardWebSocket.ts`
- Kill-switch (`POST /me/kill-switch/`) + per-strategy positions (`GET /strategies/{id}/positions/`)
- Charting in `live` mode with execution markers — `TradingChart.vue`

So this branch is a **frontend assembly** of existing stores/components into the two-phase
UX, plus **one small backend endpoint** (close a single position) the spec requires but that
does not yet exist. The Command Center is a **multi-strategy dashboard** (monitors all live
strategies at once; wizard adds new ones).

Decisions confirmed with user: full frontend reusing backend · add close-single-position
endpoint · multi-strategy Command Center.

## Branch

Create and work on: `feature/live-trading-module` (off current `feature/roadmap-audit-fixes`).

---

## Backend (one small addition)

**Close a single position at market** — the per-position "Close at Market" icon in the spec.

1. `apps/exchange/hl_client.py` — add `close_position(cred, coin) -> dict` mirroring the
   per-coin block inside `close_all_positions()` (line 128-139): resolve, call
   `exchange.market_close(coin=normalize_coin(coin), sz=None)`, best-effort try/except.
2. `apps/strategies/views.py` — add `ClosePositionView(APIView)` following the
   `StrategyPositionsView` pattern (`_user_strategy`, credential guard). Body: `{ "coin": "BTC" }`.
   Calls the new `close_position`, writes an `ExecutionLog` (`event="position.closed_manual"`),
   returns the result.
3. `apps/strategies/urls.py` — add
   `path("strategies/<int:pk>/close-position/", ClosePositionView.as_view(), ...)`.

No new model/migration. Reuses existing `hl_client`, `ExecutionLog`, kill-switch enforcement.

---

## Frontend

### Routing & nav
- `frontend/src/router/index.ts` — add child route `path: 'live'`, name `live` →
  `views/LiveTradingView.vue`.
- `frontend/src/layouts/AppSidebar.vue` — add nav item `{ name:'live', path:'/live',
  label:'nav.live', icon:'live' } `(after` strategies`) + an inline SVG branch for` live`
  (e.g. pulse/activity icon). Add `nav.live` to `locales/en.json` + `fa.json`.

### `views/LiveTradingView.vue` (new — the orchestrator)
Top-level state machine: `mode = 'wizard' | 'command'`. On mount, fetch strategies; if any
strategy is `status==='active'`, default to `command`; else `wizard`. A "＋ New deployment"
button in the Command Center re-opens the wizard. The global header (`HealthHeader.vue`,
already in `AppLayout`) keeps the persistent **KILL SWITCH** — no duplicate needed.

### Phase 1 — `modules/live/wizard/` (new components)
A vertical stepper. Reuse `SliderInput.vue`, `PineMonacoEditor.vue`, `AppModal.vue`,
`useStrategyForm.ts` (already has symbols/timeframes/risk + drag-drop `onDrop`/`onFileInput`),
`useToast`. Steps:

- `WizardStepper.vue` — step rail + next/back; tracks completion per step.
- **Step 1 `StepCredential.vue`** — masked agent-key form. Reuse `credentials` store
  `create()` then `verify()`; render green "Connected to Mainnet/Testnet" badge from the
  `verify` result / `is_active`. Existing `AccountPanel.vue` is the field reference.
- **Step 2 `StepStrategy.vue`** — split UI: drag-drop `.pine` zone + "Open editor" →
  `PineMonacoEditor.vue`. On submit call `useStrategyForm.validate()` (saves + validates),
  show spinner, surface `validation_error` inline.
- **Step 3 `StepRisk.vue`** — symbol/timeframe pickers + `SliderInput` for leverage,
  position-size %, global stop-loss % (bound to `form.live_config.risk`). Saves via
  `useStrategyForm.save()`.
- **Step 4 `StepDeploy.vue`** — summary card of all params + glowing **Initialize Live
  Engine 🚀** button → `strategy.start(id)` (fires the Celery live task) → switch parent to
  `command` mode. Surfaces the `start` endpoint's `errors[]` if validation gates fail.

The wizard creates/updates **one** strategy via `strategy.createStrategy` / `updateStrategy`,
binding the chosen credential.

### Phase 2 — `modules/live/command/` (new components)
Multi-strategy monitoring layout inside `LiveTradingView`. Reuse heavily:

- `CommandCenter.vue` — grid: main chart + right rail (strategy list / PnL) + bottom terminal.
  Subscribe via existing `useDashboardWebSocket` (already streams `candle_tick`/`pnl`/`log`).
- **Strategy selector** — list of live strategies (`strategy.strategies` filtered
  `status==='active'`); selecting one drives the chart + positions context.
- **Chart** — `TradingChart.vue` with `mode="live"` + `:strategy-id`. Execution markers
  already flow through `chart` store (`fetchMarkers`/`applyCandleTick`).
- **Positions/PnL widget** — extend `modules/live/PositionsPanel.vue`: add Side, Entry,
  Mark, Liq, color-coded uPnL columns (fields already returned by `positions/` endpoint) and
  a per-row **Close at Market** icon → new `closePosition(strategyId, coin)` call (add to
  `strategy` store) → confirm via `AppModal`.
- **Audit terminal** — reuse `modules/terminal/AuditTerminal.vue` (no `strategyId` =
  all-strategy stream).
- **Kill switch** — already global in `HealthHeader`; ensure visible (it is, in `AppLayout`).

### Store touch-ups
- `stores/strategy.ts` — add `closePosition(id, coin)` → `POST /strategies/{id}/close-position/`.
- Add `LiveConfig.risk` already typed in `api/client.ts` — no type change needed.

---

## Verification

1. **Backend**: `python manage.py test apps.strategies apps.exchange` (smoke the new view/url);
   manually `curl -X POST /api/strategies/{id}/close-position/ -d '{"coin":"BTC"}'` against
   testnet creds returns a result dict and writes an `ExecutionLog`.
2. **Frontend build/lint**: `cd frontend && npm run build` (tsc) + `npm run lint`.
3. **End-to-end (testnet)**: `docker-compose up`; log in → `/live`:
  - Wizard: enter testnet agent creds → green Connected badge; paste a sample Pine from
     `apps/transpiler/samples/` → validates; set risk; **Initialize Live Engine** → transitions
     to Command Center, Celery live task starts (`docker-compose logs celery`).
  - Command Center: chart renders live candles via WS; trigger/await a fill → marker appears;
     positions widget shows uPnL; click **Close at Market** → position closes; terminal streams
     logs; header **KILL SWITCH** halts everything.
4. Confirm wizard↔command transition both directions ("New deployment" reopens wizard).

## Critical files
- New: `frontend/src/views/LiveTradingView.vue`, `frontend/src/modules/live/wizard/*`,
  `frontend/src/modules/live/command/*`
- Edit: `frontend/src/router/index.ts`, `frontend/src/layouts/AppSidebar.vue`,
  `frontend/src/modules/live/PositionsPanel.vue`, `frontend/src/stores/strategy.ts`,
  `frontend/src/locales/{en,fa}.json`
- Backend: `apps/exchange/hl_client.py`, `apps/strategies/views.py`, `apps/strategies/urls.py`
- Reuse (unchanged): `TradingChart.vue`, `AuditTerminal.vue`, `HealthHeader.vue`,
  `KillSwitchModal.vue`, `PineMonacoEditor.vue`, `SliderInput.vue`, `AppModal.vue`,
  `useStrategyForm.ts`, `useDashboardWebSocket.ts`, `stores/credentials.ts`, `stores/chart.ts`,
  `stores/terminal.ts`
