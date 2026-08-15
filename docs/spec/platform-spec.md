# Multi-Account Trading Platform — Specification

## 1. Purpose & Core Concept

This platform is **not an exchange**. It is an order-routing and execution layer:
the operator (admin) trades manually through a single trading interface, and every
order — entry, SL/TP adjustment, and close — is simultaneously routed via API to
a set of connected accounts (the admin's own account plus partner/investor
accounts), each on their own exchange.

The admin trades once; every connected account mirrors that exact action.

## 2. Core Architecture Requirements

- Must support connecting to **up to ~10 different exchanges**.
- Must support **multiple independent accounts on the same exchange**
  (e.g., 5 partner accounts all on Hyperliquid) as **completely separate,
  isolated connections** — each with its own API key/session. One account's
  actions, rate limits, or errors must never affect another account, even on
  the same exchange. (This requirement exists specifically because a prior
  platform the admin used could not support more than one connection per
  exchange — this must not be a limitation here.)
- Supported markets: **spot and futures/perpetual**. No other market types
  required.
- The admin's own account is connected and traded through this platform the
  same way partner accounts are — there is no separate "admin-only" trading
  path.

## 3. Manual Trading Interface

A main trading page, similar in layout to a standard exchange:

- **Chart**: connected to TradingView.
- **Order entry**: market orders and limit orders.
- **Leverage**: adjustable, range 1–10x.
- **Stop-loss / Take-profit**: set at order entry.
- **SL/TP must be editable from three separate places**:
  1. At initial order entry.
  2. Directly from the chart (e.g., drag or click to adjust the SL/TP line).
  3. From the position-status row/panel at the bottom of the chart.
- **Positions panel**: shows entry price, liquidation price, current PnL,
  position size, and other standard position details.
- **Close Position button**: closes the open position at market price
  immediately.

## 4. Order Execution & Fan-Out Rules

- When the admin opens a trade (sets leverage, SL, TP, and enters), the
  **exact same leverage and the exact same SL/TP percentages** are applied
  to every connected account — regardless of each account's capital size.
  (Dollar position size will naturally differ per account since sizing is
  balance-based — see Section 5 — but the leverage and SL/TP percentages are
  identical across all accounts.)
- Any **mid-trade change** (adjusting SL/TP, or closing the position) must
  propagate to all connected accounts within a **maximum of 1 second**.
- Initial entry orders must also be dispatched to all accounts within
  **~1 second** of each other.

  > **Amended in use (see `questions.md` Q19).** The cap was 1 second on a
  > machine where that held; on the production VPS a leg's exchange round
  > trips (balance, leverage, order, then SL/TP placement) routinely landed at
  > 1–2 seconds, so a healthy order was failing the deadline and raising a
  > failure notification nobody could act on. The deadline is now
  > `FANOUT_TIMEOUT_SECONDS`, default **3 seconds** (it was briefly 4, and was
  > brought down once the adapters were kept warm between actions —
  > `apps/exchanges/pool.py` — so a healthy leg lands well inside it). What §4
  > is actually protecting is unchanged: legs run concurrently, one slow
  > exchange still cannot hold the others up past the deadline, and a leg that
  > overruns is abandoned rather than awaited. The number that was too tight
  > changed; the concurrency contract did not.
- **Independent failure handling**: if an order fails on one account
  (insufficient balance, API error, exchange downtime, etc.), execution
  must continue uninterrupted on all other accounts. One account's failure
  never blocks or delays the others.
- **Failed-order notification**: when an order fails on any account, show a
  small, persistent notification at the top of the screen. Approximate size:
  **~190px × 110px** (equivalent to ~5cm × 3cm on a standard 96 DPI display).
  The notification must remain visible until the admin manually dismisses it
  — it should not auto-expire.

  > **Amended in use (see `questions.md` Q16).** Docked over the page, these
  > covered the chart at the moment they mattered. They now live in a
  > notification centre in the top bar, present on every page, with a count
  > badge; a new failure opens it automatically and only a manual dismiss (a
  > server-side fact) clears it. Nothing auto-expires. The fixed screen
  > position was given up; the no-auto-expire requirement was not.

## 5. Position Sizing Rules

- Every trade uses **99% of the account's available balance** (99%, not a
  literal 100%, to leave headroom for exchange fee/margin buffer
  requirements that can otherwise cause an order to be rejected).
- **Only one open trade per account at a time.** Because each trade uses
  99% of balance, a new trade cannot open on an account until its current
  trade has closed.
- Leverage, SL%, and TP% are identical across all accounts on every trade
  (see Section 4); only the resulting dollar position size differs, based
  on each account's own balance.

## 6. Account Management

- **Connecting a new account**: for this version, the admin manually adds
  each account. The process is: the partner creates a **non-withdrawable**
  API key on their own exchange account and gives it to the admin; the
  admin then creates the new account connection on the platform using that
  key. (Self-service onboarding, where partners connect their own accounts
  directly, may be added in a future version — not required for v1.)
- **Accounts section UI**:
  - An icon/button to create/add a new connected account.
  - Each individual account has its own separate icons for:
    - **Pause** — temporarily stop this account from receiving new orders.
    - **Resume** — re-enable order routing for this account.
    - **Delete** — remove the account connection entirely.
- **Mid-trade connect/disconnect rules**:
  - No account may connect to an already-open trade in progress. A newly
    connected account only participates starting from the *next* new trade.
  - If a connected account disconnects while it has an open trade, it must
    wait until a new trade begins before it can resume participating (its
    existing open position on the exchange is left as-is; the platform
    does not force-close it on disconnect).
- **Admin visibility**: the admin must be able to see the current balance
  of every connected account at all times.

## 7. Security Requirements

- **All connected API keys must be non-withdrawable** — trading permissions
  only, no withdrawal rights. This is a hard requirement for every
  connected account, including the admin's own.
- **API keys must be encrypted at rest**, never stored in plain text.
- Security should be treated as a first-class concern throughout the build,
  not an afterthought — this platform holds live trading credentials for
  multiple real accounts.
- *(Recommended, to be finalized in Claude Code): an emergency "stop all"
  control that immediately halts new order routing platform-wide, for use
  if something goes wrong and immediate action is needed across every
  account at once.)*

## 8. Trade History & Reporting

- Each connected account must have its own trade history log, recording
  at minimum:
  - Currency/pair traded
  - Date and time
  - Profit/loss amount for that trade

## 9. Testing

- A **demo/test mode** is required, allowing the full platform (order
  routing, multi-account fan-out, independent failure handling, etc.) to be
  tested safely before connecting real accounts with real capital.

## 10. Open Items — To Be Refined in Claude Code

The following were flagged during planning as worth deciding but are not
yet finalized. Treat this spec as a strong starting point, not a final,
unchangeable document — expect to refine details as the platform takes
shape:

- Exact UI/UX layout beyond what's specified above.
- Notification behavior for *successful* trades/confirmations (only the
  failed-order notification is specified above).
- Whether/how self-service partner onboarding gets added later.
- Detailed exchange-by-exchange API integration specifics (rate limits,
  auth methods, order-type quirks) — to be handled per exchange as they're
  implemented.

## 11. Important Note — Not Legal or Compliance Advice

This platform is intended to route real trades for real capital belonging
to individual retail investors/partners (each with roughly $50,000–$100,000
in connected capital). Depending on jurisdiction and the exact structure of
any fee or profit-share arrangement with partners, activities like this can
fall under financial services or investment-adviser regulation (e.g., in
the US, this kind of activity can require CFTC/NFA registration as a
commodity trading advisor, or equivalent licensing elsewhere). This
document is a technical specification only. Confirm the legal/regulatory
requirements for this arrangement with a qualified professional before
connecting real partner accounts or handling real capital.
