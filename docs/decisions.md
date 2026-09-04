# Decisions — binding

Every question this project has closed, with the reasoning and the setting or
module that implements it. **Still-open questions live in `questions.md`.**

Q-numbers are cited from code comments (`questions.md Q5a` in
`config/settings.py`, `questions.md Q11` in `exchanges/hyperliquid.py`) and from
`docs/spec/conformance.md`; they mean the same thing here. Q1–Q4 and Q6–Q9 were
answered by the admin on 2026-08-11; Q5, Q10 and Q12–Q19 are answered by the
shipped default, each with both branches implemented and a test that pins it, so
what remains on those is a `.env` change rather than a decision; Q20–Q27 were
taken on 2026-08-23 ahead of `docs/bot-mode.md` being built.

Where an answer names a setting, `backend/config/settings.py` is the authority
on its current default.

---


## Q1. Exchanges ✅ All 8 in v1

Binance · Bybit · OKX · Gate.io · KuCoin · Hyperliquid · LBank · Toobit.
Hyperliquid uses the connected `hyperliquid-docs` MCP server as its doc source.

**Done since:** LBank and Toobit docs downloaded and converted to Markdown —
`reference/exchanges/lbank/api/` (spot + contract) and
`reference/exchanges/toobit/api/` (27 pages incl. copy-trading). Hyperliquid
integration notes written to `reference/exchanges/hyperliquid/README.md`.
The two placeholder `TODO.md` files are gone. Toobit's adapter was rebuilt
(2026-08-16) against those docs — the previous one was Binance request shapes
pointed at Toobit; see `docs/exchanges/coverage.md`.

Caveat: LBank futures is blocked — see Q10.

## Q2. Stack ✅ Python backend, split execution engine, bilingual frontend

- Backend Python. Django 5 + DRF + Channels for UI, accounts, key vault,
  history; **separate async execution engine** for the fan-out. Confirmed:
  "high speed and accurate with minimal latency, change if necessary."
- Frontend: **Nuxt 3 + TypeScript + Tailwind + Pinia**, deployed as a static/
  Node target in the same compose stack. Chosen for easy deploy and no
  constraints on charting or trading widgets.
- **i18n: English first and complete, then Persian.** Every string goes through
  i18n from day one — no hardcoded copy — and layout is built RTL-capable from
  the start, so Persian is a translation pass, not a rebuild.
- Visual design follows the `frontend-design` skill (Q7).

## Q3. TradingView ✅ Free now, Charting Library applied for in parallel

Confirmed: TradingView charts are mandatory, and visual SL/TP + indicator
editing on the chart is mandatory. Also confirmed: **no Charting Library access
today**, so start with the free option.

The catch: the free **embeddable widget** is an iframe. You cannot draw on it,
cannot read its price scale, and cannot drag an SL line on it. It satisfies
"show a chart" and nothing else in spec §3.

So the plan is two-phase, behind one `ChartAdapter` interface:

- **Phase 1 — TradingView Lightweight Charts** (free, Apache-2.0, self-hosted,
  no application). It is a real TradingView library, it renders our own
  datafeed, and it supports price lines we can make draggable. This is what
  makes chart-based SL/TP editing possible *now*. Cost: no built-in indicator
  suite or drawing toolbar — we implement a starter set (MA, EMA, RSI, MACD,
  Bollinger) ourselves.
- **Phase 2 — TradingView Charting Library** (also free, but access-gated behind
  an application). Full indicator suite, drawing tools, native order lines.
  **Apply now** at https://www.tradingview.com/advanced-charts/ — it is a form,
  approval takes days-to-weeks, and it is pure external lead time. When it
  lands, swap the adapter; nothing above it changes.

The setup steps for both are written up in `docs/frontend/tradingview.md`.

## Q4. Position sizing ✅ 99% as margin, leverage on top

Confirmed: leverage is used continuously, and 99% of each account's balance is
committed. So margin = 99% of the account's available balance, and leverage
multiplies on top of that (**not** 99% as notional).

- Sizing is per-account and independent: $50 account → $49.50 margin,
  $100 account → $99 margin. (See Q12 on the $10 → $9 example.)
- Balance is measured in **USDT**. An account whose balance is not in USDT is
  **reported on the dashboard** as unusable/needs-conversion rather than traded.
- **Spot uses the same 99% rule** (no leverage multiplier).
- Below exchange minimum notional → skip that account, raise the persistent
  failure notification, never round up past 99%.

Risk note, stated once so it is on the record: committing 99% of the account as
margin means a liquidation wipes essentially the whole account, since there is
no uncommitted balance left to absorb it. The liquidation *distance* is set by
leverage alone — 10% away at 10x, 20% at 5x, before fees and funding — not by
the 99%. This is your explicit instruction and is implemented as specified.

## Q5. SL/TP semantics ✅ All five decided; the shipped default is the answer

Five separate decisions, each now a setting in `settings.TRADING` with **every
branch implemented and tested**. The default *is* the decision; flipping one is
a config change, not a rewrite.

| | Decision | Setting | Default |
|---|---|---|---|
| Q5a | SL/TP % is a move in **price** | `SLTP_BASIS` | `price` |
| Q5a guard | An SL at or beyond liquidation is refused | `REJECT_SL_BEYOND_LIQUIDATION` | `true` |
| Q5b/Q5c | Each account anchors on **its own fill** | `SLTP_REFERENCE` | `own_fill` |
| Q5d | Place the new pair, **then** cancel the old | `SLTP_AMEND_STRATEGY` | `place_then_cancel` |
| Q5e | Retry twice, then close at market | `SLTP_FAILURE_POLICY` · `SLTP_FAILURE_RETRIES` | `retry_then_close` · `2` |

`apps/trading/sltp.py`, `apps/engine/executor.py` (`apply_sltp`, `_protect`),
`backend/tests/test_sltp.py`. The reading in force is written onto
`Trade.sltp_basis` at entry, so an old trade is never re-read under a new
setting. To revisit Q5a on numbers rather than prose, `/risk` in the panel —
or `POST /api/trading/risk-preview/` — renders both readings side by side.

### Q5a. Percent of price, not of margin

Worked example — $1,000 account, 10x leverage, BTC at $100,000. Margin is 99% of
$1,000 = **$990**; notional = $990 x 10 = **$9,900** ≈ 0.099 BTC.

`SL = 2%` can mean two very different things:

| Reading | Price move | SL trigger price | Loss if hit | % of account |
|---|---|---|---|---|
| **A — 2% of entry price** | 2% | $98,000 | 2% of $9,900 = **$198** | **19.8%** |
| **B — 2% of margin** | 0.2% | $99,800 | 2% of $990 = **$19.80** | **1.98%** |

Reading A loses **10x** what reading B loses — the leverage multiple. Both are
reachable here: liquidation at 10x sits 1/leverage = **10%** away ($90,000), so
a 2% stop triggers long before it.

**Decided: A, percent of price.** It is how traders and TradingView think, and
it is what a chart drag naturally produces. Its trap — that a small-sounding
number costs a fifth of the account, and that `SL = 10%` or more at 10x can
never trigger because liquidation comes first — is priced in rather than
ignored: the order ticket shows the dollar risk and the % of account beside the
input in real time, and `REJECT_SL_BEYOND_LIQUIDATION` refuses a stop that
liquidation would reach first (≥10% at 10x, ≥20% at 5x).

*(Correction: an earlier version of this file put liquidation ~1% from entry and
the loss at $1,980. Both were wrong — liquidation distance is 1/leverage and does
not depend on how much margin is committed, and the notional was overstated 10x.
The numbers above are the ones the code computes; `backend/tests/test_sltp.py`
asserts them.)*

### Q5b / Q5c. Each account anchors on its own fill price

Spec §4 says identical SL/TP percentages on every account, and every account
fills at a slightly different price — different sizes, different exchanges,
different moments inside the fan-out window. The same fork appears when the
admin **drags** the SL line, which produces one absolute price on one chart.

**Decided: the same percentage off each account's own fill price**
(`SLTP_REFERENCE=own_fill`). A drag is converted to a percentage relative to the
admin's entry and that percentage is what propagates. This is literal spec §4
and it makes each partner's risk identical in percentage terms. The other
branch, `admin_price`, pushes one absolute price to everyone and is built but
not the default.

### Q5d. Place first, then cancel — reduce-only on every stop

Some exchanges cannot modify a stop order; they need cancel-then-place. Two
orderings:

- **Cancel first, then place**: for ~50–300ms the position has **no stop at
  all**. If price gaps in that window, the loss is uncapped.
- **Place first, then cancel**: for that window there are **two stops**. If both
  trigger, the second one opens a position in the opposite direction (unless
  reduce-only is supported, which mostly it is).

**Built as `SLTP_AMEND_STRATEGY` (default `place_then_cancel`), in
`engine/executor.apply_sltp`**, with reduce-only set on every stop so a
double-trigger cannot flip the position. The stale orders are snapshotted with
`adapter.list_conditional_orders()` *before* the new pair is placed, so the
cancel can never take away what was just placed. Only **Bybit** (and the paper
adapter) truly amend in place — `POST /v5/position/trading-stop`. Hyperliquid
does **not**, despite the earlier note here: its TP/SL are ordinary trigger
orders and go through the same cancel. OKX has an `amend-algos` endpoint but
this adapter does not use it, and `native_sltp_amend` now says so rather than
claiming an amend that never happens.

### Q5e. Entry filled but SL/TP placement failed — retry twice, then close

The most dangerous state in the system, and the spec does not cover it: the
account holds a 10x leveraged position with **no stop loss**.

**Decided: retry twice over ~2 seconds, then close at market and raise a
persistent failure notification** (`SLTP_FAILURE_POLICY=retry_then_close`,
`SLTP_FAILURE_RETRIES=2`), in `engine/executor._protect`. Never leave a
leveraged position unprotected. The other implemented branch,
`retry_then_notify`, retries and then lets the position ride while notifying —
it exists for an admin who would rather keep the trade than be flattened, and
it is deliberately not the default.

## Q6. Exchange reference material ✅ Keep and use it

Goal is copy-trade execution with full API access per exchange. All vendored
docs stay. `bybit.pdf` stays.

## Q7. `SKILL.md` ✅ Keep — it is the site design guide

The root `SKILL.md` was the `frontend-design` skill. Confirmed intentional: the
panel must be beautiful as well as usable. Kept at
`reference/skills/frontend-design.SKILL.md` and referenced from `CLAUDE.md` as
the design authority for the frontend.

## Q8. `reference/` stays in the repo ✅

Needed so every exchange's API contract is available while building adapters.

## Q9. Testnet ✅ Per-exchange, and reported in the panel

Wire testnet where the exchange has one; where it does not, do not fake it —
the panel shows "this exchange has no test environment and cannot be used in
test mode". Tracked per exchange in `docs/exchanges/coverage.md`.

Known so far: **Hyperliquid has a testnet** (`api.hyperliquid-testnet.xyz`).
**Toobit: none found** in its docs. Others to be confirmed as each adapter is built.

## Q10. LBank futures ✅ Shipped spot-only; futures raises `NotSupported`

LBank's published contract API (`reference/exchanges/lbank/api/contract.md`,
downloaded in full) documents **only the public namespace**
`/cfd/openApi/v1/pub` — server time, contract list, market list, order book.

There are **no publicly documented private futures endpoints**: no place order,
cancel, position, balance, set-leverage, or SL/TP. The futures host
(`https://lbkperp.lbank.com`) is live and responds, but without the private
request/signature schemas an adapter cannot be written. LBank spot, by contrast,
is fully documented and implementable today. Three ways forward:

1. **Ask LBank for the private futures API docs** — email service@lbank.com from
   an account with futures API enabled. This is the only path to real LBank
   futures. Unknown lead time.
2. **Ship LBank as spot-only** in v1, panel shows "futures unavailable".
3. **Drop LBank** from v1 and use one of the two free slots for another exchange.

**Decided and shipped: (2).** LBank is spot-only and the panel says futures is
unavailable; the adapter raises `NotSupported` for futures rather than guessing
a signature scheme. (3) was declined — all 8 exchanges are in v1 (Q1). (1) stays
live as an *external action* with unknown lead time, not an open decision: if
the private docs arrive, futures is added then.

**Spot is a full round trip.** `close_position` sells
the holding back at market (`sell_market`, sized in the base asset) instead of
raising `NotSupported`, so the Q5e policy can actually flatten a spot leg and a
bought position is never stranded. Note LBank's asymmetric market orders: a buy
carries the *quote* amount to spend, a sell carries the *base* quantity. Spot
still has no SL/TP through the documented API, so with the default Q5e policy a
spot leg with SL/TP set will buy and immediately sell back — which is the
policy working, not a bug, but it costs two fees. Set SL/TP to blank on LBank
spot, or wait for (1).

## Q11. Hyperliquid agent wallets ✅ They cannot withdraw; no testnet check

**Answered by the admin 2026-08-23.** An agent wallet has no withdrawal
function to sign with — not on Hyperliquid and not on any of the other seven —
so a testnet drill to prove it is not a release gate. The Hyperliquid adapter
ships as it stands and is not to be modified: it works.

The §7 enforcement around it is unchanged. A credential that *proves* withdrawal
rights is still refused at connect time, and `ConnectedAccount.clean()` still
blocks activating one that was never checked. Nothing was loosened by this
answer.

*On the record about the evidence:* the vendored docs and the `hyperliquid-docs`
server are silent on the question — they neither grant an agent withdrawal
rights nor deny them (checked again 2026-08-23). The answer here is the admin's
determination, not a citation, which is why it is written down rather than left
implied.

### The part that *is* a platform problem: expiry

From the technical team, and the one thing about agent access this platform must
handle itself: **an approval lasts at most 180 days.** Confirmed in the exchange
docs — `approveAgent` takes an optional `valid_until` capped at 180 days, and an
expired API wallet is **pruned** rather than refused. There is no error, no
rejection, and no endpoint to ask. The account simply stops trading.

So the platform tracks the date and counts down to it:

| Piece | Where |
|---|---|
| The date, recorded at connect time, validated against the 180-day ceiling | `ConnectedAccount.credential_expires_at`, `ConnectedAccountCreateSerializer.validate_credential_expires_at` |
| The countdown and its three states (`""` / `expiring` / `expired`) | `apps/accounts/credentials.py` |
| The persistent notice — raised once, escalated on expiry, **cleared on renewal** | `credentials.sync_notifications`, swept from `/accounts/accounts/balances/` |
| The panel: a banner in wallet management, a badge per row, the countdown on the account page | `pages/accounts/index.vue`, `pages/accounts/[id].vue`, `components/accounts/ConnectForm.vue` |
| `CREDENTIAL_EXPIRY_WARN_DAYS` (default **21**), `CREDENTIAL_MAX_AGENT_DAYS` (**180**) | `settings.CREDENTIALS` |

Three decisions inside that, each with a test in
`backend/tests/test_credential_expiry.py`:

1. **Reported, never enforced.** An expiring credential still trades, and an
   expired one is not removed from the fan-out. Dropping an account because a
   date is near would stop it for a reason the exchange never gave, on a guess
   that the partner has not quietly renewed. When it really is dead, the leg
   fails through the path every other failure already takes.
2. **A blank date warns about nothing.** Seven of the eight venues have no expiry
   at all, and an approval whose `valid_until` nobody recorded has a date this
   platform does not know. Filling in "connect + 180 days" would put a confident
   wrong number on screen; the ceiling rejects a typo, it never invents a date.
3. **The notice clears itself on renewal.** Spec §4's rule that a notice never
   expires on its own is about a failure that already happened. This is a
   countdown, and one that has been reset is a stale claim by the platform, not
   news the admin should have to dismiss by hand. It is still never cleared by
   *time* — only by the condition ending.

## Q12. Sizing arithmetic ✅ Flat 99%, so $9.90 — then rounded down to the step

Your example: accounts of $10, $50, $100 → use $9, $49.50, $99. $49.50 and $99
are exactly 99%, but 99% of $10 is **$9.90, not $9** ($9 is 90%).

**Decided: a flat 99% everywhere** — `BALANCE_FRACTION=0.99`, so $10 → $9.90.
The $9 is read as a typo, not a second rule. The result is then rounded **down**
to the exchange's quantity step, never up, and an account below the exchange's
minimum notional is skipped entirely rather than rounded up past 99% (spec §5,
Q18). `apps/trading/sizing.py`, `backend/tests/test_sizing.py`.

## Q13. Market data — where the chart's prices come from ✅ Public feed, labelled

Spec §3 wants a chart; nothing in the spec says where the prices come from. The
platform holds trading credentials, so the decision taken is that **market data
never touches them**: `apps/exchanges/marketdata.py` is a separate, credential-
free module that calls public endpoints (Binance, then Bybit) and caches the
result across all accounts. It is not an adapter and is not per account.

Three rules fall out of that, and they are implemented rather than assumed:

1. **There are no fake prices.** *(Amended 13 Aug 2026 — see below.)* With no
   provider reachable the API returns 503 and the panel says the feed is down.
   Nothing draws a candle nobody quoted.
2. **No price means no trade sized.** A market order has no price of its own,
   and sizing needs one (qty = notional / price). The reference price reaches
   the engine only when an exchange actually answered; otherwise the adapter
   must price itself (the paper adapter does) or the leg fails loudly.
3. **PnL is computed server-side, in Decimal.** `/api/trading/positions/` marks
   every leg to market and returns the numbers as strings. The browser renders
   them; it does not re-implement the formula in floats.

Set `MARKET_DATA_ENABLED=false` for an air-gapped deployment, or reorder
`MARKET_DATA_PROVIDERS`.

**Amendment, 13 Aug 2026 — the synthetic fallback is gone.** The original answer
allowed a labelled synthetic series so the chart still drew something. The admin
rejected that: the panel must carry real prices only. `SyntheticSource` is
deleted, `get_candles`/`get_ticker` raise, the endpoints answer 503, and the
panel renders an explicit "no price feed" state.

Removing it exposed why it had been firing on the development machine at all:
`httpx` inherits the shell's `ALL_PROXY`, and a `socks://` URL — what most
shells export — is a scheme it refuses outright, so *every* provider call failed
on a machine that could reach Binance directly. `marketdata.resolve_proxy()`
now normalises that to `socks5://` (with `socksio` installed), drops a proxy it
cannot parse instead of failing the call, and takes `MARKET_DATA_PROXY` as an
explicit override. A silent fallback had been hiding a plain configuration bug,
which is the second argument against having one.

## Q14. Emergency halt — a control, not a redeploy ✅ Runtime switch, env can pin

Spec §7 recommends a "stop all" and left the shape open. Decided:

- A `KillSwitch` row, flipped from the panel's top bar (any page) or Settings,
  effective on the next order — no restart.
- `STOP_ALL=true` in the environment **pins** it on: the API refuses to clear a
  halt that was deployed, and the panel renders the control locked.
- Halting is one click with no dialog; **resuming** asks. The moment a halt is
  wanted is not the moment to fill in a form.
- Closing and amending open positions keep working while halted. A halt that
  stranded open leveraged positions would be more dangerous than what it stops.
  (Amending only *said* so until the audit: `amend_sltp` fanned out with the
  default `respect_stop_all=True`, so a halted amend returned HTTP 500. Both
  paths now pass `respect_stop_all=False` and both have a test —
  `test_sltp_can_still_be_amended_while_halted`.)
- When the switch cannot be read at all (database down), routing is treated as
  **halted**. Failing open would route partner capital on a guess.
- **Amended in use (2026-08-19).** The panel's Stop-all now *also flattens*:
  one request that halts routing and then market-closes every open trade. The
  admin's reading of the control is the operative one — stopping the next order
  does nothing about the leveraged position already running, which is the
  situation the button is reached for. The halt is applied first so nothing can
  be routed into the gap while the close fans out, and a leg the exchange would
  not flatten leaves its trade OPEN with its own §4 notice rather than being
  reported as closed.
  The API keeps the old meaning by default: flattening happens only when the
  caller sends `close_positions: true` (what the button sends), so a halt
  flipped by anything else still touches nothing that is already live.
  Pinned by `test_stop_all_can_flatten_every_open_trade` and
  `test_a_plain_halt_still_leaves_open_positions_alone`.

## Q15. One open trade per account ✅ Enforced server-side, per account

Spec §5 states it; nothing enforced it. A second entry now excludes accounts
that already hold a filled, unclosed leg, rather than refusing the whole
fan-out: one account still winding a position down is no reason to keep the
other nine flat. If *no* account is eligible the API answers 409 rather than
recording an empty trade — a ghost open trade would sit in the positions panel
looking like a position nobody holds.

## Q16. Failure notices moved into the top bar ✅ Spec §4 amendment, on the record

Spec §4 asks for a persistent ~190 × 110px notice at the top of the screen. Built
as specified, it covered the chart at exactly the moment the admin needed to
read it — reported in use, so the placement changed and the requirement did not:

- the notices now live in a **notification centre in the top bar**, present on
  every page, with an amber count on the bell whenever anything is outstanding;
- **nothing auto-expires.** Only an explicit dismiss clears an item, and the
  dismissal is recorded server-side so it survives a reload;
- a newly arrived failure **opens the panel by itself**, so it is still
  unmissable rather than merely available;
- each card keeps the spec's dimensions inside the panel.

The requirement spec §4 is protecting — a failed order on a partner's account
cannot be missed or silently timed out — is intact. The fixed screen position is
what was given up, and this is where that is recorded (spec §10 allows it).

## Q17. Installable panel (PWA) ✅ Manifest, icons, minimal worker

Requested after first use on a phone. `frontend/public/manifest.webmanifest`
plus a 192/512/maskable icon set and a 180px `apple-touch-icon`; iOS reads the
`apple-mobile-web-app-*` meta tags instead of the manifest, so those are set too.

`public/sw.js` exists **for installability, not for offline trading**, and is
written so it cannot make the panel lie: `/api/**` and `/ws/**` are never
cached, navigations are network-first, and only content-hashed build assets are
served from the cache. A cached balance or price is a wrong number presented as
a current one, which on this panel is worse than an error.

## Q18. Minimum notional on OKX and Gate.io ✅ Derived, not guessed

Spec §5 says an account below the exchange's minimum is **skipped** with a
notice. That decision is only as good as the minimum it compares against.

`OkxAdapter.get_symbol_rules` and `GateioAdapter.get_symbol_rules` both returned a
hardcoded `min_notional = D("5")`. Neither exchange publishes a per-symbol
minimum notional in the instrument endpoint the adapter already calls — OKX
enforces `minSz` (a quantity), Gate enforces a whole number of contracts — so
the 5 was a stand-in, not a reading.

It was demonstrably wrong elsewhere: Binance returns **50** for BTCUSDT, verified
live on 2026-08-13. A small account that should have been skipped could therefore
be sent an order the exchange rejects, and a leg fails at the exchange instead of
being cleanly skipped by sizing.

Options:

- Derive the floor from what the exchange *does* publish (`minSz` × mark price
  on OKX; `quanto_multiplier` × mark price on Gate) — correct, one extra call.
- Keep a constant but make it per-exchange and sourced, not a shared 5.
- Leave it and accept exchange-side rejections for tiny accounts.

*Resolved 2026-08-16 with the first option* — implemented in both adapters:

- **OKX**: `min_notional = minSz × ctVal × price`, where price is the mark price
  for futures (`GET /api/v5/public/mark-price`) and the last trade price for spot
  (`GET /api/v5/market/ticker`, futures-only mark endpoint otherwise).
- **Gate.io**: `min_notional = quanto_multiplier × mark price`, one whole
  contract valued at today's price. The adapter also stopped declaring `SPOT` in
  its capabilities — it never supported it.

The engine already reads `rules.min_notional` (via `get_symbol_rules`) when
sizing, so the fix flows straight into skip decisions. See
`docs/exchanges/coverage.md`.

## Q19. Fan-out deadline 1s → 4s → 3s → 5s → 10s, and the re-read behind it ✅ Spec §4 amendment, on the record

Reported in use: on the production VPS a healthy entry was failing the §4
deadline. Each leg's exchange round trips (balance, leverage, order, then
SL/TP placement) were landing at 1–2 seconds, the 1s cap turned that into a
failure notification nobody could act on, and the panel showed a fake
"within the budget" reading against the same number that was being blown.

The change and what it deliberately is not:

- `FANOUT_TIMEOUT_SECONDS` now defaults to **10.0** (`config/settings.py`,
  `.env.example`, `.env.production.example`), with an env override per
  deployment. Test hooks take an explicit `timeout=` so the suite stays fast
  and the platform default is only exercised at its true value. The number has
  moved 1.0 → 4.0 → 3.0 → 5.0 → 10.0; each step was reported from live use, and
  the direction is deliberate. The deadline is a tripwire for an exchange that
  has genuinely stopped answering, not a service-level target for a healthy
  leg, and every second of it costs nothing when nothing is stuck.
- It is **not** a relaxation of §4's concurrency contract. Legs still run in
  one `asyncio.gather`; one slow exchange still cannot hold up the others past
  the deadline; a leg that overruns is abandoned, not awaited; a failed order
  still raises a persistent notification.
- The spec text (platform-spec.md §4), conformance table, gap analysis, and
  the deploy runbook now all name the setting rather than the number.

Why not instead make the fan-out tolerate the 1s by pooling connections or
warming adapters? Pooling *one account's leg into another's* is still
forbidden — §2 isolation is absolute — and that was the version rejected in
the first amendment. What was added instead is a **warm adapter pool**
(`apps/exchanges/pool.py`): each account keeps its own isolated adapter, its
own client, its own rate limiter, and the pool only keeps *already-created*
adapters alive between actions. A leg no longer pays a TCP + TLS handshake
(and Hyperliquid no longer re-downloads its asset catalogue) before its first
real call, so a healthy leg lands in tens of milliseconds — which is what lets
the default sit at 3.0 rather than 4.0.

**Note:** the change moves the *deadline*. The panel's "within the budget"
check and the audit `fanout_ms` both read `FANOUT_TIMEOUT_SECONDS`, so they
stay truthful together.

### The deadline was never the real bug — the reporting was

Raising the number does not fix "the panel said the trade failed and the
exchange had opened it"; it only makes it rarer. Cancelling a coroutine cannot
unsend a request the exchange already received, so **any** leg that fails after
the order goes out may describe a position that exists.

Two things were wrong, and both are fixed:

1. **Only the deadline was re-read.** The reconcile ran for `leg.timed_out`
   alone. But the HTTP client's own ceiling sits *below* the fan-out deadline
   (`rest.default_timeout` is 0.75 of the budget), so a slow venue almost
   always raised `ExchangeUnavailable: request timed out` first — a plain
   adapter error, which never reconciled. That was the reported bug. The
   re-read now covers every **unconfirmed** leg: everything whose failure code
   is not in `fanout.NEVER_SENT_CODES` (sizing skips, the SL/TP resolver, the
   local rate limiter, a rejected credential — the failures the platform can
   name the moment it stopped).
2. **"Unknown" was reported as "did not happen".** A re-read now has three
   outcomes, not two: `late_fill` (the exchange holds the position — it is a
   fill, with protection attached or confirmed), `not_filled` (the exchange
   answered and holds nothing — the reason is kept, the account is freed), and
   *unchanged plus a warning* when the venue will not answer at all, which
   tells the admin in as many words that it is **not known** whether the order
   landed. Only the second one is treated as proof that nothing happened, and
   only for a market order — a resting limit order shows no position and is
   still live.

And because the response to the admin has to end, there is a second half:
`services.reconcile_open_trade()` asks the same question again, later, off the
positions poll (rate-limited to one sweep every five seconds across all open
panels). A fill that landed twenty seconds past the deadline still becomes a
position the panel counts, with real size, entry and PnL. Until it settles, the
account is **not** offered a new trade — spec §5's one-position-per-account
rule reads "unknown" as "possibly holding", because the alternative is routing
a second entry into an account that already has one.

## Bot mode — Q20–Q27 ✅ Answered 2026-08-23

Eight decisions that shape `docs/bot-mode.md`, taken before any of it is built,
because every one of them is cheap now and expensive in that document's Phase 6.
Same standing as Q1–Q9: binding.

The frame all eight sit inside: **a bot is a signal source, not a second
execution path.** It calls `route_open` / `route_amend` / `route_close` — the
same calls the admin's own button makes — and inherits §5 sizing, the §4 fan-out
and its deadline, account isolation, `NEVER_SENT_CODES` reconciliation, the §7
halt and §8 history by going through the front door. A second order path for the
bot would be a second set of all of those, silently different.

What actually changes when the human leaves the loop, and what every answer
below is defending against: a bug **repeats** — once per bar, at 99% of every
partner's balance; **nobody is watching at 03:00**, so "the admin sees the
notification and acts" is not a failure plan; and the blast radius is the whole
book, because there is no diversification anywhere in this system by design.

### Q20. Who decides position size ✅ The platform, always

`strategy.entry("L", strategy.long, qty=2)` names a quantity. §5 says margin is
99% of *that account's* balance with leverage on top. Both cannot hold.

**The script decides direction and timing; the platform decides size.** `qty`,
`strategy.percent_of_equity`, `default_qty_value` and `default_qty_type` are
parsed for compatibility and then **ignored, with a warning shown at upload
time** — never silently, per Q24's rule against a script that lies.

Honouring `qty` would hand a $50 account and a $50,000 account the same two
units, which is not a smaller version of the same trade — it is a different
strategy on each account. Rounding stays where it already is: `sizing.py` floors
to the exchange step and skips below minimum notional, and the bot rounds
nothing itself.

The type carries the decision: `StrategyIntent` has no quantity, leverage,
account or price field at all, so there is nowhere for a script's `qty` to
travel to.

### Q21. Leverage and SL/TP ✅ Bot-level settings; a percent `strategy.exit` wins per trade

The bot's configuration carries `leverage`, `sl_pct` and `tp_pct` exactly as the
order ticket does, and they are identical across accounts like every other
trade (§5).

If the script *also* calls `strategy.exit(loss=…, profit=…)` **in percent**, the
script wins for that trade — it is the more specific instruction — converted to
whichever Q5a basis is in force and validated against the liquidation distance
the same way the ticket validates a typed-in stop.

`strategy.exit` **in ticks or points is rejected at validation.** Converting
either needs the symbol's tick size and contract rules, which the script has no
access to and which differ per exchange; a silent guess there is a stop in the
wrong place on seven venues out of eight.

### Q22. Contention for an account ✅ First claim wins, and the admin outranks a bot

One open trade per account (§5, Q15) means two bots on two symbols will contend,
and so will a bot and a manual entry.

1. A bot entry **skips** any account already in an open trade. The existing
   `accounts_in_open_trades` check already refuses it; the bot reports it as
   **"sat out"**, not as a failure — it is the spec §6 rule, not an error, and
   the account joins the next trade.
2. A **manual** entry on an account a bot is holding is **refused**, with a
   message naming the bot and a one-click "stop the bot and take the trade".
   Quietly taking the position would leave the bot's state machine describing a
   position it no longer has.
3. **`close-all` and Stop-all stop every running bot.** This is the most
   important line of the eight. A halt that flattens positions while a bot is
   still evaluating is a halt that re-enters ninety seconds later — which is not
   a halt. `killswitch.set_stop_all(True)` and the panel's flatten path both
   stop bots, pinned by `test_stop_all_stops_every_running_bot` and
   `test_a_stopped_bot_does_not_re_enter_after_a_flatten`.

### Q23. Bar timing ✅ Confirmed bars only; `calc_on_every_tick=true` is a validation error

The bot evaluates **once, on bar close**, and routes immediately after. A
realtime bar repaints — the value a condition read mid-bar can be gone by the
close — and the backtest never sees that, which is the mechanism behind nearly
every "it backtested beautifully and lost money live". Removing it makes backtest
and live identical except for slippage, which is measurable.

`calc_on_every_tick=true` is therefore **honoured nowhere**: there is no
configuration in which this platform evaluates intrabar in v1. It was a
validation *error* until 2026-09-04 and is now an accepted-and-reported inert
property (`properties.INERT`) — the behaviour is identical and the script still
loads, because refusing a whole strategy over a setting that changes nothing
here is a rejection with no remedy.
Intrabar can return in v2 behind a per-bot flag, on top of the snapshot/restore
hooks the runtime is built with anyway, and only with a divergence test.

### Q24. The Pine subset ✅ The v1 list in `docs/bot-mode.md` §1.3 — everything else rejected by name

Full Pine v5 is a large language and chasing all of it is how this runs for six
months. v1 covers the subset listed there — series, `ta.*`, `math.*`, control
flow, user functions, inputs, `strategy.entry/close/close_all/exit`, plots as
recorded annotations — and the validator **rejects anything outside it by name,
line and column**.

Nothing outside the subset is ever silently ignored. `request.security`,
`array`/`matrix`/`map`, drawing objects, `strategy.order`/`cancel`, `pyramiding`,
`import`, and `strategy.risk.*` each get their own message saying which construct
and why. The rule is the same one Q13 took for prices: a script that loads and
quietly does not do what it says is worse than a script that will not load,
exactly as a synthetic price series is worse than a 503.

**Amendment (2026-09-03): user-defined types, methods and enums are now in the
subset.** They were three of the rejections above — "needs a type system" — and
the type system now exists (`apps/pine/objects.py`): `type` declares an object
with typed fields and defaults, `method f(T this, …)` binds a function to a type
and is dispatched and overloaded by receiver type, `enum` is a closed set of
named members usable as a `switch` subject. Objects are assigned by reference,
`var` persists one and its fields, and `Name.copy()` is the shallow copy that
breaks the reference. The Q24 rule is unchanged and still applies *inside* the
feature: the validator rejects an unknown field type, a duplicate type or
method, a method on an unknown receiver, an order call inside a method, and
recursion through methods — each by name, line and column — and `obj.field[n]`
(per-field history) stays rejected the same way `(a + b)[n]` is. What the
lightweight `var → type` inference cannot reach is a located runtime error on
the first bar, never a silent `na`. `apps/pine/parser.py`, `validate.py`,
`runtime.py` and `objects.py` hold it; `tests/fixtures/pine/accept/24_*`,
`25_*` and five `reject/semantic__*` fixtures pin it.

**Amendment (2026-09-04): what a *published* strategy is made of.**
Running the example the admin supplied — `McGinley T3 Flow Campaign`, 731 lines,
`//@version=6` — through the engine produced sixty-eight errors, not one of which
named the real problem. Q24's rule was intact; what was wrong was where the line
had been drawn. Four changes, and one refusal that stands:

- **Line wrapping is read.** TradingView continues a line indented by any number
  of spaces that is *not* a multiple of four (`style_guide.md`). The lexer
  accepted only a trailing backslash, which no exported script contains, so a
  wrapped ternary chain was a syntax error — and the parse error was then
  *replaced* by a sweep of the rest of the file for rejected namespaces, turning
  one unreadable line into sixty confident errors about lines that were fine.
  Both are fixed; the sweep now only reports what sits at or before the failure.
- **Drawing objects are accepted and drawn nowhere.** `line`, `label`, `box`,
  `table`, `polyline` and `linefill` used to be five rejections whose message
  read "has no execution effect here" — and then errored, which is the one
  combination that cannot be right, since a construct with no execution effect
  is exactly the kind this subset already accepts and records (`plot`,
  `bgcolor`). Constructors return an opaque handle so `if na(myLine)` decides
  create-or-move as it does on TradingView. The half that *can* reach an order
  is still refused by name: `DRAWING_READBACKS` — `line.get_price` and its
  family — because a coordinate read back out of a drawing becomes a condition,
  and a condition becomes an order.
- **Decorative constants are values, not argument-list decorations.** `color.*`,
  `size.*`, `position.*` and the rest were accepted only inside a `plot()`
  argument list. Every real script writes `col = up ? color.green : color.red`
  on a line of its own, so the rule cost scripts and bought nothing: a colour
  still has no arithmetic that produces a side, a price or a percent.
- **v6 is read as well as v5**, on the argument this repository already makes —
  the operators, the execution model and every `ta.*` formula are shared, and
  `reference/pinescriptv6/` is what the implementation is checked against. The
  two differences that could bite are recorded as **Q34** rather than asserted.

The refusal that stands is **`strategy.close(qty_percent = …)`** — a partial
close. Q20 drops `strategy.entry(qty = …)` with a *warning* because the
platform's own sizing is a complete answer to the question that argument asked.
Nothing answers a scale-out: `ExchangeAdapter.close_position` takes no size, so
the nearest available action is to flatten an account the script meant to keep
most of. That is a different strategy and a silent one, which is what this
decision exists to refuse. **Q33** carries the feature, alongside `pyramiding`,
which is the same multi-lot position model seen from the other side.

Also added rather than left to be discovered from a rejection: `syminfo.*`,
`timeframe.*`, `chart.*`, `timenow`, the `int`/`float`/`bool`/`string` casts,
the rest of `str.*` and `math.*`, `input.color`/`time`/`price`/`session`/
`symbol`, and the `strategy.*` performance figures (`closedtrades`,
`netprofit_percent`, `max_drawdown_percent`, …) that every published dashboard
is built from. The performance figures come from the **driver** —
`backtest._Engine._performance` and `supervisor._performance` — for the same
reason `strategy.position_size` does: the account is the driver's, and a runtime
keeping its own scoreboard would be a second one that could disagree.

`tests/fixtures/pine/accept/27_published_strategy.pine` is that example, kept as
a fixture with one edit (the scale-out), so it is lexed, parsed, validated, run
and checked for reproducibility on every commit.

### Q20 note (2026-09-04): the Properties tab is honoured by the backtest

`strategy()`'s ten Properties-tab settings — initial capital, base currency,
order size, pyramiding, commission, limit-fill verification, slippage, margin,
recalculation, fill model — used to be nine warnings saying "parsed and then
ignored". They are now `apps/pine/properties.py`, resolved in one direction
(platform default → what the script declared → what the panel overrode) and
honoured by the backtest, which is what makes a report comparable with the one
TradingView produced from the same script.

Q20 itself is unchanged and is why they are *backtest* properties: live margin
is 99% of each account's own balance with leverage on top, identical across
accounts. So `StrategyProperties.live_departures()` names every setting that
would make the report describe a platform the bot will not run on, the report
header prints them, and `Assumptions._sizing_line` says whose sizing rule
produced the curve rather than always claiming §5. `inert_here()` is the second
list: `calc_on_every_tick` (Q23 — no tick data to recalculate from) and
`fill_orders_on_standard_ohlc` (no Heikin Ashi candles to correct) are accepted
and reported as doing nothing, rather than refusing the script over a setting
that changes no behaviour here.

### Q25. The bot's own halt ✅ Seven auto-stop triggers, none of them auto-resume

Separate from and on top of the §7 platform kill switch, because the kill switch
answers "the admin wants everything stopped" and this answers "nobody is awake
and this bot is behaving in a way that means something is wrong".

| Trigger | Default |
|---|---|
| Consecutive losing trades | 5 |
| Drawdown from the bot's own peak equity | 15% |
| Bar feed gap that could not be repaired | any |
| Runtime error in the script | any — the first one |
| Broker state disagrees with bot state after 2 reconcile passes | any |
| Trades in a rolling hour | > 10 |
| Running with no confirmed bar for | 3× the timeframe |

Every row is configurable per bot with these as defaults, and every row is
**auto-stop, never auto-pause-and-resume**. A bot that stopped itself is
restarted by a person who has read why. An unrepairable feed gap stops rather
than skips, because the strategy's state machine now disagrees with the market;
a state disagreement stops rather than self-corrects, because auto-correcting a
disagreement nobody understands is how a recovery becomes a liquidation.

### Q26. Retention ✅ Every intent and action forever; bars by timeframe

`BotAction` and the intent that produced it are kept **forever**. That is the
audit trail — what the bot decided, when, why, and which legs came back — and it
is small.

Bars are the volume: 1,440 rows/day/bot at 1m. At **15m and above, every
evaluated bar is kept for the bot's lifetime**. At **1m and 5m**, only bars where
a signal or a plot value changed, plus a rolling 7-day full window for
debugging. The audit trail never depends on the bars, so trimming them loses
detail, never accountability.

### Q27. Hidden accounts ✅ Unchanged — routed to like everything else, filtered on every read

`ConnectedAccount.hidden` stays read-side only. A bot fans out to hidden
accounts identically, and nothing in `apps/pine/` or `apps/bots/` may import
`accounts.visibility` — the same prohibition `apps/engine/` is under.

Every bot **read** surface filters: bot list, bot detail, run history, backtest
reports that name accounts, and every `bot.*` WebSocket payload carrying
per-account data — totals included. Each gets its own case in
`tests/test_account_access.py`. A new bot page shipped without a filter is the
most likely way this invariant gets broken, so the test file is the checklist.

---

## Q28. Cash-flow detection threshold ✅ Per exchange, built that way from the start

**Answered by the admin 2026-08-23.** Not global-for-now-and-split-later: this
platform is meant to run for years, so the shape it will need is the shape it
gets built in. Retrofitting a per-venue threshold later means touching the money
path with live history behind it, which is the worst time to do it.

What was wrong with one number: a perpetual venue pays funding several times a
day and a spot venue pays none, so a single percentage either hides small real
transfers on spot or proposes funding as a withdrawal on perps. It cannot be
right in both places.

```
LEDGER_DETECT_MIN_PCT_HYPERLIQUID=0.5
LEDGER_DETECT_MIN_USDT_BYBIT=2
```

`settings._detect_overrides()` reads any `LEDGER_DETECT_MIN_{USDT,PCT}_<EXCHANGE>`
out of the environment into `LEDGER["DETECT_PER_EXCHANGE"]`, and
`detection.threshold(equity, exchange)` reads the override before the global.
Three properties, each with a test in `tests/test_ledger_detection.py`:

- **Each half falls back on its own.** Overriding the floor does not silently
  reset the percentage to a default nobody chose.
- **An untuned venue behaves exactly as before.** The global pair is the
  fallback, not an error — so this change moved no existing threshold.
- **Adding an exchange needs no change here.** The names come from the
  environment, not a hardcoded list.

The defaults stay global and identical until real venue data says what each
spread actually is. That measurement is not a decision, and the code no longer
waits for it.

---

# Recorded — not questions

### Legal and regulatory standing ✅ Signed off (2026-08-23)

Spec §11 flagged that routing trades for $50k–$100k of other people's capital
can trigger financial-services or trading-adviser registration depending on
jurisdiction and compensation structure.

**The admin confirms this has been reviewed and signed off by a lawyer.** It is
closed and it is not a repository question: no code change follows from it, and
nothing here gates on it. The spec's own §11 note stays as written — it records
why the question was asked, and the spec is the contract.

### Financial Management — the ledger and profit split (2026-08-16)

The admin trades once; the ledger records what capital each account has and
splits profit by role. Four decisions, now binding:

1. **Cash flows are recorded manually.** Deposits and withdrawals are entered
   in the panel, not imported — §7 requires trade-only, non-withdrawable API
   keys, so no exchange can move money and no import API exists to call. This
   is a feature boundary, not a missing one.
2. **The split divides profit only.** On a loss there is nothing to divide;
   the loss is the PnL shown, and every share is 0.
3. **One global split** in the panel settings (default investor 60 / trader 20
   / programmer 20) applies to every account; the percentages must sum to
   exactly 100. Percentages, not dollars — each account's profit is scaled by
   them.
4. **PnL is since inception**, per account and in the totals, from
   `last_balance` (the live balance poller). Nothing in the ledger is an
   exchange import; mark-to-market comes from the existing balance feed.

Backed by `backend/apps/accounts/ledger.py`, `/accounts/ledger/*` endpoints
(`tests/test_ledger.py`, `tests/test_hidden_accounts.py`) and the `/finance`
page + Settings "Profit split" card.

### Detecting a cash flow the exchange will not report (2026-08-20)

An amendment to decision 1 above, not a reversal. Cash flows are still recorded
by a person — §7 keys are trade-only and no import API exists — but the platform
no longer stays silent when it can see money move. It subtracts:

```
equity now − equity at the last flat reading
  − PnL of the legs it closed itself in that window       (A: a trade result)
  − deposits and withdrawals already recorded in it       (already explained)
  = unexplained                                            (B: out, C: in)
```

Five decisions, now binding:

1. **Equity, not available balance.** Available drops the moment margin is
   locked into a position, which would read as a withdrawal on every entry.
   `ConnectedAccount.last_equity` is the exchange's `Balance.total`.
2. **Flat to flat only.** Equity carries unrealised PnL, so mid-trade it moves
   with the market. `ledger_cursor_*` only advances on a reading taken while the
   account holds no open leg, so no window can contain a market swing.
3. **Proposed, never booked.** A `DetectedMovement` is a queue item. Invested
   capital changes only when an operator accepts it, and they may correct the
   direction and the amount on the way in — the platform inferred both by
   subtraction, and the person who moved the money knows better.
4. **A threshold, not exactness.** Fees, funding and exchange rounding move
   equity without anyone moving money. `LEDGER_DETECT_MIN_USDT` (a floor) and
   `LEDGER_DETECT_MIN_PCT` (a share of the account), larger wins. Below it the
   cursor still advances, so the noise never accumulates into a false proposal.
5. **Every write is attributed.** `LedgerEvent` is append-only and records the
   actor, the action, and the before/after of the fields that actually changed
   — including deletions, which outlive the row they describe. A blank actor
   means the platform itself, which is only ever the `detected` action.

Open: whether the threshold should be per-exchange — **Q28 in `questions.md`**.

Backed by `backend/apps/accounts/detection.py`, `backend/apps/accounts/
bookkeeping.py`, `/accounts/ledger/detections/*` and `/accounts/ledger/events/`
(`tests/test_ledger_detection.py`), and the `/finance` page's "Unexplained
balance changes" and "Who changed what" cards.
