# Hyperliquid — integration notes

No docs vendored. Query the connected **`hyperliquid-docs` MCP server**
(`searchDocumentation`, `getPage`) — it serves
https://hyperliquid.gitbook.io/hyperliquid-docs live. Notes below were pulled
from it 2026-08-11; re-verify before coding, the L1 changes.

Endpoints: `https://api.hyperliquid.xyz` (mainnet) ·
`https://api.hyperliquid-testnet.xyz` (**testnet exists** — same request shapes).
Actions POST to `/exchange`, reads POST to `/info`.
Official Python SDK: `hyperliquid-dex/hyperliquid-python-sdk`.

## Auth — the part that differs from every other exchange

There is no API key/secret. Signing is done by an **API wallet** (a.k.a. agent
wallet): a separate Ethereum keypair the account owner approves via an
`approveAgent` action. The platform stores the API wallet's **private key** —
so "encrypt keys at rest" (spec §7) applies to a private key here, not an HMAC
secret.

Rules that constrain our design:

- An account can have **1 unnamed + 3 named** API wallets (plus 2 named per
  subaccount). Expiry is settable, max 180 days out — **agent approvals expire
  and must be renewed**; the platform needs to track expiry per account and warn
  before it lapses, or that partner silently stops trading.
- API wallets **sign only**. All `/info` queries (balance, positions) must use
  the *master account address*, not the agent address. Using the agent address
  returns empty results — the classic pitfall.
- **Never reuse an agent address.** Once deregistered, its nonce state can be
  pruned and previously signed actions become replayable. Generate a fresh agent
  wallet on every re-connect.
- Approving a new *unnamed* agent deregisters the previous unnamed one. With
  multiple partner accounts, always use **named** agents to avoid stomping.

### ⚠️ Withdrawal permission — unverified

Spec §7 requires every connected credential to be non-withdrawable. The docs
pages searched do **not** state whether an API wallet can sign withdrawals or
`spotSend`/`usdSend` transfers. This must be confirmed on testnet before any
partner connects real funds — see `questions.md` Q11. Do not assume.

## Nonces — affects the fan-out engine

- 100 highest nonces stored **per signer address**; a new action needs a nonce
  above the smallest in that set and never previously used.
- Nonce must fall in `(T − 2 days, T + 1 day)` of block time.
- Docs recommend: **one API wallet per trading process**, an atomic counter for
  nonces (fast-forwardable to unix ms), and batching order/cancel requests.

For this platform: one API wallet per connected account, one atomic nonce
counter per account, never shared. This falls out naturally from the
per-account-isolation rule in `CLAUDE.md`.

## Rate limits — good news for spec §2

Limits are **address-based, sub-accounts counted as separate users**. Separate
partner accounts therefore do not contend, which is exactly the isolation the
spec demands.

But the budget is unusual: **1 request per 1 USDC of cumulative traded volume
since address inception**, with an initial buffer of 10,000 requests. Once
exhausted, an address gets 1 request per 10 seconds. A fresh, low-volume partner
account can therefore run out. Cancels get a larger allowance
(`min(limit + 100000, limit * 2)`) so positions can always be closed.

Open orders: 1000 default per user, +1 per 5M USDC volume, cap 5000.

## Trading mechanics

- **Leverage**: integer only, 1..max-per-asset, cross or isolated, set via an
  `updateLeverage` action. Spec's 1–10x range fits. Leverage is checked only at
  open; margin = `position_size * mark_price / leverage`.
- **TP/SL**: native trigger orders. Placed from the position form they default
  to full position size and resize with it; if an explicit size is set they
  become **fixed-size and stop tracking the position** — for this platform,
  always place position-scoped TP/SL, never fixed-size.
  TP/SL market orders carry 10% slippage tolerance. Setting the limit price
  controls slippage vs. fill probability.
  A `siblingFilledCanceled` status means the paired TP or SL was cancelled
  because its sibling filled — normal, not an error.
- **Order rejects to handle explicitly**: `minTradeNtlRejected` (below min
  notional — the spec §5 small-account case), `perpMarginRejected`,
  `tickRejected`, `badTriggerPxRejected`, `oracleRejected`,
  `marketOrderNoLiquidityRejected`, `scheduledCancel` (dead-man's switch).
- **"Action already expired"**: actions not accepted by the L1 within 15s are
  rejected by default. Keep that protection on — disabling it can cause an
  order to land late and, per the docs, flip a position instead of closing it.
  This directly threatens the spec §4 1-second close guarantee: an L1 that is
  congested can reject our close. Surface it as a failure notification.
- Prices must be integer multiples of tick size, sizes multiples of lot size.
