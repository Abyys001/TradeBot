# LBank API docs

Downloaded 2026-08-11 and converted to Markdown from LBank's published Slate
doc pages. Source is the live site, not a git repo — re-download to refresh.

| File | Source | Covers |
|---|---|---|
| `api/spot.md` | https://www.lbank.com/docs/ | Spot: REST auth, wallet, market data, spot trading, WebSocket market + asset/order streams, error codes (~80 KB, complete) |
| `api/contract.md` | https://www.lbank.com/docs/contract.html | Futures/CFD: intro, access URLs, signing, error codes, **public market data only** (~17 KB) |

## ⚠️ LBank futures is a blocker

`api/contract.md` is the complete published contract API doc, and it documents
only the **public** namespace `/cfd/openApi/v1/pub` — current time, contract
list, market list, order book.

**There are no publicly documented private endpoints**: no place order, no
cancel, no position query, no balance, no set-leverage, no SL/TP. Requests to
add futures docs have been open on LBank's official docs repo. Without these,
an LBank futures adapter cannot be written — see `questions.md` Q10.

Spot on LBank is fully documented and implementable today.

## Endpoints

- Spot REST: `https://api.lbkex.com/v2/…` (also `api.lbank.info`)
- Futures REST: `https://lbkperp.lbank.com/` — verified reachable
  (`GET /cfd/openApi/v1/pub/marketData` → 200)
- Futures WS: `wss://lbkperpws.lbank.com/ws`

## Signing (futures)

Header carries `timestamp` (ms, from `/cfd/openApi/v1/pub/getTime`),
`signature_method` (`RSA` or `HmacSHA256`), and `echostr` (random alphanumeric,
length 30–40).

> The "test account" section of `api/contract.md` contains a sample API key and
> private key printed in LBank's own public docs. They are illustrative — never
> paste them anywhere, and never treat that section as a real testnet.
