# Account/Trades Endpoints

## Query Sub-account (USER_DATA)

  * `GET /api/v1/subAccount/list`

### Weight：5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
userId| LONG| NO| Sub-user userId
email| String| NO| Sub-user email
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

> Response：

json
```
[
    {
        "userId": "879141111", // Sub-user userId
        "email": "aaa@rpbsho.com", // Sub-user email
        "remark": "", // Sub-user remark
        "accountList": [ // All accounts
            {
                "accountId": "1795119090857208832", // Account id
                "userId": "879145609", // userId
                "accountType": "MAIN" // Account type
            },
            {
                "accountId": "1795119090857208834",
                "userId": "879145609",
                "accountType": "FUTURES"
            }
        ]
    },
    {
        "userId": "935651111",
        "email": "qwdqwd123_na5626@08rrkf.com",
        "remark": "",
        "accountList": [
            {
                "accountId": "1974746191561298944",
                "userId": "935650120",
                "accountType": "MAIN"
            },
            {
                "accountId": "1974746191561298945",
                "userId": "935650120",
                "accountType": "FUTURES"
            }
        ]
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

**accountType Description** :

  * `MAIN`: Spot
  * `FUTURES`: U-margined Contract
  * `COPY_TRADING`: Copy Trading Account

## New Future Account Transfer

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
fromUid| LONG| YES| from uid
toUid| LONG| YES| to uid
fromAccountType| String| YES| from account type
toAccountType| String| YES| to account type
coin| String| YES| token id (e.g. USDT)
quantity| DECIMAL| YES| transfer quantity
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

accountType：

  * `MAIN`: spot account
  * `FUTURES`: U-contract account
  * `FUTURES_USDC`: USDC-M Futures account
  * `COPY_TRADING`: copy trading leader account

## Get Future Account Transaction History List (USER_DATA)

  * `GET /api/v1/account/balanceFlow`

Obtain the history of fund transfers between the spot account and the contract account.

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
    "flowTypeValue": 51,
    "flowType": "USER_ACCOUNT_TRANSFER",
    "flowName": "Transfer",
    "change": "-12.5",
    "total": "379.624059937852365",
    "voucherType": 0,
    "deductionAmount": "",
    "created": "1579093587214"
  },
  {
    "id": "536072393645448960",
    "accountId": "122216245228131",
    "coin": "USDT",
    "coinId": "USDT",
    "coinName": "USDT",
    "flowTypeValue": 7,
    "flowType": "AIRDROP",
    "flowName": "Airdrop",
    "change": "-2000",
    "total": "918662.0917630848",
    "voucherType": 0,
    "deductionAmount": "",
    "created": "1578640809195"
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
26
27
28
29
30
31
32

New response fields:

Name| Type| Description
---|---|---
voucherType| INT| Voucher type. Common deduction types: `2` cash voucher, `3` trial voucher, `7` copy-trading trial voucher, and `8` lead-trading trial voucher. `0` means no applicable voucher is associated with the flow
deductionAmount| STRING| Voucher amount deducted by this flow, preserving decimal precision as a string; empty when no deduction applies

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
accountType| INT| NO| `account_type` corresponding to the account, 1: Spot account, 3: Contract account
coin| STRING| NO| coin
flowType| INT| NO| transfer：51
fromId| LONG| NO| from id
endId| LONG| NO| end id
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
limit| INT| NO| Default`20` Min `1` Max `1000`
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

## Get account balance flow (API v2) (USER_DATA)

  * `GET /api/v2/account/balance-flow`

Same business data as v1, with normalized request/response. Successful responses use `{"code":200,"msg":"success","data":[...]}`.

### Weight：5

> Response (each item in `data`):

json
```
{
  "id": "539870570957903104",
  "accountType": "MAIN",
  "coin": "BTC",
  "symbol": "BTCUSDT",
  "flowType": "USER_ACCOUNT_TRANSFER",
  "flowName": "Transfer",
  "change": "-12.5",
  "total": "379.624059937852365",
  "voucherType": 0,
  "deductionAmount": "",
  "created": 1579093587214
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

New response fields:

Name| Type| Description
---|---|---
voucherType| INT| Voucher type. Common deduction types: `2` cash voucher, `3` trial voucher, `7` copy-trading trial voucher, and `8` lead-trading trial voucher. `0` means no applicable voucher is associated with the flow
deductionAmount| STRING| Voucher amount deducted by this flow, preserving decimal precision as a string; empty when no deduction applies

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
accountType| STRING| NO| `MAIN` or `FUTURES` (default `MAIN`)
coin| STRING| NO| token id
flowType| STRING| NO| flow type **enum name** (same as `flowType` in the response, e.g. `USER_ACCOUNT_TRANSFER`)
fromId| LONG| NO| from id
endId| LONG| NO| end id
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
limit| INT| NO| default `20`, min `1`, max `1000`
category| ENUM| NO| not used in v2; reserved
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

The v1 `GET /api/v1/account/balanceFlow` route remains available and returns the same voucher fields.

## Change Margin Type (TRADE)

  * `POST /api/v1/futures/marginType`

Change the user's margin mode on the specified symbol contract: isolated margin or cross margin.

### Weight：1

> Response：

json
```
{
    "code":200,
    "symbolId":"BTC-SWAP-USDT", //symbol
    "marginType":"CROSS" // CROSS ISOLATED
}
```

1
2
3
4
5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
marginType| ENUM| YES| `CROSS` `ISOLATED`
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

## Change Initial Leverage (TRADE)

  * `POST /api/v1/futures/leverage`

Adjust the user's opening leverage in the specified symbol contract.

### Weight：1

> Response:

json
```
{
  "code": 200,
  "symbolId": "BTC-SWAP-USDT",
  "leverage": "20"
}
```

1
2
3
4
5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
leverage| INT| YES| leverage
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

## Get the leverage multiple and position mode (USER_DATA)

  * `GET /api/v1/futures/accountLeverage`

Obtain the leverage multiples and position types of all contract trading pairs of the user. This API requires your request to be signed.

### Weight：5

> Response：

json
```
[
    {
        "symbolId":"BTC-SWAP-USDT", //symbol
        "leverage":"20",  // leverage
        "marginType":"CROSS" // CROSS;ISOLATED
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

> **U-margined futures (v2)** is documented in Account & Trades (v2) (separate page with per-endpoint navigation).

## New Order (TRADE)

`POST /api/v1/futures/order`

### Weight：1

> Response：

json
```
{
    "time": "1668418485058", // time
    "updateTime": "1668418485058",
    "orderId": "1289182123551455488",
    "clientOrderId": "test1115",
    "symbol": "BTC-SWAP-USDT", // symbol
    "price": "19000", // price
    "leverage": "2", // leverage
    "origQty": "10", // quantity
    "executedQty": "0", //Executed Quantity
    "avgPrice": "0", //average  price
    "marginLocked": "9.5", //The margin locked for this order.
    "type": "LIMIT", // type（LIMIT and STOP）
    "side": "BUY_OPEN", // side（BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE）
    "timeInForce": "GTC", // Time in Force
    "status": "NEW", //NEW、PARTIALLY_FILLED、FILLED、CANCELED、REJECTED
    "priceType": "INPUT", //INPUT、MARKET
    "contractMultiplier": "0.001" //Contract multiplier
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
side| ENUM| YES| `BUY_OPEN`、`SELL_OPEN`、`BUY_CLOSE`、`SELL_CLOSE`
type| ENUM| YES| `LIMIT` or `STOP`
quantity| LONG| YES| Numbers of orders (volume)
valueQuantity| LONG| NO| Order value quantity (USDT). For example, purchasing 2 BTC at a price of 1000 USDT: Order value = 2 × 1000 = 2000 USDT When both valueQuantity and quantity are specified, quantity takes precedence.
price| DECIMAL| NO| `LIMIT`&`INPUT` **Mandatory need**
priceType| ENUM| NO| `INPUT`、`MARKET`
stopPrice| DECIMAL| NO| `type` = `STOP` order **Mandatory need**
timeInForce| ENUM| NO| For `LIMIT` orders only. Values: `GTC`, `FOK`, `IOC`, `POST_ONLY`.
newClientOrderId| STRING| YES| A unique id among open orders. The ID of the order, defined by the user.
takeProfit| STRING| NO| Take profit price
tpTriggerBy| ENUM| NO| The price type to trigger take profit:`MARK_PRICE`, `CONTRACT_PRICE`. Default `CONTRACT_PRICE`
tpLimitPrice| STRING| NO| The limit order price when take profit price is triggered. Only works when tpOrderType=LIMIT
tpOrderType| ENUM| NO| The order type when take profit is triggered.`MARKET`(default), `LIMIT`.
stopLoss| STRING| NO| Stop loss price,
slTriggerBy| ENUM| NO| The price type to trigger take profit:`MARK_PRICE`, `CONTRACT_PRICE`. Default `CONTRACT_PRICE`
slLimitPrice| STRING| NO| The limit order price when take profit price is triggered. Only works when slOrderType=LIMI
slOrderType| ENUM| NO| The order type when take profit is triggered.`MARKET`(default), `LIMIT`.
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

### Order Side :

  * BUY_OPEN Open a long buy order to open a position to buy
  * BUY_CLOSE Close Buy Order Close Buy
  * SELL_OPEN Open a short sell order to open a position to sell
  * SELL_CLOSE Flat long sell order, close position and sell

### Price Type:

  * INPUT The system will match the order with the price you entered.
  * MARKET Orders will be matched at the latest transaction price * (1 ± 5%).

## Place Multiple Orders (TRADE)

  * `POST /api/v1/futures/batchOrders`

A maximum of 10 orders at a time, must be the same `symbol`.

### Weight: 2

> USDT-M Futures. Example:

bash
```
curl  -H "Content-Type:application/json"
-H "X-BB-APIKEY: 3jIF0QWOFAA64MnaFJz1pMvVFNaLyMThHUvhii1eyYBw4saPs9ocLasp45pqeGRs"
-X POST -d '[
   {
      "newClientOrderId": "pl2023010712345678900",
      "symbol": "BTC-SWAP-USDT",
      "side": "BUY_OPEN",
      "type": "LIMIT",
      "price": 16500,
      "quantity": 10,
      "priceType": "INPUT"
   },
   {
       "newClientOrderId": "pl2023010712345678901",
       "symbol": "BTC-SWAP-USDT",
       "side": "BUY_OPEN",
       "type": "LIMIT",
       "price": 16000,
       "quantity": 10,
       "priceType": "INPUT"
   } ]' '#HOST/api/v1/futures/batchOrders?timestamp=1673062952473&signature=f746cebecf9cf53601d2ab69b2f88f426a1c93a5f7bcc8bbdc5a2ce95c3fa976'
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

> USDC-M Futures. Example:

bash
```
curl  -H "Content-Type:application/json"
-H "X-BB-APIKEY: 3jIF0QWOFAA64MnaFJz1pMvVFNaLyMThHUvhii1eyYBw4saPs9ocLasp45pqeGRs"
-X POST -d '[
   {
      "newClientOrderId": "pl2023010712345678900",
      "symbol": "BTC-SWAP-USDC",
      "side": "BUY_OPEN",
      "type": "LIMIT",
      "price": 16500,
      "quantity": 10,
      "priceType": "INPUT"
   },
   {
       "newClientOrderId": "pl2023010712345678901",
       "symbol": "BTC-SWAP-USDC",
       "side": "BUY_OPEN",
       "type": "LIMIT",
       "price": 16000,
       "quantity": 10,
       "priceType": "INPUT"
   } ]' '#HOST/api/v1/futures/batchOrders?category=USDC&timestamp=1673062952473&signature=f746cebecf9cf53601d2ab69b2f88f426a1c93a5f7bcc8bbdc5a2ce95c3fa976'
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

> Response：

json
```
{
    "code": 200, //success
    "result": [
         {
            "code": 200, //success
            "order": {
                    "time": "1673062993867", //time
                    "updateTime": "1673062993867",
                    "orderId": "1328143087352970240",
                    "clientOrderId": "pl2023010712345678900",
                    "symbol": "BTC-SWAP-USDT",
                    "price": "16500",//price
                    "leverage": "0",//leverage
                    "origQty": "10", //quantity
                    "executedQty": "0", //Executed Quantity
                    "avgPrice": "0", //average  price
                    "marginLocked": "0", //The margin locked for this order.
                    "type": "LIMIT", // type（LIMIT and STOP）
                    "side": "BUY_OPEN", // side（BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE）
                    "timeInForce": "GTC", // Time in Force
                    "status": "NEW", //status（NEW、PARTIALLY_FILLED、FILLED、CANCELED、REJECTED）
                    "priceType": "INPUT"  //price type（INPUT、MARKET）
                    }
        },
        {
                "code": -1131, //fail
                "msg": "Balance insufficient " //reason
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
| LIST| YES| `RequestBody` parameters
timestamp| LONG| YES|
recvWindow| LONG| NO|

The batchOrders in RequestBody should fill in the order parameters in list of JSON format

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES|
side| ENUM| YES| side`BUY_OPEN`、`SELL_OPEN`、`BUY_CLOSE`、`SELL_CLOSE`
type| ENUM| YES| type`LIMIT` or `STOP`
quantity| LONG| YES| Numbers of orders (volume)
valueQuantity| LONG| NO| Order value quantity (USDT). For example, purchasing 2 BTC at a price of 1000 USDT: Order value = 2 × 1000 = 2000 USDT When both valueQuantity and quantity are specified, quantity takes precedence.
price| DECIMAL| NO| price (`LIMIT`&`INPUT`)订单 **Mandatory need**
priceType| ENUM| NO| price type`INPUT`、`MARKET`
timeInForce| ENUM| NO| For `LIMIT` orders only. Values: `GTC`, `FOK`, `IOC`, `POST_ONLY`.
newClientOrderId| STRING| YES| A unique id among open orders. The ID of the order, defined by the user.

Notes：

  * For **market order** , you need to set `type` to `LIMIT` and set `priceType` to `MARKET`. You can obtain the contract price and quantity precision configuration information at the `brokerInfo` endpoint.
  * If your balance does not meet the margin requirements (initial margin + opening fee + closing fee), there will be an `insufficient balance` (insufficient balance) error return.

## Query Order (USER_DATA)

  * `GET /api/v1/futures/order`

### Weight：1

> Response：

**Regular Order (LIMIT) Query Response:**

json
```
{
    "time": "1668418485058", // create time
    "updateTime": "1668418485058",
    "orderId": "1289182123551455488",
    "clientOrderId": "test1115", //User defined order ID
    "symbol": "BTC-SWAP-USDT", //symbol
    "price": "19000", //price
    "leverage": "2", //leverage
    "origQty": "10", //quantity
    "executedQty": "0", //Executed Quantity
    "executeQty": "0", //Executed quantity (same as executedQty)
    "avgPrice": "0", //average  price
    "marginLocked": "9.5", //The margin locked for this order.
    "type": "LIMIT", // Order type
    "side": "BUY_OPEN", // BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE
    "timeInForce": "GTC", // Time in Force
    "status": "NEW", //NEW、PARTIALLY_FILLED、FILLED、CANCELED、REJECTED
    "priceType": "INPUT", //INPUT、MARKET
    "contractMultiplier": "0.001" //Contract multiplier
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

**Stop Order (STOP) Query Response:**

json
```
{
    "time": "1767952799216", // Order creation timestamp
    "orderId": "2124136467689134848", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "1767952799112", // User defined order ID
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Price after trigger (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "2", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP", // Order type
    "side": "BUY_OPEN", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_NEW", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type after trigger (INPUT、MARKET)
    "stopPrice": "95000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger)
    "orderType": "STOP_COMMON" // Stop order type
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

**Take-Profit/Stop-Loss Order (STOP_PROFIT_LOSS) Query Response:**

json
```
{
    "time": "1767953932589", // Order creation timestamp
    "orderId": "2124145975077395200", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "STOP_LONG_PROFIT_1767953932496", // User defined order ID (auto-generated by system)
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Limit order price used when take-profit/stop-loss is triggered (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "1", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP_PROFIT_LOSS", // Order type
    "side": "SELL_CLOSE", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_NEW", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type (INPUT、MARKET)
    "stopPrice": "98000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger, 1=dynamic trigger)
    "activePrice": "0", // Activation price (used for trailing stop loss, 0 for fixed stop loss)
    "fallType": 0, // Callback type (0=none, 1=RATE ratio, 2=PRICE price difference)
    "fallQuantity": "0", // Callback quantity (used for trailing stop loss, 0 for fixed stop loss)
    "activeStatus": 0, // Activation status (0=not activated, 1=activated)
    "orderType": "STOP_LONG_PROFIT" // Take-profit/stop-loss order type (STOP_LONG_PROFIT、STOP_LONG_LOSS、STOP_SHORT_PROFIT、STOP_SHORT_LOSS, etc.)
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| order id
origClientOrderId| STRING| NO| client order id
type| ENUM| NO| Order type (`LIMIT`、`STOP`)
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recvWindow

Notes:

  * Either `orderId` or `origClientOrderId` must be sent
  * The `type` parameter only supports `LIMIT` and `STOP`. When `type` is `STOP`, the query result may be a stop order (STOP) or a take-profit/stop-loss order (STOP_PROFIT_LOSS), and the specific return type is determined by the order type specified by the order ID or client order ID

## Modify Order (TRADE)

  * `POST /api/v1/futures/order/update`

Modify orders, supporting modification of regular orders (LIMIT), stop orders (STOP), and take-profit/stop-loss orders (STOP_PROFIT_LOSS). This endpoint requires request signature.

### Weight：2

> Response：

**Regular Order (LIMIT) Modification Response:**

json
```
{
    "time": "1767952682388", // Order creation timestamp
    "updateTime": "1767952682388", // Order last update timestamp
    "orderId": "2124135487564299264", // Order ID
    "clientOrderId": "1767952681690", // User defined order ID
    "symbol": "ETH-SWAP-USDT", // Trading pair
    "price": "4000", // Order price
    "leverage": "20", // Order leverage
    "origQty": "1", // Order quantity
    "executedQty": "0", // Executed quantity
    "executeQty": "0", // Execute quantity (same as executedQty)
    "avgPrice": "0", // Average trading price
    "marginLocked": "2", // Margin locked for this order
    "type": "LIMIT", // Order type
    "side": "BUY_OPEN", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "timeInForce": "GTC", // Time in Force
    "status": "PENDING_NEW", // Order status (PENDING_NEW、NEW、PARTIALLY_FILLED、FILLED、CANCELED、REJECTED)
    "priceType": "INPUT", // Price type (INPUT、MARKET)
    "contractMultiplier": "0.01000000" // Contract multiplier
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

**Stop Order (STOP) Modification Response:**

json
```
{
    "time": "1767952799216", // Order creation timestamp
    "orderId": "2124136467689134848", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "1767952799112", // User defined order ID
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Price after trigger (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "2", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP", // Order type
    "side": "BUY_OPEN", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_NEW", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type after trigger (INPUT、MARKET)
    "stopPrice": "95000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger)
    "orderType": "STOP_COMMON" // Stop order type
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

**Take-Profit/Stop-Loss Order (STOP_PROFIT_LOSS) Modification Response:**

json
```
{
    "time": "1767953932589", // Order creation timestamp
    "orderId": "2124145975077395200", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "STOP_LONG_PROFIT_1767953932496", // User defined order ID (auto-generated by system)
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Limit order price used when take-profit/stop-loss is triggered (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "1", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP_PROFIT_LOSS", // Order type
    "side": "SELL_CLOSE", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_NEW", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type (INPUT、MARKET)
    "stopPrice": "98000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger, 1=dynamic trigger)
    "activePrice": "0", // Activation price (used for trailing stop loss, 0 for fixed stop loss)
    "fallType": 0, // Callback type (0=none, 1=RATE ratio, 2=PRICE price difference)
    "fallQuantity": "0", // Callback quantity (used for trailing stop loss, 0 for fixed stop loss)
    "activeStatus": 0, // Activation status (0=not activated, 1=activated)
    "orderType": "STOP_LONG_PROFIT" // Take-profit/stop-loss order type (STOP_LONG_PROFIT、STOP_LONG_LOSS、STOP_SHORT_PROFIT、STOP_SHORT_LOSS, etc.)
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| Order ID (choose one with`origClientOrderId`)
origClientOrderId| STRING| NO| Original client order ID (choose one with`orderId`)
newClientOrderId| STRING| NO| New order's client order ID (optional, system will auto-generate if not provided, ignored for take-profit/stop-loss orders)
type| STRING| YES| Order type:`LIMIT`、`STOP`、`STOP_PROFIT_LOSS`
quantity| DECIMAL| NO| Order quantity (supported for all order types)
valueQuantity| DECIMAL| NO| Order value quantity (supported for all order types)
price| DECIMAL| NO| Order price (required for limit orders)
priceType| STRING| NO| Price type:`INPUT` (limit)、`MARKET` (market)
stopPrice| DECIMAL| NO| Trigger price (required for stop orders and take-profit/stop-loss orders)
triggerBy| STRING| NO| Trigger price type:`MARK_PRICE` (mark price)、`CONTRACT_PRICE` (contract latest price, default)
stopType| STRING| NO| Stop loss type (for take-profit/stop-loss orders):`FIXED_STOP` (fixed stop loss, default)、`TRAILING_STOP` (trailing stop loss)
activePrice| DECIMAL| NO| Activation price (used for trailing stop loss, must be greater than 0)
fallbackType| STRING| NO| Callback type (required for trailing stop loss):`RATE` (ratio)、`PRICE` (price difference)
fallbackQuantity| DECIMAL| NO| Callback quantity (required for trailing stop loss, must be greater than 0)
category| STRING| NO| USDC contract=`USDC`, default=USDT contract
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

### Order Modification Validation Rules

  1. **Parameter Completeness Check:**

     * All order types: If all modifiable parameters are not provided, a parameter error will be returned
     * Regular orders: Error when `quantity`, `valueQuantity`, `priceType`, and `price` are all not provided
     * Stop orders: Error when `quantity`, `valueQuantity`, `stopPrice`, `triggerBy`, `priceType`, and `price` are all not provided
     * Take-profit/stop-loss orders: Error when `quantity`, `valueQuantity`, `stopPrice`, `triggerBy`, `priceType`, `price`, `stopType`, `activePrice`, `fallbackType`, and `fallbackQuantity` are all not provided
  2. **Parameter Inheritance Rules:**

     * If a parameter is not provided, the system will use the corresponding value from the original order
     * If a parameter is provided, the provided value is usually used
     * However, some fields will use the original order value when 0 is provided (e.g., when `stopPrice` is 0, the original order's `stopPrice` will be used). Please refer to the detailed description of each parameter
  3. **Equality Check:**

     * If all fields are the same as the original order, a parameter error will be returned
  4. **Modification Restrictions:**

     * Order modification does not support changing order direction (`side`) and trading pair (`symbol`), these will be automatically obtained from the original order
     * Regular orders (LIMIT) must be in `NEW` or `PARTIALLY_FILLED` status (non-terminal state) to be modified
     * Stop orders (STOP) and take-profit/stop-loss orders (STOP_PROFIT_LOSS) must be in `ORDER_NEW` status to be modified

### Order Type Description

**Regular Orders (LIMIT) Support Modification:**

  * Price type (`priceType`): `INPUT` (limit)、`MARKET` (market)
  * Price (`price`): Required if limit order
  * Quantity (`quantity`/`valueQuantity`): At least one must be provided

**Stop Orders (STOP) Support Modification:**

  * Trigger price (`stopPrice`): Required
  * Trigger price type (`triggerBy`): `MARK_PRICE` (mark price)、`CONTRACT_PRICE` (contract latest price, default)
  * Price type after trigger (`priceType`): `INPUT` (limit)、`MARKET` (market)
  * Price after trigger (`price`): Required if limit order
  * Quantity (`quantity`/`valueQuantity`): At least one must be provided

**Take-Profit/Stop-Loss Orders (STOP_PROFIT_LOSS) Support Modification:**

  * Only one order can be modified at a time (either take-profit or stop-loss)
  * Use `orderId` or `origClientOrderId` to specify the order to modify (system will automatically determine if it's take-profit or stop-loss)
  * Quantity (`quantity`/`valueQuantity`): Supports modification by quantity or value quantity, see "Parameter Usage Instructions" below for details
  * Trigger price (`stopPrice`): Required, trigger price for take-profit or stop-loss
  * Trigger price type (`triggerBy`): `MARK_PRICE` (mark price)、`CONTRACT_PRICE` (contract latest price, default)
  * Limit order price (`price`): Optional, limit order price used when take-profit/stop-loss is triggered (pass 0 or omit to use market order)
  * Stop loss type (`stopType`): `FIXED_STOP` (fixed stop loss, default)、`TRAILING_STOP` (trailing stop loss)
  * Trailing stop loss parameters (when `stopType=TRAILING_STOP`):
    * `activePrice`: Optional, activation price (must be greater than 0)
    * `fallbackType`: Required, callback type, `RATE` (ratio)、`PRICE` (price difference)
    * `fallbackQuantity`: Required, callback quantity (must be greater than 0)

### Parameter Usage Instructions

#### Basic Parameters

Parameter| Description
---|---
`orderId` / `origClientOrderId`| Choose one (required) to specify the order to modify. If both are provided,`orderId` takes precedence
`newClientOrderId`| Optional, new order's client order ID. System will auto-generate if not provided (ignored for take-profit/stop-loss orders)
`type`| Required, must match the original order type:`LIMIT`, `STOP`, `STOP_PROFIT_LOSS`

#### Quantity Parameters (quantity / valueQuantity)

**Regular Orders (LIMIT) and Stop Orders (STOP):**

  * If `quantity` is not provided or is 0, and `valueQuantity` is not provided or is 0, the original order quantity will be used (if a regular order is partially filled, the modified quantity will be the remaining unfilled quantity of the original order)
  * If `quantity` is provided with a value greater than 0, `valueQuantity` will be ignored (treated as 0)
  * If `quantity` is not provided or is 0, and `valueQuantity` is provided with a value greater than 0, `valueQuantity` will be used for modification

**Take-Profit/Stop-Loss Orders (STOP_PROFIT_LOSS):**

  * **Fixed Take-Profit/Stop-Loss (FIXED_STOP):**

    * If `quantity` is not provided, and `valueQuantity` is not provided or is 0, the original order quantity will be used
    * If `quantity` is provided with a value greater than or equal to 0, `valueQuantity` will be ignored (treated as 0)
      * `quantity` can be 0 (indicates position take-profit/stop-loss, i.e., all positions will be take-profit or stop-loss)
      * `quantity` can be greater than 0 (indicates partial take-profit/stop-loss, i.e., the specified quantity will be take-profit or stop-loss)
    * If `quantity` is not provided, and `valueQuantity` is provided with a value greater than 0, `valueQuantity` will be used for modification
  * **Trailing Stop Loss (TRAILING_STOP):**

    * If `quantity` is not provided or is 0, and `valueQuantity` is not provided or is 0, the original order quantity will be used
    * If `quantity` is provided with a value greater than 0, `valueQuantity` will be ignored (treated as 0)
    * If `quantity` is not provided or is 0, and `valueQuantity` is provided with a value greater than 0, `valueQuantity` will be used for modification

#### Price Parameters (price / priceType)

**Regular Orders (LIMIT) and Stop Orders (STOP):**

  * If `priceType` is not provided, the price type will be obtained from the original order
  * If `priceType=INPUT` and `price` is not provided or is 0, the original order price will be used
  * If `priceType=INPUT` and `price` is provided with a value greater than 0, the provided `price` will be used
  * If `priceType=MARKET`, `price` does not need to be provided (market orders are not allowed to be modified)

**Take-Profit/Stop-Loss Orders (STOP_PROFIT_LOSS):**

  * **Fixed Take-Profit/Stop-Loss (Fixed trigger to fixed trigger):**

    * If `priceType` is not provided, the price type will be obtained from the original order
    * If `priceType=INPUT` and `price` is not provided or is 0, the original order price will be used (if the original order is a market order, price must be specified)
  * **Fixed Take-Profit/Stop-Loss (Dynamic trigger to fixed trigger):**

    * `priceType` is required
    * If `priceType=INPUT`, `price` is required and must be greater than 0

#### Trigger Price Parameters (stopPrice / triggerBy)

**Stop Orders (STOP):**

  * If `stopPrice` is not provided or is 0, the original order's `stopPrice` will be used
  * If `triggerBy` is not provided, the trigger price type will be obtained from the original order

**Take-Profit/Stop-Loss Orders (STOP_PROFIT_LOSS):**

  * **Fixed Take-Profit/Stop-Loss (Fixed trigger to fixed trigger):**

    * If `stopPrice` is not provided or is 0, the original order's `stopPrice` will be used
    * If `triggerBy` is not provided, the trigger price type will be obtained from the original order
  * **Fixed Take-Profit/Stop-Loss (Dynamic trigger to fixed trigger):**

    * `stopPrice` is required and must be greater than 0
    * `triggerBy` is required

#### Trailing Stop Loss Parameters (activePrice / fallbackType / fallbackQuantity)

**Trailing Stop Loss (TRAILING_STOP):**

  * **Fixed trigger to dynamic trigger:**

    * `fallbackType` is required
    * `triggerBy` is required
    * `fallbackQuantity` is required and must be greater than 0
    * `quantity` or `valueQuantity` must be provided with a value greater than 0
    * `activePrice` is optional, if provided must be greater than 0
  * **Dynamic trigger to dynamic trigger:**

    * If `fallbackType` is not provided, the callback type will be obtained from the original order
    * If `triggerBy` is not provided, the trigger price type will be obtained from the original order
    * If `fallbackQuantity` is not provided or is 0, the original order's `fallbackQuantity` will be used
    * If `activePrice` is not provided, the original order's `activePrice` will be used
    * If `activePrice` is 0, `finalActivePrice` will be an empty string
    * If `activePrice` is provided with a value greater than 0, the provided `activePrice` will be used

## Cancel Order (TRADE)

  * `DELETE /api/v1/futures/order`

### Weight：1

> Response：

**Regular Order (LIMIT) Cancel Response:**

json
```
{
    "time": "1668418485058", // create time
    "updateTime": "1668418485058",
    "orderId": "1289182123551455488",
    "clientOrderId": "test1115", //User defined order ID
    "symbol": "BTC-SWAP-USDT",
    "price": "19000",
    "leverage": "2",
    "origQty": "10", //quantity
    "executedQty": "0", //Executed Quantity
    "executeQty": "0", //Executed quantity (same as executedQty)
    "avgPrice": "0", //avg price
    "marginLocked": "9.5", //The margin locked for this order.
    "type": "LIMIT",
    "side": "BUY_OPEN",
    "timeInForce": "GTC", // Time in Force
    "status": "CANCELED",
    "priceType": "INPUT",
    "contractMultiplier": "0.001" //Contract multiplier
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

**Stop Order (STOP) Cancel Response:**

json
```
{
    "time": "1767952799216", // Order creation timestamp
    "orderId": "2124136467689134848", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "1767952799112", // User defined order ID
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Price after trigger (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "2", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP", // Order type
    "side": "BUY_OPEN", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_CANCELED", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type after trigger (INPUT、MARKET)
    "stopPrice": "95000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger)
    "orderType": "STOP_COMMON" // Stop order type
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

**Take-Profit/Stop-Loss Order (STOP_PROFIT_LOSS) Cancel Response:**

json
```
{
    "time": "1767953932589", // Order creation timestamp
    "orderId": "2124145975077395200", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "STOP_LONG_PROFIT_1767953932496", // User defined order ID (auto-generated by system)
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Limit order price used when take-profit/stop-loss is triggered (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "1", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP_PROFIT_LOSS", // Order type
    "side": "SELL_CLOSE", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_CANCELED", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type (INPUT、MARKET)
    "stopPrice": "98000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger, 1=dynamic trigger)
    "activePrice": "0", // Activation price (used for trailing stop loss, 0 for fixed stop loss)
    "fallType": 0, // Callback type (0=none, 1=RATE ratio, 2=PRICE price difference)
    "fallQuantity": "0", // Callback quantity (used for trailing stop loss, 0 for fixed stop loss)
    "activeStatus": 0, // Activation status (0=not activated, 1=activated)
    "orderType": "STOP_LONG_PROFIT" // Take-profit/stop-loss order type (STOP_LONG_PROFIT、STOP_LONG_LOSS、STOP_SHORT_PROFIT、STOP_SHORT_LOSS, etc.)
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
orderId| LONG| NO| order id
origClientOrderId| STRING| NO| User defined order ID
type| ENUM| NO| `LIMIT` or `STOP`
symbol| STRING| NO| symbol
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

Notes：

  * Either `orderId` or `origClientOrderId` must be sent
  * The `type` parameter only supports `LIMIT` and `STOP`. When `type` is `STOP`, the cancel result may be a stop order (STOP) or a take-profit/stop-loss order (STOP_PROFIT_LOSS), and the specific return type is determined by the order type specified by the order ID or client order ID

## Cancel Orders (TRADE)

  * `DELETE /api/v1/futures/batchOrders`

### Weight：3

> Response:

json
```
{
  "code": 200,
  "message": "success",
  "timestamp": 1541161088303
}
```

1
2
3
4
5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
side| ENUM| YES| `BUY` or `SELL`
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

## Cancel Multiple Orders (TRADE)

  * `DELETE /api/v1/futures/cancelOrderByIds`

Cancel orders in bulk. A maximum of `100` entries at a time.

### Weight：3

> Response

json
```
// success
{
  "code":200,
  "result":[]
}

// Some or all of the cancellations failed
{
   "code":200,
   "result":[
       {
          "orderId":"1327047813809448704",
          "code":-2013
       },
       {
           "orderId":"1327047814212101888",
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
ids| STRING| YES| Order id (multiple separated by`,`)
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

Note: `code` returns 200 to indicate that the order cancellation request has been executed. Whether it is successful or not depends on the results in `result`. If `result` is empty, it means all successes. If it is not empty, `orderId` means that the order id failed to be canceled.`code` represents the reason for the undo failure.

## Query Current Open Order (USER_DATA)

  * `GET /api/v1/futures/openOrders`

### Weight：1

> Response：

json
```
[
  {
    "time": "1570760254539", //create time
    "updateTime": "1570760254539",
    "orderId": "469965509788581888",
    "clientOrderId": "1570760253946",  //User defined order ID
    "symbol": "BTC-SWAP-USDT",
    "price": "8502.34",
    "leverage": "20",
    "origQty": "222", //Quantity
    "executedQty": "0", // Executed Quantity
    "executeQty": "0", //Executed quantity (same as executedQty)
    "avgPrice": "0", // avg price
    "marginLocked": "0.00130552", // The margin locked for this order.
    "type": "LIMIT",
    "side": "BUY_OPEN",
    "timeInForce": "GTC", // Time in Force
    "status": "NEW",
    "priceType": "INPUT",
    "contractMultiplier": "0.001" //Contract multiplier
  },
  {
    "time": "1767952799216", // Order creation timestamp
    "orderId": "2124136467689134848", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "1767952799112", // User defined order ID
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Price after trigger (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "2", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP", // Order type
    "side": "BUY_OPEN", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_NEW", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type after trigger (INPUT、MARKET)
    "stopPrice": "95000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger)
    "orderType": "STOP_COMMON" // Stop order type
  },
  {
    "time": "1767953932589", // Order creation timestamp
    "orderId": "2124145975077395200", // Order ID
    "accountId": "2017364659728852481", // Account ID
    "clientOrderId": "STOP_LONG_PROFIT_1767953932496", // User defined order ID (auto-generated by system)
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "price": "0", // Limit order price used when take-profit/stop-loss is triggered (0 for market orders)
    "leverage": "20", // Order leverage
    "origQty": "1", // Order quantity
    "executedOrderId": "0", // Executed order ID (0 if not triggered)
    "type": "STOP_PROFIT_LOSS", // Order type
    "side": "SELL_CLOSE", // Order direction (BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE)
    "status": "ORDER_NEW", // Order status (ORDER_NEW、ORDER_FILLED、ORDER_CANCELED, etc.)
    "priceType": "MARKET", // Price type (INPUT、MARKET)
    "stopPrice": "98000", // Trigger price
    "triggerBy": "CONTRACT_PRICE", // Trigger price type (MARK_PRICE、CONTRACT_PRICE)
    "triggerType": 0, // Trigger type (0=fixed trigger, 1=dynamic trigger)
    "activePrice": "0", // Activation price (used for trailing stop loss, 0 for fixed stop loss)
    "fallType": 0, // Callback type (0=none, 1=RATE ratio, 2=PRICE price difference)
    "fallQuantity": "0", // Callback quantity (used for trailing stop loss, 0 for fixed stop loss)
    "activeStatus": 0, // Activation status (0=not activated, 1=activated)
    "orderType": "STOP_LONG_PROFIT" // Take-profit/stop-loss order type (STOP_LONG_PROFIT、STOP_LONG_LOSS、STOP_SHORT_PROFIT、STOP_SHORT_LOSS, etc.)
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| symbol
orderId| LONG| NO| orderId
type| ENUM| NO| Default`LINIT` `LIMIT` or `STOP`、`STOP_PROFIT_LOSS`
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
limit| INT| NO| Default`20` Min `1` Max `1000`
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

Notes：

  * If `orderId` is sent, all orders < `orderId` will be returned. If not, the latest outstanding order will be returned.

## Query Position (USER_DATA)

  * `GET /api/v1/futures/positions`

Returns the current position information, this API requires a request signature.

### Weight: 5

> Response

json
```
[
    {
        "symbol": "BTC-SWAP-USDT",
        "side": "LONG",
        "avgPrice": "24000",
        "position": "10", //Number of open positions (pieces)
        "available": "10", //Quantity that can be closed (pieces)
        "leverage": "2",
        "lastPrice": "16854.4",
        "positionValue": "24", //Position value
        "flp": "12077.8", //liquidation price
        "margin": "11.9825",
        "marginRate": "0.4992",
        "unrealizedPnL": "0", //The unrealized profit and loss of the current position
        "profitRate": "0", // Profit rate of current position
        "realizedPnL": "-0.018", // Realized profit and loss
        "maxNotionalValue": "60000", // maximum volume of positions at current leverage
        "marginType": "ISOLATED", // ISOLATED or CROSSED
        "markPrice": "16854.2"
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| symbol
side| ENUM| NO| position direction`LONG` or `SHORT`
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

Notes：

  * If `symbol` is not sent, all contract position information will be returned.
  * If `side` is not sent, position information in both directions will be returned.

## Query History Position List (USER_DATA)

  * `GET /api/v1/futures/historyPositions`

Query the list of closed historical positions. This endpoint requires request signature.

### Weight：5

> Response：

json
```
[
    {
        "symbol": "BTC-SWAP-USDT", // Contract identifier
        "side": "LONG", // Position direction: LONG (long position)、SHORT (short position)
        "position": "10", // Total position quantity
        "openValue": "240000", // Opening value
        "closeValue": "250000", // Closing value
        "closeTotalQty": "10", // Cumulative closed quantity
        "maxPosition": "10", // Historical maximum position
        "leverage": "20", // Leverage multiple
        "marginType": "ISOLATED", // Margin type: ISOLATED (isolated)、CROSS (cross)
        "realizedPnL": "1000", // Realized profit and loss
        "realizedPnlRate": "0.0042", // Realized profit and loss rate
        "realizedPnlWithoutFee": "1000.5", // Realized profit and loss without fees
        "unrealizedPnL": "0", // Unrealized profit and loss (only has value when partially closed)
        "unrealizedPnlRate": "0", // Unrealized profit and loss rate (only has value when partially closed)
        "status": "CLOSED", // Status: PARTIAL_CLOSE (partially closed)、CLOSED (closed)
        "openAvgPrice": "24000", // Average opening price
        "closeAvgPrice": "25000", // Average closing price
        "openFee": "0.1", // Opening fee
        "closeFee": "0.1", // Closing fee
        "openTime": 1579007187214, // Opening timestamp (milliseconds)
        "closeTime": 1579093587214, // Closing timestamp (milliseconds)
        "id": "1000" // Historical position ID (for pagination cursor)
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
26

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| Trading pair
marginType| STRING| NO| Margin type:`ISOLATED` (isolated)、`CROSS` (cross)
fromId| LONG| NO| Starting historical position ID (for pagination), default 0
toId| LONG| NO| Ending historical position ID (for pagination), default 0
startTime| LONG| NO| Start timestamp, default 0
endTime| LONG| NO| End timestamp, default 0
limit| INT| NO| Return count, default`20`, min `1`, max `1000`
category| STRING| NO| USDC contract=`USDC`, default=USDT contract
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

Notes：

  * `fromId` and `toId` must be greater than or equal to 0
  * `startTime` and `endTime` must be greater than or equal to 0
  * If both `startTime` and `endTime` are greater than 0, `startTime` must be less than or equal to `endTime`
  * Historical position query only returns closed records, will not return `NOT_CLOSED` status
  * When using `fromId` or `toId` for pagination query, it is recommended to use with `limit` parameter

## Set Trading Stop

  * `POST /api/v1/futures/position/trading-stop`

Set the take profit and stop loss for positions, supporting fixed stop loss and trailing stop loss. This API requires request signature.

### Weight：3

> Response (Fixed Stop Loss)

json
```
{
  "symbol": "BTC-SWAP-USDT",
  "side": "LONG",
  "takeProfit": "29037.2",
  "stopLoss": "27037",
  "tpTriggerBy": "CONTRACT_PRICE",
  "slTriggerBy": "CONTRACT_PRICE",
  "tpSize": "10",
  "slSize": "5"
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

> Response (Trailing Stop Loss)

json
```
{
  "symbol": "BTC-SWAP-USDT",
  "side": "LONG",
  "takeProfit": "",
  "stopLoss": "",
  "tpTriggerBy": "",
  "slTriggerBy": "CONTRACT_PRICE",
  "tpSize": "",
  "slSize": "10",
  "stopType": "TRAILING_STOP",
  "activePrice": "28000",
  "fallbackType": "RATE",
  "fallbackQuantity": "0.01"
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Trading pair
side| ENUM| YES| Position direction,`LONG` (long position) or `SHORT` (short position)
takeProfit| STRING| NO| Take profit price (used for fixed stop loss)
stopLoss| STRING| NO| Stop loss price (used for fixed stop loss)
tpTriggerBy| ENUM| NO| Take profit conditional order parameter. Trigger type:`MARK_PRICE` (mark price), `CONTRACT_PRICE` (contract latest price). Default `CONTRACT_PRICE`
slTriggerBy| ENUM| NO| Stop loss conditional order parameter. Trigger type:`MARK_PRICE` (mark price), `CONTRACT_PRICE` (contract latest price). Default `CONTRACT_PRICE`
tpSize| STRING| NO| Take-profit quantity, must be used in conjunction with`takeProfit`
slSize| STRING| NO| Stop loss quantity. For fixed stop loss, must be used in conjunction with`stopLoss`; for trailing stop loss, used to set closing quantity
stopType| STRING| NO| Stop loss type:`FIXED_STOP` (fixed stop loss, default), `TRAILING_STOP` (trailing stop loss)
activePrice| STRING| NO| Activation price (used for trailing stop loss, must be greater than 0)
fallbackType| STRING| NO| Callback type (required for trailing stop loss):`RATE` (ratio), `PRICE` (price difference)
fallbackQuantity| STRING| NO| Callback quantity (required for trailing stop loss, must be greater than 0)
category| ENUM| NO| USDC contract=`USDC`, default=USDT contract
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

Notes：

  * Fixed stop loss (`stopType=FIXED_STOP` or default):
    * Need to set `takeProfit` and/or `stopLoss`
    * If `tpSize` is set, `takeProfit` must also be set
    * If `slSize` is set, `stopLoss` must also be set
  * Trailing stop loss (`stopType=TRAILING_STOP`):
    * Do not need to set `takeProfit` and `stopLoss`, only need to set callback parameters
    * `fallbackType` and `fallbackQuantity` are required
    * `activePrice` is optional, but if provided, must be greater than 0
    * `slSize` is used to set closing quantity, if empty then close all positions

## Auto Add Margin Switch for Isolated Position (TRADE)

  * `POST /api/v1/futures/autoAddMargin`

Set the auto add margin switch for positions in isolated margin mode. This endpoint requires request signature.

### Weight：1

> Response：

json
```
{
    "code": 200 // Success
}
```

1
2
3

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Trading pair
side| STRING| YES| Position direction:`LONG` (long position), `SHORT` (short position)
enable| STRING| YES| Switch status:`ON` (enable), `OFF` (disable)
amount| STRING| NO| Additional margin amount (required when`enable=ON`, must be greater than 0)
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

Notes：

  * Copy trading mode does not support this endpoint
  * When `enable=ON`, the `amount` parameter is required and must be greater than 0
  * When `enable=OFF`, the `amount` parameter is not needed

## Flash Close (TRADE)

  * `POST /api/v1/futures/flashClose`

Flash close function, the system will automatically cancel all pending orders for the position, then close the position with a market order. This endpoint requires request signature.

### Weight：1

> Response：

json
```
{
    "code": 200, // Success
    "orderId": "1289182123551455488" // Closing order ID
}
```

1
2
3
4

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Trading pair
side| STRING| YES| Position direction:`LONG` (long position), `SHORT` (short position)
clientOrderId| STRING| NO| Client order ID (optional, auto-generated if not provided)
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

Notes：

  * Copy trading mode does not support this endpoint
  * The system will automatically cancel all pending orders for the position, then close the position with a market order

## Reverse Position (One-Click Reverse) (TRADE)

  * `POST /api/v1/futures/reversePosition`

One-click reverse function, the system will automatically close the current position, then open a reverse position. This endpoint requires request signature.

### Weight：5

> Response：

json
```
{
    "code": 200, // Success
    "orderId": "1289182123551455488" // Opening order ID
}
```

1
2
3
4

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| Trading pair
side| STRING| YES| Position direction:`LONG` (long position), `SHORT` (short position)
quantity| STRING| NO| Reverse opening quantity (optional, uses current position quantity if not provided)
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

Notes：

  * Copy trading mode does not support this endpoint
  * The system will automatically close the current position, then open a reverse position
  * If `quantity` is not specified, the current position quantity will be used
  * If `quantity` is specified, it cannot exceed the current position quantity

## Query History Orders (USER_DATA)

  * `GET /api/v1/futures/historyOrders`

### Weight：5

> Response：

json
```
[
  {
    "time": "1570760254539", //create tiem
    "updateTime": "1570760254539",
    "orderId": "469965509788581888",
    "clientOrderId": "1570760253946",  //User defined order ID
    "symbol": "BTC-SWAP-USDT",
    "price": "8502.34",
    "leverage": "20",
    "origQty": "222", // quantity
    "executedQty": "0", // Executed Quantity
    "avgPrice": "0", // avg price
    "marginLocked": "0.00130552", // The margin locked for this order.
    "type": "LIMIT",
    "side": "BUY_OPEN",
    "timeInForce": "GTC", // Time in Force
    "status": "CANCELED",
    "priceType": "INPUT"
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
symbol| STRING| NO| symbol
orderId| LONG| NO| order id
type| ENUM| NO| Default`LINIT` `LIMIT` or `STOP`
startTime| LONG| NO| start timestamp. Default value three days ago
endTime| LONG| NO| end timestamp
limit| INT| NO| Default`20` Min `1` Max `1000`
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

Notes：

  * If orderId is sent, all orders < orderId will be returned. If not, the latest order will be returned.

## Futures Account Balance (USER_DATA)

  * `GET /api/v1/futures/balance`

### Weight：5

> Response：

json
```
[
     {
        "coin": "USDT",
        "balance": "999999999999.982",
        "availableBalance": "1899999999978.4995",
        "positionMargin": "11.9825",
        "orderMargin": "9.5",
        "crossUnRealizedPnl": "10.01",
        "coupon": "100.5"
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

### Parameters

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

## Modify Isolated Position Margin (TRADE)

  * `POST /api/v1/futures/positionMargin`

Adjust the isolated margin funds for positions in isolated margin mode.

### Weight：1

> Response：

json
```
{
    "code":200,  // 200 = success
    "msg":"success",  // response message
    "symbol":"BTC-SWAP-USDT",
    "margin":15,  // Number of Margin
    "timestamp":1541161088303 // timestamp
}
```

1
2
3
4
5
6
7

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
side| ENUM| YES| `LONG` or `SHORT`
amount| DECIMAL| YES| Increase (positive value) or decrease (negative value) the amount of margin. Please note that this quantity refers to the underlying pricing asset of the contract (that is, the underlying of the contract settlement)
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

## Account Trade List (USER_DATA)

  * `GET /api/v1/futures/userTrades`

Get trade history for a specific trading pair.

### Weight：5

> Response:

json
```
[
    {
        "time": "1668425281370", //create time
        "id": "1289239136943831296", //Trade Id
        "orderId": "1289239134670518528",
        "symbol": "BTC-SWAP-USDT",
        "price": "24000",
        "qty": "9", //quantity
        "commissionAsset": "USDT",
        "commission": "0.0162",
        "makerRebate": "0",
        "type": "LIMIT",
        "isMaker": false, // isMaker
        "side": "BUY_OPEN", //BUY_OPEN、SELL_OPEN、BUY_CLOSE、SELL_CLOSE
        "realizedPnl": "0",
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
limit| INT| NO| Default`20` Min `1` Max `1000`
fromId| LONG| NO| Start from TradeId (used to query transaction orders)
toId| LONG| NO| To the end of TradeId (used to query transaction orders)
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

## Get Futures Account Transaction History List (USER_DATA)

  * `GET /api/v1/futures/balanceFlow`

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
        "symbol": "BTC-SWAP-USDT", // symbol name
        "symbolId": "BTC-SWAP-USDT",
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
symbol| STRING| NO| coin
flowType| INT| NO| flow type
fromId| LONG| NO| from id
endId| LONG| NO| end id
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
limit| INT| NO| limit
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

`flowType` enum

Description| flowType value
---|---
Fee| 10
Fund Fee| 32
Realized PNL| 28
Force liquidation| 700
ADL| 701

## Apply Download File (USER_DATA)

  * `POST /api/v1/account/download/apply`

Apply to download historical order or funding flow files. This endpoint requires request signature.

### Weight：1000

> Response：

json
```
{
    "id": 1000, // Download record ID
    "createTime": 1579093587214, // Creation timestamp
    "status": "INIT", // Status: Fixed as INIT (initialization), indicating download application has been created
    "downloadType": "ORDER", // Download type: ORDER (historical orders)、FUNDING (funding flow)
    "symbol": "BTC-SWAP-USDT" // Trading pair, empty string means all
}
```

1
2
3
4
5
6
7

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
downloadType| STRING| YES| Download type:`ORDER` (historical orders)、`FUNDING` (funding flow)
category| STRING| NO| Business type:`USDT` (default)、`USDC`
startTime| LONG| NO| Start timestamp (milliseconds), default last 7 days
endTime| LONG| NO| End timestamp (milliseconds), default last 7 days
symbol| STRING| NO| Trading pair, default empty string (all)
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

Notes：

  * The `status` returned by this endpoint is fixed as `INIT` (initialization), indicating download application has been created
  * To query download processing status, please use `/api/v1/account/download/detail` endpoint
  * If both `startTime` and `endTime` are not provided, default to last 7 days of data
  * If `endTime` is specified but `startTime` is not, `startTime` will be `endTime`-7 days
  * If `startTime` is specified but `endTime` is not, `endTime` will be `startTime`+7 days
  * Timestamps will be converted to UTC+0 date 0:00 timestamp for calculation
  * Only one file can be applied for download at a time
  * Download application count is shared with frontend requests (including web pages, etc.). Once the monthly limit is exceeded, download applications will be unavailable

## Query Download Record Detail (USER_DATA)

  * `GET /api/v1/account/download/detail`

Query detailed information of download records, including download links. This endpoint requires request signature.

### Weight：10

> Response：

json
```
{
    "id": 1000, // Download record ID
    "createTime": 1579093587214, // Creation timestamp
    "downloadType": "ORDER", // Download type: ORDER (historical orders)、FUNDING (funding flow)
    "startTime": 1579007187214, // Start timestamp
    "endTime": 1579093587214, // End timestamp
    "symbol": "BTC-SWAP-USDT", // Trading pair
    "status": "SUCCESS", // Status: INIT (initialization)、SUCCESS (success)、FAIL (failure)、EXPIRED (expired)
    "downloadLink": "https://example.com/download/file.xlsx" // Download link (only returned when status is SUCCESS and not expired)
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
id| LONG| YES| Download record ID
timestamp| LONG| YES| Timestamp
recvWindow| LONG| NO| recv window

**status Status Description：**

Status Value| Description
---|---
INIT| Initialization status (when download record is just created)
SUCCESS| Success status (file has been generated and uploaded successfully)
FAIL| Failure status (file generation or upload failed)
EXPIRED| Expired status (download link has expired)

Notes：

  * The `status` returned by this endpoint may be `INIT`, `SUCCESS`, `FAIL`, or `EXPIRED`, indicating the current status of download processing
  * `downloadLink` is only returned when status is `SUCCESS` and not expired
  * Within 7 days after the download record is created, you can obtain `downloadLink` through this endpoint; after 7 days, when requesting this endpoint again, the status will become `EXPIRED` and `downloadLink` will not be returned

## User Trade Fee Rate (USER_DATA)

  * `GET /api/v1/futures/commissionRate`

### Weight：5

> Response：

json
```
{
    "openMakerFee": "0.000006", //The trade fee rate for opening pending orders
    "openTakerFee": "0.0001", //The trade fee rate for open position taker
    "closeMakerFee": "0.0002", //The trade fee rate for closing pending orders
    "closeTakerFee": "0.0004" //The trade fee rate for closing a taker order
}
```

1
2
3
4
5
6

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

## Today Pnl (USER_DATA)

  * `GET /api/v1/futures/todayPnl`

### Weight：5

> Response：

json
```
{
    "dayProfit": "100", // UTC+0 time zone
    "dayProfitRate": "0.01" // UTC+0 time zone
}
```

1
2
3
4

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp
