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
profit split), **bot mode** — a Pine Script v5 engine (the v1 subset **plus
user-defined types, methods and enums** — `docs/decisions.md` Q24 amendment,
`apps/pine/objects.py`), backtest, supervisor and panel (`docs/bots.md`), gated
per account by two independent switches (`manual_trading_enabled`,
`bot_trading_enabled` — `docs/bots.md` §7) and restricted to **one running bot
at a time** — and an **optional security layer**: one On/Off row per control on
`/settings`, every one off by default, none of them on the order-routing path
(`docs/security-plan.md`).
**~1740 backend tests pass, `ruff` clean on everything this touched, Nuxt build
and typecheck clean.**

Every section of `docs/spec/platform-spec.md` is implemented. Two departures are
recorded rather than silent: failure notices moved from a docked card into a
top-bar notification centre (Q16 — they covered the chart), and success
confirmations, which §10 left open, are transient toasts while failures still
never expire.

Verified against a live stack, not assumed: an order routed across three demo
accounts of $10 / $50 / $100 produced margins of $9.90 (rejected — below the
exchange step), $49.50 and $99.00, fanned out in 0.3ms, amended, and closed,
with the skipped account raising a persistent notification.

**Not yet done** — see the caveats in `docs/adapters.md`
(every question is answered; `docs/decisions.md` holds them):

- Real exchange adapters are written from the vendored docs and unit-tested
  against mocked transports, but **none has been run against a live exchange or
  testnet**. Do that on testnet before any real capital.
- LBank futures is impossible to implement (Q10); the adapter raises
  `NotSupported` rather than guessing.
- Hyperliquid **agent wallets cannot withdraw** — answered by the admin, Q11,
  and no testnet drill gates the release. **Do not modify the Hyperliquid
  adapter.** Enforcement is unchanged: four exchanges (Hyperliquid, LBank, Gate,
  Toobit) publish no permission endpoint, so `verify_credentials` still reports
  the check as unprovable rather than quietly passing it, a key that proves
  withdrawal rights is still refused at connect time, and
  `ConnectedAccount.clean()` still blocks activating an unchecked credential.
  The panel shows no "unverified" badge — a permanent warning nobody can act on
  is alarm fatigue, not a dropped check.
- What Hyperliquid access *does* need watching is **expiry**: an agent approval
  lasts at most 180 days and the exchange **prunes** the wallet rather than
  refusing it, so a lapse is a silent disconnection. `apps/accounts/credentials.py`
  counts down to `ConnectedAccount.credential_expires_at`, raises a persistent
  notice inside `CREDENTIAL_EXPIRY_WARN_DAYS` (21) and clears it on renewal.
  Reported, never enforced — an expiring credential still trades.
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
- **Bot mode is built but has never run live.** Phase 7's 14-day soak and Phase
  10's checklist are calendar and human items; `apps/bots/gate.py` measures them
  and cannot shorten them, and `paper → live` is refused while any row is unmet.
  Q29 is still open: the `ta.*` golden values need a TradingView export, so the
  indicator tests currently compare against oracles transcribed from
  `reference/pinescriptv6/` — which pins the incremental implementations against
  the textbook formulas but shares any misreading of them.
  `backend/tests/fixtures/pine/golden/README.md` holds the file format, and the
  test goes live the moment an export is committed.

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
  bots.md                            **bot mode, as an operator uses it** — the subset, writing a
                                     strategy, backtesting, the promotion path, the runbook
  bot-mode.md                        the eleven-phase plan behind it, and why each phase exists
  bot-plan.md                        the execution plan under that — file manifest, settings, the test per item
  decisions.md                       every closed question, Q1–Q28, with the setting that implements it
  security-plan.md                   the optional-by-default security layer: one switch per control,
                                     none of them on the order-routing path
questions.md                         open questions only — Q29, Q31, Q32; new ones start at Q33
reference/                           read-only vendored docs & SDKs — never imported
  pinescriptv6/                      the Pine language reference (v6). The v1 subset is v5, but
                                     operators, the execution model and every ta.* formula are
                                     shared — this is what apps/pine/ is checked against.
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
| `apps/trading/possync.py` | **The exchange is the source of truth.** Sweeps every account's real position every few seconds and corrects the record both ways: a stop that fired on the venue closes the leg here, a position the platform wrote off is put back where close can reach it. Read-only against exchanges — it never places or cancels an order. It also **recovers the exit**: a leg the venue closed by itself has its exit price and realised PnL read back out of the exchange's own fills (`get_closed_pnl`), so the trade log carries money rather than a dash. Runs inline on `/positions/` and as the `possync` compose service. |
| `apps/trading/killswitch.py` | Spec §7 halt (Q14). Cache-backed so the routing path costs no query; env pin cannot be cleared from the panel. |
| `apps/accounts/visibility.py` | Read-side account filtering. One hardcoded username. Nothing in `engine/` or `services.py` may import it. |
| `apps/accounts/credentials.py` | **When a credential stops working.** A Hyperliquid agent approval is *pruned* at its expiry, not refused, so a lapse is a silent disconnection. Counts down to the recorded date, raises one persistent notice, escalates it on expiry and clears it on renewal. Measures and reports only — it never pauses an account or drops one from a fan-out. |
| `apps/accounts/sessions.py` | **Who is signed in.** One shared staff login, so access is a list of *sessions*: one row per browser, last-seen throttled to one write a minute, and only the SHA-256 of the session key — never the key. Any of them can be ended from the dashboard, which means walking the live sessions and hashing each key: the invariant is that this platform never stores one. |
| `apps/security/flags.py` | **The switches, and why they are free.** A singleton row behind one cache key, and on top of that a **process-local memo** — so a request with every control off costs a dict lookup and a float compare, no I/O at all. The price is a flip taking up to a second to reach every worker. Fails to **off** on a database error: the kill switch fails to *halted* because routing on a guess is the wrong side, and here the wrong side is locking the operator out of a live book. |
| `apps/security/middleware.py` | The three controls that have to see every request — allowlist, session window, admin-write limiter. Shaped as a guard clause on a precomputed `_middleware_active` boolean, dual-stack so the ASGI path takes no thread hand-off. `/api/trading/stop-all/` is exempt from the allowlist **by name**: a lock-out that also disables the brake is the failure this whole layer is designed around. |
| `apps/security/stepup.py` | Asking for the password again — before credentials, money records and putting a bot live, and **never** before opening, amending or closing a position, or the halt. That exclusion is the design: a prompt in front of "close this" costs money during the one minute it matters, and the attacker it would stop already holds the session. |
| `apps/security/totp.py` | The second factor, in three steps — scan, prove, save. The switch stays refused until all three are done, which is the lock-out escape written as a refusal rather than a warning. Recovery codes are SHA-256 like the session hash, and for the same reason: they are `secrets` output, not something a person chose. |
| `apps/security/audit.py` | The access history — and, more often, *not* writing it: every call returns before it builds anything while the switch is off. One write ignores that, because a log you can switch off without leaving the fact behind is not a log. `REDACTED` keeps the allowlist's contents out of it. |
| `apps/accounts/detection.py` | **How much is unexplained.** Subtracts the legs it closed itself, and the flows already on record, from what equity did. Compares flat reading to flat reading, so unrealised PnL is never inside a window. Measures only — it does not decide what the remainder *was*. |
| `apps/accounts/classify.py` | **Which of the two it was, without asking.** The platform trades every account at once, so a change that hit the whole set is the trade and one that hit a single account is somebody's own money. Plus: an emptied account is a withdrawal, and money arriving while nothing has traded is a deposit. Ordered rules, each with a reason code the panel shows. `LEDGER_AUTO_RESOLVE` decides how much it may book by itself; everything it books is a `LedgerEvent` and is reopenable. |
| `apps/accounts/bookkeeping.py` | The only place a money record is written. Every create/edit/delete/accept/attribute/reopen leaves a `LedgerEvent` with the actor — blank for the platform — and the before/after. |
| `apps/accounts/report.py` | **One account, whole.** The per-account page's single payload: connection, ledger row, every leg with what it returned, the realised curve, cash flows and detections. Derives, never decides — the money is `ledger.py`'s arithmetic and the trades are the account's own legs. |
| `apps/accounts/statement.py` | **The same account, as a document that leaves the platform.** Windowed by the two dates the operator picks, laid out with ReportLab and handed over as a PDF. It talks in money only — **no percentage appears anywhere in it**, because a rate on a page invites the reader to apply it to a number that is not there — and it says throughout that the bot placed every order. Derives nothing: `report.statement_report` does the arithmetic. |
| `apps/accounts/statement_text.py` | **Both languages, side by side.** Every phrase in the statement in English and Persian, so a wording change cannot land in one and miss the other. Also owns what makes Persian *render*: the embedded Vazirmatn faces (Helvetica has no Arabic glyphs) and `shape()`, which reshapes and reorders a run — and deliberately leaves a run with no Arabic letter alone, since running bidi over `+$1,234.00` moves the sign to the wrong end. |
| `apps/pine/` | **The Pine Script v5 engine.** Lexer, parser, the Q24 subset as data, validator, incremental `ta.*`, `objects.py` (the value model for user-defined types and enums), and a bar-at-a-time runtime that emits a `StrategyIntent`. Imports **stdlib only** — no `django.*`, no `apps.*` — which is what makes it the *same object* in a backtest and in the live loop. Checked against `reference/pinescriptv6/`, pinned by `tests/test_pine_purity.py`. |
| `apps/bots/` | **A bot is a signal source, not a second execution path.** `translate.py` turns an intent into the `route_*` calls that already exist and nothing below it is forked; `backtest.py` replays; `riskgate.py` is Q25's seven auto-stops; `supervisor.py` is one asyncio task per bot in the ASGI process; `gate.py` is the measured `paper → live` gate. |
| `apps/core/crypto.py` | Fernet encryption + rotation for credentials. |

### Frontend map

| Path | What |
|---|---|
| `stores/order.ts` | The working order. All three SL/TP surfaces write here, so they cannot disagree (spec §3). |
| `stores/market.ts` | One price feed for the whole page: candles, ticker poll, `seriesKey` (which series, so a refresh never moves the admin's view) and `feedDown`. |
| `stores/positions.ts` | The open position per account, polled from `/positions/`. PnL is never recomputed in the browser. |
| `stores/bots.ts` | Strategies and bots together — a bot's identity is "this version of that script", and splitting them means two loading states for one question. Recomputes nothing: metrics, gate rows and leg outcomes all arrive in Decimal from the server. |
| `stores/watchlist.ts` | The admin's pairs. The pinned block (`PINNED_SYMBOLS`) is code and always present; the cookie holds only what the admin added on top. One batched quote request feeds both watchlists. |
| `composables/useSltpAmend.ts` | The one path a mid-trade SL/TP change takes. Ticket, chart drag and position row all call it; one fan-out is in the air at a time and the last edit wins, because a run of drags must not let an older amend land last. |
| `composables/useChartAdapter.ts` | The chart seam — Lightweight Charts now, Charting Library later. Owns the draggable SL/TP/limit lines. |
| `pages/accounts/[id].vue` | One connection's own page, reached from every row of the accounts list: when it connected, what was paid in and out, every leg it was given and what each returned. One request (`/accounts/accounts/<id>/report/`); nothing is recomputed in the browser. |
| `components/accounts/StatementDialog.vue` | The dialog in front of that page's download: which period, and which language the *recipient* reads — asked rather than assumed, because the file is what a partner is sent and it opens on the panel's language only as the likelier answer. |
| `components/app/StopAll.vue` | The spec §7 halt, in the top bar of every page. **It stops every running bot too** (Q22) — a halt that flattens while a bot is still evaluating is a halt that re-enters ninety seconds later. |
| `pages/bots/index.vue`, `pages/bots/[id].vue` | The bots, stopped ones first: Q25's premise is that nobody is watching at 03:00, so a bot that stopped itself does not sort under the running ones where it reads as idle. The detail page's spine is the promotion gate — nine measurements, not a confirmation dialog. |
| `components/bots/PineEditor.vue` | The editor: a textarea, a gutter and a highlight layer. Not CodeMirror, for the reason `utils/icons.ts` is not an icon package — what it needs is line numbers, a Tab that inserts four spaces (Pine is whitespace-significant), auto-indent, and the validator's errors on their own lines. |
| `components/dashboard/Sessions.vue` | "Signed in": every browser holding the shared login, with device, address and last-seen, each one endable from its row. On one password this is the only place a second participant is visible — and reading that without being able to act on it was the gap. |
| `components/security/SecurityCard.vue`, `stores/security.ts` | The security layer as one card on `/settings`: a switch per control, each one's tunables underneath it and only while it is on. A refusal is an answer rather than a failure — the second-factor row says "enrol an app first" instead of springing back — and a `step_up_required` raises the password prompt and replays the click. |
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
`set_sltp` · `amend_sltp` · `close_position` · `get_position` · `get_closed_pnl` ·
`stream_events`

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
- **A trade result and a transfer are different events, not two readings of
  one.** PnL is `balance - net invested`, so attributing a change to trading
  means writing *nothing* — leaving capital alone is exactly what puts the
  change in PnL — while a transfer moves capital so PnL does not count it.
  Booking either as the other is a wrong PnL. `classify` decides which, the
  panel offers both answers, and `bookkeeping.reopen_detection` undoes any
  decision, the platform's own included. New signal for telling them apart →
  a rule in `classify`, in its precedence order, and a case in
  `tests/test_ledger_classify.py`.

## Build path

Nothing here is runnable yet. In order:

0. **Start the external lead-time item** — it blocks nothing locally but takes
   days-to-weeks: apply for the TradingView Charting Library
   (`docs/frontend/tradingview.md`). LBank private futures docs are the other
   one (`docs/decisions.md` Q10), shipped around rather than waited on.
1. Answer Q5 and Q12 — they set SL/TP semantics and exact sizing, which the
   adapter interface encodes. *(Both answered; see `docs/decisions.md`.)*
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
- New ambiguity found mid-task → append to `questions.md` (numbered from Q30),
  and move it to `docs/decisions.md` once answered. Keep building the
  parts that don't depend on the answer.
