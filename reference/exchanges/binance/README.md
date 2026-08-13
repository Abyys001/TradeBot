# Binance — reference material

Read-only. Never imported by application code (see the repo-level rule in
`reference/README.md`).

## What is here

| Path | What it is | Use it for |
|---|---|---|
| `futures-docs/usdm-futures-api.md` | 139 USDⓈ-M futures pages from developers.binance.com, mirrored to Markdown. Snapshot 2026-08-13. | Response shapes, filter definitions, error codes, changelog |
| `futures-connector-python/` | **`binance/binance-futures-connector-python`**, the official Binance connector. | Authoritative endpoint paths and parameter names |

When the two disagree, the connector wins — it is versioned by Binance itself.

## History — why this directory was rebuilt

Until 2026-08-13 this directory held `rest-docs/`, seven files cloned in
December 2020. Every one of them was a single line reading *"This has been moved
to …"*. There was no API documentation here at all, and what they pointed at was
the **spot** API — the adapter targets `fapi` (USDⓈ-M futures). The Binance
adapter had therefore been written from memory, against the rule in `CLAUDE.md`
that exchange facts come from `reference/`.

Three defects that survived because of it, each confirmed against the material
now vendored here:

- `GET /fapi/v1/balance` does not exist. Only `/fapi/v2/balance` and
  `/fapi/v3/balance` do.
- `GET /fapi/v1/positionRisk` is superseded by `/fapi/v3/positionRisk`, which
  **dropped the `leverage` field** — configuration now lives in
  `GET /fapi/v1/symbolConfig`.
- `POST /fapi/v1/order` has no `stopLoss` or `takeProfit` parameters. Protective
  orders are separate `STOP_MARKET` / `TAKE_PROFIT_MARKET` orders.

## Endpoints the adapter uses

Public / market data:

- `GET /fapi/v1/exchangeInfo` — `PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE`, `MIN_NOTIONAL`
- `GET /fapi/v1/premiumIndex` — mark price
- `GET /fapi/v2/ticker/price` — last price (**v2**, not v1)

Signed, futures host `fapi.binance.com`:

- `GET /fapi/v3/balance`
- `GET /fapi/v3/positionRisk`
- `GET /fapi/v1/symbolConfig` — per-symbol leverage and margin type
- `GET /fapi/v1/accountConfig` — dual (hedge) position mode
- `POST /fapi/v1/leverage`
- `POST /fapi/v1/order`, `DELETE /fapi/v1/order`, `GET /fapi/v1/order`
- `GET /fapi/v1/openOrders`
- `POST|PUT|DELETE /fapi/v1/listenKey` — user data stream

Signed, **spot** host `api.binance.com` (a second client — the futures host does
not serve `sapi`):

- `GET /sapi/v1/account/apiRestrictions` — `enableWithdrawals`, spec §7

WebSocket: `wss://fstream.binance.com/ws/<listenKey>`, events
`ORDER_TRADE_UPDATE` and `ACCOUNT_UPDATE`.

## Testnet

`https://testnet.binancefuture.com` for REST, `wss://stream.binancefuture.com`
for the stream. Keys are minted at testnet.binancefuture.com and are separate
from production keys.
