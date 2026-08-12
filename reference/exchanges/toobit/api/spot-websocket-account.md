# User Data Streams

  * The base API endpoint is : **https://api.toobit.com**
  * A User Data Stream `listenKey` is valid for 60 minutes after creation.
  * Doing a `PUT` on a `listenKey` will extend its validity for 60 minutes.
  * Doing a `DELETE` on a `listenKey` will close the stream and invalidate the `listenKey` .
  * Doing a `POST` on an account with an active `listenKey` will return the currently active `listenKey`and extend its validity for 60 minutes.
  * The base websocket endpoint is: **wss://stream.toobit.com**
  * User feeds are accessible via `/api/v1/ws/<listenKey>` (e.g. `wss://#HOST/api/v1/ws/<listenKey>`)
  * User feed payloads are not guaranteed to be up during busy times; make sure to order updates with `E`

## Listen Key (SPOT)

### Create a ListenKey (USER_STREAM)

  * `POST /api/v1/userDataStream`

Start a new user data stream. The stream will close after 60 minutes unless a keepalive is sent.

#### Weight：1

> Response

json
```
{
  "listenKey": "1A9LWJjuMwKWYP4QQPw34GRm8gz3x5AephXSuqcDef1RnzoBVhEeGE963CoS1Sgj"
}
```

1
2
3

#### Parameters

Name| Type| Mandatory| Description
---|---|---|---
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

### Ping/Keep-alive a ListenKey (USER_STREAM)

  * `PUT /api/v1/userDataStream`

Keepalive a user data stream to prevent a time out. User data streams will close after 60 minutes. It's recommended to send a ping about every 30 minutes.

#### Weight：1

> Response

json
```
{}
```

1

#### Parameters

Name| Type| Mandatory| Description
---|---|---|---
listenKey| STRING| YES|
recvWindow| LONG| NO|
timestamp| LONG| YES|

### Close a ListenKey (USER_STREAM)

  * `DELETE /api/v1/userDataStream`

#### Weight：1

> Response

json
```
{}
```

1

#### Parameters

Name| Type| Mandatory| Description
---|---|---|---
listenKey| STRING| YES| listenKey
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| timestamp

## Payload: Account Update

> Payload

json
```
[
  {
    "e": "outboundAccountInfo",   // Event type
    "E": 1499405658849,           // Event time
    "T": true,                    // Can trade
    "W": true,                    // Can withdraw
    "D": true,                    // Can deposit
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

Whenever the account balance changes, an event `outboundAccountInfo` is sent containing the assets that may have been moved by the event that generated the balance change.

## Payload: Order Update

> Payload

json
```
[
  {
    "e": "executionReport",        // Event type
    "E": 1499405658658,            // Event time
    "s": "ETHUSDT",                 // Symbol
    "c": 1000087761,               // Client order ID
    "S": "BUY",                    // Side
    "o": "LIMIT",                  // Order type
    "f": "GTC",                    // Time in force
    "q": "1.00000000",             // Order quantity
    "p": "0.10264410",             // Order price
    "pt": "MARKET",                // price type  INPUT:input price. MARKET: market price
    "X": "NEW",                    // Current order status
    "i": 4293153,                  // Order ID
    "l": "0.00000000",             // Last executed quantity
    "z": "0.00000000",             // Cumulative filled quantity
    "L": "0.00000000",             // Last executed price
    "n": "0",                      // Commission amount
    "N": null,                     // Commission asset
    "u": true,                     // Is the trade normal, ignore for now
    "w": true,                     // Is the order working? fixed value-true
    "m": false,                    // Is this trade the maker side?
    "O": 1499405658657,            // Order creation time
    "Z": "0.00000000"              // Cumulative quote asset transacted quantity
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

Order updates are updated through the `executionReport` event. Check out the API docs and the relevant enum definitions below. The average price can be found by dividing Z by z.

### Order Type

  * NEW
  * PARTIALLY_FILLED
  * FILLED
  * CANCELED
  * REJECTED

## Payload: Ticket push

> Payload

json
```
[
    {
        "e": "ticketInfo",                // Event type
        "E": "1668693440976",             // Event time
        "s": "BTCUSDT",                   // Symbol
        "q": "0.205",                     // quantity
        "t": "1668693440899",             // time
        "p": "441.0",                     // price
        "T": "1291488620385157122",       // ticketId
        "o": "1291488620167835136",       // orderId
        "c": "1668693440093",             // clientOrderId
        "a": "1286424214388204801",       // accountId
        "m": false,                       // isMaker
        "S": "SELL"                       // side  SELL or BUY
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
