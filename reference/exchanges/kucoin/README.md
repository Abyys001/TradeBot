# KuCoin — reference material

Read-only. Never imported by application code.

## What is here

| Path | What it is | Use it for |
|---|---|---|
| `universal-sdk/futures/` | Generated request/response models from **`Kucoin/kucoin-universal-sdk`** (`generate/futures`). | Exact JSON field names — every model carries its `__properties` list |
| `universal-sdk/account/` | Same, `generate/account`. | `GET /api/v1/user/api-key` permission scopes |
| `futures-sdk-python/` | **`Kucoin/kucoin-futures-python-sdk`**, the older official client. | Signing scheme, endpoint paths, worked response examples |
| `api-docs/` | KuCoin's Slate docs repo. | **Spot, margin and HF only — contains no futures material** |

`api-docs/` was the only KuCoin reference in this repo until 2026-08-13. It has
zero occurrences of the string "futures". The adapter targets
`api-futures.kucoin.com`, so it had been written from memory.

The defect that survived because of it: `place_order` sent
`triggerStopLossPrice` and `triggerStopUpPrice` to `POST /api/v1/orders`.
Neither is a parameter of that endpoint. `triggerStopUpPrice` /
`triggerStopDownPrice` belong to a **different** endpoint, `POST /api/v1/st-orders`.

## The two order endpoints

This distinction is the whole reason the old adapter was wrong.

`POST /api/v1/orders` — plain and stop orders. Accepts:

```
clientOid side symbol leverage type remark stop stopPriceType stopPrice
reduceOnly closeOrder forceHold stp marginMode price size timeInForce
postOnly hidden iceberg visibleSize qty valueQty
```

`POST /api/v1/st-orders` — order **with TP/SL attached at entry**. Accepts:

```
clientOid side symbol leverage type remark stopPriceType reduceOnly closeOrder
forceHold stp marginMode price size timeInForce postOnly hidden iceberg
visibleSize triggerStopUpPrice triggerStopDownPrice qty valueQty
```

Note it has no `stop`/`stopPrice`, and `orders` has no `triggerStop*`. Up and
down are **price directions, not TP and SL**: for a long, TP is `Up` and SL is
`Down`; for a short they swap.

## Endpoints the adapter uses

Futures host `api-futures.kucoin.com`:

- `GET /api/v1/contracts/{symbol}` — `multiplier`, `lotSize`, `tickSize`, `maxLeverage`, `isInverse`
- `GET /api/v1/mark-price/{symbol}/current`
- `GET /api/v1/account-overview?currency=USDT` — `availableBalance`, `accountEquity`
- `GET /api/v1/position?symbol=` — `currentQty` (contracts), `avgEntryPrice`, `realLeverage`, `marginMode`
- `POST /api/v1/orders`, `POST /api/v1/st-orders`
- `DELETE /api/v1/stopOrders?symbol=` — mass-cancel stops, used for the Q5d amend
- `DELETE /api/v1/orders/{orderId}`
- `GET /api/v1/stopOrders?symbol=`
- `POST /api/v2/changeCrossUserLeverage`, `GET /api/v2/getCrossUserLeverage`
- `POST /api/v1/bullet-private` — WebSocket token

Spot host `api.kucoin.com` (a second client — the futures host does not serve it):

- `GET /api/v1/user/api-key` — spec §7

## Spec §7 — KuCoin *can* be verified

`GET /api/v1/user/api-key` returns:

```json
{"remark":"account1","apiKey":"…","apiVersion":3,
 "permission":"General,Futures,Spot,Earn,InnerTransfer,Transfer,Margin",
 "ipWhitelist":"…","createdAt":1728443843000,"uid":165111215,"isMaster":true}
```

`permission` is a comma list drawn from
`General, Spot, Margin, Futures, InnerTransfer, Transfer, Earn`.

- **`Transfer`** is the withdrawal right — funds out to an external address.
  Spec §7 refuses the key outright.
- `InnerTransfer` only moves funds between the user's own KuCoin accounts and is
  not a withdrawal.
- `Futures` is required, or the key cannot trade at all.

The earlier claim in the adapter that "KuCoin exposes no key-permission
endpoint" was wrong. It does; it is just on the spot host.

## Signing

HMAC-SHA256 over `timestamp + METHOD + endpoint + body`, base64. For key
version 2 and above the **passphrase is itself HMAC-signed and base64-encoded**
— sending it in the clear fails with `400004`. `endpoint` includes the query
string. Both hosts use the same scheme and the same key.

## Testnet

`https://api-sandbox-futures.kucoin.com`. KuCoin has repeatedly deprecated and
restored this sandbox; treat reachability as unverified until tested.
