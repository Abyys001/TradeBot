# Websocket Market Streams

  * The base endpoint is: wss://stream.toobit.com
  * The URL format for direct access is: wss://#HOST/quote/ws/v1

## Live Subscribing/Unsubscribing to streams

  * The following data can be sent via websocket to implement subscription or unsubscription data stream.

Name| Value
---|---
topic| `realtimes`, `trade`, `kline_$interval`, `depth`
event| `sub`, `cancel`, `cancel_all`
interval| 1m, 5m, 15m, 30m, 1h, 2h, 6h, 12h, 1d, 1w, 1M

### Subscribe to a stream Request:

json
```
{
  "symbol": "$symbol0, $symbol1",
  "topic": "$topic",
  "event": "sub",
  "params": {
    "limit": "$limit",
    "binary": "false"
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

## Unsubscribe to a stream Request:

json
```
{
  "symbol": "$symbol0, $symbol1",
  "topic": "$topic",
  "event": "cancel",
  "params": {
    "limit": "$limit",
    "binary": "false"
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

## Heartbeat

Every once in a while, the client needs to send a ping frame, and the server will reply with a pong frame, otherwise the server will actively disconnect within 5 minutes.

### Request

json
```
{
  "ping": 1535975085052
}
```

1
2
3

> Response：

json
```
{
  "pong": 1535975085052
}
```

1
2
3

## Latest Contract Price Stream

Push the information of each transaction transaction by transaction. A deal, or the definition of a transaction, is that there is only one taker and one maker trading with each other. After successfully connecting to the server, the server will first push a recent 60 transactions. After this push, each push is a real-time transaction. The variable "v" can be understood as a transaction ID. This variable is globally incremented and unique. For example: Suppose there have been 3 transactions in the past 5 seconds, namely `ETH-SWAP-USDT`, `BTC-SWAP-USDT`, `DOGE-SWAP-USDT`. Their "v" will be consecutive values (112, 113, 114).

> Payload

json
```
{
    "symbol": "BTC-SWAP-USDT",
    "symbolName": "BTC-SWAP-USDTUSDT",
    "topic": "trade",
    "params": {
        "realtimeInterval": "24h",
        "binary": "false"
    },
    "data": [
        {
            "v": "1291465821801168896", // Volume
            "t": 1668690723096, // time
            "p": "399", // price
            "q": "1", // quantity
            "m": false // true = buy, false = sell
        },
        {
            "v": "1291465842546196481",
            "t": 1668690725569,
            "p": "399",
            "q": "1",
            "m": false
        }
    ],
    "f": true, // is it the first to return
    "sendTime": 1668753154192
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

### Request:

json
```
{
  "symbol": "$symbol0, $symbol1",// Symbol
  "topic": "trade",
  "event": "sub",
  "params": {
    "binary": false // Whether data returned is in binary format
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

## Mark Price Stream

Contract mark price.

> Payload

json
```
{
    "symbol": "BTC-SWAP-USDT",
    "symbolName": "BTC-SWAP-USDT",
    "topic": "markPrice",
    "params": {
        "realtimeInterval": "24h"
    },
    "data": [
        {
            "symbol": "BTC-SWAP-USDT",//symbol
            "markPrice": "16792.28",// mark price
            "time": 1668754084000
        }
    ],
    "f": false,
    "sendTime": 1668754084738
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

### Request:

json
```
{
  "symbol": "$symbol0, $symbol1", //Symbol
  "topic": "markPrice",
  "event": "sub"
}
```

1
2
3
4
5

## Kline/Candlestick Streams

The K-line stream pushes the update of the requested K-line type (the latest K-line) every second.

> Payload

json
```
{
    "symbol": "BTC-SWAP-USDT",
    "symbolName": "BTC-SWAP-USDTUSDT",
    "topic": "kline",
    "params": {
        "realtimeInterval": "24h",
        "klineType": "1m",
        "binary": "false"
    },
    "data": [
        {
            "t": 1668753840000,// start timestamp
            "s": "BTC-SWAP-USDT",// symbol
            "sn": "BTC-SWAP-USDTUSDT",// symbol name
            "c": "445",//close price
            "h": "445",//high price
            "l": "445",//low price
            "o": "445",//open price
            "v": "0"// volume
        }
    ],
    "f": true,
    "sendTime": 1668753854576
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

### Request:

json
```
{
  "symbol": "$symbol0, $symbol1",// symbol
  "topic": "kline_"+$interval,
  "event": "sub",
  "params": {
    "binary": false
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

### K线/Kline/Candlestick chart intervals:

To subscribe to Kline, you need to provide an interval parameter, the shortest is the minute line, and the longest is the monthly line. The following intervals are supported: m -> minutes; h -> hours; d -> days; w -> weeks; M -> months

  * 1m
  * 5m
  * 15m
  * 30m
  * 1h
  * 2h
  * 4h
  * 6h
  * 12h
  * 1d
  * 1w
  * 1M

## Individual Symbol Ticker Streams

24-hour complete ticker information refreshed second by symbol.

> Payload

json
```
{
    "symbol": "BTC-SWAP-USDT",
    "symbolName": "BTC-SWAP-USDTUSDT",
    "topic": "realtimes",
    "params": {
        "realtimeInterval": "24h",
        "binary": "false"
    },
    "data": [
        {
            "t": 1668753480049, //time
            "s": "BTC-SWAP-USDT", //symbol
            "sn": "BTC-SWAP-USDTUSDT", // symbol name
            "c": "445", // close price
            "h": "445", //high price
            "l": "310", //low price
            "o": "311", //open price
            "v": "3747.7597191", // Total traded base asset volume
            "qv": "1426443.9553995", // Total traded quote asset volume
            "m": "0.4309", // margin
            "e": 301 // fixed value
        }
    ],
    "f": true,
    "sendTime": 1668753481048
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

### Request:

json
```
{
  "symbol": "$symbol0, $symbol1",// symbol
  "topic": "realtimes",
  "event": "sub",
  "params": {
    "binary": false
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

## All Market Tickers Streams

24hr rolling window ticker statistics for all symbols.

> Payload

json
```
{
  "topic": "wholeRealTime", //topic
  "params": {
    "realtimeInterval": "24h",
    "binary": "false"
  },
  "data": {
    "e": "24hrTicker", //Event type
    "E": 1768249147338, //Event time
    "s": "ARC_SOL_ONCHAINUSDT", // Symbol
    "o": "0.0474", // Open price
    "h": "0.0522", // High price
    "l": "0.0467", // Low price
    "c": "0.0497", // Last price
    "v": "2299", // Total traded base asset volume
    "qv": "0", // Total traded quote asset volume
    "P": "0.0485", // Price change ratio
    "p": "0.0023", //Price change
    "ltv": "1" //quote volume of the last trade
  },
  "f": false,//is the first time to push
  "sendTime": 1768249147338 //push time
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

### Request:

json
```
{
  "topic":"wholeRealTime","event": "sub"
}
```

1
2
3

## Symbol Index Price

symbol index price

> Payload

json
```
{
    "symbol": "BTCUSDT",  // symbol
    "symbolName": "BTCUSDT", // symbolName
    "topic": "index",
    "data": [
        {
            "symbol": "BTCUSDT",  // symbol
            "index": "42992.432", // index price
            "edp": "43000.95379", // average of indices over 10 minutes
            "formula": "OKEX.BTCUSDT*1.0,KUCOIN.BTCUSDT*1.0,BINANCE.BTCUSDT*1.0,BITGET.BTCUSDT*1.0,COINBASE.BTCUSDT*1.0,BYBIT.BTCUSDT*1.0",// weighted average formula
            "time": 1703692663000  // time
        }
    ],
    "f": false,
    "sendTime": 1703692664103
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

### Request:

json
```
{
  "id":"index",
  "topic":"index",
  "event":"sub",
  "symbol":"BTCUSDT",
  "params": {
    "reduceSerial":true, // less serialization, faster push
    "binary":true,  // compression or not
    "limit":1500  // limit
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

## Partial Book Depth Streams

> Payload

json
```
{
  "symbol": "BTC-SWAP-USDT",
  "topic": "depth",
  "data": [{
    "s": "BTC-SWAP-USDT", //Symbol
    "t": 1565600357643, //time
    "v": "112801745_18", // Version number _18, where 18 indicates 18-bit precision. Version numbers are not guaranteed to be unique, but data from close dates will definitely be different.
    "b": [ //Bids
      ["11371.49", "0.0014"], //[price, quantity]
      ["11371.12", "0.2"],
      ["11369.97", "0.3523"],
      ["11369.96", "0.5"],
      ["11369.95", "0.0934"],
      ["11369.94", "1.6809"],
      ["11369.6", "0.0047"],
      ["11369.17", "0.3"],
      ["11369.16", "0.2"],
      ["11369.04", "1.3203"]
    ],
    "a": [//Asks
      ["11375.41", "0.0053"], //[price, quantity]
      ["11375.42", "0.0043"],
      ["11375.48", "0.0052"],
      ["11375.58", "0.0541"],
      ["11375.7", "0.0386"],
      ["11375.71", "2"],
      ["11377", "2.0691"],
      ["11377.01", "0.0167"],
      ["11377.12", "1.5"],
      ["11377.61", "0.3"]
    ]
  }],
  "f": true
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

### Request:

json
```
{
  "symbol": "$symbol0, $symbol1",// symbol
  "topic": "depth",
  "event": "sub",
  "params": {
    "binary": false
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

## Diff. Book Depth Streams

> Payload

json
```
{
  "symbol": "BTC-SWAP-USDT",
  "topic": "diffDepth",
  "data": [
    {
      "e": 0,
      "t": 1565687625534,
      "v": "115277986_18", //Version number _18, where 18 indicates 18-bit precision. Version numbers are not guaranteed to be unique, but data from close dates will definitely be different.
      "b": [
        ["11316.78", "0.078"],
        ["11313.16", "0.0052"],
        ["11312.12", "0"],
        ["11309.75", "0.0067"],
        ["11309.58", "0"],
        ["11306.14", "0.0073"]
      ],
      "a": [
        ["11318.96", "0.0041"],
        ["11318.99", "0.0017"],
        ["11319.12", "0.0017"],
        ["11319.22", "0.4516"],
        ["11319.23", "0.0934"],
        ["11319.24", "3.0665"]
      ]
    }
  ],
  "f": false
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

### Request:

json
```
{
  "symbol": "$symbol0, $symbol1",//Symbol
  "topic": "diffDepth",
  "event": "sub",
  "params": {
    "binary": false
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

## Individual Symbol Book Ticker Streams

> Payload

json
```
{
  "topic": "bookTicker", //topic
  "params": {
    "symbol": "BTC-SWAP-USDT",
    "realtimeInterval": "24h"
  },
  "data": {
    "e": "bookTicker", //event type
    "E": 1768249193064, //event time
    "s": "BTC-SWAP-USDT", // symbol
    "b": "91791.9", // best bid price
    "bq": "41710", // best bid qty
    "a": "92704.1", // best ask price
    "aq": "57121", // best ask qty
    "t": 1768249193006 // transaction time
  },
  "f": false, //is the first time to return
  "sendTime": 1768249193064 //push time
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

### Request:

json
```
{
  "symbol": "BTC-SWAP-USDT",
  "topic":"bookTicker",
  "event": "sub"
}
```

1
2
3
4
5

## All Book Tickers Stream

descrpption：Pushes any update to the best bid or ask's price or quantity in real-time for all symbols.

> Payload

json
```
{
  "topic": "wholeBookTicker",//topic
  "params": {
    "realtimeInterval": "24h"
  },
  "data": {
    "e": "wholeBookTicker",// event type
    "E": 1768249218139,// event time
    "s": "ETH-SWAP-USDT",// symbol
    "b": "4325",// best bid price
    "bq": "405",// best bid qty
    "a": "4330",// best ask price
    "aq": "310",// best ask qty
    "t": 1768249218057 // transaction time
  },
  "f": false, //is the first time to return
  "sendTime": 1768249218139 //push time
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

### Request:

json
```
{
  "topic":"wholeBookTicker","event": "sub"
}
```

1
2
3

Push the changing part of the order book (if any) every second. In incremental depth information, the quantity is not necessarily equal to the quantity corresponding to the price. If the quantity=0, it means that the price in the last push is no longer available. If the quantity>0, the quantity at this time is the quantity corresponding to the updated price Assume that there is such an item in the returned data we received: `["0.00181860", "155.92000000"]// price, quantity` If the next returned data contains: `["0.00181860", "12.3"]` This means that the quantity corresponding to this price has changed, and the changed quantity has been updated If the next returned data contains: `["0.00181860", "0"]` This means that the quantity corresponding to this price has disappeared and will be deleted in the client.
