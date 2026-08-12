# Websocket Market Streams

  * The base endpoint is: wss://stream.toobit.com
  * The URL format for direct access is: wss://#HOST/quote/ws/v1

Name| value
---|---
topic| `realtimes`, `trade`, `kline_$interval`, `depth`,`markPrice`,`markPriceKline_$interval`,`index indexKline_$interval`
event| `sub`, `cancel`, `cancel_all`
interval| `1m`, `5m`, `15m`, `30m`, `1h`, `2h`, `6h`, `12h`, `1d`, `1w`, `1M`

## Live Subscribing/Unsubscribing to streams

### Subscribe to a stream:

  * Request

json
```
{
  "symbol": "$symbol0, $symbol1",
  "topic": "$topic",
  "event": "sub",
  "params": {
    "limit": "$limit", // kline return upper limit is 2000, the default is 1
    "binary": "false" //Whether the returned data is compressed, the default is false
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

### Unsubscribe to a stream:

  * Request

json
```
{
  "symbol": "$symbol0, $symbol1",
  "topic": "$topic",
  "event": "cancel",
  "params": {
    "limit": "$limit", // kline return upper limit is 2000, the default is 1
    "binary": "false" //Whether the returned data is compressed, the default is false
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

> Payblad

json
```
{
    "pong": 1535975085052
}
```

1
2
3

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

## Trade Streams

Push the information of each transaction transaction by transaction. A deal, or the definition of a transaction, is that there is only one taker and one maker trading with each other. After successfully connecting to the server, the server will first push a recent 60 transactions. After this push, each push is a real-time transaction. The variable "v" can be understood as a transaction ID. This variable is globally incremented and unique. For example: Suppose there have been 3 transactions in the past 5 seconds, namely `ETHUSDT`, `BTCUSDT`, `BHTBTC`. Their "v" will be consecutive values (112, 113, 114).

> Payload

json
```
{
    "symbol": "BTCUSDT",
    "symbolName": "BTCUSDT",
    "topic": "trade",
    "params": {
        "realtimeInterval": "24h",
        "binary": "false"
    },
    "data": [
        {
            "v": "1291465821801168896",
            "t": 1668690723096, //time
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
  "symbol": "$symbol0, $symbol1",
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

## Kline/Candlestick Streams

The Kline/Candlestick Stream push updates to the current klines/candlestick every second.

### Kline/Candlestick chart intervals:

m -> minutes; h -> hours; d -> days; w -> weeks; M -> months

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

> Payload

json
```
{
    "symbol": "BTCUSDT",
    "symbolName": "BTCUSDT",
    "topic": "kline",
    "params": {
        "realtimeInterval": "24h",
        "klineType": "1m",
        "binary": "false"
    },
    "data": [
        {
            "t": 1668753840000,// Event time
            "s": "BTCUSDT",// symbol
            "sn": "BTCUSDT",// symbol name
            "c": "445",//Close price
            "h": "445",//High price
            "l": "445",//Low price
            "o": "445",//Open price
            "v": "0"//Base asset volume
        }
    ],
    "f": true,// Is it the first return
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
  "symbol": "$symbol0, $symbol1",
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

## Individual Symbol Ticker Streams

24-hour complete ticker information refreshed second by symbol

> Payload

json
```
{
    "symbol": "BTCUSDT",
    "symbolName": "BTCUSDT",
    "topic": "realtimes",
    "params": {
        "realtimeInterval": "24h",
        "binary": "false"
    },
    "data": [
        {
            "t": 1668753480049, //time
            "s": "BTCUSDT", //symbol
            "sn": "BTCUSDT", // symbol name
            "c": "445", //Close price
            "h": "445", //High price
            "l": "310", // Low price
            "o": "311", //Open price
            "v": "3747.7597191", //Total traded base asset volume
            "qv": "1426443.9553995", // Total traded quote asset volume
            "m": "0.4309", // margin
            "e": 301 // trade id
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
  "symbol": "$symbol0, $symbol1",
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

## Partial Book Depth Streams

Symbol's depth information.

  * Order book snapshot frequency: every 300ms, if the book changes.

  * Order book snapshot frequency depth: bids and asks 300 each

  * Order book version change trigger event：

    * The order enters the order book
    * Order leaves the order book
    * Order Quantity Change
    * Order Completed

> Payload

json
```
{
  "symbol": "BTCUSDT",
  "topic": "depth",
  "data": [{
    "s": "BTCUSDT", //Symbol
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
  "f": true//Is it the first return
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
  "symbol": "$symbol0, $symbol1",
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

## Diff. Depth Stream

> Payload

json
```
{
  "symbol": "BTCUSDT",
  "topic": "diffDepth",
  "data": [{
    "e": 0,
    "t": 1565687625534,
    "v": "115277986_18",//Version number _18, where 18 indicates 18-bit precision. Version numbers are not guaranteed to be unique, but data from close dates will definitely be different.
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
  }],
  "f": false //Is it the first return
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
  "symbol": "$symbol0, $symbol1",
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

Push the changing part of the order book (if any) every second. In incremental depth information, the quantity is not necessarily equal to the quantity corresponding to the price. If the quantity=0, it means that the price in the last push is no longer available. If the quantity>0, the quantity at this time is the quantity corresponding to the updated price Suppose there is such an item in the returned data we received:

json
```
["0.00181860", "155.92000000"]// price, quantity
```

1

If the next returned data contains:

json
```
["0.00181860", "12.3"]
```

1

This means that the quantity corresponding to this price has changed, and the changed quantity has been updated If the next returned data contains:

json
```
["0.00181860", "0"]
```

1

This means that the quantity corresponding to this price has disappeared and will be deleted in the client.
