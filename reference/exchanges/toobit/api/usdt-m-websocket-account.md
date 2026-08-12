# User Data Streams

  * The base API endpoint is : **https://api.toobit.com**
  * A User Data Stream `listenKey` is valid for 60 minutes after creation.
  * Doing a PUT on a `listenKey` will extend its validity for 60 minutes.
  * Doing a DELETE on a `listenKey` will close the stream and invalidate the listenKey .
  * Doing a POST on an account with an active `listenKey` will return the currently active `listenKey` and extend its validity for 60 minutes.
  * The base websocket endpoint is: **wss://stream.toobit.com**
  * User feeds are accessible via `/api/v1/ws/<listenKey>` (e.g. `wss://#HOST/api/v1/ws/<listenKey>`)
  * User feed payloads are not guaranteed to be up during busy times; make sure to order updates with `E`

## Start User Data Stream (USER_STREAM)

  * `POST /api/v1/listenKey`

Start a new user data stream. The stream will close after 60 minutes unless a keepalive is sent.

### Weight： 1

> Response：

json
```
{
  "listenKey": "1A9LWJjuMwKWYP4QQPw34GRm8gz3x5AephXSuqcDef1RnzoBVhEeGE963CoS1Sgj"
}
```

1
2
3

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

## Keepalive User Data Stream (USER_STREAM)

  * `PUT /api/v1/listenKey`

Keepalive a user data stream to prevent a time out. User data streams will close after 60 minutes. It's recommended to send a ping about every 60 minutes.

### Weight： 1

> Response：

json
```
{}
```

1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
listenKey| STRING| YES| listenKey
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

## Close User Data Stream (USER_STREAM)

  * `DELETE /api/v1/listenKey`

### Weight： 1

> Response：

json
```
{}
```

1

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
listenKey| STRING| YES| listenKey
category| ENUM| NO| USDC-M Futures=`USDC`, Default=USDT-M Futures.
timestamp| LONG| YES| timestamp
recvWindow| LONG| NO| recv window

## User Data Stream Expired

  * `/api/v1/ws/`

> Response

json
```
{
  "eventTime": 1767536100360,//event time
  "eventType": "listenKeyWillExpire",//event type
  "listenKey": "zUeuthxEYbqupygpYQKPTgDemAQWXJdrpzVhmVOSKSDUzMWzIAVgPgYbDLuxBpNu"//listenkey
}
```

1
2
3
4
5

  * push notifications will begin 5 minutes before the expiration date, and will be sent every minute.

## Event: Balance

The `event type` of the account update event is fixed to `outboundContractAccountInfo`

> Payload

json
```
[
  {
    "e": "outboundContractAccountInfo",                // event type
    "E": 1564745798939,                   // event time
    "T": true ,                  // Can trade
    "W": true ,                  // Can withdraw
    "D": true ,                  // Can deposit
    "B": [                        // Balances changed
      {
        "a": "LTC",               // Asset
        "f": "17366.18538083",    // Free amount
        "l": "0.00000000"         // Locked amount
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

  * When the account information changes, this event will be pushed:
    * This event will only be pushed when there is a change in account information

## Event: Position Update

> Position Payload

json
```
[
    {
        "e": "outboundContractPositionInfo",                // Event type
        "E": "1668693440976",             // Event time
        "A": "1270447370291795457",      // account id
        "s": "BTC-SWAP-USDT",             // Symbol
        "S": "LONG",                      // side
        "p": "441.0",                     // avg price
        "P": "1291488620385157122",       // total position
        "a": "1000",                      // Available positions
        "f": "1291488620167835136",       // liquidation price
        "m": "18.2",                      // Position Margin
        "r": "44",                        // Realized profit and loss
        "mt": "CROSS",                     // Position type
        "rr": "89",                       // riskRate Account risk rate reaches 100 to trigger forced liquidation
        "up": "12",                      // unrealizedPnL
        "pr": "0.003",                  //  Profit rate of current position
        "pv": "123",                    //  Position value (USDT)
        "v": "10"                     // leverage
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

  * position information: push only when there is a change in the symbol position.
  * The field `mt` represents the position type `CROSS` cross margin; `ISOLATED` isolated margin

## Event: Order

This type of event will be pushed when a new order is created, an order has a new deal, or a new state change.

> Order Payload

json
```
[
  {
    "e": "contractExecutionReport",        // Event type
    "E": 1499405658658,            // Event time
    "s": "BTC-SWAP-USDT",          // Symbol
    "c": 1000087761,               // Client order ID
    "C": true,                     // Is close order
    "S": "BUY",                    // Side
    "o": "LIMIT",                  // Order type
    "f": "GTC",                    // Time in force
    "q": "1.00000000",             // Order quantity （contracts)
    "p": "0.10264410",             // Order price
    "pt": "MARKET",                // price type  INPUT: user input price.  MARKET: market price
    "X": "NEW",                    // Current order status
    "i": 4293153,                  // Order ID
    "l": "0.00000000",             // Last executed quantity （contracts)
    "z": "0.00000000",             // Cumulative filled quantity （contracts)
    "L": "0.00000000",             // Last executed price
    "n": "0",                      // Commission amount
    "N": null,                     // Commission asset
    "u": true,                     // Is the trade normal, ignore for now
    "w": true,                     // Is the order working Stops will have
    "m": false,                    // Is this trade the maker side
    "mt": "CROSS",                 // Position type
    "O": 1499405658657,            // Order creation time
    "Z": "0.00000000",             // Cumulative quote asset transacted quantity
    "v": "20",                     // leverage
    "U": 1499405658658,            // update order time
    "rp": "-4.3058"                // Clos Order Cumulative realisedPnl
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

  * The average price can be found by dividing `Z` by `z`
  * The field `mt` represents the position type `CROSS` cross margin; `ISOLATED` isolated margin

### Side

  * BUY
  * SELL

### Order Type

  * MARKET
  * LIMIT
  * STOP_LIMIT Plan entrusted

### Price Type

  * INPUT user input price
  * MARKET market price

### Order Status

  * NEW

  * PARTIALLY_FILLED

  * FILLED

  * CANCELED

  * PENDING_CANCEL

  * REJECTED

### Time in force

  * GTC
  * IOC
  * FOK

### Plan order or stop loss order status

  * ORDER_NEW
  * ORDER_FILLED
  * ORDER_REJECTED
  * ORDER_CANCELED
  * ORDER_FAILED

### Take profit and stop loss type

  * STOP_LONG_PROFIT Long position take profit
  * STOP_LONG_LOSS Long position stop loss
  * STOP_SHORT_PROFIT Plan entrustment-short position take profit
  * STOP_SHORT_LOSS Plan order - short position stop loss

## Event: Trade Update

Will push when there is a deal

> Trade Payload

json
```
[
    {
        "e": "ticketInfo",                // Event type
        "E": "1668693440976",             // Event time
        "s": "BTC-SWAP-USDT",             // Symbol
        "q": "0.205",                     // quantity
        "t": "1668693440899",             // time
        "p": "441.0",                     // price
        "T": "1291488620385157122",       // ticketId
        "o": "1291488620167835136",       // orderId
        "c": "1668693440093",             // clientOrderId
        "a": "1286424214388204801",       // accountId
        "m": false,                       // isMaker
        "S": "SELL"                       // side
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

## TP/SL Order

All planned orders will be pushed to you, and stop-loss and take-profit orders will be filtered based on the value of planOrderType.

> Payload

json
```
{
  "eventType": "planExecutionReport",//event type
  "time": "1767521501840",//order created time
  "orderId": "2120518483020142848",//order id
  "accountId": "1752238453238626818",//account id
  "brokerUserId": "4910055547259955197",//user id
  "clientOrderId": "1767521500131",//User order ID (subscribed by the user when placing an order via API; generated by the system when placing an order on the page).
  "symbolId": "BTC-SWAP-USDT",// symbol id
  "symbolName": "BTCUSDT",//symbol name
  "baseTokenId": "BTC-SWAP-USDT",//baseTokenId
  "baseTokenName": "BTC-SWAP-USDT",
  "quoteTokenId": "USDT",//quote token
  "quoteTokenName": "USDT",//quote token name
  "price": "0",//Order price
  "origQty": "10",//order quantity
  "type": "STOP",//order type-STOP Plan commission（fixed value）
  "planOrderType": "STOP_SHORT_PROFIT",//plan order type STOP_LONG_PROFIT, STOP_LONG_LOSS,STOP_SHORT_PROFIT, STOP_SHORT_LOSS, STOP_COMMON
  "side": "BUY_CLOSE",//BUY_OPEN SELL_OPEN BUY_CLOSE SELL_CLOSE
  "status": "ORDER_NEW",//ORDER_NEW -wait to trigger，ORDER_FILLED -triggered ORDER_REJECTED -trigger failed ORDER_CANCELED -canceled ORDER_FAILED  ORDER_NOT_EFFECTIVE -SP or SL doesn't take effect
  "triggerPrice": "91446",//trigger price
  "quotePrice": "91493.1",//quote token price
  "executedOrderId": "0",//There will be a value after triggering.
  "executedPrice": "0",//There will be a value after triggering.
  "executedQty": "0",//There will be a value after triggering.
  "updateTime": "1767521529483",
  "priceType": "MARKET_PRICE",//INPUT MARKET_PRICE
  "quotePriceType": 0,//Trigger price type: 0 - Latest price, 1 - Index price, 2 - Mark price
  "leverage": "10",
  "spOrderId": "2120518483020142848",//Take Profit Order ID
  "slOrderId": "0",//Stop Loss Order ID
  "openOrdinaryOrderId": "2120518481434695937",//Common order ID
  "openOrderId": "0",//Opening order ID: not 0 in split position mode, 0 in combined position mode.
  "triggerType": 0,//0 fixed trigger, 1 moving trigger
  "activePrice": "0",//Trailing stop-loss/take-profit activation price (value only applies when activated)
  "fallType": 0,//Trailing stop-loss/take-profit trigger price pullback type: 0 percentage, 1 spread
  "fallQuantity": "0",//The value is always 0, so stop-loss and take-profit orders are not used.
  "activeStatus": 0,//Trailing stop-loss and take-profit activation status: 0 Not activated, 1 Activated
  "triggerDelay": 0,//Trigger delay (seconds)
  "marginType": "CROSS",//Position type CROSS，ISOLATED
  "isGuaranteedPrice": 0,//Is the price guaranteed? 1 Yes, 0 No
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
