# Exchange coverage matrix

Source of truth for which exchanges the platform must support and what reference
material exists for each. Derived from `docs/spec/exchange_list.original.txt`
(the admin's raw list, kept verbatim — names there contain typos) and
`docs/spec/platform-spec.md` §2 ("up to ~10 exchanges").

**All 8 are in v1** (admin, 2026-08-11 — `questions.md` Q1). Build order below is
a sequencing proposal; scope is not negotiable.

| # | Exchange | Raw list entry | Order | Reference material | Testnet | Status |
|---|---|---|---|---|---|---|
| 1 | Hyperliquid | `hyperliqid #important` | 1st — flagged important | `reference/exchanges/hyperliquid/README.md` + `hyperliquid-docs` MCP | ✅ `api.hyperliquid-testnet.xyz` | adapter written; blocked on Q11 |
| 2 | Bybit | `bybit` | 2nd | `reference/exchanges/bybit/` (v5 docs + skill + PDF) | ✅ | adapter written |
| 3 | Binance | `binance` | 3rd | `reference/exchanges/binance/futures-docs/` (139 USDⓈ-M pages) + `futures-connector-python/` (official SDK) | ✅ | adapter written |
| 4 | OKX | `okexhcange` | 4th | `reference/exchanges/okx/ts-sdk/` | ✅ | adapter written |
| 5 | Gate.io | `gateio` | 5th | `reference/exchanges/gateio/python-sdk/` | ✅ | adapter written |
| 6 | KuCoin | `kocoin` | 6th | `reference/exchanges/kucoin/universal-sdk/` + `futures-sdk-python/`. **`api-docs/` is spot/margin only — no futures material** | ✅ | adapter written |
| 7 | Toobit | `twobit` | 7th | `reference/exchanges/toobit/api/` (27 pages, downloaded) | ❌ none found in docs | adapter written |
| 8 | LBank | `lbank` | 8th | `reference/exchanges/lbank/api/` (spot + contract, downloaded) | ❌ | spot only — 🔴 **futures blocked, Q10** |

"Adapter written" means written from the reference material above and unit-tested
against a mocked transport. **None has been run against a live exchange or
testnet** (`docs/adapters.md`).

Binance and KuCoin were rebuilt on 2026-08-13 after their reference directories
turned out to hold no futures material at all — the adapters had been written
from memory, against the rule in `CLAUDE.md`. See each
`reference/exchanges/*/README.md` for the defects that survived because of it.

Testnet column feeds spec §9: exchanges marked ❌ must be shown in the panel as
"no test environment — cannot be used in test mode" (`questions.md` Q9).

## Known blockers

- **LBank futures**: only the public namespace is publicly documented. No
  private order/position/balance endpoints exist in any published doc. See
  `reference/exchanges/lbank/README.md` and `questions.md` Q10.
- **Hyperliquid**: agent-wallet withdrawal rights unverified against spec §7.
  See `questions.md` Q11.

## Per-exchange capability checklist

Each integration must answer these before it is considered done. Answers below
are read off the adapter's `Capabilities` and its implemented methods, not from
intent — if the code changes, so does this table.

- [x] Spot supported? Futures/perpetual supported? (spec §2 requires both)
- [x] Leverage 1–10x settable per-symbol via API? (spec §3)
- [x] Native SL/TP attached at entry, or must be emulated with conditional orders?
- [x] SL/TP amendable on an open position without cancel+replace? (spec §4, 1s budget)
- [x] Market close of a full position in one call? (spec §3)
- [x] Available-balance query for 99% sizing? Quantity/notional step + min-notional rules? (spec §5)
- [x] Non-withdrawable / trade-only API key scope available? (spec §7 — hard requirement)
- [x] Multiple independent API keys per exchange usable concurrently, with **per-key** rate limits (not per-IP)? (spec §2 — this is the key requirement the prior platform failed)
- [x] Testnet / demo environment for spec §9 test mode?
- [x] Private WebSocket order/position stream for fill + liquidation events?

| | Markets | SL/TP at entry | Native amend | Per-key limits | Key scope readable | Private WS stream |
|---|---|---|---|---|---|---|
| Hyperliquid | spot + futures | ❌ separate trigger orders | ❌ | ✅ per address | ⚠️ Q11 unverified | ❌ |
| Bybit | spot + futures | ✅ | ✅ `POST /v5/position/trading-stop` | ✅ | ✅ | ❌ |
| Binance | futures | ❌ `POST /fapi/v1/order` has no `stopLoss`/`takeProfit` | ❌ | ❌ weights are per-IP too | ⚠️ spot host only — a futures-only key is flagged | ✅ `listenKey` user stream |
| OKX | spot + futures | ✅ | ❌ | ✅ | ✅ | ❌ |
| Gate.io | futures ⚠️ | ❌ | ❌ | ✅ | ❌ | ❌ |
| KuCoin | futures | ✅ `POST /api/v1/st-orders` | ❌ | ✅ | ⚠️ spot host only | ✅ |
| Toobit | spot + futures | ✅ | ❌ | ✅ | ❌ | ❌ |
| LBank | spot only | ❌ | ❌ | ✅ | ❌ | ❌ |

⚠️ Gate.io declares `SPOT` in its `Capabilities` but `get_symbol_rules` raises
`NotSupported` for it — the adapter is futures-only in practice. Either the
capability or the method is wrong; it is listed here as futures.

Where "SL/TP at entry" is ❌ the protection is a separate order placed after the
fill — the unprotected window Q5e's failure policy covers. Where "native amend"
is ❌ an amend is place-then-cancel around the old pair (Q5d). "Key scope
readable" ❌ means spec §7 cannot be checked programmatically; the account is
flagged **unverified** in the panel rather than passed silently.

**Min-notional is per symbol and must be read from the exchange, not assumed.**
Binance returns 50 for BTCUSDT, not 5. `OkxAdapter.get_symbol_rules` and
`GateioAdapter.get_symbol_rules` still hardcode `min_notional = 5`; anything
sizing against those two is sizing against a guess.
