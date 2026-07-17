# Algo Trader — Master Roadmap

**What this is:** the single end-to-end path from where your codebase stands today to a
platform you can safely run with real investors and real money on Tabdeal.

**The product in one sentence:** admins upload & activate a Pine strategy → the internal
Pine engine generates one signal per closed candle → the signal fans out to every active
investor's own Tabdeal futures account (sized off *their* equity) → 20% of each investor's
realized profit (above a high-water mark) accrues to your destination account as a ledger
entry → both sides watch their own profit charts.

> **Read this first.** A large part of this system is *already built* (see §1). The real
> work remaining is not "write the features" — it is **verify, harden, secure, deploy, and
> make it compliant**. That is what turns a working prototype into a professional product.

---

## 1. Where you are today (honest current-state snapshot)

Based on the code in the project, these are effectively **done or mostly done**:

| Area | Status | Evidence in repo |
|---|---|---|
| Auth: session login, CSRF, forced first-login password change, `me` | ✅ Done | `apps/accounts/views.py` |
| Roles (`admin` / `investor`) + `IsAdminRole` / `IsInvestorRole` | ✅ Defined + used | `apps/accounts/permissions.py` |
| Admin creates/lists/resets/disables investors | ✅ Done | `InvestorViewSet`, `InvestorsView.vue` |
| Encrypted Tabdeal credentials (AES-256-GCM at rest) | ✅ Done | `apps/credentials/` |
| Tabdeal Futures REST client (signing, errors, order/close/SL-TP) | ✅ Done + tested | `apps/exchange/tabdeal_futures.py`, `test_tabdeal.py` |
| Credential verification branches to Tabdeal | ✅ Done | `verify_tabdeal_credential` |
| Pine transpiler + live runner (exchange-agnostic signals) | ✅ Done | `apps/transpiler/` |
| `TabdealBroker` (per-account sizing/leverage/risk) | ✅ Present | referenced in `apps/copytrading/tests.py` |
| Fan-out subscriptions (auto-follow active investors) | ✅ Done | `apps/copytrading/subscriptions.py` |
| Profit-share ledger: 20% configurable, per-investor high-water mark | ✅ Done + tested | `apps/copytrading/fees.py`, `FeeLedgerEntry`, `PlatformFeeConfig` |
| Admin fee config (share %, destination account) | ✅ Done | `CopyTradingView.vue`, `apps/copytrading/views.py` |
| Admin overview (per-investor realized PnL, fees accrued/owed) | ✅ Done | `AdminCopyOverviewView`, `AdminFeeLedgerView` |
| Risk gate + emergency kill-switch | ✅ Present | `apps/risk`, `emergency_stop_all_task` |
| Vue 3 SPA with equity curves, stat cards, per-user WebSocket | ✅ Done | `EquityCurve.vue`, `TradingChart.vue`, etc. |

**Conclusion:** the feature build described in your message is ~80% implemented. The
remaining 20% is the part that decides whether this works "professionally": end-to-end
verification against the real exchange, hardening, security, deployment, monitoring, and
compliance. The rest of this document is that path.

---

## 2. The critical path (do these in order)

```
Stage A  Verify the money path end-to-end on ONE real (small) account
Stage B  Harden execution (reconciliation, idempotency, error isolation)
Stage C  Security & secrets hardening
Stage D  Compliance / legal / custody model  ← do NOT skip; blocks going live
Stage E  Deployment & infrastructure
Stage F  Monitoring, alerting, backups, runbooks
Stage G  Controlled rollout (paper → 1 investor → small cohort → open)
```

Everything below expands each stage into concrete tasks with a **"Done when"** bar so you
always know whether a stage is truly finished.

---

## Stage A — Verify the money path end-to-end (highest priority)

You have the parts; you have **not yet proven they work together against the live Tabdeal
API with real fills.** Until this is done, nothing else matters. Use a **dedicated test
account with a tiny balance** (e.g. the equivalent of a few dollars) and the smallest
possible position sizes.

### A1. Single-account smoke test (no fan-out yet)
- Create one Tabdeal API key (trade-enabled, **withdrawals disabled**). Activate futures on
  it once (set leverage — recall error `1207` means futures not yet active).
- Run the full sequence manually against the real API through `TabdealFuturesClient`:
  `verify_credentials` → `get_balance` → `set_leverage` → `place_market_order` (min qty) →
  `get_positions` → `set_position_sl_tp` → `close_position` → `user_trades`.
- **Done when:** a real order opens, a SL/TP attaches, the position closes, and the realized
  PnL you compute matches what Tabdeal shows in its own UI.

### A2. One-investor fan-out test
- Create one investor via the admin panel; that investor logs in, changes password, pastes
  the Tabdeal key; verify it turns green.
- Activate a simple Pine strategy in the admin panel (something that fires quickly, e.g. a
  short SMA cross on a fast timeframe, or a forced test signal).
- **Done when:** activating the strategy produces a real futures order on the investor's
  account, and a `CopyOrder` + `CopyTrade` are written correctly.

### A3. Round-trip + fee math verification
- Let a trade open and close. Confirm entry→exit are paired into one `CopyTrade`, `gross_pnl`
  is correct, the high-water mark updates, and — only if the trade lifted cumulative profit
  above the prior HWM — a `FeeLedgerEntry` of exactly `share_pct%` of the *new* profit is
  created.
- Verify a *losing* trade followed by a partial recovery charges **no** fee until the old
  peak is exceeded (this is the whole point of the HWM).
- **Done when:** the numbers in the admin overview and the ledger match a hand calculation
  for at least 3 scenarios: win, loss, loss-then-recovery.

### A4. Sizing correctness across different equities
- Give two test accounts different balances. Confirm each account's position size is a
  correct percentage of **its own** equity, not a shared absolute size.
- **Done when:** account with 2× the equity opens ~2× the notional, within precision limits.

> **Exit criteria for Stage A:** you have watched money move correctly, in and out, on real
> accounts, with correct PnL and correct fee accrual. Screenshot/log everything.

---

## Stage B — Harden execution (make it reliable, not just working)

A single successful trade is not a product. These are the failures that hurt real users.

### B1. Order reconciliation
- Build a Tabdeal reconciliation loop parallel to `apps/execution/order_sync.py`: poll open
  orders / recent `user_trades`, update `CopyOrder`/`CopyTrade` from the exchange's truth,
  and detect fills you missed (e.g. process restarted mid-trade).
- **Done when:** killing the worker mid-trade and restarting it leaves the DB consistent with
  the exchange within one poll cycle.

### B2. Idempotency
- Attach a unique `clientOrderId` per intended order so a retried request can't double-open
  (Tabdeal returns error `1213` on a duplicate `clientOrderId` — treat that as "already
  placed", not a failure).
- **Done when:** a forced retry of the same signal never produces two positions.

### B3. Per-investor error isolation
- One investor's failure (bad key, insufficient balance `1218`/`1209`, futures not active
  `1207`, rate limit `1216`) must **not** block the fan-out to everyone else. Catch,
  record on that investor's `CopyOrder`, alert, continue.
- **Done when:** with 3 investors where #2 has an invalid key, #1 and #3 still trade and #2
  is flagged with a clear reason.

### B4. Partial fills & precision
- Handle `PARTIALLY_FILLED`, round quantity/price to the symbol's `pricePrecision` /
  `quantityPrecision` from `exchange_info`, and respect min-notional filters (error `1208`).
- **Done when:** small accounts near the minimum order size either trade cleanly or are
  skipped with a clear "below minimum" reason — never rejected silently.

### B5. Rate-limit backoff
- Wrap signed calls with exponential backoff on `1216`; keep the existing nonce lock /
  throttle wrapper.
- **Done when:** fanning out to N investors in a burst never trips a sustained rate-limit
  error.

### B6. Kill-switch verification
- Confirm the emergency stop actually disables trading, halts strategies, and closes
  positions across **all** accounts, and that a per-investor `is_trading_enabled=false`
  removes just that investor from fan-out.
- **Done when:** hitting the kill switch during an open position flattens everyone.

> **Exit criteria for Stage B:** you can lose a worker, hit a rate limit, and have one bad
> investor in the batch — and the system stays correct and keeps serving everyone else.

---

## Stage C — Security & secrets hardening

You are custodying trade-enabled API keys for other people's money. Treat this like it
matters, because a leak here is catastrophic.

- **Key permissions:** enforce/instruct that investor Tabdeal keys are **trade-only with
  withdrawals disabled**. Document it in the investor onboarding UI. This is your single
  biggest protection: even a full breach can't move funds off the exchange.
- **Encryption key management:** the AES key that decrypts stored credentials must live in a
  secrets manager or env-injected secret, **never** in the repo or DB. Rotate procedure
  documented.
- **Transport & session:** HTTPS only, secure + httpOnly + SameSite cookies, CSRF on all
  state-changing routes (you already have CSRF — verify it's enforced everywhere), strict
  CORS.
- **Authorization audit:** confirm **every** admin endpoint has `IsAdminRole` and every
  investor endpoint is scoped to `request.user`. Write a test that a logged-in investor
  cannot hit any admin route or read another investor's PnL/ledger.
- **Rate-limit auth endpoints:** throttle login and password reset to stop brute force.
- **Password policy:** enforce Django validators; keep the forced first-login change.
- **Secrets in logs:** verify API keys/secrets are never logged (the client already logs only
  the exception *type* on verify failure — keep that discipline everywhere).
- **Dependency scanning:** run `pip-audit` / `npm audit` in CI; pin versions.
- **Audit trail:** log who activated/deactivated strategies, changed fee config, changed the
  destination account, reset passwords, or toggled trading — with timestamp and actor.

> **Done when:** an external checklist (or a security-minded friend) can't find an admin
> route without a role check, a key in a log, or the encryption key in the repo.

---

## Stage D — Compliance, legal & custody model (do not skip)

This is the part most likely to sink the project if ignored, and it isn't a coding task.
**I'm not a lawyer and this isn't legal advice — but a professional roadmap has to name
these risks so you can get proper advice before real money is involved.**

- **You are handling other people's money for profit and taking a fee.** In most
  jurisdictions, pooling or managing investor funds and charging a performance fee is a
  *regulated activity* (asset management / investment advisory / collective investment).
  Doing it without the right registration or licence can carry serious penalties. Get a
  qualified local lawyer to tell you what applies to you and your investors.
- **Custody model matters — and yours is actually the safer one.** Because keys are
  trade-only and funds stay in each investor's own Tabdeal account, you never take custody
  and can't withdraw. Keep it that way. Your 20% is collected **off-platform** as an
  accounting ledger, exactly as designed. Never build a withdrawal path.
- **Investor agreement:** every investor must accept written terms covering: the fee (20%
  above high-water mark), that trading is high-risk and losses are possible, that they retain
  custody, how and when the fee is settled, and how they can stop/withdraw. Add a click-through
  acceptance in onboarding and store the acceptance record.
- **Tabdeal-specific:** confirm Tabdeal's Terms of Service permit third-party managed/copy
  trading via API and automated bots. Confirm the regulatory/sanctions context of the
  exchange and your investors' jurisdictions with your lawyer.
- **Tax & records:** keep exportable per-investor records of trades, PnL, fees accrued, and
  fees settled (your ledger already supports this — make sure it exports cleanly).
- **KYC:** decide whether you need to identify investors; Tabdeal already KYCs the account
  holders, but *you* accepting their funds-management may create your own obligation.

> **Done when:** you have written terms accepted by each investor, a lawyer's sign-off on your
> model in your jurisdiction, and confirmation Tabdeal's ToS allows what you're doing.

---

## Stage E — Deployment & infrastructure

Move off "runs on my laptop" to something that survives restarts and doesn't lose trades.

- **Processes:** Django/ASGI app, Celery workers, Celery beat (scheduler), Redis (broker +
  channels/WebSocket), Postgres (not SQLite in production). Containerize with Docker Compose
  or deploy to a small managed platform.
- **Time sync:** the host clock **must** be tightly NTP-synced — Tabdeal rejects requests
  whose timestamp is off (`1101`/`1102`). This is a common, silent cause of "everything
  fails."
- **Config via env:** all secrets and hosts (`api1.tabdeal.org`, DB, Redis, encryption key)
  from environment, separate settings for dev/staging/prod.
- **Migrations:** run migrations on deploy; never edit the DB by hand.
- **Zero-loss restarts:** a deploy or crash mid-trade must not orphan a position — this is why
  Stage B reconciliation comes first.
- **Static/frontend:** build the Vue SPA and serve it behind the same domain; WebSocket
  endpoint reachable through your proxy (nginx/Caddy) with correct upgrade headers.

> **Done when:** you can `deploy`, reboot the box, and the system reconnects, reconciles, and
> keeps trading with no manual intervention.

---

## Stage F — Monitoring, alerting, backups & runbooks

- **Health checks:** feed freshness, Celery liveness, trading on/off, DB, Redis — you already
  surface some of this in the UI; wire it to alerts.
- **Alerting:** on fan-out errors, credential-verify failures, rate limits, worker death,
  reconciliation mismatches — push to Telegram (you already have `apps/telegram`) and/or
  email.
- **Metrics/dashboards:** trades/day, fill rate, error rate, per-investor equity, total AUM
  proxy, fees accrued vs settled.
- **Backups:** automated Postgres backups + a **tested** restore. A backup you haven't
  restored is not a backup.
- **Runbooks:** short written procedures for: "an investor's key stopped working", "the kill
  switch was hit", "the clock drifted", "a deploy went bad", "reconciliation shows a
  mismatch."

> **Done when:** something breaks at 3am and an alert tells you what, and a runbook tells you
> how to fix it.

---

## Stage G — Controlled rollout

Never flip straight to many investors with real money.

1. **Paper / dry-run:** a mode that runs the whole pipeline but doesn't place real orders —
   validate signals, sizing, and ledger math end-to-end with no risk.
2. **One real investor, tiny balance:** you or a fully-informed friend. Run for days across
   real market conditions.
3. **Small cohort (3–5):** verify error isolation and fee settlement with real people and a
   real settlement cycle.
4. **Open up gradually**, watching the monitoring from Stage F.

> **Done when:** you've completed a full real settlement cycle (accrue 20% → mark settled) with
> a small cohort and nobody hit a surprise.

---

## 3. Recommended immediate next actions (this week)

1. **Stage A1–A2**: prove one real order + one real fan-out on a tiny test account. This is
   the highest-value thing you can do and it de-risks everything else.
2. **Stage A3**: verify the 20% high-water-mark math against a hand calculation.
3. **Stage C authorization audit**: write the test that an investor can't reach admin routes
   or another investor's data. Cheap, high-impact.
4. **Stage D**: start the legal/compliance conversation *now* — it has the longest lead time
   and can block launch regardless of how good the code is.

---

## 4. Reference map (where things live)

- **Exchange spec:** `Tabdeal_API_Reference.md` — base host `https://api1.tabdeal.org`, FAPI is
  Binance-Futures-shaped, HMAC-SHA256 signing, timestamps in **milliseconds**, read paths use
  the `r/` prefix.
- **Tabdeal client:** `apps/exchange/tabdeal_futures.py` (+ `tabdeal_signing.py`,
  `tabdeal_errors.py`, `test_tabdeal.py`).
- **Fan-out & fees:** `apps/copytrading/{models,subscriptions,fees,views,tasks}.py`.
- **Pine engine:** `apps/transpiler/live/runner.py`, `runtime/` (broker interface + brokers).
- **Roles/auth:** `apps/accounts/`. **Risk/kill-switch:** `apps/risk/`.
- **Frontend:** `frontend/src/views/admin/{InvestorsView,CopyTradingView}.vue`, shared chart
  components, per-user WebSocket store.

---

### One caution worth repeating
The technology here is largely built and the *safe* custody model (trade-only keys, funds stay
with investors, fee tracked off-platform) is already the right choice — keep it. The two things
most likely to turn this from a working prototype into a real, professional product are
**(1) proving the money path end-to-end on real accounts (Stage A)** and **(2) getting the
legal/compliance model right before real investors join (Stage D)**. Do those two in parallel
with the hardening work and you're on a solid path.
