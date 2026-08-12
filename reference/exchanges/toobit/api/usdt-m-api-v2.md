# Account & Trades (v2)

REST API v2 for **USDT-M / USDC-M** under `/api/v2/futures`. Paths use **kebab-case**. For **spot / shared account** v2 (e.g. balance flow on `/api/v2/account`), see Account & Trades (v2).

## Overview

Successful responses use:

json
```
{ "code": 200, "msg": "success", "data": { } }
```

1

  * `code` = `200` on success; errors use **negative** codes (see Error codes).
  * Lists wrap rows in `data` as a JSON **array** (e.g. open orders, trades). Batch new order returns an array of `{ "code", "order" }` per item.
  * See _Basic information_ for SIGNED and **JSON request body (v2)** (same page).
  * **Wire format (JSON):** Integer timestamps and ids that are 64-bit in the system are sent as **strings** in JSON (not unquoted numbers). **Null** fields are usually **omitted** from the body (you will not see `"field": null` for most optional keys). Optional fields such as `stopPrice` or `triggerBy` only appear in the response when they have a value.

* * *

## Enum parameters (reference)

Allowed values for common string enums in requests/responses. Each field below has the **same allowed values on every route** where it appears.

Parameter| Allowed values
---|---
**category**| `USDT` (USDT-M), `USDC` (USDC-M)
**side**| `BUY`, `SELL`
**positionSide**| `LONG`, `SHORT`
**type**|  Regular order: `LIMIT` limit order, `MARKET` market order
Plan order: `STOP` converts to limit order on trigger, `STOP_MARKET` converts to market order on trigger
Update plan order body: `STOP` plan orders, `STOP_PROFIT_LOSS` TP/SL orders
**stopCategory**| `STOP` plan orders, `STOP_PROFIT_LOSS` TP/SL orders
**timeInForce**| `GTC`, `FOK`, `IOC`, `POST_ONLY`
**triggerBy** / **tpTriggerBy** / **slTriggerBy**| `CONTRACT_PRICE`, `MARK_PRICE`
**tpOrderType** / **slOrderType**| `MARKET`, `LIMIT`
**stopOrderType**| `TAKE_PROFIT`, `STOP_LOSS`
**stopType**| `FIXED_STOP`, `TRAILING_STOP`
**fallbackType**| `RATE`, `PRICE`

* * *

## New regular order (TRADE)

  * `POST /api/v2/futures/order`

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Contract symbol id
side| STRING| YES| `BUY` or `SELL`
positionSide| STRING| YES| `LONG` or `SHORT`
type| STRING| YES| `LIMIT` or `MARKET`
newClientOrderId| STRING| YES| Client order id
quantity| DECIMAL| NO| Order quantity (unit: contracts); at least one of `quantity` / `valueQuantity` must be non-zero
valueQuantity| DECIMAL| NO| USDT notional; at least one of `quantity` / `valueQuantity` must be non-zero
price| DECIMAL| NO| Required when `type` = `LIMIT`; omit for `MARKET`
timeInForce| STRING| NO| One of `GTC`, `FOK`, `IOC`, `POST_ONLY`. Default `GTC`.
takeProfit| STRING| NO| Take-profit price
tpTriggerBy| STRING| NO| Price type used to trigger take-profit: `CONTRACT_PRICE`, `MARK_PRICE`
tpLimitPrice| STRING| NO| Limit price after take-profit is triggered (when `tpOrderType` = `LIMIT`)
tpOrderType| STRING| NO| Order type after take-profit is triggered: `MARKET`, `LIMIT`
stopLoss| STRING| NO| Stop-loss price
slTriggerBy| STRING| NO| Price type used to trigger stop-loss: `CONTRACT_PRICE`, `MARK_PRICE`
slLimitPrice| STRING| NO| Limit price after stop-loss is triggered (when `slOrderType` = `LIMIT`)
slOrderType| STRING| NO| Order type after stop-loss is triggered: `MARKET`, `LIMIT`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1668418485058",
    "updateTime": "1668418485058",
    "orderId": "1289182123551455488",
    "clientOrderId": "test1115",
    "symbol": "BTC-SWAP-USDT",
    "price": "19000",
    "leverage": "2",
    "origQty": "10",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "9.5",
    "type": "LIMIT",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "NEW",
    "contractMultiplier": "0.001"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23

* * *

## Batch new orders (JSON) (TRADE)

  * `POST /api/v2/futures/batch-orders`

### Weight：2

`Content-Type: application/json` — request **body** is a JSON **array** of order objects. For signing details, see JSON Request Body Signing Examples (API v2).

### Query parameters (signed)

Name| Type| Mandatory| Description
---|---|---|---
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| required for SIGNED
recvWindow| LONG| NO| recv window

### Request body (JSON array) — each element

Each object carries the same business fields as a single **New regular order** ; semantics match that endpoint’s table.

Name| Type| Mandatory| Description
---|---|---|---
newClientOrderId| STRING| YES| Client order id
symbol| STRING| YES| Contract symbol id
side| STRING| YES| `BUY` or `SELL`
positionSide| STRING| YES| `LONG` or `SHORT`
type| STRING| YES| `LIMIT` or `MARKET`
quantity| DECIMAL| NO| Per element quantity (unit: contracts); at least one of `quantity` / `valueQuantity` must be non-zero
valueQuantity| DECIMAL| NO| USDT notional; at least one of `quantity` / `valueQuantity` must be non-zero
price| DECIMAL| NO| Required per element when `type` = `LIMIT`; defaults to `0` if omitted
timeInForce| STRING| NO| One of `GTC`, `FOK`, `IOC`, `POST_ONLY`; per element defaults to `GTC` if omitted

### Response

`data` is an array of `{ code, order }`; failed legs return `order = null`, successful legs return an order object.

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "code": 200,
      "order": {
        "time": "1668418485058",
        "updateTime": "1668418485058",
        "orderId": "1289182123551455488",
        "clientOrderId": "c1",
        "symbol": "BTC-SWAP-USDT",
        "price": "19000",
        "leverage": "2",
        "origQty": "10",
        "executedQty": "0",
        "avgPrice": "0",
        "marginLocked": "9.5",
        "type": "LIMIT",
        "side": "BUY",
        "positionSide": "LONG",
        "timeInForce": "GTC",
        "status": "NEW",
        "contractMultiplier": "0.001"
      }
    },
    {
      "code": -2011,
      "order": null
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32

* * *

## Update regular order (TRADE)

  * `POST /api/v2/futures/order/update`

### Weight：2

### Parameters

`LIMIT` orders only — amend price/size per the parameter table.

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| Mutually exclusive with `origClientOrderId`; pass one to identify the order
origClientOrderId| STRING| NO| Mutually exclusive with `orderId`; client id of the order to update
newClientOrderId| STRING| NO| New client id; default generated if omitted
quantity| DECIMAL| NO| New quantity (optional, unit: contracts)
valueQuantity| DECIMAL| NO| New value quantity; default `0`
price| DECIMAL| NO| New price; default `0`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952682388",
    "updateTime": "1767952682388",
    "orderId": "2124135487564299264",
    "clientOrderId": "1767952681690",
    "symbol": "ETH-SWAP-USDT",
    "price": "4000",
    "leverage": "20",
    "origQty": "1",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "2",
    "type": "LIMIT",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "NEW",
    "contractMultiplier": "0.01"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23

* * *

## Cancel one regular order (TRADE)

  * `DELETE /api/v2/futures/order`

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| Mutually exclusive with `origClientOrderId`; pass one to cancel
origClientOrderId| STRING| NO| Mutually exclusive with `orderId`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1668418485058",
    "updateTime": "1668418490000",
    "orderId": "1289182123551455488",
    "clientOrderId": "test1115",
    "symbol": "BTC-SWAP-USDT",
    "price": "19000",
    "leverage": "2",
    "origQty": "10",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "0",
    "type": "LIMIT",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "CANCELED",
    "contractMultiplier": "0.001"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23

* * *

## Batch cancel regular orders (TRADE)

  * `DELETE /api/v2/futures/batch-orders`

### Weight：3

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Comma-separated contract symbol ids
side| STRING| NO| Optional `BUY` or `SELL`; omit = no side filter. No `positionSide` on this route.
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

`data` is always `null` (no order payload, no string enums on this route).

json
```
{
  "code": 200,
  "msg": "success",
  "data": null
}
```

1
2
3
4
5

* * *

## Get one regular order (USER_DATA)

  * `GET /api/v2/futures/order`

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| Mutually exclusive with `origClientOrderId`; pass one to query
origClientOrderId| STRING| NO| Mutually exclusive with `orderId`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1668418485058",
    "updateTime": "1668418485058",
    "orderId": "1289182123551455488",
    "clientOrderId": "test1115",
    "symbol": "BTC-SWAP-USDT",
    "price": "19000",
    "leverage": "2",
    "origQty": "10",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "9.5",
    "type": "LIMIT",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "NEW",
    "contractMultiplier": "0.001"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23

* * *

## Open regular orders (USER_DATA)

  * `GET /api/v2/futures/open-orders`

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| Filter by symbol id; empty = all
orderId| LONG| NO| Cursor
limit| INT| NO| default `20`, min `1`, max `1000`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "time": "1668418485058",
      "updateTime": "1668418485058",
      "orderId": "1289182123551455488",
      "clientOrderId": "test1115",
      "symbol": "BTC-SWAP-USDT",
      "price": "19000",
      "leverage": "2",
      "origQty": "10",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "9.5",
      "type": "LIMIT",
      "side": "BUY",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "NEW",
      "contractMultiplier": "0.001"
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25

* * *

## History regular orders (USER_DATA)

  * `GET /api/v2/futures/history-orders`

### Weight：5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| Filter by symbol id; empty = all
orderId| LONG| NO| Cursor; default `0`
startTime| LONG| NO| Start (ms); default rolling window if `<= 0`
endTime| LONG| NO| End (ms)
limit| INT| NO| default `20`, min `1`, max `1000`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "time": "1668418485058",
      "updateTime": "1668418485058",
      "orderId": "1289182123551455488",
      "clientOrderId": "test1115",
      "symbol": "BTC-SWAP-USDT",
      "price": "19000",
      "leverage": "2",
      "origQty": "10",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "9.5",
      "type": "LIMIT",
      "side": "BUY",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "NEW",
      "contractMultiplier": "0.001"
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25

* * *

## User trades (USER_DATA)

  * `GET /api/v2/futures/user-trades`

### Weight：5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Contract symbol id
fromId| LONG| NO| default `0`
toId| LONG| NO| default `0`
startTime| LONG| NO| Start (ms)
endTime| LONG| NO| End (ms)
limit| INT| NO| default `20`, min `1`, max `1000`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "time": "1668419000000",
      "createdTime": "1668419000100",
      "id": "9876543210",
      "orderId": "1289182123551455488",
      "matchOrderId": "1289182123551456000",
      "matchAccountId": "10001",
      "accountId": "122216245228131",
      "symbol": "BTC-SWAP-USDT",
      "price": "19000",
      "qty": "1",
      "commissionAsset": "USDT",
      "commission": "0.01",
      "makerRebate": "0",
      "type": "LIMIT",
      "side": "BUY",
      "positionSide": "LONG",
      "realizedPnl": "0",
      "ticketId": "t1",
      "isMaker": true,
      "matchOrderStrategy": 0
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28

* * *

## New plan order (TRADE)

  * `POST /api/v2/futures/algo-order`

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Contract symbol id
side| STRING| YES| `BUY` or `SELL`
positionSide| STRING| YES| `LONG` or `SHORT`
type| STRING| YES| `STOP` or `STOP_MARKET`
stopPrice| DECIMAL| YES| Trigger price
newClientOrderId| STRING| YES| Client order id
quantity| DECIMAL| NO| Order quantity (unit: contracts); at least one of `quantity` / `valueQuantity` must be non-zero
valueQuantity| DECIMAL| NO| USDT notional; at least one of `quantity` / `valueQuantity` must be non-zero
price| DECIMAL| NO| Required when `type` = `STOP` (limit price after trigger); omit for `STOP_MARKET`
timeInForce| STRING| NO| One of `GTC`, `FOK`, `IOC`, `POST_ONLY`; default `GTC` if omitted
triggerBy| STRING| NO| Trigger price type: `CONTRACT_PRICE` (default), `MARK_PRICE`
takeProfit| STRING| NO| Take-profit price
tpTriggerBy| STRING| NO| Price type used to trigger take-profit: `CONTRACT_PRICE`, `MARK_PRICE`
tpLimitPrice| STRING| NO| Limit price after take-profit is triggered (when `tpOrderType` = `LIMIT`)
tpOrderType| STRING| NO| Order type after take-profit is triggered: `MARKET`, `LIMIT`
stopLoss| STRING| NO| Stop-loss price
slTriggerBy| STRING| NO| Price type used to trigger stop-loss: `CONTRACT_PRICE`, `MARK_PRICE`
slLimitPrice| STRING| NO| Limit price after stop-loss is triggered (when `slOrderType` = `LIMIT`)
slOrderType| STRING| NO| Order type after stop-loss is triggered: `MARKET`, `LIMIT`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

**Example — plan order (`STOP` / `STOP_MARKET`):**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952799216",
    "updateTime": "1767952799216",
    "orderId": "2124136467689134848",
    "clientOrderId": "1767952799112",
    "symbol": "BTC-SWAP-USDT",
    "price": "0",
    "leverage": "20",
    "origQty": "2",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "10",
    "type": "STOP_MARKET",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_NEW",
    "contractMultiplier": "0.001",
    "stopPrice": "95000",
    "triggerBy": "CONTRACT_PRICE"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25

* * *

## Update plan order (TRADE)

  * `POST /api/v2/futures/algo-order/update`

### Weight：2

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
type| STRING| YES| `STOP` (plan-order row) or `STOP_PROFIT_LOSS` (TP/SL row)
orderId| LONG| NO| Mutually exclusive with `origClientOrderId`; pass one to locate the row to amend
origClientOrderId| STRING| NO| Mutually exclusive with `orderId`; client id of the row to amend
newClientOrderId| STRING| NO| New client id; default generated if omitted
quantity| DECIMAL| NO| New quantity (unit: contracts)
valueQuantity| DECIMAL| NO| default `0`
price| DECIMAL| NO| default `0`
stopPrice| DECIMAL| NO| Trigger price; default `0`
triggerBy| STRING| NO| `CONTRACT_PRICE` or `MARK_PRICE`. Empty / omitted keeps the order’s original trigger type.
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

The returned object reflects the order family chosen by the request body's `type`: plan family returns `STOP` / `STOP_MARKET`, TP/SL family returns `STOP_PROFIT_LOSS` / `STOP_PROFIT_LOSS_MARKET`. TP/SL rows may include additional enum fields `stopOrderType`, `stopType`, and `fallbackType` (for trailing scenarios), plus related fields such as `activePrice`, `fallbackQuantity`, `activeStatus`, etc.

**Example — plan family:**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952799216",
    "updateTime": "1767952800000",
    "orderId": "2124136467689134848",
    "clientOrderId": "1767952799112",
    "symbol": "BTC-SWAP-USDT",
    "price": "96000",
    "leverage": "20",
    "origQty": "2",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "10",
    "type": "STOP",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_NEW",
    "contractMultiplier": "0.001",
    "stopPrice": "95000",
    "triggerBy": "CONTRACT_PRICE"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25

**Example — TP/SL family:**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952801000",
    "updateTime": "1767952802000",
    "orderId": "2124136467689135000",
    "clientOrderId": "1767952800001",
    "symbol": "BTC-SWAP-USDT",
    "price": "100000",
    "leverage": "20",
    "origQty": "1",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "5",
    "type": "STOP_PROFIT_LOSS",
    "side": "SELL",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_NEW",
    "contractMultiplier": "0.001",
    "stopPrice": "99000",
    "triggerBy": "CONTRACT_PRICE",
    "stopOrderType": "TAKE_PROFIT",
    "stopType": "FIXED_STOP"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27

* * *

## Get one plan order (USER_DATA)

  * `GET /api/v2/futures/algo-order`

### Weight：1

Plan and TP/SL rows resolve by id only.

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| Mutually exclusive with `origClientOrderId`; pass one to query
origClientOrderId| STRING| NO| Mutually exclusive with `orderId`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

`data` is a single plan or TP/SL order:

  * `type`:
    * `STOP` — plan order, **limit** fill after trigger;
    * `STOP_MARKET` — plan order, **market** fill after trigger;
    * `STOP_PROFIT_LOSS` — TP/SL condition, **limit** after trigger;
    * `STOP_PROFIT_LOSS_MARKET` — TP/SL condition, **market** after trigger.
  * When `type` is `STOP_PROFIT_LOSS` or `STOP_PROFIT_LOSS_MARKET`, the row may include additional enum fields `stopOrderType` and `stopType`.
  * For trailing scenarios, the row may also include `fallbackType`, `activePrice`, `fallbackQuantity`, `activeStatus`, etc., when applicable.

**Example — plan order (`STOP` / `STOP_MARKET`):**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952799216",
    "updateTime": "1767952800000",
    "orderId": "2124136467689134848",
    "clientOrderId": "1767952799112",
    "symbol": "BTC-SWAP-USDT",
    "price": "0",
    "leverage": "20",
    "origQty": "2",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "10",
    "type": "STOP",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_NEW",
    "contractMultiplier": "0.001",
    "stopPrice": "96000",
    "triggerBy": "CONTRACT_PRICE"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25

**Example — TP/SL limit (`STOP_PROFIT_LOSS`, take-profit):**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952801000",
    "updateTime": "1767952802000",
    "orderId": "2124136467689135000",
    "clientOrderId": "tp-001",
    "symbol": "BTC-SWAP-USDT",
    "price": "100000",
    "leverage": "20",
    "origQty": "1",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "5",
    "type": "STOP_PROFIT_LOSS",
    "side": "SELL",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_NEW",
    "contractMultiplier": "0.001",
    "stopPrice": "99000",
    "triggerBy": "MARK_PRICE",
    "stopOrderType": "TAKE_PROFIT",
    "stopType": "FIXED_STOP"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27

**Example — TP/SL market (`STOP_PROFIT_LOSS_MARKET`, stop-loss):**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952803000",
    "updateTime": "1767952803000",
    "orderId": "2124136467689135001",
    "clientOrderId": "sl-mkt-001",
    "symbol": "BTC-SWAP-USDT",
    "price": "0",
    "leverage": "20",
    "origQty": "1",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "5",
    "type": "STOP_PROFIT_LOSS_MARKET",
    "side": "SELL",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_NEW",
    "contractMultiplier": "0.001",
    "stopPrice": "92000",
    "triggerBy": "CONTRACT_PRICE",
    "stopOrderType": "STOP_LOSS",
    "stopType": "FIXED_STOP"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27

**Example — trailing stop-loss (`TRAILING_STOP`, optional `activePrice` / `fallback*` when applicable):**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952804000",
    "updateTime": "1767952804000",
    "orderId": "2124136467689135002",
    "clientOrderId": "trail-001",
    "symbol": "BTC-SWAP-USDT",
    "price": "0",
    "leverage": "20",
    "origQty": "1",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "5",
    "type": "STOP_PROFIT_LOSS",
    "side": "SELL",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_NEW",
    "contractMultiplier": "0.001",
    "stopPrice": "0",
    "triggerBy": "CONTRACT_PRICE",
    "stopOrderType": "STOP_LOSS",
    "stopType": "TRAILING_STOP",
    "activePrice": "95000",
    "fallbackType": "RATE",
    "fallbackQuantity": "0.01",
    "activeStatus": 0
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31

* * *

## Cancel one plan order (TRADE)

  * `DELETE /api/v2/futures/algo-order`

Cancels a **single** plan or TP/SL row by id.

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| Mutually exclusive with `origClientOrderId`; pass one to cancel
origClientOrderId| STRING| NO| Mutually exclusive with `orderId`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

`data` is the canceled order's final snapshot (plan or TP/SL):

  * `type`: same set as **Get one plan order** → **Response** — `STOP`, `STOP_MARKET`, `STOP_PROFIT_LOSS`, `STOP_PROFIT_LOSS_MARKET`.
  * TP/SL rows also carry `stopOrderType` (`TAKE_PROFIT`, `STOP_LOSS`) and `stopType` (`FIXED_STOP`, `TRAILING_STOP`); trailing rows may include `activePrice`, `fallbackType` (`RATE`, `PRICE`), etc., when applicable.

**Example — plan canceled:**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952799216",
    "updateTime": "1767952805000",
    "orderId": "2124136467689134848",
    "clientOrderId": "1767952799112",
    "symbol": "BTC-SWAP-USDT",
    "price": "0",
    "leverage": "20",
    "origQty": "2",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "10",
    "type": "STOP",
    "side": "BUY",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_CANCELED",
    "contractMultiplier": "0.001",
    "stopPrice": "96000",
    "triggerBy": "CONTRACT_PRICE"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25

**Example — TP/SL canceled:**

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "time": "1767952801000",
    "updateTime": "1767952805000",
    "orderId": "2124136467689135000",
    "clientOrderId": "tp-001",
    "symbol": "BTC-SWAP-USDT",
    "price": "100000",
    "leverage": "20",
    "origQty": "1",
    "executedQty": "0",
    "avgPrice": "0",
    "marginLocked": "5",
    "type": "STOP_PROFIT_LOSS",
    "side": "SELL",
    "positionSide": "LONG",
    "timeInForce": "GTC",
    "status": "ORDER_CANCELED",
    "contractMultiplier": "0.001",
    "stopPrice": "99000",
    "triggerBy": "MARK_PRICE",
    "stopOrderType": "TAKE_PROFIT",
    "stopType": "FIXED_STOP"
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27

* * *

## Open plan orders (USER_DATA)

  * `GET /api/v2/futures/open-algo-orders`

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| Filter; empty = all
orderId| LONG| NO| Cursor
stopCategory| STRING| NO| `STOP` (plan orders only) or `STOP_PROFIT_LOSS` (TP/SL only); if **omitted** , results are **plan`STOP` only** (excludes TP/SL)
limit| INT| NO| default `20`, min `1`, max `1000`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

`data` is an array of plan / TP-SL order rows:

  * Per-row `type`: same four values and meanings as **Get one plan order** → **Response** — `STOP`, `STOP_MARKET`, `STOP_PROFIT_LOSS`, `STOP_PROFIT_LOSS_MARKET`. Which rows appear is determined by request `stopCategory` (it filters the row set only; it does not change per-row enum semantics).
  * TP/SL rows also carry `stopOrderType` (`TAKE_PROFIT`, `STOP_LOSS`) and `stopType` (`FIXED_STOP`, `TRAILING_STOP`); trailing rows may include `activePrice`, `fallbackType` (`RATE`, `PRICE`), `fallbackQuantity`, `activeStatus`, etc., when applicable.

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "time": "1767952799216",
      "updateTime": "1767952799216",
      "orderId": "2124136467689134848",
      "clientOrderId": "1767952799112",
      "symbol": "BTC-SWAP-USDT",
      "price": "0",
      "leverage": "20",
      "origQty": "2",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "10",
      "type": "STOP_MARKET",
      "side": "BUY",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "ORDER_NEW",
      "contractMultiplier": "0.001",
      "stopPrice": "95000",
      "triggerBy": "CONTRACT_PRICE"
    },
    {
      "time": "1767952801000",
      "updateTime": "1767952802000",
      "orderId": "2124136467689135000",
      "clientOrderId": "tp-001",
      "symbol": "BTC-SWAP-USDT",
      "price": "100000",
      "leverage": "20",
      "origQty": "1",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "5",
      "type": "STOP_PROFIT_LOSS",
      "side": "SELL",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "ORDER_NEW",
      "contractMultiplier": "0.001",
      "stopPrice": "99000",
      "triggerBy": "MARK_PRICE",
      "stopOrderType": "TAKE_PROFIT",
      "stopType": "FIXED_STOP"
    },
    {
      "time": "1767952803000",
      "updateTime": "1767952803000",
      "orderId": "2124136467689135001",
      "clientOrderId": "sl-mkt-001",
      "symbol": "BTC-SWAP-USDT",
      "price": "0",
      "leverage": "20",
      "origQty": "1",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "5",
      "type": "STOP_PROFIT_LOSS_MARKET",
      "side": "SELL",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "ORDER_NEW",
      "contractMultiplier": "0.001",
      "stopPrice": "92000",
      "triggerBy": "CONTRACT_PRICE",
      "stopOrderType": "STOP_LOSS",
      "stopType": "FIXED_STOP"
    },
    {
      "time": "1767952804000",
      "updateTime": "1767952804000",
      "orderId": "2124136467689135002",
      "clientOrderId": "trail-001",
      "symbol": "BTC-SWAP-USDT",
      "price": "0",
      "leverage": "20",
      "origQty": "1",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "5",
      "type": "STOP_PROFIT_LOSS",
      "side": "SELL",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "ORDER_NEW",
      "contractMultiplier": "0.001",
      "stopPrice": "0",
      "triggerBy": "CONTRACT_PRICE",
      "stopOrderType": "STOP_LOSS",
      "stopType": "TRAILING_STOP",
      "activePrice": "95000",
      "fallbackType": "RATE",
      "fallbackQuantity": "0.01",
      "activeStatus": 0
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
95
96
97
98
99
100

* * *

## History plan orders (USER_DATA)

  * `GET /api/v2/futures/history-algo-orders`

### Weight：5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| Filter; empty = all
orderId| LONG| NO| default `0`
stopCategory| STRING| NO| `STOP` (plan orders only) or `STOP_PROFIT_LOSS` (TP/SL only); if **omitted** , results are **plan`STOP` only** (excludes TP/SL)
startTime| LONG| NO| Start (ms); default rolling window if `<= 0`
endTime| LONG| NO| End (ms)
limit| INT| NO| default `20`, min `1`, max `1000`
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

`data` is an array of plan / TP-SL order rows:

  * Per-row `type`: same four values and meanings as **Get one plan order** → **Response** — `STOP`, `STOP_MARKET`, `STOP_PROFIT_LOSS`, `STOP_PROFIT_LOSS_MARKET`. Which rows appear is determined by request `stopCategory` (it filters the row set only; it does not change per-row enum semantics).
  * TP/SL rows also carry `stopOrderType` (`TAKE_PROFIT`, `STOP_LOSS`) and `stopType` (`FIXED_STOP`, `TRAILING_STOP`); trailing rows may include `activePrice`, `fallbackType` (`RATE`, `PRICE`), `fallbackQuantity`, `activeStatus`, etc., when applicable.

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "time": "1767952799216",
      "updateTime": "1767952799216",
      "orderId": "2124136467689134848",
      "clientOrderId": "1767952799112",
      "symbol": "BTC-SWAP-USDT",
      "price": "0",
      "leverage": "20",
      "origQty": "2",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "10",
      "type": "STOP_MARKET",
      "side": "BUY",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "ORDER_NEW",
      "contractMultiplier": "0.001",
      "stopPrice": "95000",
      "triggerBy": "CONTRACT_PRICE"
    },
    {
      "time": "1767952801000",
      "updateTime": "1767952802000",
      "orderId": "2124136467689135000",
      "clientOrderId": "tp-001",
      "symbol": "BTC-SWAP-USDT",
      "price": "100000",
      "leverage": "20",
      "origQty": "1",
      "executedQty": "0",
      "avgPrice": "0",
      "marginLocked": "5",
      "type": "STOP_PROFIT_LOSS",
      "side": "SELL",
      "positionSide": "LONG",
      "timeInForce": "GTC",
      "status": "ORDER_NEW",
      "contractMultiplier": "0.001",
      "stopPrice": "99000",
      "triggerBy": "MARK_PRICE",
      "stopOrderType": "TAKE_PROFIT",
      "stopType": "FIXED_STOP"
    }
  ]
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50

* * *

## Batch cancel plan orders (TRADE)

  * `DELETE /api/v2/futures/batch-cancel-algo-orders`

### Weight：3

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Comma-separated symbol ids
stopCategory| STRING| YES| **Required** : `STOP` (cancel plan orders for the symbol) or `STOP_PROFIT_LOSS` (cancel TP/SL rows for the symbol)
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

`data` is always `null` (no order payload, no string enums on this route).

json
```
{
  "code": 200,
  "msg": "success",
  "data": null
}
```

1
2
3
4
5

* * *

## Change leverage (TRADE)

  * `POST /api/v2/futures/leverage`

### Weight：1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Contract symbol id
leverage| STRING| YES| Target leverage (string in request)
category| STRING| NO| USDT-M: `USDT`, USDC-M: `USDC`; default `USDT`
timestamp| LONG| YES| —
recvWindow| LONG| NO| recv window

### Response

`data` reflects the new leverage setting; no string-enum fields (`leverage` is numeric).

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "symbolId": "BTC-SWAP-USDT",
    "leverage": 20
  }
}
```

1
2
3
4
5
6
7
8

* * *

## Get API trial vouchers (USER_DATA)

  * `GET /api/v2/futures/voucher/list`

### Weight: 5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
token| STRING| YES| Voucher token, for example `USDT`; leading and trailing whitespace is ignored
voucherStatus| STRING| NO| `NOT_USED`, `USING`, `USED`, or `FROZEN`; omit to query all statuses; case-insensitive
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| Receive window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "vouchers": [
      {
        "relationId": "987654321",
        "amount": "100",
        "voucherBalance": "80",
        "voucherStatus": "USING",
        "createTime": "1782468000000",
        "expireTime": "1785060000000",
        "remainingType": 3,
        "token": "USDT",
        "claimThreshold": "futures trading volume500USDT",
        "tradeRate": "1",
        "isMerge": 1,
        "isFee": 1,
        "transferInInvalidation": false,
        "transferOutInvalidation": true
      }
    ]
  }
}
```

1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24

Name| Type| Description
---|---|---
data.vouchers| ARRAY| Trial voucher list; an empty array is returned when no voucher matches
relationId| LONG| User-voucher relation ID; returned as a string in JSON
amount| STRING| Voucher face value
voucherBalance| STRING| Remaining voucher balance
voucherStatus| STRING| Normalized status: `NOT_USED`, `USING`, `USED`, or `FROZEN`
createTime| LONG| Creation time in milliseconds; returned as a string in JSON
expireTime| LONG| Expiration time in milliseconds; returned as a string in JSON
remainingType| INT| Voucher balance type; `3` means balance trial voucher
token| STRING| Voucher token
claimThreshold| STRING| Claim threshold description
tradeRate| STRING| Proportion available for order placement
isMerge| INT| Whether merging is allowed: `0` no, `1` yes
isFee| INT| Whether fees can be deducted: `0` no, `1` yes
transferInInvalidation| BOOLEAN| Whether an asset transfer in invalidates the voucher
transferOutInvalidation| BOOLEAN| Whether an asset transfer out invalidates the voucher

An empty parameter or invalid status returns `-1105` or `-1130`. Query failures default to `-1402`. See Error Codes for other voucher errors.

* * *

## Receive an API trial voucher (TRADE)

  * `POST /api/v2/futures/voucher/receive`

Read-only API keys cannot receive a voucher.

### Weight: 10

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
relationId| LONG| YES| User-voucher relation ID to receive; must be greater than `0`
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| Receive window

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "relationId": "987654321",
    "voucherBalance": "50",
    "voucherStatus": "USING"
  }
}
```

1
2
3
4
5
6
7
8
9

Name| Type| Description
---|---|---
relationId| LONG| Received user-voucher relation ID; returned as a string in JSON
voucherBalance| STRING| Voucher balance after receipt
voucherStatus| STRING| Normalized status after receipt

A read-only API key returns `-1020`, an invalid `relationId` returns `-1130`, and receipt failures default to `-1403`. See Error Codes for other voucher errors.
