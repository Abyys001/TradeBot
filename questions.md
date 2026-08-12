# Questions & decisions

**Status: Q1–Q4, Q6–Q9 answered by the admin 2026-08-11 and now binding.**
Q5 was too vague to answer — it is re-asked below, broken into five concrete
sub-questions. Q10–Q12 are new, found while downloading the LBank/Toobit/
Hyperliquid docs.

Answers here are the source of truth alongside `docs/spec/platform-spec.md`.

---

# Open — need answers

## Q5. SL/TP semantics — re-asked concretely

The original question was too broad. Five separate decisions, each with a
worked example. **Q5a and Q5e are the important ones.**

> **Both options are already built.** Every sub-question below is a setting in
> `.env`, with both branches implemented and tested — answering it is a config
> change, not a rewrite. To decide Q5a by looking at numbers rather than prose,
> run the stack and open **`/risk`** in the panel: type a balance, leverage and
> SL%, and it shows what that percentage costs under both readings side by side.
> Same numbers via the API:
>
> ```bash
> curl -X POST localhost:8000/api/trading/risk-preview/ \
>   -H 'Content-Type: application/json' \
>   -d '{"balance":"1000","leverage":10,"entry":"100000","side":"long","sl_pct":"2"}'
> ```

### Q5a. Is SL/TP a percentage of price, or of your money?

Worked example — $1,000 account, 10x leverage, BTC at $100,000. Margin is 99% of
$1,000 = **$990**; notional = $990 x 10 = **$9,900** ≈ 0.099 BTC.

You type `SL = 2%`. That can mean two very different things:

| Reading | Price move | SL trigger price | Loss if hit | % of account |
|---|---|---|---|---|
| **A — 2% of entry price** | 2% | $98,000 | 2% of $9,900 = **$198** | **19.8%** |
| **B — 2% of margin** | 0.2% | $99,800 | 2% of $990 = **$19.80** | **1.98%** |

Reading A loses **10x** what reading B loses — the leverage multiple. Both are
reachable here: liquidation at 10x sits 1/leverage = **10%** away ($90,000), so
a 2% stop triggers long before it.

The trap in reading A is the size of a "small-sounding" number: `SL = 2%` costs
a fifth of the account, and `SL = 10%` or more can never trigger at all,
because liquidation comes first.

- Which reading do you want?
- If A (price %), do you want the order ticket to display the resulting loss in
  dollars and as % of account, and to refuse an SL at or beyond the liquidation
  distance (≥10% at 10x, ≥20% at 5x)? Strongly recommended either way.

*(Correction: an earlier version of this file put liquidation ~1% from entry and
the loss at $1,980. Both were wrong — liquidation distance is 1/leverage and does
not depend on how much margin is committed, and the notional was overstated 10x.
The numbers above are the ones the code computes; `backend/tests/test_sltp.py`
asserts them.)*

*My recommendation:* percent **of price** (matches how traders and TradingView
think, and matches what you drag on the chart), but the order ticket shows the
dollar risk and % of account next to it in real time, and blocks an SL placed
past liquidation. Say the word if you meant margin %.

### Q5b. Same percentage or same price across accounts?

Spec §4 says identical SL/TP percentages on every account. All accounts fill at
slightly different prices (different sizes, different exchanges, different
moments within the 1-second window). So:

- Does each account compute its SL/TP from **its own fill price** (same %,
  different absolute prices), or
- Does every account get the **same absolute price**, taken from your admin
  account's fill?

*Recommendation:* same **percentage off each account's own fill price** — this
is literal spec §4 and it makes each partner's risk identical in % terms.

### Q5c. When you drag the SL line on the chart, what actually propagates?

Dragging gives an absolute price on your chart. Every account then needs a new
SL. Same fork as Q5b: recompute the % from your position and apply that % to
each account's own entry, or push your absolute price to everyone?

*Recommendation:* convert the drag to a % relative to **your** entry, then apply
that % to each account's own entry. Consistent with Q5b.

### Q5d. Amending SL/TP — brief gap, or brief overlap?

Some exchanges cannot modify a stop order; they need cancel-then-place. Two
orderings:

- **Cancel first, then place**: for ~50–300ms the position has **no stop at
  all**. If price gaps in that window, the loss is uncapped.
- **Place first, then cancel**: for that window there are **two stops**. If both
  trigger, the second one opens a position in the opposite direction (unless
  reduce-only is supported, which mostly it is).

*Recommendation:* place-first-then-cancel, with reduce-only set on every
stop so a double-trigger cannot flip the position. Where an exchange supports
true amend (Bybit, Hyperliquid), amend and skip the dance entirely.

### Q5e. Entry filled but SL/TP placement failed — what then?

This is the most dangerous state in the system and the spec does not cover it.
The account now holds a **10x leveraged position with no stop loss**. Options:

1. **Retry** the SL/TP (how many times, over how long?).
2. **Close the position at market immediately** — guarantees no unprotected
   exposure, but exits a trade you wanted, at a small loss.
3. **Notify and leave it** — the position rides unprotected until you act.

*Recommendation:* retry twice over ~2 seconds, then close at market and raise a
persistent failure notification. Never leave a leveraged position unprotected.

---

## Q10. 🔴 LBank futures cannot be built — decide the fallback

LBank's published contract API (`reference/exchanges/lbank/api/contract.md`,
downloaded in full) documents **only the public namespace**
`/cfd/openApi/v1/pub` — server time, contract list, market list, order book.

There are **no publicly documented private futures endpoints**: no place order,
cancel, position, balance, set-leverage, or SL/TP. The futures host
(`https://lbkperp.lbank.com`) is live and responds, but without the private
request/signature schemas an adapter cannot be written. LBank spot, by contrast,
is fully documented and implementable today.

You said all 8 exchanges are in v1, so pick one:

1. **Ask LBank for the private futures API docs** — email service@lbank.com from
   an account with futures API enabled. This is the only path to real LBank
   futures. Unknown lead time.
2. **Ship LBank as spot-only** in v1, panel shows "futures unavailable".
3. **Drop LBank** from v1 and use one of the two free slots for another exchange.

*Recommendation:* start (1) today since it has external lead time, ship (2) in
the meantime.

## Q11. 🔴 Hyperliquid — can an API wallet withdraw?

Spec §7 makes non-withdrawable credentials a hard requirement. Hyperliquid has
no API keys: the platform holds an **agent-wallet private key**. The docs I
searched do not state whether an agent wallet can sign a withdrawal or a
`usdSend`/`spotSend` transfer.

Until this is verified on testnet, connecting a real partner's Hyperliquid
account may violate spec §7 without anyone realizing.

- Do you want this verified on testnet before the Hyperliquid adapter ships?
  (I can test it: approve an agent on testnet, attempt a withdrawal with it,
  record the result.)
- If agent wallets *can* withdraw, is Hyperliquid still in v1? It would be the
  one exchange where a platform breach could drain partner funds.

*Recommendation:* verify on testnet first, and treat the result as a go/no-go
for Hyperliquid onboarding. Also note agent approvals **expire (max 180 days)** —
the platform must track expiry per account and warn before a partner silently
stops trading.

## Q12. Sizing arithmetic — your example says $9, the rule says $9.90

Your example: accounts of $10, $50, $100 → use $9, $49.50, $99.

$49.50 and $99 are exactly 99%. But 99% of $10 is **$9.90, not $9** ($9 is 90%).

- Typo, and the rule is a flat 99% everywhere?
- Or is there rounding-down to a step size that I should implement (and if so,
  to what precision)?

*Assumption until you say otherwise:* flat 99%, so $9.90 — with the result then
rounded **down** to the exchange's quantity step, never up.

---

## Q13. Market data — where the chart's prices come from ✅ Public feed, labelled

Spec §3 wants a chart; nothing in the spec says where the prices come from. The
platform holds trading credentials, so the decision taken is that **market data
never touches them**: `apps/exchanges/marketdata.py` is a separate, credential-
free module that calls public endpoints (Binance, then Bybit) and caches the
result across all accounts. It is not an adapter and is not per account.

Three rules fall out of that, and they are implemented rather than assumed:

1. **Fake prices are labelled.** With no provider reachable, the API serves a
   deterministic synthetic series with `live: false`, and the panel renders a
   "sample prices" badge next to the price. An unlabelled fake series on a
   trading screen is how someone reads a number that was never real.
2. **A synthetic price never sizes a trade.** A market order has no price of its
   own, and sizing needs one (qty = notional / price). The reference price is
   passed to the engine *only* when the feed is live; otherwise the adapter must
   price itself (the paper adapter does) or the leg fails loudly.
3. **PnL is computed server-side, in Decimal.** `/api/trading/positions/` marks
   every leg to market and returns the numbers as strings. The browser renders
   them; it does not re-implement the formula in floats.

Set `MARKET_DATA_ENABLED=false` for an air-gapped deployment, or reorder
`MARKET_DATA_PROVIDERS`.

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
- When the switch cannot be read at all (database down), routing is treated as
  **halted**. Failing open would route partner capital on a guess.

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

---

# Answered — binding decisions

## Q1. Exchanges ✅ All 8 in v1

Binance · Bybit · OKX · Gate.io · KuCoin · Hyperliquid · LBank · Toobit.
Hyperliquid uses the connected `hyperliquid-docs` MCP server as its doc source.

**Done since:** LBank and Toobit docs downloaded and converted to Markdown —
`reference/exchanges/lbank/api/` (spot + contract) and
`reference/exchanges/toobit/api/` (27 pages incl. copy-trading). Hyperliquid
integration notes written to `reference/exchanges/hyperliquid/README.md`.
The two placeholder `TODO.md` files are gone.

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

---

## Not a question — recorded

Spec §11: routing trades for $50k–$100k of other people's capital can trigger
financial-services or trading-advisor registration depending on jurisdiction and
compensation structure. Lawyer question, not a repo question. Noted so it is not
forgotten before the first real partner account connects.
