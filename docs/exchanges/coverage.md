# Exchange coverage matrix

Source of truth for which exchanges the platform must support and what reference
material exists for each. Derived from `docs/spec/exchange_list.original.txt`
(the admin's raw list, kept verbatim — names there contain typos) and
`docs/spec/platform-spec.md` §2 ("up to ~10 exchanges").

**All 8 are in v1** (admin, 2026-08-11 — `questions.md` Q1). Build order below is
a sequencing proposal; scope is not negotiable.

| # | Exchange | Raw list entry | Order | Reference material | Testnet | Status |
|---|---|---|---|---|---|---|
| 1 | Hyperliquid | `hyperliqid #important` | 1st — flagged important | `reference/exchanges/hyperliquid/README.md` + `hyperliquid-docs` MCP | ✅ `api.hyperliquid-testnet.xyz` | docs gathered; blocked on Q11 |
| 2 | Bybit | `bybit` | 2nd | `reference/exchanges/bybit/` (v5 docs + skill + PDF) | tbc | not started |
| 3 | Binance | `binance` | 3rd | `reference/exchanges/binance/rest-docs/` | tbc | not started |
| 4 | OKX | `okexhcange` | 4th | `reference/exchanges/okx/ts-sdk/` | tbc | not started |
| 5 | Gate.io | `gateio` | 5th | `reference/exchanges/gateio/python-sdk/` | tbc | not started |
| 6 | KuCoin | `kocoin` | 6th | `reference/exchanges/kucoin/api-docs/` | tbc | not started |
| 7 | Toobit | `twobit` | 7th | `reference/exchanges/toobit/api/` (27 pages, downloaded) | ❌ none found in docs | docs gathered |
| 8 | LBank | `lbank` | 8th | `reference/exchanges/lbank/api/` (spot + contract, downloaded) | tbc | 🔴 **futures blocked — Q10** |

Testnet column feeds spec §9: exchanges marked ❌ must be shown in the panel as
"no test environment — cannot be used in test mode" (`questions.md` Q9).

## Known blockers

- **LBank futures**: only the public namespace is publicly documented. No
  private order/position/balance endpoints exist in any published doc. See
  `reference/exchanges/lbank/README.md` and `questions.md` Q10.
- **Hyperliquid**: agent-wallet withdrawal rights unverified against spec §7.
  See `questions.md` Q11.

## Per-exchange capability checklist

Each integration must answer these before it is considered done. Fill in as work
proceeds.

- [ ] Spot supported? Futures/perpetual supported? (spec §2 requires both)
- [ ] Leverage 1–10x settable per-symbol via API? (spec §3)
- [ ] Native SL/TP attached at entry, or must be emulated with conditional orders?
- [ ] SL/TP amendable on an open position without cancel+replace? (spec §4, 1s budget)
- [ ] Market close of a full position in one call? (spec §3)
- [ ] Available-balance query for 99% sizing? Quantity/notional step + min-notional rules? (spec §5)
- [ ] Non-withdrawable / trade-only API key scope available? (spec §7 — hard requirement)
- [ ] Multiple independent API keys per exchange usable concurrently, with **per-key** rate limits (not per-IP)? (spec §2 — this is the key requirement the prior platform failed)
- [ ] Testnet / demo environment for spec §9 test mode?
- [ ] Private WebSocket order/position stream for fill + liquidation events?
