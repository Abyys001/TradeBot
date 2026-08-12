# Spot Account/Trade

## Test New Order (TRADE)

  * `POST /api/v1/spot/orderTest (HMAC SHA256)`

Test new order creation and signature/recvWindow long. Creates and validates a new order but does not send it into the matching engine.

### Weight：1

> Response

json
```
{}
```

1

### Parameters

Same as `POST /api/v1/spot/order`

## New Order (TRADE)

  * `POST /api/v1/spot/order (HMAC SHA256)`

Send in a new order.

### Weight：1

> Response

json
```
{
  "accountId": "1287091689761137921",
  "symbol": "BTCUSDT",
  "symbolName": "BTCUSDT",
  "clientOrderId": "1668483032042259",
  "orderId": "1289723583082363136",
  "transactTime": "1668483032058",
  "price": "400",
  "origQty": "1",
  "executedQty": "0",
  "status": "FILLED",
  "timeInForce": "GTC",
  "type": "LIMIT",
  "side": "SELL"
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
side| ENUM| YES| `BUY` or `SELL`
type| ENUM| YES| See enumeration definition for details: order type
timeInForce| ENUM| NO| For details, see enumeration definition: valid methods
quantity| DECIMAL| YES| Order quantity. When `type=MARKET` and `side=BUY`, this field must contain the order amount in the quote asset (for example, the USDT amount for `BTCUSDT`).
price| DECIMAL| NO| price
newClientOrderId| STRING| NO| A unique id among open orders. Automatically generated if not sent.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

Additional mandatory parameters based on `type`:

Type| Additional mandatory parameters
---|---
`LIMIT`| `quantity`,`price`
`MARKET`| `quantity`
`LIMIT_MAKER`| `quantity`, `price`

## Place Multiple Orders (TRADE)

  * `POST /api/v1/spot/batchOrders (HMAC SHA256)`

### Weight：2

Create new orders in batches, up to `20` orders at a time, must be the same `symbol`.

> example：

bash
```
curl  -H "Content-Type:application/json" -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" -X POST -d '[
{     "newClientOrderId": "pl12241234567898",
      "symbol": "BTCUSDT",
      "side": "SELL",
      "type": "LIMIT",
      "price": 17001,
      "quantity": 1
},
{     "newClientOrderId": "pl12241234567899",
      "symbol": "BTCUSDT",
      "side": "SELL",
      "type": "LIMIT",
      "price": 17002,
      "quantity": 1
 } ]' 'https://api.toobit.com/api/v1/spot/batchOrders?timestamp=1671880913657&signature=7548b6834613afed3b7d3b0b9bfb0e0b3e3799c46db3ea6b952439fde35cb88f'
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

> Response success :

json
```
{
  "code": 0,
  "result": [
    {
      "code": 0,
      "order": {
        "accountId": "1287091689761137921",
        "symbol": "BTCUSDT",
        "symbolName": "BTCUSDT",
        "clientOrderId": "pl12241234567898",
        "orderId": "202212241234567898",
        "transactTime": "1671880251836",
        "price": "17001",
        "origQty": "1",
        "executedQty": "0",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "SELL"
      }
    },
    {
      "code": 0,
      "order": {
        "accountId": "1287091689761137921",
        "symbol": "BTCUSDT",
        "symbolName": "BTCUSDT",
        "clientOrderId": "pl12241234567899",
        "orderId": "202212241234567899",
        "transactTime": "1671880251853",
        "price": "17002",
        "origQty": "1",
        "executedQty": "0",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "SELL"
      }
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

fail :

json
```
{
  "code": 0,
  "result": [
    {
      "code": -1149,
      "msg": "Create order failed"
    },
    {
      "code": -1149,
      "msg": "Create order failed"
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
| list| YES| `RequestBody` parameter
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

**The batchOrders in RequestBody should fill in the order parameters in list of JSON format**

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
side| ENUM| YES| `BUY` or `SELL`
type| ENUM| YES| See enumeration definition for details: `orderType`
timeInForce| ENUM| NO| See enumeration definition for details: `timeInForce`
quantity| DECIMAL| YES| quantity
price| DECIMAL| NO| price
newClientOrderId| STRING| YES| A unique id among open orders. The ID of the order, defined by the user

Depending on the order `type`, certain parameters are mandatory:

Type| Additional mandatory parameters
---|---
`LIMIT`| `quantity`,`price`
`MARKET`| `quantity`
`LIMIT_MAKER`| `quantity`, `price`

## Cancel Order (TRADE)

  * `DELETE /api/v1/spot/order (HMAC SHA256)`

Cancel an active order.

### Weight：1

> Response

json
```
{
  "symbol": "LTCBTC",
  "orderId": "1",
  "clientOrderId": "9t1M2K0Ya092",
  "price": "0.1",
  "origQty": "1.0",
  "executedQty": "0.0",
  "status": "CANCELED",
  "timeInForce": "GTC",
  "type": "LIMIT",
  "side": "BUY",
  "transactTime": "1499827319559"
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| order id
clientOrderId| STRING| NO| client order id
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

Either `orderId` or `clientOrderId` must be sent.

## Cancel All Open Orders (TRADE)

  * `DELETE /api/v1/spot/openOrders (HMAC SHA256)`

### Weight：5

> Response

json
```
{
  "success": true
}
```

1
2
3

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| symbol
side| ENUM| NO| `BUY` or `SELL`
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

## Cancel Multiple Orders (TRADE)

  * `DELETE /api/v1/spot/cancelOrderByIds (HMAC SHA256)`

Cancel orders in batches according to the order id, **maximum 100 items at a time**

### Weight：5

> Response

success :

json
```
{
  "code":0, // 0 On behalf of successful execution
  "result":[] //
}
```

1
2
3
4

Some or all of the cancellations failed:

json
```
{
   "code":0,
   "result":[
       {
          "orderId":"202212231234567895",
          "code":-2013 //
       },
       {
           "orderId":"202212231234567896",
           "code":-2013
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
ids| STRING| YES| order Id （Multiple separated by `,`）
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

Note: **code** returns `0` to indicate that the order cancellation request has been executed. Whether it is successful or not depends on the results in `result`. If `result` is empty, it means that all of them are successful, and if `orderId` is not empty, it means that the cancellation failed The order id, `code` represents the reason for the cancellation failure.

## Query Order (USER_DATA)

  * `GET /api/v1/spot/order (HMAC SHA256)`

### Weight：1

> Response

json
```
{
  "symbol": "LTCBTC",
  "orderId": "1",
  "clientOrderId": "9t1M2K0Ya092",
  "price": "0.1",
  "origQty": "1.0",
  "executedQty": "0.0",
  "cumulativeQuoteQty": "0.0",
  "status": "NEW",
  "timeInForce": "GTC",
  "type": "LIMIT",
  "side": "BUY",
  "stopPrice": "0.0",
  "icebergQty": "0.0",
  "time": "1499827319559",
  "updateTime": "1499827319559",
  "isWorking": true
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| order id
origClientOrderId| STRING| NO| client order id
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

Notes：

  * Either `orderId` or `origClientOrderId` must be sent.
  * For some historical orders cumulativeQuoteQty will be < 0, meaning the data is not available at this time.

## Current Open Orders (USER_DATA)

  * `GET /api/v1/spot/openOrders (HMAC SHA256)`

Get all open orders on a symbol. **Careful** when accessing this with no symbol.

### Weight ：1

> Response

json
```
[
  {
    "symbol": "LTCBTC",
    "orderId": "1",
    "clientOrderId": "t7921223K12",
    "price": "0.1",
    "origQty": "1.0",
    "executedQty": "0.0",
    "cumulativeQuoteQty": "0.0",
    "status": "NEW",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "side": "BUY",
    "stopPrice": "0.0",
    "icebergQty": "0.0",
    "time": "1499827319559",
    "updateTime": "1499827319559",
    "isWorking": true
  }
]
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| order id
symbol| STRING| NO| symbol
limit| INT| NO| Default 500; Max 1000.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

Notes：

  * If orderId is set, it will filter orders smaller than orderId. Otherwise, the most recent order information will be returned.

## All Orders (USER_DATA)

  * `GET /api/v1/spot/tradeOrders (HMAC SHA256)`

Get all account orders; active, canceled, or filled.

### Weight：5

> Response

json
```
[
  {
    "symbol": "LTCBTC",
    "orderId": "1",
    "clientOrderId": "987yjj2Ym",
    "price": "0.1",
    "origQty": "1.0",
    "executedQty": "0.0",
    "cumulativeQuoteQty": "0.0",
    "status": "NEW",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "side": "BUY",
    "stopPrice": "0.0",
    "icebergQty": "0.0",
    "time": "1499827319559",
    "updateTime": "1499827319559",
    "isWorking": true
  }
]
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| order id
symbol| STRING| NO| symbol
startTime| LONG| NO| start timestamp.Default value three days ago
endTime| LONG| NO| end timestamp
limit| INT| NO| Default 500; Max 1000.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

## Account Information (USER_DATA)

  * `GET /api/v1/account`

### Weight：5

> Response

json
```
{
    "balances": [
        {
            "coin": "BTC",
            "total": "995.899",
            "free": "995.899",
            "locked": "0"
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

## Account Trade List (USER_DATA)

  * `GET /api/v1/account/trades`

### Weight：5

> Response

json
```
[
    {
        "id": "1291291745779199489",
        "symbol": "BTCUSDT",
        "symbolName": "BTCUSDT",
        "orderId": "1290805676579237376",
        "matchOrderId": "1291291745191996928",
        "price": "314",
        "qty": "0.71433122",
        "commission": "0.22430000308",
        "commissionAsset": "USDT",
        "time": "1668669971575",
        "isBuyer": false,
        "isMaker": true,
        "fee": {
            "feeCoinId": "USDT",
            "feeCoinName": "USDT",
            "fee": "0.22430000308"
        },
        "feeCoinId": "USDT",
        "feeAmount": "0.22430000308",
        "makerRebate": "0",
        "ticketId": "1185465136943458745" // ticketId
    }
]
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
fromId| LONG| NO| from id
toId| LONG| NO| end id
limit| INT| NO| Number of items displayed per page
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

Notes：

  * If only fromId is set，it will get orders < that fromId in descending order.
  * If only toId is set, it will get orders > that toId in ascending order.
  * If fromId is set and toId is set, it will get orders < that fromId and > that toId in descending order.
  * If fromId is not set and toId it not set, most recent order are returned in descending order.

## Query Sub-account (USER_DATA)

  * `GET /api/v1/account/subAccount`

### Weight：5

> Response：

json
```
[
    {
        "accountId": "122216245228131",
        "accountName": "",
        "accountType": 1,
        "accountIndex": 0
    },
    {
        "accountId": "482694560475091200",
        "accountName": "createSubAccountByCurl",
        "accountType": 1, // Sub-account type, 1: Spot account, 3: Contract account
        "accountIndex": 1
    }
]
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

## Account Transfer

  * `POST /api/v1/subAccount/transfer`

Supported transfer operations:

  * Parent account operation Transfer from parent `spot account` to any sub-account `spot account`, `U-position contract account`.
  * Transfer between parent account `Spot account` and `U-position contract account`.
  * Parent account operation Transfer of any sub-account `Spot account`, `U-contract account` to parent account `Spot account`
  * Parent account operation Transfer between `spot account` and `U-contract account` of a particular sub-account
  * Sub-user operation Transfer from the current sub-account `spot account` to the parent account `spot account` and `U-contract account
  * Sub-user operation Transfer between the current sub-user's `Spot account` and `U-contract account

Execute the transfer between the spot account and the contract account

### Weight：1

> Response：

json
```
{
    "code": 200, // 200 = success
    "msg": "success" // response message
}
```

1
2
3
4

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
transferId| LONG| NO| Transfer ID, same transferId can prevent duplicate transfers
fromUid| LONG| YES| from uid
toUid| LONG| YES| to uid
fromAccountType| String| YES| from account type
toAccountType| String| YES| to account type
coin| String| YES| token id (e.g. USDT, BTC)
quantity| DECIMAL| YES| transfer quantity
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

accountType：

  * `MAIN`: spot account
  * `FUTURES`: U-contract account
  * `FUTURES_USDC`: USDC-M Futures account

## Get Account Transaction History List (USER_DATA)

  * `GET /api/v1/account/balanceFlow`

For a normalized v2 request/response, see Account & Trades (v2).

### Weight：5

> Response：

json
```
[
  {
    "id": "539870570957903104",
    "accountId": "122216245228131",
    "coin": "BTC",
    "coinId": "BTC",
    "coinName": "BTC",
    "symbol": "BTCUSDT",
    "symbolId": "BTCUSDT",
    "flowTypeValue": 51,
    "flowType": "USER_ACCOUNT_TRANSFER",
    "flowName": "Transfer",
    "change": "-12.5",
    "total": "379.624059937852365",
    "voucherType": 0,
    "deductionAmount": "",
    "created": "1579093587214"
  }
]
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

New response fields:

Name| Type| Description
---|---|---
voucherType| INT| Voucher type. Common deduction types: `2` cash voucher, `3` trial voucher, `7` copy-trading trial voucher, and `8` lead-trading trial voucher. `0` means no applicable voucher is associated with the flow
deductionAmount| STRING| Voucher amount deducted by this flow, preserving decimal precision as a string; empty when no deduction applies

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
accountType| INT| NO| Account corresponding to `account_type`, 1: Spot account, 3: Contract account
coin| STRING| NO| coin
flowType| INT| NO| transfer：51
fromId| LONG| NO| from id
endId| LONG| NO| end id
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
limit| INT| NO| limit
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

## Get API KEY Type (USER_DATA)

  * `GET /api/v1/account/checkApiKey`

> Response

json
```
{
  "accountType": "master"
}
```

1
2
3

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

  * accountType:
    * master
    * spot
    * contract

> **Account (v2)** flows (e.g. `GET /api/v2/account/balance-flow`) are in Account & Trades (v2) (under _Spot_ in the sidebar). U-margined **futures (v2)** : Account & Trades (v2) (under _USDT-M_).
