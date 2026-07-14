# TradeBot — Multi-Investor Copy-Trading Platform (Tabdeal) — Roadmap

## Context

We are turning TradeBot into a **managed copy-trading platform on Tabdeal**. The
operating model:

1. **You (admin)** create investor accounts (username/password) from a super-admin panel.
2. **Investors** log into their own panel, paste their **Tabdeal API key/secret**, and
   watch charts of their own profit/PnL.
3. **You** upload and **activate a Pine strategy in your panel**. When it fires, the trade
   **fans out to every active investor's Tabdeal futures account**, each sized off that
   investor's own equity.
4. **20% of each investor's profit** (configurable) is automatically accrued to a
   destination account you configure in your panel — tracked as a **ledger/accrual** with a
   **per-investor high-water mark** (agent/API keys are trade-only and cannot move funds
   on-chain, so collection is accounting-based, settled off-platform).

### Locked decisions (from planning Q&A)
- **Exchange:** Tabdeal (not Hyperliquid) — **Futures/perp** (`fapi`), supports long+short+leverage.
- **Signal source:** the **internal Pine engine** (`apps/transpiler`) — activate in admin panel. No TradingView needed.
- **Fan-out:** **auto-follow all active investors** with a verified Tabdeal credential + trading enabled.
- **Profit share:** **ledger/accrual**, **20% configurable**, **per closed trade + high-water mark**.

### What already exists (reuse — do NOT rebuild)
- **Auth:** session login, CSRF, `change-password`, forced `must_change_password` flow, `me`. `apps/accounts`, `apps/dashboard/views.py`.
- **Roles:** `User.role` (`admin`/`investor`) + `IsAdminRole`/`IsInvestorRole` in `apps/accounts/permissions.py` — **defined but not enforced anywhere yet**.
- **Credentials:** user-facing `ExchangeCredential` CRUD + AES-256-GCM at rest; Tabdeal fields `api_key_enc`/`api_secret_enc` and `set_api_credentials`/`get_api_key`/`get_api_secret` already exist (`apps/credentials/`).
- **Pine engine:** full transpiler + live runner (`apps/transpiler/live/runner.py`, `runtime/interpreter.py`) — exchange-agnostic signal generation. Only the broker layer is Hyperliquid-specific.
- **Fan-out data model:** `apps/copytrading/models.py` already has `CopySignal → CopySubscription → CopyOrder → CopyTrade (platform_share_amount) → EquitySnapshot`, including `platform_share_pct` default 20. **Models only — no views/tasks/logic.**
- **Risk + kill-switch:** `apps/risk`, `User.is_trading_enabled`, `emergency_stop_all_task`.
- **Frontend:** mature Vue 3 SPA — `LoginView`, per-user WebSocket, `EquityCurve.vue`, `StatCard.vue`, `AnalyticsView.vue`, `TradingChart.vue` (lightweight-charts), Pinia stores.
- **Tabdeal reference:** `Tabdeal_API_Reference.md` (1067 lines, real spec) + official `tabdeal-python` SDK.

### What must be built
1. Admin provisioning (create/manage investors) + role enforcement.
2. A **real Tabdeal futures client** (the current `apps/exchange/tabdeal_*.py` is an unverified, wrong-endpoint scaffold).
3. A **Tabdeal broker** behind a broker interface (today `LiveBroker` is Hyperliquid-hardcoded).
4. **Copy-trade fan-out** wiring the Pine runner to the `copytrading` models.
5. **Profit-share ledger** (20%, high-water mark, destination account).
6. **Investor profit dashboards** (largely assembling existing components).

---

## Target Architecture

```
Admin panel ──activate strategy──▶ Pine runner (single eval per closed candle)
                                          │ captures intended action (long/short/close)
                                          ▼
                                  Fan-out task (copytrading)
                     ┌────────────────────┼────────────────────┐
                     ▼                     ▼                     ▼
              TabdealBroker         TabdealBroker         TabdealBroker
              (investor A cred)     (investor B cred)     (investor C cred)
                     │ size = % of A's own equity          │
                     ▼                                     ▼
              Tabdeal Futures API (per investor)     CopyOrder / CopyTrade
                                                     + HWM → platform_share (20%)
                                                     → Ledger (destination account)
```

Key design choice: run the interpreter **once** per candle using a **`SignalCaptureBroker`**
(records `entry/close/exit` intents without placing orders — like `WarmupBroker` but
capturing), then a fan-out step replays the captured action against each investor's
`TabdealBroker`. This avoids N interpreter runs and keeps per-account sizing/risk isolated.

---

## Phased Roadmap

### Phase 0 — Roles & admin provisioning
**Goal:** you can create investor accounts; admin/investor APIs are separated.
- Enforce roles: apply `IsAdminRole` (`apps/accounts/permissions.py`) to admin-only endpoints; keep investor endpoints user-scoped.
- **Admin user-management API** (new `apps/accounts` viewset, admin-only): create investor (username, temp password, `role=investor`, `must_change_password=True`, `is_trading_enabled` toggle), list/reset-password/disable. Reuse existing `change_password_view` for the investor's first-login flow.
- Add `role`/`must_change_password` to `CustomUserAdmin` fieldsets (`apps/accounts/admin.py`).
- **Frontend:** admin-only "Investors" view (create/list/reset), gated on `auth.user.role === 'admin'`; extend `frontend/src/stores/auth.ts` + router guard.
- **Files:** `apps/accounts/{views,serializers,urls,admin}.py`; `frontend/src/views/admin/InvestorsView.vue` (+ store, nav in `AppSidebar.vue`).

### Phase 1 — Tabdeal futures client
**Goal:** we can verify a credential and place/close a futures order on one account.
- Adopt official **`tabdeal-python`** SDK (add to `requirements.txt`) OR finish the scaffold against `Tabdeal_API_Reference.md`. **Recommendation: use the official SDK** (`tabdeal.future.Future`) to avoid endpoint/signing drift; keep `tabdeal_rate_limit.py` (`signed_action`, nonce lock) as the throttle wrapper.
- Build `TabdealFuturesClient` (in `apps/exchange/`): `verify_credentials`, `get_balance` (futures, field `freeze` not `locked`), `get_positions` (`/r/fapi/v3/positionRisk`), `set_leverage` (`POST /fapi/v1/leverage`), `place_market_order` (`POST /fapi/v1/order`), `place_tpsl` (`POST /fapi/v1/positionSlTp`), `close_position`.
- **Fix credential verification:** branch `apps/credentials/views.py` + `tasks.py` on `exchange == TABDEAL` to call the Tabdeal verifier instead of the Hyperliquid `verify_credential`.
- Delete/replace the misleading scaffold (`tabdeal_client.py` wrong host `api.tabdeal.org` → `api1.tabdeal.org`, wrong read paths).
- **Files:** `apps/exchange/tabdeal_futures.py` (new), `apps/credentials/{views,tasks}.py`, `config/settings/base.py` (Tabdeal settings), `requirements.txt`.

### Phase 2 — Broker abstraction + Tabdeal broker
**Goal:** the Pine engine can route to Tabdeal, and we can capture signals for fan-out.
- Extract a minimal **broker interface** from `LiveBroker` (`apps/transpiler/runtime/order_router.py`): `entry(side, qty, ...)`, `close(...)`, `exit(...)`, `last_action`.
- Build **`TabdealBroker`** implementing that interface against `TabdealFuturesClient`, with per-account sizing (percent-of-equity read from that investor's Tabdeal balance), leverage from `strategy.live_config`, and per-account risk gate (`apps/risk`) + kill-switch (`credential.user.is_trading_enabled`).
- Build **`SignalCaptureBroker`** (records intended actions only) for the single-eval fan-out path.
- **Files:** `apps/transpiler/runtime/order_router.py` (+ new `tabdeal_broker.py`, `signal_capture_broker.py`), `apps/execution/models.py` (persist to `CopyOrder` for copy trades).

### Phase 3 — Copy-trade fan-out
**Goal:** activating a strategy in the admin panel trades every active investor's account.
- On strategy **activate** (`apps/strategies/views.py::StartStrategyView`): create/refresh a `CopySignal` for the strategy and **auto-create `CopySubscription`s for all active investors** who have a verified Tabdeal credential + `is_trading_enabled`. (Add a nightly/enable-time reconcile so new investors auto-join.)
- Refactor the runner: in `apps/transpiler/live/runner.py::_process_one`, run interpreter once with `SignalCaptureBroker`, then enqueue a **`fan_out_signal_task`** (new, in `apps/copytrading/tasks.py`) that iterates active subscriptions and dispatches the captured action via `TabdealBroker`, writing `CopyOrder`/`CopyTrade` and pairing entry→exit into round-trips.
- Respect per-investor sizing (`position_size_pct` / `risk_factor`) and risk gates; skip investors whose kill-switch is off or credential failed verify.
- Build `apps/copytrading/{views,urls,tasks}.py` (currently empty `urls.py`).
- **Files:** `apps/copytrading/{tasks,views,urls}.py`, `apps/strategies/views.py`, `apps/transpiler/live/runner.py`.

### Phase 4 — Profit-share ledger (the 20%)
**Goal:** 20% of each investor's realized profit accrues to your destination account, with HWM.
- **Destination account config:** admin-set in panel (new `PlatformFeeConfig`: `share_pct` default 20, destination label/account). "the account I enter in my panel."
- **High-water mark** per `CopySubscription` (track peak realized equity). On `CopyTrade` close: compute `gross_pnl`; if it lifts the subscription above its HWM, take `share_pct` of the new profit → `platform_share_amount`; update HWM. No charge while recovering a drawdown.
- **Ledger:** new `FeeLedgerEntry` (subscription, trade, amount, accrued_at, settled_at, status) → running "owed" balance per investor and platform total. Reuse existing `CopyTrade.platform_share_amount`/`gross_pnl` fields.
- Surface balances in both panels; export/settlement marking (off-platform settlement per locked decision).
- **Files:** `apps/copytrading/models.py` (+ `PlatformFeeConfig`, `FeeLedgerEntry`, HWM field/migration), `apps/copytrading/{tasks,views}.py`.

### Phase 5 — Investor & admin dashboards / charts
**Goal:** investors monitor their profit; admin monitors all investors + fees.
- **Investor panel:** equity curve (from `EquitySnapshot` via periodic `capture_equity_task`), realized/unrealized PnL, per-strategy performance, open positions, fees owed. Reuse `EquityCurve.vue`, `StatCard.vue`, `AnalyticsView.vue`, `TradingChart.vue`; new copytrading Pinia store + REST endpoints in `apps/copytrading/views.py`.
- **Admin overview:** all investors (AUM proxy = summed Tabdeal balances), total accrued fees, per-investor status, active strategies. Extend `apps/dashboard/overview.py`.
- Reuse the per-user WebSocket (`apps/dashboard/publish.py`, `useDashboardWebSocket.ts`) to push PnL/equity ticks.
- **Files:** `apps/copytrading/views.py`, `apps/dashboard/overview.py`, `frontend/src/{views,modules,stores}/...`.

### Phase 6 — Hardening
- Tabdeal order **reconciliation** (parallel to `apps/execution/order_sync.py`) — poll fills, update `CopyOrder`/`CopyTrade`.
- Idempotency (client order IDs), partial fills, rate-limit backoff, per-account error isolation (one investor failing must not block others).
- Testnet/dry-run mode + a paper fan-out path for validation before real keys.
- Telegram/Signum alerts on fan-out events (reuse `apps/telegram`, `apps/integrations`).

---

## Critical files
- Reuse/extend: `apps/copytrading/models.py`, `apps/accounts/permissions.py`, `apps/credentials/{models,views,serializers}.py`, `apps/transpiler/live/runner.py`, `apps/transpiler/runtime/order_router.py`, `apps/risk/`, `apps/dashboard/{overview,publish}.py`.
- New: `apps/exchange/tabdeal_futures.py`, `apps/transpiler/runtime/tabdeal_broker.py` + `signal_capture_broker.py`, `apps/copytrading/{views,urls,tasks}.py`, admin investor viewset in `apps/accounts/`.
- Reference: `Tabdeal_API_Reference.md`.

## Verification
- **Unit:** Tabdeal signing/error parsing (extend `apps/exchange/test_tabdeal.py`); HWM + 20% fee math; fan-out sizing.
- **Integration (testnet/sandbox Tabdeal keys):** create investor via admin API → investor logs in, changes password, adds Tabdeal key → verify succeeds → activate a shorting Pine strategy in admin panel → confirm a futures order lands on each investor account → close → confirm `CopyTrade`, HWM update, and 20% ledger accrual.
- **E2E UI:** drive the flow in the browser (login, add key, admin activate, watch investor equity curve/PnL update over WebSocket) — use the `verify` skill / browser MCP.
- **Regression:** existing Hyperliquid path and `pytest apps/transpiler apps/exchange apps/credentials` stay green (broker refactor must not break the HL `LiveBroker`).

## Key risks / constraints
- **No on-chain fee sweep:** trade-only keys can't move funds → 20% is a ledger, settled off-platform (locked decision).
- **Tabdeal API unknowns:** confirm futures endpoints/leverage/TP-SL against `Tabdeal_API_Reference.md` + SDK before live use; test on small size first.
- **Broker refactor risk:** keep `LiveBroker` (Hyperliquid) working while introducing the interface — both must coexist.
- **Per-account isolation:** one investor's failure/rate-limit must not halt the fan-out for others.
