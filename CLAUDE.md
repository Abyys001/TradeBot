# WalletManager_CopyTrader

Order-routing / execution layer. The admin trades once through one interface;
every action (entry, SL/TP change, close) fans out over API to N connected
accounts across ~10 exchanges, each account an isolated connection.

**Not an exchange. Not a signal service.** It holds live trading credentials for
real partner capital — see "Security invariants" below before touching anything.

## Status

Working end to end: the fan-out engine, sizing, SL/TP policy, credential
encryption, staff-gated order routing, per-account trade history, the WebSocket
channel, all eight exchange adapters, a public market-data feed with live
mark-to-market PnL, the runtime emergency halt, a watchlist, an installable
(PWA) bilingual Nuxt panel with draggable chart order lines.
**119 backend tests pass, `ruff` clean, Nuxt build clean.**

Every section of `docs/spec/platform-spec.md` is implemented. Two departures are
recorded rather than silent: failure notices moved from a docked card into a
top-bar notification centre (Q16 — they covered the chart), and success
confirmations, which §10 left open, are transient toasts while failures still
never expire.

Verified against a live stack, not assumed: an order routed across three demo
accounts of $10 / $50 / $100 produced margins of $9.90 (rejected — below the
exchange step), $49.50 and $99.00, fanned out in 0.3ms, amended, and closed,
with the skipped account raising a persistent notification.

**Not yet done** — see `questions.md` and the caveats in `docs/adapters.md`:

- Real exchange adapters are written from the vendored docs and unit-tested
  against mocked transports, but **none has been run against a live exchange or
  testnet**. Do that on testnet before any real capital.
- LBank futures is impossible to implement (Q10); the adapter raises
  `NotSupported` rather than guessing.
- Hyperliquid agent-wallet withdrawal rights are still unverified (Q11).
- Market data is a **public** feed (Binance → Bybit, no credentials, Q13). Where
  no provider is reachable the API serves labelled synthetic candles and the
  panel says "sample prices"; a synthetic price is never used to size an order.
- The chart is Lightweight Charts. TradingView's Charting Library swaps in
  behind the same `ChartAdapter` seam once access is granted.

Every open question is a **setting with all branches built**, so answering one
is a `.env` change rather than a rewrite. `/risk` in the panel answers Q5a from
numbers.

## Layout

```
backend/    Django 5 + DRF + Channels, apps/ under it, config/ project root
frontend/   Nuxt 3 + TS + Tailwind + Pinia + i18n
docs/
  spec/platform-spec.md              authoritative requirements (§ numbering used everywhere)
  spec/conformance.md                every clause -> where it lives -> the test that proves it
  spec/exchange_list.original.txt    admin's raw exchange list, verbatim
  exchanges/coverage.md              exchange matrix + per-exchange capability checklist
  frontend/tradingview.md            chart setup: Lightweight Charts now, Charting Library later
questions.md                         decisions + remaining open questions
reference/                           read-only vendored exchange docs & SDKs — never imported
```

### Backend map

| Path | What |
|---|---|
| `apps/exchanges/base.py` | **The adapter seam.** `ExchangeAdapter` + `Capabilities`. Everything above it is exchange-agnostic. |
| `apps/exchanges/paper.py` | In-memory adapter: spec §9 demo mode *and* the fan-out test fixture (injectable latency/failures). |
| `apps/engine/fanout.py` | `fan_out()` — concurrent legs, per-leg deadline, failures returned as data. |
| `apps/engine/executor.py` | `open_trade` / `amend_sltp` / `close_trade`; Q5e failure policy lives in `_protect`. |
| `apps/trading/sizing.py` | Spec §5 — 99% as margin, round down, skip below minimum. |
| `apps/trading/sltp.py` | Q5a both readings; `compare_bases()` powers `/risk`. |
| `apps/exchanges/marketdata.py` | **Public** prices (Q13). Credential-free, cached, provider fallback, synthetic last resort — never an adapter. |
| `apps/trading/market_views.py` | Candles, ticker, and `/positions/` — legs marked to market, PnL in Decimal on this side of the wire. |
| `apps/trading/killswitch.py` | Spec §7 halt (Q14). Cache-backed so the routing path costs no query; env pin cannot be cleared from the panel. |
| `apps/core/crypto.py` | Fernet encryption + rotation for credentials. |

### Frontend map

| Path | What |
|---|---|
| `stores/order.ts` | The working order. All three SL/TP surfaces write here, so they cannot disagree (spec §3). |
| `stores/market.ts` | One price feed for the whole page: candles, ticker poll, and the `live` flag that drives the "sample prices" badge. |
| `stores/positions.ts` | The open position per account, polled from `/positions/`. PnL is never recomputed in the browser. |
| `stores/watchlist.ts` | The admin's pairs, in a cookie. One batched quote request feeds both watchlists. |
| `composables/useChartAdapter.ts` | The chart seam — Lightweight Charts now, Charting Library later. Owns the draggable SL/TP/limit lines. |
| `components/app/StopAll.vue` | The spec §7 halt, in the top bar of every page. |
| `components/app/NotificationCenter.vue` | Spec §4 failure notices (Q16 amendment). Nothing here auto-expires. |
| `public/manifest.webmanifest`, `public/sw.js` | Installable panel (Q17). The worker never caches `/api` or `/ws`. |

## Running it

```bash
cp .env.example .env          # then set CREDENTIAL_ENCRYPTION_KEYS — see the file
docker compose up -d --build  # panel on :3000, API on :8000
```

Without Docker: `backend/.venv` + `python manage.py migrate runserver`,
and `npm run dev` in `frontend/`. Tests: `cd backend && .venv/bin/python -m pytest`.

## Target architecture

Backend Python throughout. Frontend Nuxt 3 + TypeScript + Tailwind + Pinia,
**English complete first, Persian second** — every string goes through i18n from
day one and layouts are RTL-capable from the start, so Persian is a translation
pass rather than a rebuild. Visual design follows
`reference/skills/frontend-design.SKILL.md`; the panel has to be good-looking,
not just functional.

```
Admin browser (Nuxt 3 + TradingView)
        │ WebSocket
        ▼
API / gateway (Django 5 + DRF + Channels)  ← accounts, auth, history, encrypted key vault
        │ in-process command bus
        ▼
Execution engine (async Python, asyncio)   ← the 1-second fan-out lives here
        │ N independent adapter tasks, one per connected account
        ▼
Exchange adapters (one module per exchange, common Adapter interface)
```

Why the engine is separate from Django: spec §4 caps mid-trade propagation at
**1 second** across all accounts. That means one `asyncio.gather` over per-account
tasks with per-task timeouts, not a Celery queue (broker round-trip + worker
prefetch blows the budget). Celery stays for non-latency work only — history
aggregation, balance polling, reconciliation.

### The Adapter interface is the core seam

Every exchange implements the same interface; the engine knows nothing about any
specific exchange. Minimum surface, derived from the spec:

`get_balance` · `set_leverage` · `place_market` · `place_limit` ·
`set_sltp` · `amend_sltp` · `close_position` · `get_position` · `stream_events`

Capability differences (native SL/TP vs emulated, per-symbol vs per-account
leverage) are declared per adapter and handled behind the interface — never with
`if exchange == "binance"` in engine code.

## Invariants — do not violate

**Security (spec §7)**

- API keys are **encrypted at rest**, never plaintext, never in logs, never in
  API responses (not even masked-by-frontend — the server must not send them).
- Every connected key must be **trade-only, non-withdrawable**. Verify the
  permission scope at connect time where the exchange API allows it; refuse the
  connection when withdrawal rights are detected.
- Never log request bodies containing signatures or secrets.
- No key material in `reference/`, fixtures, tests, or scratch files.

**Execution (spec §4, §5)**

- Account isolation is absolute: one account's failure, rate limit, or exchange
  outage must never block, delay, or abort another. Per-account tasks, per-account
  clients, per-account rate limiters, per-task timeouts.
- Identical **leverage and SL/TP percentages** across all accounts; only dollar
  size differs (spec §5).
- **Sizing:** margin = 99% of that account's available **USDT** balance, with
  leverage multiplying on top (not 99% as notional). Spot uses the same 99% with
  no multiplier. An account not denominated in USDT is **reported on the
  dashboard as unusable**, not traded. Below the exchange's minimum notional →
  **skip that account** with a failure notification; never round up past 99%.
  Round sizes **down** to the exchange step, never up.
- One open trade per account at a time.
- No account joins a trade already in progress (spec §6).
- Failed order → persistent notification (~190×110px) that only manual dismissal
  clears (spec §4).

**Money**

- `Decimal` everywhere for prices, sizes, balances. No floats. Round to each
  exchange's tick/step rules *before* sending, never after.

## Build path

Nothing here is runnable yet. In order:

0. **Start the two external lead-time items today** — they block nothing locally
   but take days-to-weeks: apply for the TradingView Charting Library
   (`docs/frontend/tradingview.md`), and email LBank for private futures API
   docs (`questions.md` Q10).
1. Answer `questions.md` Q5 and Q12 — they set SL/TP semantics and exact sizing,
   which the adapter interface encodes.
2. Scaffold `backend/` (Django + DRF + Channels) and `frontend/` (Nuxt 3),
   Docker-first: `cp .env.example .env` → `docker compose up -d --build`.
3. Build the Adapter interface + an in-memory **paper adapter** first — it is
   also spec §9's demo mode, and it lets the fan-out engine be tested with no
   real credentials.
4. Fan-out engine against the paper adapter, with timing assertions on the 1s budget.
5. Real adapters in the order in `docs/exchanges/coverage.md`, Hyperliquid
   first — it is the flagged-important one *and* has the most unusual auth
   model (agent wallets, per-signer nonces), so it stress-tests the interface
   hardest. Verify Q11 on testnet before it ships.
6. Trading UI: chart (`docs/frontend/tradingview.md`), order entry, 3-way SL/TP
   editing, positions panel. English strings complete before Persian starts.

## Working notes

- Cite the spec by section (`§4`) when justifying behaviour; the spec is the
  contract with the admin.
- The spec is explicitly a starting point (§10), not frozen — but changes to it
  get recorded there, not silently in code.
- Exchange API facts come from `reference/` or the `hyperliquid-docs` MCP server,
  not from memory. Exchange APIs drift.
- New ambiguity found mid-task → append to `questions.md`, keep building the
  parts that don't depend on the answer.
