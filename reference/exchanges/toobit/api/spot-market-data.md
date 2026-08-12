# Market Data Endpoints

## Check Server Time

  * `GET /api/v1/time`

Test connectivity to the Rest API and get the current server time.

**Weight** :1

> Response

json
```
{
  "serverTime": 1538323200000
}
```

1
2
3

### Parameters

NONE

## Exchange Information

  * `GET /api/v1/exchangeInfo`

Current exchange trading rules and symbol information

Important Notice

The `rateLimits` field in the response will be removed in future iterations. A new endpoint will be provided to retrieve rate limit information. Please do not rely on this field.

**Weight** :1

> Response

json
```
{
  "timezone": "UTC",
  "serverTime": "1668407511495",
  "brokerFilters": [],
  "symbols": [ // spot symbols
    {
      "filters":[
          {
              "minPrice":"0.01",
              "maxPrice":"100000.00000000",
              "tickSize":"0.01",
              "filterType":"PRICE_FILTER"
          },
          {
              "minQty":"0.0001", // min trade quantity
              "maxQty":"4000", // max trade quantity
              "stepSize":"0.0001",
              "filterType":"LOT_SIZE"
          },
          {
              "minNotional":"10",
              "filterType":"MIN_NOTIONAL"
          },
              {
              "minAmount":"10", // minimum transaction amount
              "maxAmount":"6600000", // maximum trade amount
              "minBuyPrice":"0.01", // minimum buy price
              "filterType":"TRADE_AMOUNT"
          },
          {
              "maxSellPrice":"999999999", // limit max sell price
              "buyPriceUpRate":"0.1", // maximum sell price
              "sellPriceDownRate":"0.1", // maximum sell price
              "sellPriceDownRate":"0.1", // the maximum sell price of the limit
              "maxEntrustNum":"100000",  // the maximum number of orders (contracts)
              "maxConditionNum":"100000", // maximum number of condition orders (contracts)
              "filterType":"LIMIT_TRADING"
          },
          {
              "buyPriceUpRate":"0.1", // Buy cannot be higher than 10% of the marked (contract)/latest (spot) price
              "sellPriceDownRate":"0.1", // Sell cannot be less than 10% of the marked (contract)/latest (spot) price
              "filterType":"MARKET_TRADING"
          },
          {
              "noAllowMarketStartTime":"0", // Market order start time is not allowed
              "noAllowMarketEndTime":"0", // Do not allow the market order end time
              "limitOrderStartTime":"0", // the start time of a limit order
              "limitOrderEndTime":"0", // Limit order end time
              "limitMinPrice":"0", // the minimum price of a limit order
              "limitMaxPrice":"0", // the maximum price of the limit order
              "filterType":"OPEN_QUOTE"
          }
      ],
      "symbol": "ETHUSDT",
      "symbolName": "ETHUSDT",
      "status": "TRADING",
      "baseAsset": "ETH",
      "baseAssetName": "ETH",
      "baseAssetPrecision": "0.0001",
      "quoteAsset": "USDT",
      "quoteAssetName": "USDT",
      "quotePrecision": "0.01",
      "icebergAllowed": false,
      "isAggregate": false,
      "allowMargin": true
    }
  ],
  "rateLimits": [ // Note: This field will be removed in future iterations. A new endpoint will be provided to retrieve rate limit information
    {
      "rateLimitType": "REQUEST_WEIGHT",
      "interval": "MINUTE",
      "intervalUnit": 1,
      "limit": 3000
    },
    {
      "rateLimitType": "ORDERS",
      "interval": "SECOND",
      "intervalUnit": 2,
      "limit": 60
    }
  ],
  "options": [],
  "contracts": [ // Futures(contracts) symbols
    {
      "filters":[
          {
              "minPrice":"0.01",
              "maxPrice":"100000.00000000",
              "tickSize":"0.01",
              "filterType":"PRICE_FILTER"
          },
          {
              "minQty":"0.0001", // min trade quantity, token quantity not contracts
              "maxQty":"4000", // max trade quantity, token quantity not contracts
              "stepSize":"0.0001",
              "filterType":"LOT_SIZE"
          },
          {
              "minNotional":"10",
              "filterType":"MIN_NOTIONAL"
          },
              {
              "minAmount":"10", // minimum transaction amount
              "maxAmount":"6600000", // maximum trade amount
              "minBuyPrice":"0.01", // minimum buy price
              "filterType":"TRADE_AMOUNT"
          },
          {
              "maxSellPrice":"999999999", // limit max sell price
              "buyPriceUpRate":"0.1", // maximum sell price
              "sellPriceDownRate":"0.1", // maximum sell price
              "sellPriceDownRate":"0.1", // the maximum sell price of the limit
              "maxEntrustNum":"100000",  // the maximum number of orders (contracts)
              "maxConditionNum":"100000", // maximum number of condition orders (contracts)
              "filterType":"LIMIT_TRADING"
          },
          {
              "buyPriceUpRate":"0.1", // Buy cannot be higher than 10% of the marked (contract)/latest (spot) price
              "sellPriceDownRate":"0.1", // Sell cannot be less than 10% of the marked (contract)/latest (spot) price
              "filterType":"MARKET_TRADING"
          },
          {
              "noAllowMarketStartTime":"0", // Market order start time is not allowed
              "noAllowMarketEndTime":"0", // Do not allow the market order end time
              "limitOrderStartTime":"0", // the start time of a limit order
              "limitOrderEndTime":"0", // Limit order end time
              "limitMinPrice":"0", // the minimum price of a limit order
              "limitMaxPrice":"0", // the maximum price of the limit order
              "filterType":"OPEN_QUOTE"
          }
      ],
      "symbol": "BTC-SWAP-USDT",
      "symbolName": "BTC-SWAP-USDTUSDT",
      "status": "TRADING",
      "baseAsset": "BTC-SWAP-USDT",
      "baseAssetPrecision": "1",
      "quoteAsset": "USDT",
      "quoteAssetPrecision": "0.1",
      "icebergAllowed": false,
      "inverse": false,
      "index": "BTCUSDT",
      "marginToken": "USDT",
      "marginPrecision": "0.0001",
      "contractMultiplier": "0.0001",
      "underlying": "BTC",
      "riskLimits": [
        {
          "riskLimitId": "200000133",
          "quantity": "1000000.0",
          "initialMargin": "0.01",
          "maintMargin": "0.005"
        },
        {
          "riskLimitId": "200000134",
          "quantity": "2000000.0",
          "initialMargin": "0.02",
          "maintMargin": "0.01"
        },
        {
          "riskLimitId": "200000135",
          "quantity": "3000000.0",
          "initialMargin": "0.03",
          "maintMargin": "0.015"
        },
        {
          "riskLimitId": "200000136",
          "quantity": "4000000.0",
          "initialMargin": "0.04",
          "maintMargin": "0.02"
        }
      ]
    },
    {
      "filters":[
          {
              "minPrice":"0.01",
              "maxPrice":"100000.00000000",
              "tickSize":"0.01",
              "filterType":"PRICE_FILTER"
          },
          {
              "minQty":"0.0001",
              "maxQty":"4000",
              "stepSize":"0.0001",
              "filterType":"LOT_SIZE"
          },
          {
              "minNotional":"10",
              "filterType":"MIN_NOTIONAL"
          },
              {
              "minAmount":"10", // minimum transaction amount
              "maxAmount":"6600000", // maximum trade amount
              "minBuyPrice":"0.01", // minimum buy price
              "filterType":"TRADE_AMOUNT"
          },
          {
              "maxSellPrice":"999999999", // limit max sell price
              "buyPriceUpRate":"0.1", // maximum sell price
              "sellPriceDownRate":"0.1", // maximum sell price
              "sellPriceDownRate":"0.1", // the maximum sell price of the limit
              "maxEntrustNum":"100000",  // the maximum number of orders (contracts)
              "maxConditionNum":"100000", // maximum number of condition orders (contracts)
              "filterType":"LIMIT_TRADING"
          },
          {
              "buyPriceUpRate":"0.1", // Buy cannot be higher than 10% of the marked (contract)/latest (spot) price
              "sellPriceDownRate":"0.1", // Sell cannot be less than 10% of the marked (contract)/latest (spot) price
              "filterType":"MARKET_TRADING"
          },
          {
              "noAllowMarketStartTime":"0", // Market order start time is not allowed
              "noAllowMarketEndTime":"0", // Do not allow the market order end time
              "limitOrderStartTime":"0", // the start time of a limit order
              "limitOrderEndTime":"0", // Limit order end time
              "limitMinPrice":"0", // the minimum price of a limit order
              "limitMaxPrice":"0", // the maximum price of the limit order
              "filterType":"OPEN_QUOTE"
          }
      ],
      "symbol": "BTC-SWAP",
      "symbolName": "BTC-SWAP",
      "status": "TRADING",
      "baseAsset": "BTC-SWAP",
      "baseAssetPrecision": "1",
      "quoteAsset": "USDT",
      "quoteAssetPrecision": "0.1",
      "icebergAllowed": false,
      "inverse": true,
      "index": "BTCUSDT",
      "marginToken": "BTC",
      "marginPrecision": "0.00000001",
      "contractMultiplier": "1.0",
      "underlying": "BTC",
      "riskLimits": [
        {
          "riskLimitId": "200000137",
          "quantity": "1000000.0",
          "initialMargin": "0.01",
          "maintMargin": "0.005"
        },
        {
          "riskLimitId": "200000138",
          "quantity": "2000000.0",
          "initialMargin": "0.02",
          "maintMargin": "0.01"
        },
        {
          "riskLimitId": "200000139",
          "quantity": "3000000.0",
          "initialMargin": "0.03",
          "maintMargin": "0.015"
        },
        {
          "riskLimitId": "200000140",
          "quantity": "4000000.0",
          "initialMargin": "0.04",
          "maintMargin": "0.02"
        }
      ]
    }
  ],
  "coins": [
    {
      "coinId": "ETH",
      "coinName": "ETH",
      "coinFullName": "Ethereum",
      "allowWithdraw": true,
      "allowDeposit": true,
      "chainTypes": []
    },
    {
      "coinId": "USDT",
      "coinName": "USDT",
      "coinFullName": "TetherUS",
      "allowWithdraw": true,
      "allowDeposit": true,
      "chainTypes": [
        {
          "chainType": "ERC20",
          "withdrawFee": "0.1",
          "minWithdrawQuantity": "10",
          "maxWithdrawQuantity": "1000",
          "minDepositQuantity": "1",
          "allowDeposit": true,
          "allowWithdraw": true
        },
        {
          "chainType": "TRC20",
          "withdrawFee": "0.1",
          "minWithdrawQuantity": "10",
          "maxWithdrawQuantity": "1000",
          "allowDeposit": true,
          "allowWithdraw": true
        },
        {
          "chainType": "OMNI",
          "withdrawFee": "0.1",
          "minWithdrawQuantity": "10",
          "maxWithdrawQuantity": "1000",
          "allowDeposit": true,
          "allowWithdraw": true
        }
      ]
    },
    {
      "coinId": "BTC",
      "coinName": "BTC",
      "coinFullName": "Bitcoin",
      "allowWithdraw": false,
      "allowDeposit": false,
      "chainTypes": []
    },
    {
      "coinId": "UNI",
      "coinName": "UNI",
      "coinFullName": "uniswap",
      "allowWithdraw": false,
      "allowDeposit": false,
      "chainTypes": []
    },
    {
      "coinId": "XRP",
      "coinName": "XRP",
      "coinFullName": "XRP",
      "allowWithdraw": false,
      "allowDeposit": false,
      "chainTypes": []
    },
    {
      "coinId": "EOS",
      "coinName": "EOS1",
      "coinFullName": "EOS",
      "allowWithdraw": true,
      "allowDeposit": true,
      "chainTypes": []
    },
    {
      "coinId": "JET",
      "coinName": "JET",
      "coinFullName": "JET",
      "allowWithdraw": false,
      "allowDeposit": false,
      "chainTypes": []
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
101
102
103
104
105
106
107
108
109
110
111
112
113
114
115
116
117
118
119
120
121
122
123
124
125
126
127
128
129
130
131
132
133
134
135
136
137
138
139
140
141
142
143
144
145
146
147
148
149
150
151
152
153
154
155
156
157
158
159
160
161
162
163
164
165
166
167
168
169
170
171
172
173
174
175
176
177
178
179
180
181
182
183
184
185
186
187
188
189
190
191
192
193
194
195
196
197
198
199
200
201
202
203
204
205
206
207
208
209
210
211
212
213
214
215
216
217
218
219
220
221
222
223
224
225
226
227
228
229
230
231
232
233
234
235
236
237
238
239
240
241
242
243
244
245
246
247
248
249
250
251
252
253
254
255
256
257
258
259
260
261
262
263
264
265
266
267
268
269
270
271
272
273
274
275
276
277
278
279
280
281
282
283
284
285
286
287
288
289
290
291
292
293
294
295
296
297
298
299
300
301
302
303
304
305
306
307
308
309
310
311
312
313
314
315
316
317
318
319
320
321
322
323
324
325
326
327
328
329
330
331
332
333
334
335
336
337
338
339
340
341
342
343
344
345
346
347

### Parameters

NONE

## Order Book

  * `GET /quote/v1/depth`

**权重：**

> Response

json
```
{
  "t": 1672035413265,//Matching time
  "b": [
    [
      "3.90000000",   // price
      "431.00000000"  // quantity
    ],
    [
      "4.00000000",
      "431.00000000"
    ]
  ],
  "a": [
    [
      "4.00000200",  // price
      "12.00000000"  // quantity
    ],
    [
      "5.10000000",
      "28.00000000"
    ]
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
limit| INT| NO| Default 100;

Notes: If you set `limit=0`, a lot of data will be returned.

## Recent Trades List

  * `GET /quote/v1/trades`

Get recent trades.

**Weight** : 1

> Response

json
```
[
  {
    "p": "4.00000100",
    "q": "12.00000000",
    "t": 1499865549590,
    "ibm": true  // Transaction direction isBuyerMaker
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES|
limit| INT| NO| Default 60; Max 60.

## Kline/Candlestick Data

  * `GET /quote/v1/klines`

Kline/candlestick bars for a symbol. Klines are uniquely identified by their open time.

**Weight** :1

> Response

json
```
[
  [
    1499040000000,      // Kline open time
    "0.01634790",       // Open price
    "0.80000000",       // High price
    "0.01575800",       //  Low price
    "0.01577100",       // Close price
    "148976.11427815",  // Volume
    1499644799999,      //  Kline Close time
    "2434.19055334",    // Quote asset volume
    308,                // Number of trades
    "1756.87402397",    // Taker buy base asset volume
    "28.46694368"       // Taker buy quote asset volume
  ]
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
interval| ENUM| YES| interval
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
limit| INT| NO| Default 1000; Max 1000.

  * If `startTime` and `endTime` are not sent, only the latest K line will be returned.

## 24hr Ticker Price Change Statistics

  * `GET /quote/v1/ticker/24hr`

24 hour rolling window price change statistics. Careful when accessing this with no symbol.

**Weight** :

1 if only one `symbol` was sent; 40 if no `symbol` was sent.

> Response

json
```
[
    {
        "t": 1538725500422,   // time
        "a": "1.10000000",    // highest selling price
        "b": "1.00000000",    // highest bid
        "s": "ETHUSDT",        // symbol
        "c": "4.00000200",    // latest transaction price
        "o": "99.00000000",   // opening price
        "h": "100.00000000",  // highest price
        "l": "0.10000000",    // lowest price
        "v": "8913.30000000", // Total trade volume (in base asset)
        "qv": "15.30000000",   // otal trade volume (in quote asset)
        "pc": "15.30000000",   // priceChange
        "pcp": "15.30000000"   // priceChangePercent
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| symbol

  * If the symbol is not sent, all symbol data will be returned.

## Symbol Price Ticker

  * `GET /quote/v1/ticker/price`

Latest price for a symbol or symbols.

**Weight** :1

> Response

json
```
[
  {
    "s": "LTCBTC",     // symbol
    "p": "4.00000200"  // price
  }
]
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
symbol| STRING| NO| symbol

  * If the symbol is not sent, all symbol data will be returned.

## Symbol Order Book Ticker

  * `GET /quote/v1/ticker/bookTicker`

Best price/qty on the order book for a symbol or symbols.

**Weight** :1

> Response

json
```
[
  {
      "t": 1672035413265,     // time
      "s": "LTCBTC",            // symbol
      "b": "4.00000000",        // bidPrice
      "bq": "431.00000000",     // bidQty
      "a": "4.00000200",        // askPrice
      "aq": "9.00000000"        // askQty
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| NO| symbol

  * If the symbol is not sent, the best order book price for all symbols will be returned.

## Merge Depth

  * `GET /quote/v1/depth/merged`

**Weight** : 1

> Response

json
```
{
    "t": 1672035413265,//time
    "b": [//Buy Depth High to Low
        [
            "16851.95",//price
            "0.003321"//quantity
        ],
        [
            "16851.87",
            "0.005456"
        ],
        [
            "16851.47",
            "0.002219"
        ]
    ],
    "a": [//Sell Depth Low to High
        [
            "16870.19",
            "0.003838"
        ],
        [
            "16873.05",
            "0.00361"
        ],
        [
            "16873.06",
            "0.002623"
        ]
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
symbol| STRING| YES| symbol
scale| INT| NO| Gears: `0`,`1`,`2`,`3`,`4`,`5` For example: `0`means gear `1`, `1` means gear `2`
limit| INT| NO| limit
