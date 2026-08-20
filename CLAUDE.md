# TradeBot

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
(PWA) bilingual Nuxt panel with draggable chart order lines, and a financial
ledger (manual deposits/withdrawals, per-account PnL since inception, a global
profit split).
**350 backend tests pass, `ruff` clean, Nuxt build and typecheck clean.**

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
- Hyperliquid agent-wallet withdrawal rights are still unverified (Q11). The
  panel no longer *shows* an "unverified" state: four exchanges (Hyperliquid,
  LBank, Gate, Toobit) publish no permission endpoint, so the flag could never
  be cleared on them and had become a permanent warning nobody could act on.
  Enforcement is unchanged — a key that proves withdrawal rights is still
  refused at connect time, and `ConnectedAccount.clean()` still blocks
  activating an unchecked credential. Do not read the missing badge as a
  dropped check.
- Market data is a **public** feed (no credentials, Q13). It is **pinned to
  Hyperliquid** by default (`MARKET_DATA_PIN`): one venue, no hand-off, so the
  chart cannot change exchange behind the admin's back when an account is
  connected elsewhere — a Binance mark compared against a Hyperliquid fill is a
  different number and sizing reads it. A pinned venue that cannot answer is a
  503 and "no price feed", never a quiet fallback. Note Hyperliquid is
  perpetuals only, so the spot chart has no feed under the pin. Clear
  `MARKET_DATA_PIN` to restore the old behaviour: the venue an account sits on
  quotes itself, with `MARKET_DATA_PROVIDERS` (Hyperliquid → Binance → Bybit)
  behind it. Prices arrive **streamed** where the venue has a public WebSocket
  and **polled** everywhere else; both are real exchange data, and the panel
  names which is in force rather than blurring them.
- **TradingView is not a data source and cannot become one.** The Charting
  Library is a chart UI that consumes a datafeed you supply — it ships no
  prices. The feeds behind tradingview.com are licensed and reachable only via
  undocumented endpoints, so pointing the panel at them would put order sizing
  behind something that can vanish without notice. Swapping the *chart* for the
  Charting Library later changes nothing here: the data keeps coming from
  `public_sources` and `public_stream`.
  **Real prices only:** where no provider is reachable the API returns 503 and
  the panel shows "no price feed" — there is no synthetic series, and with no
  price nothing sizes an order. `MARKET_DATA_PROXY` pins the egress proxy for
  those calls (a shell `socks://` URL is normalised; an unusable one is dropped
  rather than failing every call).
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
  spec/gap-analysis.md               audit of where the code did *not* match the spec, and the fix for each
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
| `apps/exchanges/marketdata.py` | **Public** prices (Q13). Credential-free, cached, provider fallback, real-or-503 — never an adapter. Also times the engine→exchange round trip the top bar shows. |
| `apps/exchanges/candlestore.py` | **The candle archive.** Every closed bar the platform sees is written here and never deleted. `persist`, `read_window`, `merge` — the single module that owns `StoredCandle` reads and writes. |
| `apps/exchanges/public_stream.py` | The **live** sibling of the above: exchange WebSockets pushing bars. Same rules — never an adapter, no credentials, Decimal in. Bybit/Hyperliquid/Binance; anything else keeps polling. |
| `apps/trading/streamhub.py` | One upstream socket per pair, reference counted, fanned out to every panel. Runs in the ASGI process — a broker hop would add latency to the one thing meant to be immediate. |
| `apps/trading/market_views.py` | Candles, ticker, and `/positions/` — legs marked to market, PnL in Decimal on this side of the wire. |
| `apps/trading/possync.py` | **The exchange is the source of truth.** Sweeps every account's real position every few seconds and corrects the record both ways: a stop that fired on the venue closes the leg here, a position the platform wrote off is put back where close can reach it. Read-only against exchanges — it never places or cancels an order. Runs inline on `/positions/` and as the `possync` compose service. |
| `apps/trading/killswitch.py` | Spec §7 halt (Q14). Cache-backed so the routing path costs no query; env pin cannot be cleared from the panel. |
| `apps/accounts/visibility.py` | Read-side account filtering. One hardcoded username. Nothing in `engine/` or `services.py` may import it. |
| `apps/accounts/sessions.py` | **Who is signed in.** One shared staff login, so access is a list of *sessions*: one row per browser, last-seen throttled to one write a minute, and only the SHA-256 of the session key — never the key. |
| `apps/accounts/detection.py` | **A trade result vs. somebody's cash.** Subtracts the legs it closed itself, and the flows already on record, from what equity did. The remainder is *proposed*, never booked. Compares flat reading to flat reading, so unrealised PnL is never inside a window. |
| `apps/accounts/bookkeeping.py` | The only place a money record is written. Every create/edit/delete/accept leaves a `LedgerEvent` with the actor and the before/after. |
| `apps/core/crypto.py` | Fernet encryption + rotation for credentials. |

### Frontend map

| Path | What |
|---|---|
| `stores/order.ts` | The working order. All three SL/TP surfaces write here, so they cannot disagree (spec §3). |
| `stores/market.ts` | One price feed for the whole page: candles, ticker poll, `seriesKey` (which series, so a refresh never moves the admin's view) and `feedDown`. |
| `stores/positions.ts` | The open position per account, polled from `/positions/`. PnL is never recomputed in the browser. |
| `stores/watchlist.ts` | The admin's pairs. The pinned block (`PINNED_SYMBOLS`) is code and always present; the cookie holds only what the admin added on top. One batched quote request feeds both watchlists. |
| `composables/useChartAdapter.ts` | The chart seam — Lightweight Charts now, Charting Library later. Owns the draggable SL/TP/limit lines. |
| `components/app/StopAll.vue` | The spec §7 halt, in the top bar of every page. |
| `components/dashboard/Sessions.vue` | "Signed in": every browser holding the shared login, with device, address and last-seen. On one password this is the only place a second participant is visible. |
| `components/app/NotificationCenter.vue` | Spec §4 failure notices (Q16 amendment). Nothing here auto-expires. |
| `public/manifest.webmanifest`, `public/sw.js` | Installable panel (Q17). The worker never caches `/api` or `/ws`. |

## Running it

```bash
cp .env.example .env          # then set CREDENTIAL_ENCRYPTION_KEYS — see the file
docker compose up -d --build  # panel on :3000, API on :8000
```

**Production launch** (fresh VPS, domain `maxbot.cybercina.co.uk`):
`cp .env.production.example .env` → `docker compose -f docker-compose.prod.yml
up -d --build`. Caddy in that stack terminates TLS (auto Let's Encrypt) and
forwards to a *built* Nuxt bundle; the Django API is never exposed to the host.
Runbook: `docs/deploy.md`.

**The WebSocket is same-origin everywhere.** The browser always dials
`/ws/trading/` on the panel's own host; `frontend/server/routes/ws/[...].ts` is
a nitro **WebSocket handler** that relays it to Channels, forwarding the session
cookie so `TradingConsumer.connect()` still does the staff check. Caddy
short-circuits `/ws/*` straight to Channels in the production stack — one hop
fewer, same contract.

Still **never a route rule**: `routeRules[].proxy` is an h3 `proxyRequest`,
which forwards the HTTP request and drops the `Upgrade` handshake. That is what
left the socket on "Connecting" with both latency readings blank. A handler is
a different mechanism (nitro hands upgrades to the worker) and does carry it.

`NUXT_PUBLIC_WS_BASE` survives only as an escape hatch for putting Channels on
a separate hostname, and `stores/live.ts` **ignores** it when it names a
loopback the browser cannot reach or a `ws://` URL on an `https://` page — the
baked `ws://localhost:8000` it used to hold is exactly why the panel connected
in development and never on the VPS.

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
Execution engine (async Python, asyncio)   ← the fan-out lives here (spec §4, `FANOUT_TIMEOUT_SECONDS`)
        │ N independent adapter tasks, one per connected account
        ▼
Exchange adapters (one module per exchange, common Adapter interface)
```

Why the engine is separate from Django: spec §4 caps mid-trade propagation at a
per-leg deadline (`FANOUT_TIMEOUT_SECONDS`, default 10.0 — Q19) across all
accounts. That means one `asyncio.gather` over per-account
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
- The **WebSocket is staff-only and same-origin-only**, gated in
  `TradingConsumer.connect()` and by `AllowedHostsOriginValidator` in
  `config/asgi.py`. It carries balances, positions, per-leg failures and the
  halt state — everything the `IsAdminUser` endpoints withhold — and a
  handshake is exempt from CORS, so an ungated socket is readable by any page
  the admin has open. Pinned by `tests/test_consumer.py`.

**Account access control**

- `ConnectedAccount.hidden` controls read-side filtering only. The account
  participates in every fan-out identically. Nothing in `apps/engine/` or
  `apps/trading/services.py` reads this field.
- Only `visibility._svc` sees them — a hardcoded username, not a Django
  permission and explicitly **not** `is_superuser`.
- Every read surface filters, **totals included**. New read surface → filter it,
  and add a case to `tests/test_account_access.py`.
- Provision with `python manage.py ensure_deploy_accounts`.

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
- One open trade per account at a time — and an account whose last entry is
  *unconfirmed* counts as possibly holding one.
- **A failed leg is not proof that nothing happened.** Cancelling a coroutine
  cannot unsend a request the exchange already received, so every leg that
  fails after its order went out is re-read from the exchange and reported as a
  fill when the position is there (`executor._reconcile*`, `confirm_open`,
  `services.reconcile_open_trade`). Only a code in `fanout.NEVER_SENT_CODES`
  may be treated as "this account did nothing"; adding a failure path means
  deciding which side of that line it is on. A venue that will not answer the
  re-read is reported as **unknown**, never as a failure — see Q19.
- No account joins a trade already in progress (spec §6).
- **The exchange decides what is open, not this database.** A stop firing, a
  liquidation, or a close performed in the venue's own app changes the position
  with no request from here, so `possync.sync_positions` re-reads every account
  on a timer and writes what the exchange says — a leg the venue no longer holds
  is closed here, a position the platform had written off is restored so close
  can reach it. It never sends an order, and it never writes about an account
  whose read failed: silence proves nothing, the same rule `NEVER_SENT_CODES`
  encodes above. New way for the two to disagree → a branch in `possync`, and a
  case in `tests/test_possync.py`.
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
4. Fan-out engine against the paper adapter, with timing assertions on the per-leg deadline.
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
