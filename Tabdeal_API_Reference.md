# Tabdeal Exchange API — Reference Document

> Source: `به داکیومنت API تبدیل.txt` (Tabdeal official API documentation, Persian).
> This document is a complete English transcription/summary of that file, reorganized for use as
> the technical spec when building a trading bot against Tabdeal. Every endpoint, parameter,
> sample payload, websocket topic and error code from the source file is captured below.

**Official Python SDK:** `Tabdeal-Python` (`pip install tabdeal-python` style usage; classes used
throughout the docs: `tabdeal.spot.Spot`, `tabdeal.isolated_margin.IsolatedMargin`,
`tabdeal.future.Future`, `tabdeal.websocket_client.SpotWebsocketClient` /
`FutureWebsocketClient` / `FutureBroadcastWebsocketClient`, and `tabdeal.enums` for
`OrderSides` / `OrderTypes`.)

**REST base host:** `https://api1.tabdeal.org`
**Spot/Margin websocket host:** `wss://api1.tabdeal.org/stream/`
**Futures (FAPI) websocket hosts:** `wss://api1.tabdeal.org/special_margin/stream/` and
`wss://api1.tabdeal.org/special_margin/broadcast/`

The Futures/Pro-Leverage API is namespaced under `fapi` (vs `api` for spot/margin) and is
deliberately designed to be **structurally compatible with Binance Futures**, so existing
Binance-Futures bot code/SDKs can largely be pointed at Tabdeal's `fapi` endpoints instead.

Path convention observed throughout the docs: **read (`GET`) endpoints are generally prefixed
with `r/`** (e.g. `/r/api/v1/order`), while **write endpoints (`POST`/`DELETE`/`PUT`) generally
omit the `r/` prefix** (e.g. `/api/v1/order`). There are a handful of exceptions called out
explicitly below (e.g. isolated-margin transfer is `r/` even for `POST`, and several
isolated-margin history/account endpoints are *not* `r/` even though they are `GET`) — always use
the exact path given per endpoint, not the general rule.

---

## Table of Contents

1. [Security & Authentication](#1-security--authentication)
2. [Common Enums / Status Codes](#2-common-enums--status-codes)
3. [Spot Trading Endpoints](#3-spot-trading-endpoints)
4. [Spot Market Data Endpoints](#4-spot-market-data-endpoints)
5. [Spot WebSocket — Market Data](#5-spot-websocket--market-data)
6. [Spot WebSocket — User Data](#6-spot-websocket--user-data)
7. [Wallet](#7-wallet)
8. [Isolated Margin Trading](#8-isolated-margin-trading)
9. [Futures / Professional Leverage (FAPI)](#9-futures--professional-leverage-fapi)
10. [FAPI WebSockets](#10-fapi-websockets)
11. [Error Codes](#11-error-codes)
12. [Version History](#12-version-history)
13. [Notes for Bot Implementation](#13-notes-for-bot-implementation)

---

## 1. Security & Authentication

### Security mechanism types

| Type | Requirement |
|---|---|
| `TRADE` | Requires `api-key` **and** `signature` |
| `USER` | Requires `api-key` only |
| `NONE` | No auth required |

### How to authenticate a `TRADE` request

1. Get your `api-key` / `api-secret` from the Tabdeal website (API key management page).
2. Send the API key as an HTTP header on every request:
   ```
   X-MBX-APIKEY: your_api_key
   ```
3. Append a `timestamp` (epoch **milliseconds**) to your outgoing parameters.
4. Serialize all parameters (including `timestamp`) into a query string:
   ```
   param_1=test_1&param_2=test_2&...&timestamp=1507725176595
   ```
5. Sign that query string with **HMAC-SHA256**, keyed with your `api-secret`.
6. Append the resulting hex digest as a `signature` parameter and send the request (query
   string for `GET`/`DELETE`, matching the Binance-style signing convention).

### `USER` requests

Only the `X-MBX-APIKEY` header is required — no `signature`/`timestamp` needed. Used for
listen-key management endpoints (spot user-data-stream).

### `NONE` requests

Public market-data endpoints — no key/signature needed at all.

---

## 2. Common Enums / Status Codes

### Order status

| Status | Meaning |
|---|---|
| `NEW` | Order created |
| `PARTIALLY_FILLED` | Order partially filled |
| `FILLED` | Order fully filled |
| `CANCELED` | Order canceled |
| `REJECTED` | Order rejected |

### Order type

- `LIMIT`
- `MARKET`
- `STOP_LOSS_LIMIT`

### Order side

- `BUY`
- `SELL`

### OCO (One-Cancels-the-Other) list status

| Status | Meaning |
|---|---|
| `EXECUTING` | The OCO (or one of its child orders) is being created/executed |
| `ALL_DONE` | OCO and all child orders have finished |
| `REJECT` | OCO rejected or canceled |

### OCO child-order status

| Status | Meaning |
|---|---|
| `RESPONSE` | One child order was canceled/rejected |
| `EXEC_STARTED` | Child orders became active or changed state |
| `ALL_DONE` | Child orders finished |

---

## 3. Spot Trading Endpoints

All endpoints below use the `TRADE` security type (api-key + signature) unless noted.
`symbol` = market without underscore (`BTCIRT`); `tabdealSymbol` = market with underscore
(`BTC_IRT`). Exactly one of `symbol`/`tabdealSymbol` must be sent where required (they're
interchangeable — same market, different formatting).

### 3.1 New Order

`POST /api/v1/order` **[TRADE]**

```python
from tabdeal.spot import Spot
from tabdeal.enums import OrderSides, OrderTypes

client = Spot(api_key, api_secret)
order = client.new_order(symbol='BTCIRT', side=OrderSides.SELL, type=OrderTypes.MARKET, quantity="0.001")
```

| Param | Required | Type | Notes |
|---|---|---|---|
| `side` | Yes | ENUM | `BUY` / `SELL` |
| `type` | Yes | ENUM | `MARKET` / `LIMIT` / `STOP_LOSS_LIMIT` |
| `quantity` | Yes | DECIMAL | Amount to buy/sell |
| `timestamp` | Yes | LONG | Request time |
| `signature` | Yes | STRING | HMAC signature |
| `symbol` | No* | STRING | Market, no underscore |
| `tabdealSymbol` | No* | STRING | Market, with underscore |
| `newClientOrderId` | No | STRING | User-generated unique order id |
| `price` | No** | DECIMAL | Required if `type=LIMIT` |
| `stopPrice` | No** | DECIMAL | Required if `type=STOP_LOSS_LIMIT` |

\* one of `symbol`/`tabdealSymbol` is required. \** becomes required depending on `type`.

Sample response includes `orderId`, `status`, `executedQty`, `cummulativeQuoteQty`
(note: both `cummulativeQuoteQty` and the correctly-spelled `cumulativeQuoteQty` are returned —
same value, kept for backward compatibility), and a `fills` array (price/qty/commission per fill,
only for market orders that filled immediately).

### 3.2 Get Order

`GET /r/api/v1/order` **[TRADE]**

```python
order = client.get_order(symbol='BTC_IRT', order_id=140)
```

| Param | Required | Type |
|---|---|---|
| `timestamp` / `signature` | Yes | — |
| `symbol` / `tabdealSymbol` | one required | STRING |
| `orderId` | one of these two required | LONG |
| `origClientOrderId` | | STRING |

### 3.3 Open Orders

`GET /r/api/v1/openOrders` **[TRADE]**

Returns open orders for a market, or **all markets** if `symbol`/`tabdealSymbol` omitted.

### 3.4 Paginated Open Orders

`GET /r/api/v1/paginatedOpenOrders` **[TRADE]**

```python
orders = client.get_paginated_open_orders(symbol='BTCIRT', page=1, page_size=250)
```

| Param | Required | Notes |
|---|---|---|
| `page` | No | default `1` |
| `page_size` | No | default `100`, max `500` (clamped automatically) |

Response: `{ "number_of_pages": N, "results": [...] }`. Faster alternative to `openOrders` for
large order counts.

### 3.5 Cancel Order

`DELETE /api/v1/order` **[TRADE]**

Cancels a single order. Requires `symbol`/`tabdealSymbol` + one of `orderId`/`origClientOrderId`.

### 3.6 All Orders

`GET /r/api/v1/allOrders` **[TRADE]**

| Param | Required | Notes |
|---|---|---|
| `symbol`/`tabdealSymbol` | No | omit → all markets |
| `startTime` / `endTime` | No | ms epoch, filters by creation time |
| `limit` | No | max `1000`, default `50` |

### 3.7 Non-Expired All Orders

`DELETE /api/v1/nonExpiredAllOrders` **[TRADE]** — *(note: documented HTTP verb is `DELETE` but
it is a read/listing call — likely a documentation quirk; treat per actual server behavior)*

Returns orders that are still "alive" (not canceled) — i.e. `NEW`/`PARTIALLY_FILLED`/`FILLED`.

| Param | Required | Notes |
|---|---|---|
| `startTime` | No | default = 1 day ago; **cannot be more than 1 day in the past** |
| `endTime` | No | default = now |
| `limit` | No | default `50`, max `1000` |

### 3.8 Cancel All Open Orders

`DELETE /api/v1/openOrders` **[TRADE]**

Cancels all open orders for a market (also cancels OCO orders on that market). ⚠️ If canceling
one order in the batch fails, the rest are **not** canceled — re-check open orders and retry on
error.

### 3.9 New OCO Order

`POST /api/v1/order/oco` **[TRADE]**

```python
oco = client.new_oco_order(
    symbol='BTC_IRT', side=OrderSides.SELL, quantity="0.005",
    price="100100000", stop_price="99899999", stop_limit_price="99890000",
    list_client_order_id="oco_6", limit_client_order_id="limit_6", stop_client_order_id="stop_6"
)
```

| Param | Required | Type |
|---|---|---|
| `side` | Yes | ENUM |
| `quantity` | Yes | DECIMAL |
| `price` | Yes | DECIMAL — limit-leg price |
| `stopPrice` | Yes | DECIMAL — stop trigger price |
| `stopLimitPrice` | Yes | DECIMAL — stop-leg limit price |
| `timestamp`/`signature` | Yes | — |
| `symbol`/`tabdealSymbol` | one required | |
| `listClientOrderId` | No | user id for the whole OCO |
| `limitClientOrderId` | No | user id for the limit leg |
| `stopClientOrderId` | No | user id for the stop leg |

Response includes `orderListId`, `contingencyType: "OCO"`, both child `orders` (ids) and full
`orderReports` for each leg.

### 3.10 Get OCO Order

`GET /r/api/v1/orderList` **[TRADE]** — by `orderListId` or `origClientOrderId` (one required).

### 3.11 Open OCO Orders

`GET /r/api/v1/openOrderList` **[TRADE]** — no filter params besides auth.

### 3.12 Cancel OCO Order

`DELETE /api/v1/orderList` **[TRADE]** — requires `symbol`/`tabdealSymbol` + one of
`orderListId`/`listClientOrderId`. Response includes both order refs and full `orderReports`.

### 3.13 All OCO Orders

`GET /r/api/v1/allOrderList` **[TRADE]** — `startTime`/`endTime`/`limit` (max `1000`, default
`50`).

### 3.14 My Trades

`GET /r/api/v1/myTrades` **[TRADE]**

| Param | Required | Notes |
|---|---|---|
| `symbol`/`tabdealSymbol` | Yes | |
| `startTime`/`endTime` | No | |
| `limit` | No | max `1000`, default `50` |
| `orderId` | No | filter trades belonging to one order |

Each trade row: `id`, `orderId`, `price`, `qty`, `quoteQty`, `commission`, `commissionAsset`,
`time`, `isBuyer`, `isMaker`.

### 3.15 Account Info

`GET /r/api/v1/account` **[TRADE]**

Returns `makerCommission`, `takerCommission`, `canTrade`, `canWithdraw`, `canDeposit`,
`accountType: "SPOT"`, `balances: [{asset, free, freeze}, ...]`, `permissions`.

---

## 4. Spot Market Data Endpoints

All `[NONE]` — no auth required.

### 4.1 Order Book (Depth)

`GET /r/api/v1/depth` **[NONE]**

| Param | Required | Notes |
|---|---|---|
| `symbol`/`tabdealSymbol` | one required | |
| `limit` | No | max `5000`, default `50` |

Response: `{ "bids": [[price, qty], ...], "asks": [[price, qty], ...] }`.

### 4.2 Recent Trades

`GET /r/api/v1/trades` **[NONE]**

`symbol`/`tabdealSymbol` (required), `limit` (max `1000`, default `50`). Rows:
`id`, `price`, `qty`, `quoteQty`, `time`, `isBuyerMaker`.

### 4.3 Exchange Info

`GET /r/api/v1/exchangeInfo` **[NONE]**

Accepts `symbol`, `symbols`, `tabdealSymbol`, `tabdealSymbols`, `limit` (max `1000`, default
`50`). Omit all symbol filters to get every market. Each market entry includes:

- `baseAsset` / `quoteAsset` (+ precisions)
- `orderTypes` (e.g. `LIMIT`, `STOP_LOSS_LIMIT`, `MARKET`)
- `icebergAllowed`, `ocoAllowed`, `quoteOrderQtyMarketAllowed`, `allowTrailingStop`
- `isSpotTradingAllowed`, `isMarginTradingAllowed`
- `filters[]`: **this is the critical bit for order validation logic** —
  - `PRICE_FILTER`: `minPrice`, `maxPrice`, `tickSize`
  - `PERCENT_PRICE`: `multiplierUp`, `multiplierDown`, `avgPriceMins`
  - `LOT_SIZE`: `minQty`, `stepSize`
  - `MIN_NOTIONAL`: `minNotional`, `applyToMarket`, `avgPriceMins`
  - `MARKET_LOT_SIZE`: `minQty`, `maxQty`, `stepSize`

A trading bot **must** fetch and respect these filters before submitting any order (round
price to `tickSize`, quantity to `stepSize`, enforce `minNotional`, clamp to `PERCENT_PRICE`
bands) or the exchange will reject the order.

### 4.4 Ping

`GET /r/api/v1/ping` **[NONE]** — connectivity test, returns `{}`.

### 4.5 Server Time

`GET /r/api/v1/time` **[NONE]** — returns `{ "serverTime": <ms epoch> }`. Use this to
compute/correct clock skew before signing requests (see error `1101`).

---

## 5. Spot WebSocket — Market Data

**Endpoint:** `wss://api1.tabdeal.org/stream/`

Subscribe by sending JSON:

```json
{ "method": "SUBSCRIBE", "params": ["usdtirt@depth@2000ms"], "id": 1 }
```

| Field | Required | Notes |
|---|---|---|
| `method` | Yes | Only `SUBSCRIBE` is documented |
| `id` | Yes | Unique request id (echoed back in the ack) |
| `params` | Depends on method | List of topics |

Successful subscribe ack: `{ "result": null, "id": 1 }`.

### Order book topic

Format: `[symbol]@depth@2000ms` (only period documented for spot is **2000ms**), e.g.
`"btcusdt@depth@2000ms"`, `"usdtirt@depth@2000ms"`.

```python
from tabdeal.websocket_client import SpotWebsocketClient

def handler(message):
    print(message)

tabdeal_ws = SpotWebsocketClient()
tabdeal_ws.market_order_book(symbol="bnbusdt", id=1, callback=handler)
```

Push message shape:

```json
{
  "stream": "usdtirt@depth@2000ms",
  "data": {
    "e": "depthUpdate", "E": 1657530675579, "s": "USDTIRT",
    "b": [["32290", "155.903075"], ...],
    "a": [["32311", "76.378076"], ...]
  }
}
```

To subscribe to multiple markets, add multiple topics to `params` in one message.

---

## 6. Spot WebSocket — User Data

**Endpoint:** `wss://api1.tabdeal.org/stream/streams={listen_key}`

Each user has one `listenKey` used to receive their own account/order events.
**A `listenKey` is valid for 60 minutes** and must be renewed (or a new one issued, which
also renews the old one and returns the same key).

### 6.1 Create Listen Key

`POST /api/v1/userDataStream` **[USER]**

```python
listen_key = client.new_listen_key()   # -> {"listenKey": "..."}
```

If a valid key already exists, calling this again just extends it and returns the same key.

### 6.2 Renew Listen Key

`PUT /api/v1/userDataStream` **[USER]** — extends validity by 60 minutes. Response `{}`.

### 6.3 Close Listen Key

`DELETE /api/v1/userDataStream` **[USER]** — invalidates the key. Response `{}`.

### 6.4 Connecting

```python
from tabdeal.websocket_client import SpotWebsocketClient
from tabdeal.spot import Spot

tabdeal = Spot(api_key=api_key)
response = tabdeal.new_listen_key()
tabdeal_ws = SpotWebsocketClient()
tabdeal_ws.user_data(listen_key=response["listenKey"], callback=handler)
```

### 6.5 Order Update Event (`executionReport`)

```json
{
  "e": "executionReport", "E": 1499405658658, "s": "ETHBTC",
  "c": "mUvoqJxFIILMdfAW5iGSOW", "S": "BUY", "o": "LIMIT", "f": "GTC",
  "q": "1.00000000", "p": "0.10264410", "P": "0.00000000", "g": -1,
  "x": "NEW", "X": "NEW", "i": 4293153, "l": "0.00000000", "z": "0.00000000",
  "L": "0.00000000", "n": "0", "N": null, "t": -1, "m": false, "O": 1499405658657
}
```

Field `x` = the operation just performed on the order:

| `x` value | Meaning |
|---|---|
| `NEW` | Order created |
| `CANCELED` | Order canceled |
| `TRADE` | Order was (partially/fully) filled |
| `TRIGGERRED` | A `STOP` order was triggered |

Sent whenever a new order is created, an existing order is canceled, or an order is filled
(fully or partially).

### 6.6 OCO Update Event (`listStatus`)

```json
{
  "e": "listStatus", "E": 1564035303637, "s": "ETHBTC", "g": 2, "c": "OCO",
  "l": "EXEC_STARTED", "L": "EXECUTING", "C": "F4QN4G8DlFATFlIUQ0cjdD",
  "T": 1564035303625,
  "O": [ {"s": "ETHBTC", "i": 17, "c": "AJYsMjErWJesZvqlJCTUgL"},
         {"s": "ETHBTC", "i": 18, "c": "bfYPSQdLoqAJeNrOr9adzq"} ]
}
```

When an OCO child order changes state, **both** the `listStatus` (OCO) event and the matching
`executionReport` (order) event are sent.

---

## 7. Wallet

### 7.1 Funding Assets

`GET /r/api/v1/asset/get-funding-asset` **[TRADE]**

```python
order = client.funding_wallet(asset='BTC')   # -> {"asset": "BTC", "free": "...", "freeze": "..."}
```

Omit `asset` to get every asset's balance in the funding wallet.

---

## 8. Isolated Margin Trading

Uses `from tabdeal.isolated_margin import IsolatedMargin`. All endpoints `[TRADE]`.

### 8.1 Transfer (Spot ↔ Isolated Margin)

`POST /r/api/v1/margin/isolated/transfer`

```python
transfer = client.transfer(asset='BTC', amount="0.01", trans_from="ISOLATED_MARGIN", trans_to="SPOT", symbol="BTCUSDT")
```

| Param | Required | Type |
|---|---|---|
| `asset` | Yes | STRING |
| `transFrom` / `transTo` | Yes | ENUM: `ISOLATED_MARGIN` / `SPOT` |
| `amount` | Yes | DECIMAL |
| `symbol`/`tabdealSymbol` | one required | |

Response: `{ "tranId": <id> }`.

### 8.2 Transfer History

`GET /r/api/v1/margin/isolated/transfer`

Params: `asset`, `symbol`/`tabdealSymbol` (required), `startTime`, `endTime`, `size` (default
`10`, max `1000`), `current` (page number), `type` (`ROLL_OUT`/`ROLL_IN`). Rows include
`status` (`PENDING`/`CONFIRMED`/`FAILED`), `txId`, `transFrom`, `transTo`.

### 8.3 Open Margin Orders

`GET /r/api/v1/margin/openOrders` — same shape as spot open orders.

### 8.4 Cancel All Margin Open Orders

`DELETE /api/v1/margin/openOrders` — same "partial failure" caveat as spot cancel-all.

### 8.5 All Margin Orders

`GET /r/api/v1/margin/allOrders` — `symbol`/`tabdealSymbol`, `startTime`, `endTime`, `limit`
(max `1000`, default `50`).

### 8.6 New Margin Order

`POST /api/v1/margin/order`

```python
order = client.create_margin_order(symbol='BTCIRT', side=OrderSides.BUY, type=OrderTypes.MARKET, quantity="0.001", borrow_quantity="4500000")
```

Same params as spot new-order **plus**:

| Param | Required | Notes |
|---|---|---|
| `borrow_quantity` | Yes | Amount of credit/leverage to borrow. **Buy order** → denominated in the *quote* asset. **Sell order** → denominated in the *base* asset. |

### 8.7 Get Margin Order

`GET /r/api/v1/margin/order` — by `orderId` or `origClientOrderId`.

### 8.8 Cancel Margin Order

`DELETE /api/v1/margin/order` — by `orderId` or `origClientOrderId`.

### 8.9 All Margin-Tradable Assets

`GET /api/v1/margin/allAssets` — no input params.

```json
[{ "assetFullName": "TetherUS", "symbol": "USDTIRT", "tabdealSymbol": "BTC_USDT",
   "assetName": "USDT", "isBorrowable": true, "userMaxBorrow": "150.00000000" }]
```

### 8.10 Repay History

`GET /api/v1/margin/repay` — `asset`, `isolatedSymbol`/`tabdealSymbol`, `txId`, `startTime`,
`endTime`, `size`, `current`. Rows: `amount`, `interest`, `principal`, `status`, `txId`.

### 8.11 Interest History

`GET /api/v1/margin/interestHistory` — same paging params. `type` is either:

- `PERIODIC` — interest accrued per hour of holding the loan
- `ON_BORROW` — first interest charge taken when the loan is issued

### 8.12 Isolated Margin Account Info

`GET /api/v1/margin/isolated/account`

```python
assets = client.get_isolated_margin_account(symbols=["BTCUSDT"])
```

`symbols` (comma-list, optional — omit for all). Per-market entry includes `baseAsset` /
`quoteAsset` breakdown (`borrowed`, `free`, `interest`, `locked`, `netAsset`,
`netAssetOfBtc`/`netAssetOfUsdt`), `marginLevel`, `marginLevelStatus`
(`EXCESSIVE`/`NORMAL`/`MARGIN_CALL`/`FORCE_LIQUIDATION`), `marginRatio`, `indexPrice`,
`liquidatePrice`, `liquidateRate`, `tradeEnabled`. When `symbols` is omitted, response also adds
account-wide totals: `totalAssetOfUsdt/Btc`, `totalLiabilityOfUsdt/Btc`, `totalNetAssetOfUsdt/Btc`.

### 8.13 Forced Liquidation History

`GET /api/v1/margin/forceLiquidationRec` — `isolatedSymbol`/`tabdealSymbol`, `startTime`,
`endTime`, `size`, `current`. Rows: `avgPrice`, `executedQty`, `price`, `qty`, `isIsolated`,
`updatedTime`.

### 8.14 Loan (Borrow) History

`GET /api/v1/margin/loan` — `asset`, `isolatedSymbol`/`tabdealSymbol`, `startTime`, `endTime`,
`size`, `current`. Rows: `txId`, `principal`, `status`, `timestamp`.

---

## 9. Futures / Professional Leverage (FAPI)

Prefix: `fapi`. Structurally mirrors Binance Futures — same param names/response shapes where
possible, so Binance-Futures bot code should port over with minimal changes. `TRADE` endpoints
use the **same auth mechanism as spot** (`X-MBX-APIKEY` header + `timestamp` + `signature`).

If Futures/Pro-Leverage is **not enabled** for the account, server returns error `1207`
("Futures not active") — the user must first call the leverage-setup endpoint (see 9.9) to
activate it. Client class: `from tabdeal.future import Future`.

### 9.1 Ping

`GET /r/fapi/v1/ping` **[NONE]** → `{}`.

### 9.2 Server Time

`GET /r/fapi/v1/time` **[NONE]** → `{ "serverTime": ... }`.

### 9.3 Exchange Info

`GET /r/fapi/v1/exchangeInfo` **[NONE]** — `symbol` / `symbols` (comma-list) optional, omit for
all. Per symbol: `status`, `baseAsset`, `quoteAsset`, `pricePrecision`, `quantityPrecision`,
`quotePrecision`.

### 9.4 Order Book (Depth)

`GET /r/fapi/v1/depth` **[NONE]** — `symbol` (required), `limit` (default `100`, min `5`, max
`100`).

### 9.5 Aggregated Depth

`GET /r/fapi/v1/aggDepth` **[NONE]**

| Param | Required | Notes |
|---|---|---|
| `symbol` | Yes | |
| `aggregationPrecision` | Yes | price bucket size (> 0); e.g. `1` groups by 1, `100` groups by 100 |
| `limitRows` | No | max rows |

Response: `{ "asks": [{price, amount}], "bids": [{price, amount}], "sequence": N, "market_info": {symbol} }`
— note this is a **different shape** than `/depth` (objects, not `[price, qty]` tuples).

### 9.6 New Futures Order

`POST /fapi/v1/order` **[TRADE]** — **only `LIMIT` and `MARKET` are supported** (no
stop/take-profit order *type*; SL/TP is handled via a dedicated position endpoint, 9.16).

| Param | Required | Type | Notes |
|---|---|---|---|
| `symbol` | Yes | STRING | |
| `side` | Yes | ENUM | `BUY`/`SELL` |
| `type` | Yes | ENUM | `LIMIT`/`MARKET` only |
| `quantity` | Yes | DECIMAL | required for `LIMIT`; server may compute for `MARKET` |
| `price` | No | DECIMAL | recommended for `MARKET` too |
| `timeInForce` | No | ENUM | `GTC`/`IOC`/`FOK`, default `GTC` — **other TIF values not yet supported** |
| `reduceOnly` | No | BOOLEAN | **not yet supported** (default `false`) |
| `newClientOrderId` | No | STRING | |
| `timestamp`/`signature` | Yes | | |

Response includes `orderId`, `status`, `avgPrice`, `origQty`/`executedQty`/`cumQty`/`cumQuote`,
`timeInForce`, `reduceOnly`, `closePosition`, `positionSide`, `stopPrice`, `workingType`
(`MARK_PRICE`), `priceProtect`, timestamps.

### 9.7 Get Futures Order

`GET /r/fapi/v1/order` **[TRADE]** — `symbol` + `orderId` **required** (`origClientOrderId`
documented but **currently unsupported** — only `orderId` lookup works today).

### 9.8 Cancel Futures Order

`DELETE /fapi/v1/order` **[TRADE]** — params may be sent in query string or JSON body.
`symbol` + `orderId` required; `origClientOrderId` not yet supported.

### 9.9 Open Futures Orders

`GET /r/fapi/v1/openOrders` **[TRADE]** — `symbol` optional (omit → all symbols), `limit`
(default `50`, min `1`, max `100`).

### 9.10 All Futures Orders

`GET /r/fapi/v1/allOrders` **[TRADE]**

| Param | Required | Notes |
|---|---|---|
| `symbol` | Yes | |
| `orderId` | No | currently unused server-side |
| `startTime`/`endTime` | No | ms |
| `isActive` | No | `1`=active, other=closed, empty=no filter |
| `isDone` | No | `1`=done, `0`=canceled, empty=no filter |
| `limit` | No | default `50`, max `100` |

### 9.11 Position Risk

`GET /r/fapi/v3/positionRisk` **[TRADE]** — `symbol` optional. Returns `positionAmt`,
`entryPrice`, `markPrice`, `unRealizedProfit`, `liquidationPrice`, `leverage`, `marginType`
(`cross`), `positionSide` (`BOTH`).

### 9.12 Get Leverage

`GET /r/fapi/v1/leverage` **[TRADE]** — `symbol` required → `{ "leverage": N, "symbol": "..." }`.

### 9.13 Set Leverage

`POST /fapi/v1/leverage` **[TRADE]** — `symbol` + `leverage` (INT, min `1`) required. **This is
also how a user activates Futures/Pro-Leverage trading if it's currently disabled** (error 1207).

### 9.14 Account Info

`GET /r/fapi/v3/account` **[TRADE]** — `canTrade`/`canDeposit`/`canWithdraw`, `assets[]`
(`walletBalance`, `unrealizedProfit`, `marginBalance`, `availableBalance`,
`crossWalletBalance`, `crossUnPnl`), `positions[]` (same shape as position-risk entries).

### 9.15 Balance

`GET /r/fapi/v3/balance` **[TRADE]** — per-asset `walletBalance`, `availableBalance`,
`crossWalletBalance`, `crossUnPnl`.

### 9.16 Transfer (Spot ↔ Futures wallet)

`POST /fapi/v1/transfer` **[TRADE]**

| Param | Required | Notes |
|---|---|---|
| `type` | Yes | INT: `2` = Spot → Futures, `1` = Futures → Spot |
| `amount` | Yes | DECIMAL |
| `asset` | Yes | STRING |

Response: `{ "tranId": N }`.

### 9.17 Transfer History

`GET /r/fapi/v1/transfer` **[TRADE]** — `type` (`1`/`2`, optional), `startTime`, `endTime`,
`limit` (default `50`, max `100`), `purpose` (filter), `revoked` (documented, **currently
unused by server**).

### 9.18 User Trades

`GET /r/fapi/v1/userTrades` **[TRADE]** — `symbol` required; `startTime`, `endTime`, `fromId`
(currently unused), `limit` (default `50`, max `100`). Rows: `id`, `orderId`, `price`, `qty`,
`quoteQty`, `commission`, `commissionAsset`, `time`, `buyer`, `maker`.

### 9.19 Income History

`GET /r/fapi/v1/income` **[TRADE]**

| Param | Required | Notes |
|---|---|---|
| `symbol` | No | |
| `incomeType` | No | `Transfer`, `TakerCommission`, `MakerCommission`, `TradePNL`, `AdlPNL`, `Liquidation`, `InsuranceFund` |
| `startTime`/`endTime` | No | |
| `limit` | No | default `100`, max `100` |

### 9.20 Force Orders (Liquidations)

`GET /r/fapi/v1/forceOrders` **[TRADE]** — `symbol` optional filter; `startTime`/`endTime`
documented but **currently unused server-side**. Max 100 rows returned.

### 9.21 Position History

`GET /r/fapi/v1/position` **[TRADE]**

| Param | Required | Notes |
|---|---|---|
| `symbol` | No | |
| `side` | No | `BUY`/`SELL` |
| `state` | No | internal position state |
| `isActive` | No | `1`=open only, `0`=closed only |
| `startTime`/`endTime` | No | |
| `limit` | No | default `50`, max `100` |

Rows: `id`, `symbol`, `side`, `positionAmt`, `entryPrice`, `avgExitPrice`, `realizedPnl`,
`status` (`ACTIVE`/closed), `createdTime`, `updateTime`.

### 9.22 Close Position

`DELETE /fapi/v1/position` **[TRADE]** — closes the **entire** open position for a symbol via
a market order. Params may go in query string or body. `symbol` required. Response
`{ "msg": "success" }`.

### 9.23 Set Position Stop-Loss / Take-Profit

`POST /fapi/v1/positionSlTp` **[TRADE]**

| Param | Required | Notes |
|---|---|---|
| `positionId` | Yes | LONG |
| `symbol` | No | extra validation against the position |
| `slPrice` | No* | stop-loss price |
| `tpPrice` | No* | take-profit price |
| `workingType` | No | `MARK_PRICE` / `CONTRACT_PRICE` |

\* at least one of `slPrice`/`tpPrice` must be present. Only **one active SL and one active TP
per position** is allowed (see errors 5017/5018).

---

## 10. FAPI WebSockets

Two separate connection types, both under a **different path prefix** (`special_margin/`) than
the spot websocket (`stream/`).

| | Market WS (spot) | FAPI WS |
|---|---|---|
| URL | `wss://api1.tabdeal.org/stream/` | `.../special_margin/stream/` and `.../special_margin/broadcast/` |
| Markets | Spot, e.g. `btcusdt`, `usdtirt` | Futures, e.g. `BTC_USDT` |
| Topic format | `symbol@depth@PERIOD` | `special_margin@SYMBOL@depth@PERIOD` |
| Allowed periods | `2000ms` only | `100ms`, `200ms`, `1000ms`, `5000ms` |

⚠️ **Connection limit:** don't subscribe to more than ~50 markets on a single websocket
connection — open additional connections for more, or you risk disconnects.

⚠️ Roughly **once per hour** the FAPI websocket sends a plain-text `connection closed ok`
message — on receipt, close and reopen the connection (this is expected/normal, not an error).

### 10.1 Stream endpoint (order book, JSON protocol)

`wss://api1.tabdeal.org/special_margin/stream/`

```json
{ "method": "SUBSCRIBE", "id": 1, "params": ["special_margin@BTC_USDT@depth@1000ms"] }
```

Multiple markets/periods can be combined in one `params` array. Ack on success:
`{ "result": null, "id": 1 }` (only sent if **at least one** topic in `params` is valid; an
empty/missing `params` gets no ack at all). Invalid individual topics return
`{ "code": ..., "msg": ... }` and are simply skipped — the connection stays open unless some
other error occurs.

```python
from tabdeal.websocket_client import FutureWebsocketClient

client = FutureWebsocketClient()   # defaults to special_margin/stream/
client.subscribe(callback=on_message, payload={
    "method": "SUBSCRIBE", "id": 1, "params": ["special_margin@BTC_USDT@depth@1000ms"],
})
```

Push message:

```json
{
  "stream": "special_margin-BTC_USDT-depth-1000ms",
  "data": {
    "e": "depthUpdate", "E": 1657530675579, "s": "BTCUSDT",
    "b": [["39792.23", "8.27169"], ["39792.18", "0.33006"]],
    "a": [["39792.24", "1.27040"], ["39792.27", "0.00850"]]
  }
}
```

Note: `data` is delivered as a **JSON string** that must be parsed client-side into the object
shown above.

### 10.2 Broadcast endpoint (recent trades, plain-text protocol)

`wss://api1.tabdeal.org/special_margin/broadcast/`

This endpoint speaks **plain text**, not JSON-with-method. Immediately after connecting, send a
raw string to subscribe:

- **Trades for one market:** send `"BASE_QUOTE"`, e.g. `"BTC_USDT"` → server streams
  `{"trade": {...}}` for every new trade.
- **Market-info channel only** (no trade replay): send a 4-part underscore string
  `BASE_QUOTE_market_information`, e.g. `"BTC_USDT_market_information"`.

Invalid subscribe string → server returns `{"error": "Invalid params"}` and **closes the
connection**.

```python
import json, websocket

def on_message(ws, message):
    try:
        print(json.loads(message))
    except json.JSONDecodeError:
        print(message)

def on_open(ws):
    ws.send("BTC_USDT")  # or "BTC_USDT_market_information"

ws_app = websocket.WebSocketApp(
    "wss://api1.tabdeal.org/special_margin/broadcast/",
    on_open=on_open, on_message=on_message,
)
ws_app.run_forever()
```

The SDK's `FutureBroadcastWebsocketClient` points at the right URL but its built-in `subscribe()`
is JSON-oriented — for this plain-text endpoint, send the raw string yourself right after
`on_open` (as above), rather than relying on the SDK helper.

---

## 11. Error Codes

All errors are returned as JSON: `{ "code": <int>, "msg": "<string>" }`.

### Server errors

| Code | Meaning |
|---|---|
| 1000 | Server error (unspecified) |
| 1001 | Server error (unspecified) |
| 1002 | High order load / congestion |
| 1003 | Requested feature not available |

### Authentication errors

| Code | Meaning |
|---|---|
| 1100 | Missing `signature`/`timestamp`/`api_key`, or the api-key doesn't exist |
| 1101 | Invalid `timestamp` — clock is >60s ahead of server, or outside the receive window |
| 1102 | Invalid receive window, or receive window > 60000 |
| 1103 | Invalid `signature` |

### Request errors

| Code | Meaning |
|---|---|
| 1200 | Unknown client-side error — contact support |
| 1201 | Invalid parameters sent |
| 1202 | Malformed JSON body |
| 1203 | A required parameter was not sent |
| 1204 | Order not found |
| 1205 | OCO not found |
| 1206 | Market/symbol not found |
| 1207 | `startTime`/`endTime` range exceeds 90 days |
| 1208 | Order does not comply with market rules (filters) |
| 1209 | OCO pricing is invalid |
| 1210 | `timestamp` must be in milliseconds |
| 1211 | Invalid symbol/market string structure |
| 1212 | Asset not found |
| 1213 | An order already exists with this `clientOrderId` |
| 1214 | `listenKey` not found |
| 1215 | Order already canceled |
| 1216 | Rate limit exceeded |
| 1217 | This HTTP method is not allowed on this endpoint |
| 1218 | Insufficient balance/credit |

### FAPI (Futures) errors

*(these codes are reused/overloaded specifically within `fapi`-prefixed endpoints — note some
numbers collide in meaning with the general table above, so interpret by context/endpoint)*

| Code | Meaning (within FAPI context) |
|---|---|
| 1207 | Futures/Pro-Leverage not active for this account ("Futures not active") — *on some FAPI endpoints this code instead means the startTime/endTime range error* |
| 1208 | Invalid symbol or asset |
| 1209 | Validation error on order amount/price (insufficient balance, invalid qty/price, below/above min/max) |
| 1203 | Required parameter missing/invalid (e.g. order `type` must be `LIMIT` or `MARKET`) |
| 1204 | Order not found |
| 1300 | Server error (unspecified) |

⚠️ FAPI websocket note: a plain-text `connection closed ok` message (roughly hourly) means:
close and reopen the socket.

### Margin (leveraged trading) errors

| Code | Meaning |
|---|---|
| 5000 | Your margin (isolated) account is disabled |
| 5001 | Amount exceeds the allowed maximum |
| 5002 | Please enter values greater than zero |
| 10013 | Amount entered exceeds your collateral |
| 5004 | Market credit-issuance cap reached |
| 3027 | Selected asset has no margin trading |
| 3028 | This market doesn't support margin trading |
| 5007 | You're not allowed to transfer funds into this margin account |
| 5008 | Cannot transfer assets out of the margin account |
| 3006 | You've reached your borrow limit |
| 5010 | You're not allowed to borrow |
| 10008 | Borrowing is not possible for this asset |
| 3015 | Repayment amount exceeds the loan amount |
| 21007 | You are currently being liquidated |
| 5014 | Amount entered exceeds the max transferable amount |
| 5015 | You have no open position currently |
| 5016 | Order not filled yet / no open position — SL/TP can only be set on an open position |
| 5017 | Only one active stop-loss allowed per position |
| 5018 | Only one active stop-loss allowed per position *(duplicate of 5017 in source doc)* |
| 5019 | The entered price is invalid |
| 5020 | No active SL/TP exists for this position |

---

## 12. Version History

| Version | Date (Persian calendar) | Added |
|---|---|---|
| 0.6.0 | Mordad 1401 | `POST r/api/v1/account` for account info; user-data websocket; order-book websocket |
| 0.7.0 | Dey 1402 | Isolated margin trading (order placement in margin markets); `orderId` filter for "my trades" |
| 0.8.0 | Ordibehesht 1403 | Paginated open orders (faster open-orders listing); "non-expired all orders" (active + successful orders only) |
| 0.9.0 | Ordibehesht 1405 | Futures / Professional Leverage (FAPI) REST API; FAPI websockets |

---

## 13. Notes for Bot Implementation

These are practical, code-facing takeaways distilled from the spec above — useful when
designing the bot's exchange-adapter layer:

1. **Auth core.** One signer utility is enough for the whole exchange: build the query string
   (alphabetical order not stated as required, but keep param order deterministic), append
   `timestamp`, HMAC-SHA256 with `api_secret`, append as `signature`. Reused identically across
   Spot, Margin, and FAPI — only the header (`X-MBX-APIKEY`) and base path differ.
2. **Clock sync.** Call `GET /r/api/v1/time` (or FAPI's `/r/fapi/v1/time`) on startup and
   periodically; cache the offset vs local clock to avoid error `1101`.
3. **Market metadata is mandatory before trading.** Pull `exchangeInfo` (spot: `/r/api/v1/exchangeInfo`,
   futures: `/r/fapi/v1/exchangeInfo`) and cache `tickSize`/`stepSize`/`minNotional`/price bands per
   symbol; round/validate every order client-side to avoid needless rejections (`1208`).
4. **Idempotent order submission.** Always set `newClientOrderId` (spot/margin) so retries after a
   network timeout can't double-submit (`1213` protects you if you do retry with the same id).
5. **Order lifecycle via websocket, not polling.** For spot/margin, open the user-data stream
   (`listenKey`, renew every ~30–45 min since it expires at 60) and drive order/position state
   from `executionReport`/`listStatus` events instead of polling `GET order` — much lower latency
   and rate-limit pressure. FAPI currently has **no documented user-data (private) websocket** for
   order/position push updates — for FAPI, poll `openOrders`/`position`/`positionRisk` at a sane
   interval, or fall back to the public depth/broadcast websockets for market data while polling
   REST for account/order state.
6. **FAPI is Binance-Futures-shaped.** If there's ever a desire to reuse an existing Binance
   Futures bot codebase/strategy engine, the `fapi` surface is the fastest integration path —
   same field names (`positionAmt`, `entryPrice`, `markPrice`, `crossWalletBalance`, etc).
7. **FAPI order types are limited today**: only `LIMIT`/`MARKET`, no native stop orders —
   protective stop-loss/take-profit must go through `POST /fapi/v1/positionSlTp` against an
   *existing* position, not through the order-placement endpoint. Spot/Margin, by contrast, does
   support `STOP_LOSS_LIMIT` and full OCO (`order/oco`) — a spot/margin bot can build native
   bracket orders; a futures bot must open the position first, then attach SL/TP.
8. **Leverage/Futures must be explicitly enabled** (error `1207` "Futures not active") — the bot's
   onboarding flow for a new API key should call `POST /fapi/v1/leverage` (set-leverage) once to
   activate it before attempting any FAPI order.
9. **Cancel-all is not atomic.** Both spot (`DELETE /api/v1/openOrders`) and margin
   (`DELETE /api/v1/margin/openOrders`) cancel-all-orders calls can partially fail; the bot's
   "flatten/cancel everything" routine must re-fetch open orders after calling this and retry
   until the list is empty (with a max-retry / alerting guard).
10. **Rate limits** aren't given as explicit numbers in this doc (no `X-MBX-USED-WEIGHT`-style
    header documented) — code defensively: exponential backoff on error `1216`
    ("too many requests"), and prefer the paginated/non-expired endpoints over naive full-history
    polling for order state.
11. **Websocket connection hygiene:** cap subscriptions to ~50 symbols per FAPI websocket
    connection (spec explicitly warns of disconnects beyond that), and handle the ~hourly
    `connection closed ok` text frame on FAPI sockets by reconnecting + resubscribing.
12. **Two numeric families to reconcile:** spot/margin responses repeat the same value under both
    `cummulativeQuoteQty` (legacy misspelling) and `cumulativeQuoteQty` — parse either/both
    defensively since which one is populated may vary by endpoint/version.
13. **Credential storage** — this exchange only needs `api_key` + `api_secret` (both are opaque
    bearer-style secrets, no OAuth/refresh flow) — a good fit for the same encrypted-secret-vault
    pattern (e.g. AES-256-GCM at rest) already used for other exchange credentials in this
    workspace's bot projects.
