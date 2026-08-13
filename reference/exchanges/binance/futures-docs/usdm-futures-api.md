# Binance USDⓈ-M Futures — API documentation snapshot

Source: developers.binance.com, mirrored as Markdown by
https://github.com/rusty-trading/crypto-exchange-docs (binance.md), filtered here to the
USDⓈ-M futures pages only. Snapshot taken 2026-08-13.

Authoritative cross-check for every endpoint used by our adapter is the official
connector SDK vendored alongside this file in ../futures-connector-python/.

[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Place_Multiple_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders#__docusaurus_skipToContent_fallback)

On this page

# Place Multiple Orders(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders\#api-description "Direct link to API Description")

Place Multiple Orders

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/batchOrders`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders\#request-weight "Direct link to Request Weight")

5 on 10s order rate limit(X-MBX-ORDER-COUNT-10S);
1 on 1min order rate limit(X-MBX-ORDER-COUNT-1M);
5 on IP rate limit(x-mbx-used-weight-1m);

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| batchOrders | LIST<JSON> | YES | order list. Max 5 orders |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

**Where `batchOrders` is the list of order parameters in JSON**

- **Example:** /fapi/v1/batchOrders?batchOrders=\[{"type":"LIMIT","timeInForce":"GTC",\
\
\
"symbol":"BTCUSDT","side":"BUY","price":"10001","quantity":"0.001"}\]

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| side | ENUM | YES |  |
| positionSide | ENUM | NO | Default `BOTH` for One-way Mode ; `LONG` or `SHORT` for Hedge Mode. It must be sent with Hedge Mode. |
| type | ENUM | YES |  |
| timeInForce | ENUM | NO |  |
| quantity | DECIMAL | YES |  |
| reduceOnly | STRING | NO | "true" or "false". default "false". |
| price | DECIMAL | NO |  |
| newClientOrderId | STRING | NO | A unique id among open orders. Automatically generated if not sent. Can only be string following the rule: `^[\.A-Z\:/a-z0-9_-]{1,36}$` |
| stopPrice | DECIMAL | NO | Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| activationPrice | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, default as the latest price(supporting different `workingType`) |
| callbackRate | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, min 0.1, max 4 where 1 for 1% |
| workingType | ENUM | NO | stopPrice triggered by: "MARK\_PRICE", "CONTRACT\_PRICE". Default "CONTRACT\_PRICE" |
| priceProtect | STRING | NO | "TRUE" or "FALSE", default "FALSE". Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| newOrderRespType | ENUM | NO | "ACK", "RESULT", default "ACK" |
| priceMatch | ENUM | NO | only avaliable for `LIMIT`/ `STOP`/ `TAKE_PROFIT` order; can be set to `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`: / `QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`; Can't be passed together with `price` |
| selfTradePreventionMode | ENUM | NO | `EXPIRE_TAKER`:expire taker order when STP triggers/ `EXPIRE_MAKER`:expire taker order when STP triggers/ `EXPIRE_BOTH`:expire both orders when STP triggers; default `NONE` |
| goodTillDate | LONG | NO | order cancel time for timeInForce `GTD`, mandatory when `timeInforce` set to `GTD`; order the timestamp only retains second-level precision, ms part will be ignored; The goodTillDate timestamp must be greater than the current time plus 600 seconds and smaller than 253402300799000 |

> - Paremeter rules are same with `New Order`
> - Batch orders are processed concurrently, and the order of matching is not guaranteed.
> - The order of returned contents for batch orders is the same as the order of the order list.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
	 	"clientOrderId": "testOrder",\
	 	"cumQty": "0",\
	 	"cumQuote": "0",\
	 	"executedQty": "0",\
	 	"orderId": 22542179,\
	 	"avgPrice": "0.00000",\
	 	"origQty": "10",\
	 	"price": "0",\
	  	"reduceOnly": false,\
	  	"side": "BUY",\
	  	"positionSide": "SHORT",\
	  	"status": "NEW",\
	  	"stopPrice": "9300",		// please ignore when order type is TRAILING_STOP_MARKET\
	  	"symbol": "BTCUSDT",\
	  	"timeInForce": "GTC",\
	  	"type": "TRAILING_STOP_MARKET",\
	  	"origType": "TRAILING_STOP_MARKET",\
	  	"activatePrice": "9020",	// activation price, only return with TRAILING_STOP_MARKET order\
	  	"priceRate": "0.3",			// callback rate, only return with TRAILING_STOP_MARKET order\
	 	"updateTime": 1566818724722,\
	 	"workingType": "CONTRACT_PRICE",\
	 	"priceProtect": false,      // if conditional order trigger is protected\
		"priceMatch": "NONE",              //price match mode\
		"selfTradePreventionMode": "NONE", //self trading preventation mode\
		"goodTillDate": 1693207680000      //order pre-set auot cancel time for TIF GTD order\
	},\
	{\
		"code": -2022,\
		"msg": "ReduceOnly Order is rejected."\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Cancel_Order.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order#__docusaurus_skipToContent_fallback)

On this page

# Cancel Order (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order\#api-description "Direct link to API Description")

Cancel an active order.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order\#http-request "Direct link to HTTP Request")

DELETE `/fapi/v1/order`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Either `orderId` or `origClientOrderId` must be sent.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
 	"clientOrderId": "myOrder1",
 	"cumQty": "0",
 	"cumQuote": "0",
 	"executedQty": "0",
 	"orderId": 283194212,
 	"origQty": "11",
 	"origType": "TRAILING_STOP_MARKET",
  	"price": "0",
  	"reduceOnly": false,
  	"side": "BUY",
  	"positionSide": "SHORT",
  	"status": "CANCELED",
  	"stopPrice": "9300",				// please ignore when order type is TRAILING_STOP_MARKET
  	"closePosition": false,   // if Close-All
  	"symbol": "BTCUSDT",
  	"timeInForce": "GTC",
  	"type": "TRAILING_STOP_MARKET",
  	"activatePrice": "9020",			// activation price, only return with TRAILING_STOP_MARKET order
  	"priceRate": "0.3",					// callback rate, only return with TRAILING_STOP_MARKET order
 	"updateTime": 1571110484038,
 	"workingType": "CONTRACT_PRICE",
 	"priceProtect": false,            // if conditional order trigger is protected
	"priceMatch": "NONE",              //price match mode
	"selfTradePreventionMode": "NONE", //self trading preventation mode
	"goodTillDate": 1693207680000      //order pre-set auot cancel time for TIF GTD order
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Modify_Isolated_Position_Margin.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin#__docusaurus_skipToContent_fallback)

On this page

# Modify Isolated Position Margin(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin\#api-description "Direct link to API Description")

Modify Isolated Position Margin

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/positionMargin`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| positionSide | ENUM | NO | Default `BOTH` for One-way Mode ; `LONG` or `SHORT` for Hedge Mode. It must be sent with Hedge Mode. |
| amount | DECIMAL | YES |  |
| type | INT | YES | 1: Add position margin，2: Reduce position margin |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Only for isolated symbol

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"amount": 100.0,
  	"code": 200,
  	"msg": "Successfully modify position margin.",
  	"type": 1
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Isolated-Position-Margin#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Futures_Transaction_History_Download_Link_by_Id.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id#__docusaurus_skipToContent_fallback)

On this page

# Get Futures Transaction History Download Link by Id (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id\#api-description "Direct link to API Description")

Get futures transaction history download link by Id

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/income/asyn/id`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id\#request-weight "Direct link to Request Weight")

**10**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| downloadId | STRING | YES | get by download id api |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Download link expiration: 24h

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
{
	"downloadId":"545923594199212032",
  	"status":"completed",     // Enum：completed，processing
  	"url":"www.binance.com",  // The link is mapped to download id
  	"notified":true,          // ignore
  	"expirationTimestamp":1645009771000,  // The link would expire after this timestamp
  	"isExpired":null,
}

```

> **OR** (Response when server is processing)

```codeBlockLines_aHhF
{
	"downloadId":"545923594199212032",
  	"status":"processing",
  	"url":"",
  	"notified":false,
  	"expirationTimestamp":-1
  	"isExpired":null,

}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Transaction-History-Download-Link-by-Id#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_All_Market_Liquidation_Order_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams#__docusaurus_skipToContent_fallback)

On this page

# All Market Liquidation Order Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams\#stream-description "Direct link to Stream Description")

The All Liquidation Order Snapshot Streams push force liquidation order information for all symbols in the market.
For each symbol，only the latest one liquidation order within 1000ms will be pushed as the snapshot. If no liquidation happens in the interval of 1000ms, no stream will be pushed.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams\#stream-name "Direct link to Stream Name")

`!forceOrder@arr`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams\#update-speed "Direct link to Update Speed")

**1000ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{

	"e":"forceOrder",                   // Event Type
	"E":1568014460893,                  // Event Time
	"o":{

		"s":"BTCUSDT",                   // Symbol
		"S":"SELL",                      // Side
		"o":"LIMIT",                     // Order Type
		"f":"IOC",                       // Time in Force
		"q":"0.014",                     // Original Quantity
		"p":"9910",                      // Price
		"ap":"9910",                     // Average Price
		"X":"FILLED",                    // Order Status
		"l":"0.014",                     // Order Last Filled Quantity
		"z":"0.014",                     // Order Filled Accumulated Quantity
		"T":1568014460893,          	 // Order Trade Time
	}
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_All_Market_Mini_Tickers_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream#__docusaurus_skipToContent_fallback)

On this page

# All Market Mini Tickers Stream

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream\#stream-description "Direct link to Stream Description")

24hr rolling window mini-ticker statistics for all symbols. These are NOT the statistics of the UTC day, but a 24hr rolling window from requestTime to 24hrs before. Note that only tickers that have changed will be present in the array.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream\#stream-name "Direct link to Stream Name")

`!miniTicker@arr`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream\#update-speed "Direct link to Update Speed")

**1000ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
    "e": "24hrMiniTicker",  // Event type\
    "E": 123456789,         // Event time\
    "s": "BTCUSDT",         // Symbol\
    "c": "0.0025",          // Close price\
    "o": "0.0010",          // Open price\
    "h": "0.0025",          // High price\
    "l": "0.0010",          // Low price\
    "v": "10000",           // Total traded base asset volume\
    "q": "18"               // Total traded quote asset volume\
  }\
]

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_faq_stp_faq.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#__docusaurus_skipToContent_fallback)

On this page

# Self Trade Prevention (STP) FAQ

## What is Self Trade Prevention? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#what-is-self-trade-prevention "Direct link to What is Self Trade Prevention?")

Self Trade Prevention (or STP) prevents orders of users, or the user's `tradeGroupId` to match against their own.

## What defines a self-trade? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#what-defines-a-self-trade "Direct link to What defines a self-trade?")

A self-trade can occur in either scenario:

- The order traded against the same account.
- The order traded against an account with the same `tradeGroupId`.

## What happens when STP is triggered? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#what-happens-when-stp-is-triggered "Direct link to What happens when STP is triggered?")

There are three possible modes for what the system will do if an order could create a self-trade.

`EXPIRE_TAKER` \- This mode prevents a trade by immediately expiring the taker order's remaining quantity.

`EXPIRE_MAKER` \- This mode prevents a trade by immediately expiring the potential maker order's remaining quantity.

`EXPIRE_BOTH` \- This mode prevents a trade by immediately expiring both the taker and the potential maker orders' remaining quantities.

The STP event will occur depending on the STP mode of the **taker order**.

Thus, the STP mode of an order that goes on the book is no longer relevant and will be ignored for all future order processing.

## Where do I set STP mode for an order? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#where-do-i-set-stp-mode-for-an-order "Direct link to Where do I set STP mode for an order?")

STP can only be set using field `selfTradePreventionMode` through API endpoints below:

- POST `/fapi/v1/order`
- POST `/fapi/v1/batchOrders`

## What is a Trade Group Id? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#what-is-a-trade-group-id "Direct link to What is a Trade Group Id?")

Different accounts with the same `tradeGroupId` are considered part of the same "trade group". Orders submitted by members of a trade group are eligible for STP according to the taker-order's STP mode.

A user can confirm if their accounts are under the same `tradeGroupId` from the API either from `GET fapi/v3/account` (REST API).

If the value is `-1`, then the `tradeGroupId` has not been set for that account, so the STP may only take place between orders of the same account.

We will release feature for user to group subaccounts to same `tradeGroupId` on website in future updates.

## How do I know which symbol uses STP? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#how-do-i-know-which-symbol-uses-stp "Direct link to How do I know which symbol uses STP?")

Placing orders on all symbols in `GET fapi/v1/exchangeInfo` can set `selfTradePreventionMode`.

## What order types support STP? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#what-order-types-support-stp "Direct link to What order types support STP?")

`LIMIT`/ `MARKET`/ `STOP`/ `TAKE_PROFIT`/ `STOP_MARKET`/ `TAKE_PROFIT_MARKET`/ `TRAILING_STOP_MARKET` all supports STP when Time in force(timeInForce) set to `GTC`/ `IOC`/ `GTD`.
STP won't take effect for Time in force(timeInForce) `FOK` or `GTX`

## Does Modify order support STP? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#does-modify-order-support-stp "Direct link to Does Modify order support STP?")

No. Modify order that has reset `selfTradePreventionMode` to `NONE`

## How do I know if an order expired due to STP? [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#how-do-i-know-if-an-order-expired-due-to-stp "Direct link to How do I know if an order expired due to STP?")

The order will have the status `EXPIRED_IN_MATCH`.

In user data stream event `ORDER_TRADE_UPDATE`, field `X` would be `EXPIRED_IN_MATCH` if order is expired due to STP

```codeBlockLines_aHhF
{
  "e":"ORDER_TRADE_UPDATE",      // Event Type
  "E":1568879465651,             // Event Time
  "T":1568879465650,             // Transaction Time
  "o":{
    "s":"BTCUSDT",               // Symbol
    "c":"TEST",                  // Client Order Id
      // special client order id:
      // starts with "autoclose-": liquidation order
      // "adl_autoclose": ADL auto close order
      // "settlement_autoclose-": settlement order for delisting or delivery
    "S":"SELL",                  // Side
    "o":"TRAILING_STOP_MARKET",  // Order Type
    "f":"GTC",                   // Time in Force
    "q":"0.001",                 // Original Quantity
    "p":"0",                     // Original Price
    "ap":"0",                    // Average Price
    "sp":"7103.04",              // Stop Price. Please ignore with TRAILING_STOP_MARKET order
    "x":"EXPIRED",               // Execution Type
    "X":"EXPIRED_IN_MATCH",      // Order Status
    "i":8886774,                 // Order Id
    "l":"0",                     // Order Last Filled Quantity
    "z":"0",                     // Order Filled Accumulated Quantity
    "L":"0",                     // Last Filled Price
    "N":"USDT",                  // Commission Asset, will not push if no commission
    "n":"0",                     // Commission, will not push if no commission
    "T":1568879465650,           // Order Trade Time
    "t":0,                       // Trade Id
    "b":"0",                     // Bids Notional
    "a":"9.91",                  // Ask Notional
    "m":false,                   // Is this trade the maker side?
    "R":false,                   // Is this reduce only
    "wt":"CONTRACT_PRICE",       // Stop Price Working Type
    "ot":"TRAILING_STOP_MARKET", // Original Order Type
    "ps":"LONG",                 // Position Side
    "cp":false,                  // If Close-All, pushed with conditional order
    "AP":"7476.89",              // Activation Price, only puhed with TRAILING_STOP_MARKET order
    "cr":"5.0",                  // Callback Rate, only puhed with TRAILING_STOP_MARKET order
    "pP": false,                 // ignore
    "si": 0,                     // ignore
    "ss": 0,                     // ignore
    "rp":"0",                    // Realized Profit of the trade
    "V": "EXPIRE_MAKER",         // selfTradePreventionMode
    "pm":"QUEUE",                // price match type
    "gtd":1768879465650          // good till date
   }
}

```

## STP Examples: [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq\#stp-examples "Direct link to STP Examples:")

For all these cases, assume that all orders for these examples are made on the same account.

**Scenario A- A user sends an order with `EXPIRE_MAKER` that would match with their orders that are already on the book.**

```codeBlockLines_aHhF
Maker Order 1: symbol=BTCUSDT side=BUY  type=LIMIT quantity=1 price=20002 selfTradePreventionMode=EXPIRE_MAKER
Maker Order 2: symbol=BTCUSDT side=BUY  type=LIMIT quantity=1 price=20001 selfTradePreventionMode=EXPIRE_MAKER
Taker Order 1: symbol=BTCUSDT side=SELL type=LIMIT quantity=1 price=20000 selfTradePreventionMode=EXPIRE_MAKER

```

**Result**: The orders that were on the book will expire due to STP, and the taker order will go on the book.

Maker Order 1

```codeBlockLines_aHhF
{
    "orderId": 292864710,
    "symbol": "BTCUSDT",
    "status": "FILLED",
    "clientOrderId": "testMaker1",
    "price": "20002",
    "avgPrice": "20002",
    "origQty": "1",
    "executedQty": "1",
    "cumQuote": "20002",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

Maker Order 2

```codeBlockLines_aHhF
{
    "orderId": 292864711,
    "symbol": "BTCUSDT",
    "status": "EXPIRED_IN_MATCH",
    "clientOrderId": "testMaker2",
    "price": "20001",
    "avgPrice": "0.0000",
    "origQty": "1",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

Output of the Taker Order

```codeBlockLines_aHhF
{
    "orderId": 292864712,
    "symbol": "BTCUSDT",
    "status": "PARTIALLY_FILLED",
    "clientOrderId": "testTaker1",
    "price": "20000",
    "avgPrice": "20002",
    "origQty": "2",
    "executedQty": "1",
    "cumQuote": "20002",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "SELL",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

**Scenario B - A user sends an order with `EXPIRE_TAKER` that would match with their orders already on the book.**

```codeBlockLines_aHhF
Maker Order 1: symbol=BTCUSDT side=BUY  type=LIMIT quantity=1 price=20002  selfTradePreventionMode=EXPIRE_MAKER
Maker Order 2: symbol=BTCUSDT side=BUY  type=LIMIT quantity=1 price=20001  selfTradePreventionMode=EXPIRE_MAKER
Taker Order 1: symbol=BTCUSDT side=SELL type=LIMIT quantity=2 price=3      selfTradePreventionMode=EXPIRE_TAKER

```

**Result**: The orders already on the book will remain, while the taker order will expire.

Maker Order 1

```codeBlockLines_aHhF
{
    "orderId": 292864710,
    "symbol": "BTCUSDT",
    "status": "FILLED",
    "clientOrderId": "testMaker1",
    "price": "20002",
    "avgPrice": "0.0000",
    "origQty": "1",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

Maker Order 2

```codeBlockLines_aHhF
{
    "orderId": 292864711,
    "symbol": "BTCUSDT",
    "status": "EXPIRED_IN_MATCH",
    "clientOrderId": "testMaker2",
    "price": "20001",
    "avgPrice": "0.0000",
    "origQty": "1",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

Output of the Taker order

```codeBlockLines_aHhF
{
    "orderId": 292864712,
    "symbol": "BTCUSDT",
    "status": "EXPIRED_IN_MATCH",
    "clientOrderId": "testTaker1",
    "price": "20000",
    "avgPrice": "0.0000",
    "origQty": "3",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "SELL",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_TAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

**Scenario C- A user has an order on the book, and then sends an order with `EXPIRE_BOTH` that would match with the existing order.**

```codeBlockLines_aHhF
Maker Order: symbol=BTCUSDT side=BUY  type=LIMIT quantity=1 price=20002 selfTradePreventionMode=EXPIRE_MAKER
Taker Order: symbol=BTCUSDT side=SELL type=LIMIT quantity=3 price=20000 selfTradePreventionMode=EXPIRE_BOTH

```

**Result:** Both orders will expire.

Maker Order

```codeBlockLines_aHhF
{
    "orderId": 292864710,
    "symbol": "BTCUSDT",
    "status": "EXPIRED_IN_MATCH",
    "clientOrderId": "testMaker1",
    "price": "20002",
    "avgPrice": "0.0000",
    "origQty": "1",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

Taker Order

```codeBlockLines_aHhF
{
    "orderId": 292864712,
    "symbol": "BTCUSDT",
    "status": "EXPIRED_IN_MATCH",
    "clientOrderId": "testTaker1",
    "price": "20000",
    "avgPrice": "0.0000",
    "origQty": "3",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "SELL",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_BOTH",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

**Scenario D - A user has an order on the book with `EXPIRE_MAKER`, and then sends a new order with `EXPIRE_TAKER` which would match with the existing order.**

```codeBlockLines_aHhF
Maker Order: symbol=BTCUSDT side=BUY  type=LIMIT quantity=1 price=1 selfTradePreventionMode=EXPIRE_MAKER
Taker Order: symbol=BTCUSDT side=SELL type=LIMIT quantity=1 price=1 selfTradePreventionMode=EXPIRE_TAKER

```

**Result**: The taker order's STP mode will be used, so the taker order will be expired.

Maker Order

```codeBlockLines_aHhF
{
    "orderId": 292864710,
    "symbol": "BTCUSDT",
    "status": "NEW",
    "clientOrderId": "testMaker1",
    "price": "20002",
    "avgPrice": "0.0000",
    "origQty": "1",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

Taker Order

```codeBlockLines_aHhF
{
    "orderId": 292864712,
    "symbol": "BTCUSDT",
    "status": "EXPIRED_IN_MATCH",
    "clientOrderId": "testTaker1",
    "price": "20000",
    "avgPrice": "0.0000",
    "origQty": "3",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "SELL",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_TAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

**Scenario E - A user sends a market order with `EXPIRE_MAKER` which would match with an existing order.**

```codeBlockLines_aHhF
Maker Order: symbol=ABCDEF side=BUY  type=LIMIT  quantity=1 price=1  selfTradePreventionMode=EXPIRE_MAKER
Taker Order: symbol=ABCDEF side=SELL type=MARKET quantity=3          selfTradePreventionMode=EXPIRE_MAKER

```

**Result**: The existing order expires with the status `EXPIRED_IN_MATCH`, due to STP.
The new order also expires but with status `EXPIRED`, due to low liquidity on the order book.

Maker Order

```codeBlockLines_aHhF
{
    "orderId": 292864710,
    "symbol": "BTCUSDT",
    "status": "EXPIRED_IN_MATCH",
    "clientOrderId": "testMaker1",
    "price": "20002",
    "avgPrice": "0.0000",
    "origQty": "1",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

Taker Order

```codeBlockLines_aHhF
{
    "orderId": 292864712,
    "symbol": "BTCUSDT",
    "status": "EXPIRED",
    "clientOrderId": "testTaker1",
    "price": "20000",
    "avgPrice": "0.0000",
    "origQty": "3",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "SELL",
    "positionSide": "BOTH",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "EXPIRE_MAKER",
    "goodTillDate": "null",
    "priceProtect": false,
    "origType": "LIMIT",
    "time": 1692849639460,
    "updateTime": 1692849639460
}

```

- [What is Self Trade Prevention?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#what-is-self-trade-prevention)
- [What defines a self-trade?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#what-defines-a-self-trade)
- [What happens when STP is triggered?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#what-happens-when-stp-is-triggered)
- [Where do I set STP mode for an order?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#where-do-i-set-stp-mode-for-an-order)
- [What is a Trade Group Id?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#what-is-a-trade-group-id)
- [How do I know which symbol uses STP?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#how-do-i-know-which-symbol-uses-stp)
- [What order types support STP?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#what-order-types-support-stp)
- [Does Modify order support STP?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#does-modify-order-support-stp)
- [How do I know if an order expired due to STP?](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#how-do-i-know-if-an-order-expired-due-to-stp)
- [STP Examples:](https://developers.binance.com/docs/derivatives/usds-margined-futures/faq/stp-faq#stp-examples)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Futures_Trading_Quantitative_Rules_Indicators.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators#__docusaurus_skipToContent_fallback)

On this page

# Futures Trading Quantitative Rules Indicators (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators\#api-description "Direct link to API Description")

Futures trading quantitative rules indicators, for more information on this, please refer to the [Futures Trading Quantitative Rules](https://www.binance.com/en/support/faq/4f462ebe6ff445d4a170be7d9e897272)

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/apiTradingStatus`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators\#request-weight "Direct link to Request Weight")

- **1** for a single symbol
- **10** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
{
    "indicators": { // indicator: quantitative rules indicators, value: user's indicators value, triggerValue: trigger indicator value threshold of quantitative rules.
        "BTCUSDT": [\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "UFR",  // Unfilled Ratio (UFR)\
                "value": 0.05,  // Current value\
                "triggerValue": 0.995  // Trigger value\
            },\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "IFER",  // IOC/FOK Expiration Ratio (IFER)\
                "value": 0.99,  // Current value\
                "triggerValue": 0.99  // Trigger value\
            },\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "GCR",  // GTC Cancellation Ratio (GCR)\
                "value": 0.99,  // Current value\
                "triggerValue": 0.99  // Trigger value\
            },\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "DR",  // Dust Ratio (DR)\
                "value": 0.99,  // Current value\
                "triggerValue": 0.99  // Trigger value\
            }\
        ],
        "ETHUSDT": [\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "UFR",\
                "value": 0.05,\
                "triggerValue": 0.995\
            },\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "IFER",\
                "value": 0.99,\
                "triggerValue": 0.99\
            },\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "GCR",\
                "value": 0.99,\
                "triggerValue": 0.99\
            }\
            {\
				"isLocked": true,\
			    "plannedRecoverTime": 1545741270000,\
                "indicator": "DR",\
                "value": 0.99,\
                "triggerValue": 0.99\
            }\
        ]
    },
    "updateTime": 1545741270000
}

```

> Or (account violation triggered)

```codeBlockLines_aHhF
{
    "indicators":{
        "ACCOUNT":[\
            {\
                "indicator":"TMV",  //  Too many violations under multiple symbols trigger account violation\
                "value":10,\
                "triggerValue":1,\
                "plannedRecoverTime":1644919865000,\
                "isLocked":true\
            }\
        ]
    },
    "updateTime":1644913304748
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Trading-Quantitative-Rules-Indicators#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api#__docusaurus_skipToContent_fallback)

On this page

# New Order(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api\#api-description "Direct link to API Description")

Send in a new order.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/order`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api\#request-weight "Direct link to Request Weight")

1 on 10s order rate limit(X-MBX-ORDER-COUNT-10S);
1 on 1min order rate limit(X-MBX-ORDER-COUNT-1M);
0 on IP rate limit(x-mbx-used-weight-1m)

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| side | ENUM | YES |  |
| positionSide | ENUM | NO | Default `BOTH` for One-way Mode ; `LONG` or `SHORT` for Hedge Mode. It must be sent in Hedge Mode. |
| type | ENUM | YES |  |
| timeInForce | ENUM | NO |  |
| quantity | DECIMAL | NO | Cannot be sent with `closePosition` = `true`(Close-All) |
| reduceOnly | STRING | NO | "true" or "false". default "false". Cannot be sent in Hedge Mode; cannot be sent with `closePosition` = `true` |
| price | DECIMAL | NO |  |
| newClientOrderId | STRING | NO | A unique id among open orders. Automatically generated if not sent. Can only be string following the rule: `^[\.A-Z\:/a-z0-9_-]{1,36}$` |
| stopPrice | DECIMAL | NO | Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| closePosition | STRING | NO | `true`, `false`；Close-All，used with `STOP_MARKET` or `TAKE_PROFIT_MARKET`. |
| activationPrice | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, default as the latest price(supporting different `workingType`) |
| callbackRate | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, min 0.1, max 10 where 1 for 1% |
| workingType | ENUM | NO | stopPrice triggered by: "MARK\_PRICE", "CONTRACT\_PRICE". Default "CONTRACT\_PRICE" |
| priceProtect | STRING | NO | "TRUE" or "FALSE", default "FALSE". Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| newOrderRespType | ENUM | NO | "ACK", "RESULT", default "ACK" |
| priceMatch | ENUM | NO | only avaliable for `LIMIT`/ `STOP`/ `TAKE_PROFIT` order; can be set to `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`: / `QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`; Can't be passed together with `price` |
| selfTradePreventionMode | ENUM | NO | `EXPIRE_TAKER`:expire taker order when STP triggers/ `EXPIRE_MAKER`:expire taker order when STP triggers/ `EXPIRE_BOTH`:expire both orders when STP triggers; default `NONE` |
| goodTillDate | LONG | NO | order cancel time for timeInForce `GTD`, mandatory when `timeInforce` set to `GTD`; order the timestamp only retains second-level precision, ms part will be ignored; The goodTillDate timestamp must be greater than the current time plus 600 seconds and smaller than 253402300799000 |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

Additional mandatory parameters based on `type`:

| Type | Additional mandatory parameters |
| --- | --- |
| `LIMIT` | `timeInForce`, `quantity`, `price` |
| `MARKET` | `quantity` |
| `STOP/TAKE_PROFIT` | `quantity`, `price`, `stopPrice` |
| `STOP_MARKET/TAKE_PROFIT_MARKET` | `stopPrice` |
| `TRAILING_STOP_MARKET` | `callbackRate` |

> - Order with type `STOP`, parameter `timeInForce` can be sent ( default `GTC`).
>
> - Order with type `TAKE_PROFIT`, parameter `timeInForce` can be sent ( default `GTC`).
>
> - Condition orders will be triggered when:
>   - If parameter `priceProtect` is sent as true:
>
>     - when price reaches the `stopPrice` ，the difference rate between "MARK\_PRICE" and "CONTRACT\_PRICE" cannot be larger than the "triggerProtect" of the symbol
>     - "triggerProtect" of a symbol can be got from `GET /fapi/v1/exchangeInfo`
>   - `STOP`, `STOP_MARKET`:
>
>     - BUY: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") >= `stopPrice`
>     - SELL: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") <= `stopPrice`
>   - `TAKE_PROFIT`, `TAKE_PROFIT_MARKET`:
>
>     - BUY: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") <= `stopPrice`
>     - SELL: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") >= `stopPrice`
>   - `TRAILING_STOP_MARKET`:
>
>     - BUY: the lowest price after order placed `<= ` activationPrice `, and the latest price >` = the lowest price \* (1 + `callbackRate`)
>     - SELL: the highest price after order placed >= `activationPrice`, and the latest price <= the highest price \* (1 - `callbackRate`)
> - For `TRAILING_STOP_MARKET`, if you got such error code.
>
>   `{"code": -2021, "msg": "Order would immediately trigger."}`
>
>
>   means that the parameters you send do not meet the following requirements:
>   - BUY: `activationPrice` should be smaller than latest price.
>   - SELL: `activationPrice` should be larger than latest price.
> - If `newOrderRespType ` is sent as `RESULT` :
>   - `MARKET` order: the final FILLED result of the order will be return directly.
>   - `LIMIT` order with special `timeInForce`: the final status result of the order(FILLED or EXPIRED) will be returned directly.
> - `STOP_MARKET`, `TAKE_PROFIT_MARKET` with `closePosition` = `true`:
>   - Follow the same rules for condition orders.
>   - If triggered， **close all** current long position( if `SELL`) or current short position( if `BUY`).
>   - Cannot be used with `quantity` paremeter
>   - Cannot be used with `reduceOnly` parameter
>   - In Hedge Mode,cannot be used with `BUY` orders in `LONG` position side. and cannot be used with `SELL` orders in `SHORT` position side
> - `selfTradePreventionMode` is only effective when `timeInForce` set to `IOC` or `GTC` or `GTD`.
>
> - In extreme market conditions, timeInForce `GTD` order auto cancel time might be delayed comparing to `goodTillDate`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
 	"clientOrderId": "testOrder",
 	"cumQty": "0",
 	"cumQuote": "0",
 	"executedQty": "0",
 	"orderId": 22542179,
 	"avgPrice": "0.00000",
 	"origQty": "10",
 	"price": "0",
  	"reduceOnly": false,
  	"side": "BUY",
  	"positionSide": "SHORT",
  	"status": "NEW",
  	"stopPrice": "9300",		// please ignore when order type is TRAILING_STOP_MARKET
  	"closePosition": false,   // if Close-All
  	"symbol": "BTCUSDT",
  	"timeInForce": "GTD",
  	"type": "TRAILING_STOP_MARKET",
  	"origType": "TRAILING_STOP_MARKET",
  	"activatePrice": "9020",	// activation price, only return with TRAILING_STOP_MARKET order
  	"priceRate": "0.3",			// callback rate, only return with TRAILING_STOP_MARKET order
 	"updateTime": 1566818724722,
 	"workingType": "CONTRACT_PRICE",
 	"priceProtect": false,      // if conditional order trigger is protected
 	"priceMatch": "NONE",              //price match mode
 	"selfTradePreventionMode": "NONE", //self trading preventation mode
 	"goodTillDate": 1693207680000      //order pre-set auot cancel time for TIF GTD order
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_Order_Update.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update#__docusaurus_skipToContent_fallback)

On this page

# Event: Order Update

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update\#event-description "Direct link to Event Description")

When new order created, order status changed will push such event.
event type is `ORDER_TRADE_UPDATE`.

**Side**

- BUY
- SELL

**Order Type**

- LIMIT
- MARKET
- STOP
- STOP\_MARKET
- TAKE\_PROFIT
- TAKE\_PROFIT\_MARKET
- TRAILING\_STOP\_MARKET
- LIQUIDATION

**Execution Type**

- NEW
- CANCELED
- CALCULATED - Liquidation Execution
- EXPIRED
- TRADE
- AMENDMENT - Order Modified

**Order Status**

- NEW
- PARTIALLY\_FILLED
- FILLED
- CANCELED
- EXPIRED
- EXPIRED\_IN\_MATCH

**Time in force**

- GTC
- IOC
- FOK
- GTX

**Working Type**

- MARK\_PRICE
- CONTRACT\_PRICE

**Liquidation and ADL:**

- If user gets liquidated due to insufficient margin balance:
  - `c` shows as "autoclose-XXX"， `X` shows as "NEW"
- If user has enough margin balance but gets ADL:
  - `c` shows as “adl\_autoclose”， `X` shows as “NEW”

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update\#event-name "Direct link to Event Name")

`ORDER_TRADE_UPDATE`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e":"ORDER_TRADE_UPDATE",		   // Event Type
  "E":1568879465651,			       // Event Time
  "T":1568879465650,			       // Transaction Time
  "o":{
    "s":"BTCUSDT",			         // Symbol
    "c":"TEST",				           // Client Order Id
      // special client order id:
      // starts with "autoclose-": liquidation order
      // "adl_autoclose": ADL auto close order
      // "settlement_autoclose-": settlement order for delisting or delivery
    "S":"SELL",					         // Side
    "o":"TRAILING_STOP_MARKET",	 // Order Type
    "f":"GTC",					         // Time in Force
    "q":"0.001",				         // Original Quantity
    "p":"0",					           // Original Price
    "ap":"0",					           // Average Price
    "sp":"7103.04",				       // Stop Price. Please ignore with TRAILING_STOP_MARKET order
    "x":"NEW",					         // Execution Type
    "X":"NEW",					         // Order Status
    "i":8886774,				         // Order Id
    "l":"0",					           // Order Last Filled Quantity
    "z":"0",					           // Order Filled Accumulated Quantity
    "L":"0",					           // Last Filled Price
    "N":"USDT",            	     // Commission Asset, will not push if no commission
    "n":"0",               	     // Commission, will not push if no commission
    "T":1568879465650,			     // Order Trade Time
    "t":0,			        	       // Trade Id
    "b":"0",			    	         // Bids Notional
    "a":"9.91",					         // Ask Notional
    "m":false,					         // Is this trade the maker side?
    "R":false,					         // Is this reduce only
    "wt":"CONTRACT_PRICE", 		   // Stop Price Working Type
    "ot":"TRAILING_STOP_MARKET", // Original Order Type
    "ps":"LONG",					       // Position Side
    "cp":false,						       // If Close-All, pushed with conditional order
    "AP":"7476.89",				       // Activation Price, only puhed with TRAILING_STOP_MARKET order
    "cr":"5.0",					         // Callback Rate, only puhed with TRAILING_STOP_MARKET order
    "pP": false,                 // If price protection is turned on
    "si": 0,                     // ignore
    "ss": 0,                     // ignore
    "rp":"0",	   					       // Realized Profit of the trade
    "V":"EXPIRE_TAKER",          // STP mode
    "pm":"OPPONENT",             // Price match mode
    "gtd":0                      // TIF GTD order auto cancel time
  }
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Order-Update#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Old_Trades_Lookup.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup#__docusaurus_skipToContent_fallback)

On this page

# Old Trades Lookup (MARKET\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup\#api-description "Direct link to API Description")

Get older market historical trades.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/historicalTrades`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup\#request-weight "Direct link to Request Weight")

**20**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| limit | INT | NO | Default 100; max 500. |
| fromId | LONG | NO | TradeId to fetch from. Default gets most recent trades. |

> - Market trades means trades filled in the order book. Only market trades will be returned, which means the insurance fund trades and ADL trades won't be returned.
> - Only supports data from within the last three months

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
    "id": 28457,\
    "price": "4.00000100",\
    "qty": "12.00000000",\
    "quoteQty": "8000.00",\
    "time": 1499865549590,\
    "isBuyerMaker": true,\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Old-Trades-Lookup#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Multi_Assets_Mode_Asset_Index.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index#__docusaurus_skipToContent_fallback)

On this page

# Multi-Assets Mode Asset Index

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index\#api-description "Direct link to API Description")

asset index for Multi-Assets mode

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/assetIndex`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index\#request-weight "Direct link to Request Weight")

**1** for a single symbol; **10** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO | Asset pair |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
{
	"symbol": "ADAUSD",
	"time": 1635740268004,
	"index": "1.92957370",
	"bidBuffer": "0.10000000",
	"askBuffer": "0.10000000",
	"bidRate": "1.73661633",
	"askRate": "2.12253107",
	"autoExchangeBidBuffer": "0.05000000",
	"autoExchangeAskBuffer": "0.05000000",
	"autoExchangeBidRate": "1.83309501",
	"autoExchangeAskRate": "2.02605238"
}

```

> Or(without symbol)

```codeBlockLines_aHhF
[\
	{\
		"symbol": "ADAUSD",\
		"time": 1635740268004,\
		"index": "1.92957370",\
		"bidBuffer": "0.10000000",\
		"askBuffer": "0.10000000",\
		"bidRate": "1.73661633",\
		"askRate": "2.12253107",\
		"autoExchangeBidBuffer": "0.05000000",\
		"autoExchangeAskBuffer": "0.05000000",\
		"autoExchangeBidRate": "1.83309501",\
		"autoExchangeAskRate": "2.02605238"\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Multi-Assets-Mode-Asset-Index#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Query_Rate_Limit.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit#__docusaurus_skipToContent_fallback)

On this page

# Query User Rate Limit (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit\#api-description "Direct link to API Description")

Query User Rate Limit

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/rateLimit/order`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
    "rateLimitType": "ORDERS",\
    "interval": "SECOND",\
    "intervalNum": 10,\
    "limit": 10000,\
  },\
  {\
    "rateLimitType": "ORDERS",\
    "interval": "MINUTE",\
    "intervalNum": 1,\
    "limit": 20000,\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Query-Rate-Limit#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Delivery_Price.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price#__docusaurus_skipToContent_fallback)

On this page

# Quarterly Contract Settlement Price

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price\#api-description "Direct link to API Description")

Latest price for a symbol or symbols.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price\#http-request "Direct link to HTTP Request")

GET `/futures/data/delivery-price`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price\#request-weight "Direct link to Request Weight")

**0**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| pair | STRING | YES | e.g BTCUSDT |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
        "deliveryTime": 1695945600000,\
        "deliveryPrice": 27103.00000000\
    },\
    {\
        "deliveryTime": 1688083200000,\
        "deliveryPrice": 30733.60000000\
    },\
    {\
        "deliveryTime": 1680220800000,\
        "deliveryPrice": 27814.20000000\
    },\
    {\
        "deliveryTime": 1648166400000,\
        "deliveryPrice": 44066.30000000\
    }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Delivery-Price#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Get_Order_Modify_History.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History#__docusaurus_skipToContent_fallback)

On this page

# Get Order Modify History (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History\#api-description "Direct link to API Description")

Get order modification history

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/orderAmendment`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| startTime | LONG | NO | Timestamp in ms to get modification history from INCLUSIVE |
| endTime | LONG | NO | Timestamp in ms to get modification history until INCLUSIVE |
| limit | INT | NO | Default 50; max 100 |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Either `orderId` or `origClientOrderId` must be sent, and the `orderId` will prevail if both are sent.
> - Order modify history longer than 3 month is not avaliable

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
        "amendmentId": 5363,	// Order modification ID\
        "symbol": "BTCUSDT",\
        "pair": "BTCUSDT",\
        "orderId": 20072994037,\
        "clientOrderId": "LJ9R4QZDihCaS8UAOOLpgW",\
        "time": 1629184560899,	// Order modification time\
        "amendment": {\
            "price": {\
                "before": "30004",\
                "after": "30003.2"\
            },\
            "origQty": {\
                "before": "1",\
                "after": "1"\
            },\
            "count": 3	// Order modification count, representing the number of times the order has been modified\
        }\
    },\
    {\
        "amendmentId": 5361,\
        "symbol": "BTCUSDT",\
        "pair": "BTCUSDT",\
        "orderId": 20072994037,\
        "clientOrderId": "LJ9R4QZDihCaS8UAOOLpgW",\
        "time": 1629184533946,\
        "amendment": {\
            "price": {\
                "before": "30005",\
                "after": "30004"\
            },\
            "origQty": {\
                "before": "1",\
                "after": "1"\
            },\
            "count": 2\
        }\
    },\
    {\
        "amendmentId": 5325,\
        "symbol": "BTCUSDT",\
        "pair": "BTCUSDT",\
        "orderId": 20072994037,\
        "clientOrderId": "LJ9R4QZDihCaS8UAOOLpgW",\
        "time": 1629182711787,\
        "amendment": {\
            "price": {\
                "before": "30002",\
                "after": "30005"\
            },\
            "origQty": {\
                "before": "1",\
                "after": "1"\
            },\
            "count": 1\
        }\
    }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Order-Modify-History#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Mark_Price_Stream_for_All_market.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market#__docusaurus_skipToContent_fallback)

On this page

# Mark Price Stream for All market

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market\#stream-description "Direct link to Stream Description")

Mark price and funding rate for all symbols pushed every 3 seconds or every second.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market\#stream-name "Direct link to Stream Name")

`!markPrice@arr` or `!markPrice@arr@1s`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market\#update-speed "Direct link to Update Speed")

**3000ms** or **1000ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
    "e": "markPriceUpdate",  	// Event type\
    "E": 1562305380000,      	// Event time\
    "s": "BTCUSDT",          	// Symbol\
    "p": "11185.87786614",   	// Mark price\
    "i": "11784.62659091"		// Index price\
    "P": "11784.25641265",		// Estimated Settle Price, only useful in the last hour before the settlement starts\
    "r": "0.00030000",       	// Funding rate\
    "T": 1562306400000       	// Next funding time\
  }\
]

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream-for-All-market#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_Trade_Lite.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Trade-Lite#__docusaurus_skipToContent_fallback)

On this page

# Event: Trade Lite Update

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Trade-Lite\#event-description "Direct link to Event Description")

Fast trade stream reduces data latency compared original `ORDER_TRADE_UPDATE` stream. However, it only pushes TRADE Execution Type, and fewer data fields.

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Trade-Lite\#event-name "Direct link to Event Name")

`TRADE_LITE`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Trade-Lite\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e":"TRADE_LITE",             // Event Type
  "E":1721895408092,            // Event Time
  "T":1721895408214,            // Transaction Time
  "s":"BTCUSDT",                // Symbol
  "q":"0.001",                  // Original Quantity
  "p":"0",                      // Original Price
  "m":false,                    // Is this trade the maker side?
  "c":"z8hcUoOsqEdKMeKPSABslD", // Client Order Id
      // special client order id:
      // starts with "autoclose-": liquidation order
      // "adl_autoclose": ADL auto close order
      // "settlement_autoclose-": settlement order for delisting or delivery
  "S":"BUY",                   // Side
  "L":"64089.20",              // Last Filled Price
  "l":"0.040",                 // Order Last Filled Quantity
  "t":109100866,               // Trade Id
  "i":8886774,                // Order Id
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Trade-Lite#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Trade-Lite#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Trade-Lite#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_All_Market_Tickers_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams#__docusaurus_skipToContent_fallback)

On this page

# All Market Tickers Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams\#stream-description "Direct link to Stream Description")

24hr rolling window ticker statistics for all symbols. These are NOT the statistics of the UTC day, but a 24hr rolling window from requestTime to 24hrs before. Note that only tickers that have changed will be present in the array.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams\#stream-name "Direct link to Stream Name")

`!ticker@arr`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams\#update-speed "Direct link to Update Speed")

**1000ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
	  "e": "24hrTicker",  // Event type\
	  "E": 123456789,     // Event time\
	  "s": "BTCUSDT",     // Symbol\
	  "p": "0.0015",      // Price change\
	  "P": "250.00",      // Price change percent\
	  "w": "0.0018",      // Weighted average price\
	  "c": "0.0025",      // Last price\
	  "Q": "10",          // Last quantity\
	  "o": "0.0010",      // Open price\
	  "h": "0.0025",      // High price\
	  "l": "0.0010",      // Low price\
	  "v": "10000",       // Total traded base asset volume\
	  "q": "18",          // Total traded quote asset volume\
	  "O": 0,             // Statistics open time\
	  "C": 86400000,      // Statistics close time\
	  "F": 0,             // First trade ID\
	  "L": 18150,         // Last trade Id\
	  "n": 18151          // Total number of trades\
	}\
]

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Tickers-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Symbol_Order_Book_Ticker.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker#__docusaurus_skipToContent_fallback)

On this page

# Symbol Order Book Ticker

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker\#api-description "Direct link to API Description")

Best price/qty on the order book for a symbol or symbols.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/ticker/bookTicker`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker\#request-weight "Direct link to Request Weight")

**2** for a single symbol;

**5** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

> - If the symbol is not sent, bookTickers for all symbols will be returned in an array.
> - The field `X-MBX-USED-WEIGHT-1M` in response header is not accurate from this endpoint, please ignore.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "symbol": "BTCUSDT",
  "bidPrice": "4.00000000",
  "bidQty": "431.00000000",
  "askPrice": "4.00000200",
  "askQty": "9.00000000",
  "time": 1589437530011   // Transaction time
}

```

> OR

```codeBlockLines_aHhF
[\
	{\
  		"symbol": "BTCUSDT",\
  		"bidPrice": "4.00000000",\
  		"bidQty": "431.00000000",\
  		"askPrice": "4.00000200",\
  		"askQty": "9.00000000",\
  		"time": 1589437530011\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Order-Book-Ticker#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_BNB_Burn_Status.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status#__docusaurus_skipToContent_fallback)

On this page

# Get BNB Burn Status (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status\#api-description "Direct link to API Description")

Get user's BNB Fee Discount (Fee Discount On or Fee Discount Off )

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/feeBurn`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status\#request-weight "Direct link to Request Weight")

**30**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"feeBurn": true // "true": Fee Discount On; "false": Fee Discount Off
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-BNB-Burn-Status#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Mark_Price_Kline_Candlestick_Data.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data#__docusaurus_skipToContent_fallback)

On this page

# Mark Price Kline/Candlestick Data

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data\#api-description "Direct link to API Description")

Kline/candlestick bars for the mark price of a symbol.
Klines are uniquely identified by their open time.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/markPriceKlines`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data\#request-weight "Direct link to Request Weight")

based on parameter `LIMIT`

| LIMIT | weight |
| --- | --- |
| \[1,100) | 1 |\
| \[100, 500) | 2 |\
| \[500, 1000\] | 5 |\
| \> 1000 | 10 |\
\
## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data\#request-parameters "Direct link to Request Parameters")\
\
| Name | Type | Mandatory | Description |\
| --- | --- | --- | --- |\
| symbol | STRING | YES |  |\
| interval | ENUM | YES |  |\
| startTime | LONG | NO |  |\
| endTime | LONG | NO |  |\
| limit | INT | NO | Default 500; max 1500. |\
\
> - If startTime and endTime are not sent, the most recent klines are returned.\
\
## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data\#response-example "Direct link to Response Example")\
\
```codeBlockLines_aHhF\
[\
  [\
    1591256460000,     		// Open time\
    "9653.29201333",    	// Open\
    "9654.56401333",     	// High\
    "9653.07367333",     	// Low\
    "9653.07367333",     	// Close (or latest price)\
    "0	", 					// Ignore\
    1591256519999,      	// Close time\
    "0",    				// Ignore\
    60,                	 	// Ignore\
    "0",    				// Ignore\
    "0",      			 	// Ignore\
    "0" 					// Ignore\
  ]\
]\
\
```\
\
- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data#api-description)\
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data#http-request)\
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data#request-weight)\
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data#request-parameters)\
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Current_Multi_Assets_Mode.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode#__docusaurus_skipToContent_fallback)

On this page

# Get Current Multi-Assets Mode (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode\#api-description "Direct link to API Description")

Get user's Multi-Assets mode (Multi-Assets Mode or Single-Asset Mode) on _**Every symbol**_

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/multiAssetsMargin`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode\#request-weight "Direct link to Request Weight")

**30**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"multiAssetsMargin": true // "true": Multi-Assets Mode; "false": Single-Asset Mode
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Multi-Assets-Mode#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Composite_Index_Symbol_Information_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams#__docusaurus_skipToContent_fallback)

On this page

# Composite Index Symbol Information Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams\#stream-description "Direct link to Stream Description")

Composite index information for index symbols pushed every second.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@compositeIndex`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams\#update-speed "Direct link to Update Speed")

**1000ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e":"compositeIndex",		// Event type
  "E":1602310596000,		// Event time
  "s":"DEFIUSDT",			// Symbol
  "p":"554.41604065",		// Price
  "C":"baseAsset",
  "c":[      				// Composition\
  	{\
  		"b":"BAL",			// Base asset\
  		"q":"USDT",         // Quote asset\
  		"w":"1.04884844",	// Weight in quantity\
  		"W":"0.01457800",   // Weight in percentage\
  		"i":"24.33521021"   // Index price\
  	},\
  	{\
  		"b":"BAND",\
  		"q":"USDT" ,\
  		"w":"3.53782729",\
  		"W":"0.03935200",\
  		"i":"7.26420084"\
    }\
  ]
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Composite-Index-Symbol-Information-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_24hr_Ticker_Price_Change_Statistics.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics#__docusaurus_skipToContent_fallback)

On this page

# 24hr Ticker Price Change Statistics

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics\#api-description "Direct link to API Description")

24 hour rolling window price change statistics.

**Careful** when accessing this with no symbol.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/ticker/24hr`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics\#request-weight "Direct link to Request Weight")

**1** for a single symbol;

**40** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

> - If the symbol is not sent, tickers for all symbols will be returned in an array.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
{
  "symbol": "BTCUSDT",
  "priceChange": "-94.99999800",
  "priceChangePercent": "-95.960",
  "weightedAvgPrice": "0.29628482",
  "lastPrice": "4.00000200",
  "lastQty": "200.00000000",
  "openPrice": "99.00000000",
  "highPrice": "100.00000000",
  "lowPrice": "0.10000000",
  "volume": "8913.30000000",
  "quoteVolume": "15.30000000",
  "openTime": 1499783499040,
  "closeTime": 1499869899040,
  "firstId": 28385,   // First tradeId
  "lastId": 28460,    // Last tradeId
  "count": 76         // Trade count
}

```

> OR

```codeBlockLines_aHhF
[\
	{\
  		"symbol": "BTCUSDT",\
  		"priceChange": "-94.99999800",\
  		"priceChangePercent": "-95.960",\
  		"weightedAvgPrice": "0.29628482",\
  		"lastPrice": "4.00000200",\
  		"lastQty": "200.00000000",\
  		"openPrice": "99.00000000",\
  		"highPrice": "100.00000000",\
  		"lowPrice": "0.10000000",\
  		"volume": "8913.30000000",\
  		"quoteVolume": "15.30000000",\
  		"openTime": 1499783499040,\
  		"closeTime": 1499869899040,\
  		"firstId": 28385,   // First tradeId\
  		"lastId": 28460,    // Last tradeId\
  		"count": 76         // Trade count\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Download_Id_For_Futures_Trade_History.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History#__docusaurus_skipToContent_fallback)

On this page

# Get Download Id For Futures Trade History (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History\#api-description "Direct link to API Description")

Get download id for futures trade history

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/trade/asyn`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History\#request-weight "Direct link to Request Weight")

**1000**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| startTime | LONG | YES | Timestamp in ms |
| endTime | LONG | YES | Timestamp in ms |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Request Limitation is 5 times per month, shared by front end download page and rest api
> - The time between `startTime` and `endTime` can not be longer than 1 year

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"avgCostTimestampOfLast30d":7241837, // Average time taken for data download in the past 30 days
  	"downloadId":"546975389218332672",
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Trade-History#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Download_Id_For_Futures_Order_History.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History#__docusaurus_skipToContent_fallback)

On this page

# Get Download Id For Futures Order History (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History\#api-description "Direct link to API Description")

Get Download Id For Futures Order History

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/order/asyn`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History\#request-weight "Direct link to Request Weight")

**1000**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| startTime | LONG | YES | Timestamp in ms |
| endTime | LONG | YES | Timestamp in ms |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Request Limitation is 10 times per month, shared by front end download page and rest api
> - The time between `startTime` and `endTime` can not be longer than 1 year

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"avgCostTimestampOfLast30d":7241837, // Average time taken for data download in the past 30 days
  	"downloadId":"546975389218332672",
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Order-History#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_websocket_api_Symbol_Order_Book_Ticker.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker#__docusaurus_skipToContent_fallback)

On this page

# Symbol Order Book Ticker

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker\#api-description "Direct link to API Description")

Best price/qty on the order book for a symbol or symbols.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker\#method "Direct link to Method")

`ticker.book`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "9d32157c-a556-4d27-9866-66760a174b57",
    "method": "ticker.book",
    "params": {
        "symbol": "BTCUSDT"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker\#request-weight "Direct link to Request Weight")

**2** for a single symbol;

**5** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

> - If the symbol is not sent, bookTickers for all symbols will be returned in an array.
> - The field `X-MBX-USED-WEIGHT-1M` in response header is not accurate from this endpoint, please ignore.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "id": "9d32157c-a556-4d27-9866-66760a174b57",
  "status": 200,
  "result": {
    "lastUpdateId": 1027024,
    "symbol": "BTCUSDT",
    "bidPrice": "4.00000000",
    "bidQty": "431.00000000",
    "askPrice": "4.00000200",
    "askQty": "9.00000000",
    "time": 1589437530011   // Transaction time
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 2\
    }\
  ]
}

```

> OR

```codeBlockLines_aHhF
{
  "id": "9d32157c-a556-4d27-9866-66760a174b57",
  "status": 200,
  "result": [\
    {\
      "lastUpdateId": 1027024,\
      "symbol": "BTCUSDT",\
      "bidPrice": "4.00000000",\
      "bidQty": "431.00000000",\
      "askPrice": "4.00000200",\
      "askQty": "9.00000000",\
      "time": 1589437530011\
    }\
  ],
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 2\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Order-Book-Ticker#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Exchange_Information.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information#__docusaurus_skipToContent_fallback)

On this page

# Exchange Information

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information\#api-description "Direct link to API Description")

Current exchange trading rules and symbol information

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/exchangeInfo`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information\#request-parameters "Direct link to Request Parameters")

NONE

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"exchangeFilters": [],
 	"rateLimits": [\
 		{\
 			"interval": "MINUTE",\
   			"intervalNum": 1,\
   			"limit": 2400,\
   			"rateLimitType": "REQUEST_WEIGHT"\
   		},\
  		{\
  			"interval": "MINUTE",\
   			"intervalNum": 1,\
   			"limit": 1200,\
   			"rateLimitType": "ORDERS"\
   		}\
   	],
 	"serverTime": 1565613908500,    // Ignore please. If you want to check current server time, please check via "GET /fapi/v1/time"
 	"assets": [ // assets information\
 		{\
 			"asset": "BUSD",\
   			"marginAvailable": true, // whether the asset can be used as margin in Multi-Assets mode\
   			"autoAssetExchange": 0 // auto-exchange threshold in Multi-Assets margin mode\
   		},\
 		{\
 			"asset": "USDT",\
   			"marginAvailable": true,\
   			"autoAssetExchange": 0\
   		},\
 		{\
 			"asset": "BNB",\
   			"marginAvailable": false,\
   			"autoAssetExchange": null\
   		}\
   	],
 	"symbols": [\
 		{\
 			"symbol": "BLZUSDT",\
 			"pair": "BLZUSDT",\
 			"contractType": "PERPETUAL",\
 			"deliveryDate": 4133404800000,\
 			"onboardDate": 1598252400000,\
 			"status": "TRADING",\
 			"maintMarginPercent": "2.5000",   // ignore\
 			"requiredMarginPercent": "5.0000",  // ignore\
 			"baseAsset": "BLZ",\
 			"quoteAsset": "USDT",\
 			"marginAsset": "USDT",\
 			"pricePrecision": 5,	// please do not use it as tickSize\
 			"quantityPrecision": 0, // please do not use it as stepSize\
 			"baseAssetPrecision": 8,\
 			"quotePrecision": 8,\
 			"underlyingType": "COIN",\
 			"underlyingSubType": ["STORAGE"],\
 			"settlePlan": 0,\
 			"triggerProtect": "0.15", // threshold for algo order with "priceProtect"\
 			"filters": [\
 				{\
 					"filterType": "PRICE_FILTER",\
     				"maxPrice": "300",\
     				"minPrice": "0.0001",\
     				"tickSize": "0.0001"\
     			},\
    			{\
    				"filterType": "LOT_SIZE",\
     				"maxQty": "10000000",\
     				"minQty": "1",\
     				"stepSize": "1"\
     			},\
    			{\
    				"filterType": "MARKET_LOT_SIZE",\
     				"maxQty": "590119",\
     				"minQty": "1",\
     				"stepSize": "1"\
     			},\
     			{\
    				"filterType": "MAX_NUM_ORDERS",\
    				"limit": 200\
  				},\
  				{\
    				"filterType": "MAX_NUM_ALGO_ORDERS",\
    				"limit": 10\
  				},\
  				{\
  					"filterType": "MIN_NOTIONAL",\
  					"notional": "5.0",\
  				},\
  				{\
    				"filterType": "PERCENT_PRICE",\
    				"multiplierUp": "1.1500",\
    				"multiplierDown": "0.8500",\
    				"multiplierDecimal": 4\
    			}\
   			],\
 			"OrderType": [\
   				"LIMIT",\
   				"MARKET",\
   				"STOP",\
   				"STOP_MARKET",\
   				"TAKE_PROFIT",\
   				"TAKE_PROFIT_MARKET",\
   				"TRAILING_STOP_MARKET"\
   			],\
   			"timeInForce": [\
   				"GTC",\
   				"IOC",\
   				"FOK",\
   				"GTX"\
 			],\
 			"liquidationFee": "0.010000",	// liquidation fee rate\
   			"marketTakeBound": "0.30",	// the max price difference rate( from mark price) a market order can make\
 		}\
   	],
	"timezone": "UTC"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_websocket_api.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api#__docusaurus_skipToContent_fallback)

On this page

# New Order(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api\#api-description "Direct link to API Description")

Send in a new order.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api\#method "Direct link to Method")

`order.place`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "3f7df6e3-2df4-44b9-9919-d2f38f90a99a",
    "method": "order.place",
    "params": {
        "apiKey": "HMOchcfii9ZRZnhjp2XjGXhsOBd6msAhKz9joQaWwZ7arcJTlD2hGPHQj1lGdTjR",
        "positionSide": "BOTH",
        "price": "43187.00",
        "quantity": 0.1,
        "side": "BUY",
        "symbol": "BTCUSDT",
        "timeInForce": "GTC",
        "timestamp": 1702555533821,
        "type": "LIMIT",
        "signature": "0f04368b2d22aafd0ggc8809ea34297eff602272917b5f01267db4efbc1c9422"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api\#request-weight "Direct link to Request Weight")

**0**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| side | ENUM | YES |  |
| positionSide | ENUM | NO | Default `BOTH` for One-way Mode ; `LONG` or `SHORT` for Hedge Mode. It must be sent in Hedge Mode. |
| type | ENUM | YES |  |
| timeInForce | ENUM | NO |  |
| quantity | DECIMAL | NO | Cannot be sent with `closePosition` = `true`(Close-All) |
| reduceOnly | STRING | NO | "true" or "false". default "false". Cannot be sent in Hedge Mode; cannot be sent with `closePosition` = `true` |
| price | DECIMAL | NO |  |
| newClientOrderId | STRING | NO | A unique id among open orders. Automatically generated if not sent. Can only be string following the rule: `^[\.A-Z\:/a-z0-9_-]{1,36}$` |
| stopPrice | DECIMAL | NO | Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| closePosition | STRING | NO | `true`, `false`；Close-All，used with `STOP_MARKET` or `TAKE_PROFIT_MARKET`. |
| activationPrice | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, default as the latest price(supporting different `workingType`) |
| callbackRate | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, min 0.1, max 10 where 1 for 1% |
| workingType | ENUM | NO | stopPrice triggered by: "MARK\_PRICE", "CONTRACT\_PRICE". Default "CONTRACT\_PRICE" |
| priceProtect | STRING | NO | "TRUE" or "FALSE", default "FALSE". Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| newOrderRespType | ENUM | NO | "ACK", "RESULT", default "ACK" |
| priceMatch | ENUM | NO | only avaliable for `LIMIT`/ `STOP`/ `TAKE_PROFIT` order; can be set to `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`: / `QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`; Can't be passed together with `price` |
| selfTradePreventionMode | ENUM | NO | `NONE`:No STP / `EXPIRE_TAKER`:expire taker order when STP triggers/ `EXPIRE_MAKER`:expire taker order when STP triggers/ `EXPIRE_BOTH`:expire both orders when STP triggers; default `NONE` |
| goodTillDate | LONG | NO | order cancel time for timeInForce `GTD`, mandatory when `timeInforce` set to `GTD`; order the timestamp only retains second-level precision, ms part will be ignored; The goodTillDate timestamp must be greater than the current time plus 600 seconds and smaller than 253402300799000 |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

Additional mandatory parameters based on `type`:

| Type | Additional mandatory parameters |
| --- | --- |
| `LIMIT` | `timeInForce`, `quantity`, `price` or `priceMatch` |
| `MARKET` | `quantity` |
| `STOP/TAKE_PROFIT` | `quantity`, `stopPrice`, `price` or `priceMatch` |
| `STOP_MARKET/TAKE_PROFIT_MARKET` | `stopPrice` |
| `TRAILING_STOP_MARKET` | `callbackRate` |

> - Order with type `STOP`, parameter `timeInForce` can be sent ( default `GTC`).
>
> - Order with type `TAKE_PROFIT`, parameter `timeInForce` can be sent ( default `GTC`).
>
> - Condition orders will be triggered when:
>   - If parameter `priceProtect` is sent as true:
>
>     - when price reaches the `stopPrice` ，the difference rate between "MARK\_PRICE" and "CONTRACT\_PRICE" cannot be larger than the "triggerProtect" of the symbol
>     - "triggerProtect" of a symbol can be got from `GET /fapi/v1/exchangeInfo`
>   - `STOP`, `STOP_MARKET`:
>
>     - BUY: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") >= `stopPrice`
>     - SELL: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") <= `stopPrice`
>   - `TAKE_PROFIT`, `TAKE_PROFIT_MARKET`:
>
>     - BUY: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") <= `stopPrice`
>     - SELL: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") >= `stopPrice`
>   - `TRAILING_STOP_MARKET`:
>
>     - BUY: the lowest price after order placed `<= ` activationPrice `, and the latest price >` = the lowest price \* (1 + `callbackRate`)
>     - SELL: the highest price after order placed >= `activationPrice`, and the latest price <= the highest price \* (1 - `callbackRate`)
> - For `TRAILING_STOP_MARKET`, if you got such error code.
>
>   `{"code": -2021, "msg": "Order would immediately trigger."}`
>
>
>   means that the parameters you send do not meet the following requirements:
>   - BUY: `activationPrice` should be smaller than latest price.
>   - SELL: `activationPrice` should be larger than latest price.
> - If `newOrderRespType ` is sent as `RESULT` :
>   - `MARKET` order: the final FILLED result of the order will be return directly.
>   - `LIMIT` order with special `timeInForce`: the final status result of the order(FILLED or EXPIRED) will be returned directly.
> - `STOP_MARKET`, `TAKE_PROFIT_MARKET` with `closePosition` = `true`:
>   - Follow the same rules for condition orders.
>   - If triggered， **close all** current long position( if `SELL`) or current short position( if `BUY`).
>   - Cannot be used with `quantity` paremeter
>   - Cannot be used with `reduceOnly` parameter
>   - In Hedge Mode,cannot be used with `BUY` orders in `LONG` position side. and cannot be used with `SELL` orders in `SHORT` position side

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "id": "3f7df6e3-2df4-44b9-9919-d2f38f90a99a",
    "status": 200,
    "result": {
        "orderId": 325078477,
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "iCXL1BywlBaf2sesNUrVl3",
        "price": "43187.00",
        "avgPrice": "0.00",
        "origQty": "0.100",
        "executedQty": "0.000",
        "cumQty": "0.000",
        "cumQuote": "0.00000",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "reduceOnly": false,
        "closePosition": false,
        "side": "BUY",
        "positionSide": "BOTH",
        "stopPrice": "0.00",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": false,
        "origType": "LIMIT",
        "priceMatch": "NONE",
        "selfTradePreventionMode": "NONE",
        "goodTillDate": 0,
        "updateTime": 1702555534435
    },
    "rateLimits": [\
        {\
            "rateLimitType": "ORDERS",\
            "interval": "SECOND",\
            "intervalNum": 10,\
            "limit": 300,\
            "count": 1\
        },\
        {\
            "rateLimitType": "ORDERS",\
            "interval": "MINUTE",\
            "intervalNum": 1,\
            "limit": 1200,\
            "count": 1\
        },\
        {\
            "rateLimitType": "REQUEST_WEIGHT",\
            "interval": "MINUTE",\
            "intervalNum": 1,\
            "limit": 2400,\
            "count": 1\
        }\
    ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Recent_Trades_List.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List#__docusaurus_skipToContent_fallback)

On this page

# Recent Trades List

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List\#api-description "Direct link to API Description")

Get recent market trades

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/trades`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| limit | INT | NO | Default 500; max 1000. |

> - Market trades means trades filled in the order book. Only market trades will be returned, which means the insurance fund trades and ADL trades won't be returned.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
    "id": 28457,\
    "price": "4.00000100",\
    "qty": "12.00000000",\
    "quoteQty": "48.00",\
    "time": 1499865549590,\
    "isBuyerMaker": true,\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Recent-Trades-List#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Start_User_Data_Stream_Wsp.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp#__docusaurus_skipToContent_fallback)

On this page

# Start User Data Stream (USER\_STREAM)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp\#api-description "Direct link to API Description")

Start a new user data stream. The stream will close after 60 minutes unless a keepalive is sent. If the account has an active `listenKey`, that `listenKey` will be returned and its validity will be extended for 60 minutes.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp\#method "Direct link to Method")

`userDataStream.start`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp\#request "Direct link to Request")

```codeBlockLines_aHhF
{
  "id": "d3df8a61-98ea-4fe0-8f4e-0fcea5d418b0",
  "method": "userDataStream.start",
  "params": {
    "apiKey": "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A"
  }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp\#request-parameters "Direct link to Request Parameters")

None

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "id": "d3df8a61-98ea-4fe0-8f4e-0fcea5d418b0",
  "status": 200,
  "result": {
    "listenKey": "xs0mRXdAKlIPDRFrlPcw0qI41Eh3ixNntmymGyhrhgqo7L6FuLaWArTD7RLP"
  },
   "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 2\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream-Wsp#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Long_Short_Ratio.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio#__docusaurus_skipToContent_fallback)

On this page

# Long/Short Ratio

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio\#api-description "Direct link to API Description")

Query symbol Long/Short Ratio

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio\#http-request "Direct link to HTTP Request")

GET `/futures/data/globalLongShortAccountRatio`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio\#request-weight "Direct link to Request Weight")

**0**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| period | ENUM | YES | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit | LONG | NO | default 30, max 500 |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |

> - If startTime and endTime are not sent, the most recent data is returned.
> - Only the data of the latest 30 days is available.
> - IP rate limit 1000 requests/5min

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
         "symbol":"BTCUSDT",  // long/short account num ratio of all traders\
	      "longShortRatio":"0.1960",  //long account num ratio of all traders\
	      "longAccount": "0.6622",   // short account num ratio of all traders\
	      "shortAccount":"0.3378",\
	      "timestamp":"1583139600000"\
\
     },\
\
     {\
\
         "symbol":"BTCUSDT",\
	      "longShortRatio":"1.9559",\
	      "longAccount": "0.6617",\
	      "shortAccount":"0.3382",\
	      "timestamp":"1583139900000"\
\
        },\
\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Query_Current_Open_Order.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order#__docusaurus_skipToContent_fallback)

On this page

# Query Current Open Order (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order\#api-description "Direct link to API Description")

Query open order

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/openOrder`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Either `orderId` or `origClientOrderId` must be sent
> - If the queried order has been filled or cancelled, the error message "Order does not exist" will be returned.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  	"avgPrice": "0.00000",
  	"clientOrderId": "abc",
  	"cumQuote": "0",
  	"executedQty": "0",
  	"orderId": 1917641,
  	"origQty": "0.40",
  	"origType": "TRAILING_STOP_MARKET",
  	"price": "0",
  	"reduceOnly": false,
  	"side": "BUY",
  	"positionSide": "SHORT",
  	"status": "NEW",
  	"stopPrice": "9300",				// please ignore when order type is TRAILING_STOP_MARKET
  	"closePosition": false,   			// if Close-All
  	"symbol": "BTCUSDT",
  	"time": 1579276756075,				// order time
  	"timeInForce": "GTC",
  	"type": "TRAILING_STOP_MARKET",
  	"activatePrice": "9020",			// activation price, only return with TRAILING_STOP_MARKET order
  	"priceRate": "0.3",					// callback rate, only return with TRAILING_STOP_MARKET order
  	"updateTime": 1579276756075,
  	"workingType": "CONTRACT_PRICE",
  	"priceProtect": false,            // if conditional order trigger is protected
	"priceMatch": "NONE",              //price match mode
    "selfTradePreventionMode": "NONE", //self trading preventation mode
    "goodTillDate": 0      //order pre-set auot cancel time for TIF GTD order
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Current-Open-Order#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_websocket_api_Query_Order.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order#__docusaurus_skipToContent_fallback)

On this page

# Query Order (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order\#api-description "Direct link to API Description")

Check an order's status.

- These orders will not be found:
  - order status is `CANCELED` or `EXPIRED` **AND** order has NO filled trade **AND** created time + 3 days < current time
  - order create time + 90 days < current time

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order\#method "Direct link to Method")

`order.status`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "0ce5d070-a5e5-4ff2-b57f-1556741a4204",
    "method": "order.status",
    "params": {
        "apiKey": "HMOchcfii9ZRZnhjp2XjGXhsOBd6msAhKz9joQaWwZ7arcJTlD2hGPHQj1lGdTjR",
        "orderId": 328999071,
        "symbol": "BTCUSDT",
        "timestamp": 1703441060152,
        "signature": "ba48184fc38a71d03d2b5435bd67c1206e3191e989fe99bda1bc643a880dfdbf"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

Notes:

> - Either `orderId` or `origClientOrderId` must be sent.
> - `orderId` is self-increment for each specific `symbol`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
 "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
 "status": 200,
 "result": {
  "avgPrice": "0.00000",
  "clientOrderId": "abc",
  "cumQuote": "0",
  "executedQty": "0",
  "orderId": 1917641,
  "origQty": "0.40",
  "origType": "TRAILING_STOP_MARKET",
  "price": "0",
  "reduceOnly": false,
  "side": "BUY",
  "positionSide": "SHORT",
  "status": "NEW",
  "stopPrice": "9300",    // please ignore when order type is TRAILING_STOP_MARKET
  "closePosition": false,   // if Close-All
  "symbol": "BTCUSDT",
  "time": 1579276756075,    // order time
  "timeInForce": "GTC",
  "type": "TRAILING_STOP_MARKET",
  "activatePrice": "9020",   // activation price, only return with TRAILING_STOP_MARKET order
  "priceRate": "0.3",     // callback rate, only return with TRAILING_STOP_MARKET order
  "updateTime": 1579276756075,  // update time
  "workingType": "CONTRACT_PRICE",
  "priceProtect": false            // if conditional order trigger is protected
 }
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Query-Order#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Change_Position_Mode.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode#__docusaurus_skipToContent_fallback)

On this page

# Change Position Mode(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode\#api-description "Direct link to API Description")

Change user's position mode (Hedge Mode or One-way Mode ) on _**EVERY symbol**_

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/positionSide/dual`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| dualSidePosition | STRING | YES | "true": Hedge Mode; "false": One-way Mode |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"code": 200,
	"msg": "success"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Position-Mode#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Change_Initial_Leverage.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage#__docusaurus_skipToContent_fallback)

On this page

# Change Initial Leverage(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage\#api-description "Direct link to API Description")

Change user's initial leverage of specific symbol market.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/leverage`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| leverage | INT | YES | target initial leverage: int from 1 to 125 |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
 	"leverage": 21,
 	"maxNotionalValue": "1000000",
 	"symbol": "BTCUSDT"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Initial-Leverage#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Futures_Order_History_Download_Link_by_Id.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id#__docusaurus_skipToContent_fallback)

On this page

# Get Futures Order History Download Link by Id (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id\#api-description "Direct link to API Description")

Get futures order history download link by Id

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/order/asyn/id`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id\#request-weight "Direct link to Request Weight")

**10**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| downloadId | STRING | YES | get by download id api |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Download link expiration: 24h

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
{
	"downloadId":"545923594199212032",
  	"status":"completed",     // Enum：completed，processing
  	"url":"www.binance.com",  // The link is mapped to download id
  	"notified":true,          // ignore
  	"expirationTimestamp":1645009771000,  // The link would expire after this timestamp
  	"isExpired":null,
}

```

> **OR** (Response when server is processing)

```codeBlockLines_aHhF
{
	"downloadId":"545923594199212032",
  	"status":"processing",
  	"url":"",
  	"notified":false,
  	"expirationTimestamp":-1
  	"isExpired":null,

}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Order-History-Download-Link-by-Id#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Change_Margin_Type.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type#__docusaurus_skipToContent_fallback)

On this page

# Change Margin Type(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type\#api-description "Direct link to API Description")

Change symbol level margin type

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/marginType`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| marginType | ENUM | YES | ISOLATED, CROSSED |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"code": 200,
	"msg": "success"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Margin-Type#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_common_definition.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#__docusaurus_skipToContent_fallback)

On this page

# Public Endpoints Info

## Terminology [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#terminology "Direct link to Terminology")

- `base asset` refers to the asset that is the `quantity` of a symbol.
- `quote asset` refers to the asset that is the `price` of a symbol.

## ENUM definitions [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#enum-definitions "Direct link to ENUM definitions")

**Symbol type:**

- FUTURE

**Contract type (contractType):**

- PERPETUAL
- CURRENT\_MONTH
- NEXT\_MONTH
- CURRENT\_QUARTER
- NEXT\_QUARTER
- PERPETUAL\_DELIVERING

**Contract status (contractStatus, status):**

- PENDING\_TRADING
- TRADING
- PRE\_DELIVERING
- DELIVERING
- DELIVERED
- PRE\_SETTLE
- SETTLING
- CLOSE

**Order status (status):**

- NEW
- PARTIALLY\_FILLED
- FILLED
- CANCELED
- REJECTED
- EXPIRED
- EXPIRED\_IN\_MATCH

**Order types (orderTypes, type):**

- LIMIT
- MARKET
- STOP
- STOP\_MARKET
- TAKE\_PROFIT
- TAKE\_PROFIT\_MARKET
- TRAILING\_STOP\_MARKET

**Order side (side):**

- BUY
- SELL

**Position side (positionSide):**

- BOTH
- LONG
- SHORT

**Time in force (timeInForce):**

- GTC - Good Till Cancel(GTC order valitidy is 1 year from placement)
- IOC - Immediate or Cancel
- FOK - Fill or Kill
- GTX - Good Till Crossing (Post Only)
- GTD - Good Till Date

**Working Type (workingType)**

- MARK\_PRICE
- CONTRACT\_PRICE

**Response Type (newOrderRespType)**

- ACK
- RESULT

**Kline/Candlestick chart intervals:**

m -> minutes; h -> hours; d -> days; w -> weeks; M -> months

- 1m
- 3m
- 5m
- 15m
- 30m
- 1h
- 2h
- 4h
- 6h
- 8h
- 12h
- 1d
- 3d
- 1w
- 1M

**STP MODE (selfTradePreventionMode):**

- EXPIRE\_TAKER
- EXPIRE\_BOTH
- EXPIRE\_MAKER

**Price Match (priceMatch)**

- NONE (No price match)
- OPPONENT (counterparty best price)
- OPPONENT\_5 (the 5th best price from the counterparty)
- OPPONENT\_10 (the 10th best price from the counterparty)
- OPPONENT\_20 (the 20th best price from the counterparty)
- QUEUE (the best price on the same side of the order book)
- QUEUE\_5 (the 5th best price on the same side of the order book)
- QUEUE\_10 (the 10th best price on the same side of the order book)
- QUEUE\_20 (the 20th best price on the same side of the order book)

**Rate limiters (rateLimitType)**

> REQUEST\_WEIGHT

```codeBlockLines_aHhF
  {
  	"rateLimitType": "REQUEST_WEIGHT",
  	"interval": "MINUTE",
  	"intervalNum": 1,
  	"limit": 2400
  }

```

> ORDERS

```codeBlockLines_aHhF
  {
  	"rateLimitType": "ORDERS",
  	"interval": "MINUTE",
  	"intervalNum": 1,
  	"limit": 1200
   }

```

- REQUEST\_WEIGHT

- ORDERS


**Rate limit intervals (interval)**

- MINUTE

# Filters

Filters define trading rules on a symbol or an exchange.

## Symbol filters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#symbol-filters "Direct link to Symbol filters")

### PRICE\_FILTER [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#price_filter "Direct link to PRICE_FILTER")

> **/exchangeInfo format:**

```codeBlockLines_aHhF
  {
    "filterType": "PRICE_FILTER",
    "minPrice": "0.00000100",
    "maxPrice": "100000.00000000",
    "tickSize": "0.00000100"
  }

```

The `PRICE_FILTER` defines the `price` rules for a symbol. There are 3 parts:

- `minPrice` defines the minimum `price`/ `stopPrice` allowed; disabled on `minPrice` == 0.
- `maxPrice` defines the maximum `price`/ `stopPrice` allowed; disabled on `maxPrice` == 0.
- `tickSize` defines the intervals that a `price`/ `stopPrice` can be increased/decreased by; disabled on `tickSize` == 0.

Any of the above variables can be set to 0, which disables that rule in the `price filter`. In order to pass the `price filter`, the following must be true for `price`/ `stopPrice` of the enabled rules:

- `price` >= `minPrice`
- `price` <= `maxPrice`
- ( `price`- `minPrice`) % `tickSize` == 0

### LOT\_SIZE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#lot_size "Direct link to LOT_SIZE")

> **/exchangeInfo format:**

```codeBlockLines_aHhF
  {
    "filterType": "LOT_SIZE",
    "minQty": "0.00100000",
    "maxQty": "100000.00000000",
    "stepSize": "0.00100000"
  }

```

The `LOT_SIZE` filter defines the `quantity` (aka "lots" in auction terms) rules for a symbol. There are 3 parts:

- `minQty` defines the minimum `quantity` allowed.
- `maxQty` defines the maximum `quantity` allowed.
- `stepSize` defines the intervals that a `quantity` can be increased/decreased by.

In order to pass the `lot size`, the following must be true for `quantity`:

- `quantity` >= `minQty`
- `quantity` <= `maxQty`
- ( `quantity`- `minQty`) % `stepSize` == 0

### MARKET\_LOT\_SIZE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#market_lot_size "Direct link to MARKET_LOT_SIZE")

> **/exchangeInfo format:**

```codeBlockLines_aHhF
  {
    "filterType": "MARKET_LOT_SIZE",
    "minQty": "0.00100000",
    "maxQty": "100000.00000000",
    "stepSize": "0.00100000"
  }

```

The `MARKET_LOT_SIZE` filter defines the `quantity` (aka "lots" in auction terms) rules for `MARKET` orders on a symbol. There are 3 parts:

- `minQty` defines the minimum `quantity` allowed.
- `maxQty` defines the maximum `quantity` allowed.
- `stepSize` defines the intervals that a `quantity` can be increased/decreased by.

In order to pass the `market lot size`, the following must be true for `quantity`:

- `quantity` >= `minQty`
- `quantity` <= `maxQty`
- ( `quantity`- `minQty`) % `stepSize` == 0

### MAX\_NUM\_ORDERS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#max_num_orders "Direct link to MAX_NUM_ORDERS")

> **/exchangeInfo format:**

```codeBlockLines_aHhF
  {
    "filterType": "MAX_NUM_ORDERS",
    "limit": 200
  }

```

The `MAX_NUM_ORDERS` filter defines the maximum number of orders an account is allowed to have open on a symbol.

Note that both "algo" orders and normal orders are counted for this filter.

### MAX\_NUM\_ALGO\_ORDERS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#max_num_algo_orders "Direct link to MAX_NUM_ALGO_ORDERS")

> **/exchangeInfo format:**

```codeBlockLines_aHhF
  {
    "filterType": "MAX_NUM_ALGO_ORDERS",
    "limit": 100
  }

```

The `MAX_NUM_ALGO_ORDERS ` filter defines the maximum number of all kinds of algo orders an account is allowed to have open on a symbol.

The algo orders include `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET`, and `TRAILING_STOP_MARKET` orders.

### PERCENT\_PRICE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#percent_price "Direct link to PERCENT_PRICE")

> **/exchangeInfo format:**

```codeBlockLines_aHhF
  {
    "filterType": "PERCENT_PRICE",
    "multiplierUp": "1.1500",
    "multiplierDown": "0.8500",
    "multiplierDecimal": 4
  }

```

The `PERCENT_PRICE` filter defines valid range for a price based on the mark price.

In order to pass the `percent price`, the following must be true for `price`:

- BUY: `price` <= `markPrice` \\* `multiplierUp`
- SELL: `price` >= `markPrice` \\* `multiplierDown`

### MIN\_NOTIONAL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition\#min_notional "Direct link to MIN_NOTIONAL")

> **/exchangeInfo format:**

```codeBlockLines_aHhF
  {
    "filterType": "MIN_NOTIONAL",
    "notional": "5.0"
  }

```

The `MIN_NOTIONAL` filter defines the minimum notional value allowed for an order on a symbol.
An order's notional value is the `price` \\* `quantity`.
Since `MARKET` orders have no price, the mark price is used.

- [Terminology](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#terminology)
- [ENUM definitions](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#enum-definitions)
- [Symbol filters](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#symbol-filters)
  - [PRICE\_FILTER](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#price_filter)
  - [LOT\_SIZE](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#lot_size)
  - [MARKET\_LOT\_SIZE](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#market_lot_size)
  - [MAX\_NUM\_ORDERS](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#max_num_orders)
  - [MAX\_NUM\_ALGO\_ORDERS](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#max_num_algo_orders)
  - [PERCENT\_PRICE](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#percent_price)
  - [MIN\_NOTIONAL](https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition#min_notional)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Diff_Book_Depth_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams#__docusaurus_skipToContent_fallback)

On this page

# Diff. Book Depth Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams\#stream-description "Direct link to Stream Description")

Bids and asks, pushed every 250 milliseconds, 500 milliseconds, 100 milliseconds (if existing)

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@depth` OR `<symbol>@depth@500ms` OR `<symbol>@depth@100ms`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams\#update-speed "Direct link to Update Speed")

**250ms**, **500ms**, **100ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e": "depthUpdate", // Event type
  "E": 123456789,     // Event time
  "T": 123456788,     // Transaction time
  "s": "BTCUSDT",     // Symbol
  "U": 157,           // First update ID in event
  "u": 160,           // Final update ID in event
  "pu": 149,          // Final update Id in last stream(ie `u` in last stream)
  "b": [              // Bids to be updated\
    [\
      "0.0024",       // Price level to be updated\
      "10"            // Quantity\
    ]\
  ],
  "a": [              // Asks to be updated\
    [\
      "0.0026",       // Price level to be updated\
      "100"          // Quantity\
    ]\
  ]
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Kline_Candlestick_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams#__docusaurus_skipToContent_fallback)

On this page

# Kline/Candlestick Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams\#stream-description "Direct link to Stream Description")

The Kline/Candlestick Stream push updates to the current klines/candlestick every 250 milliseconds (if existing).

**Kline/Candlestick chart intervals:**

m -> minutes; h -> hours; d -> days; w -> weeks; M -> months

- 1m
- 3m
- 5m
- 15m
- 30m
- 1h
- 2h
- 4h
- 6h
- 8h
- 12h
- 1d
- 3d
- 1w
- 1M

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@kline_<interval>`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams\#update-speed "Direct link to Update Speed")

**250ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e": "kline",     // Event type
  "E": 1638747660000,   // Event time
  "s": "BTCUSDT",    // Symbol
  "k": {
    "t": 1638747660000, // Kline start time
    "T": 1638747719999, // Kline close time
    "s": "BTCUSDT",  // Symbol
    "i": "1m",      // Interval
    "f": 100,       // First trade ID
    "L": 200,       // Last trade ID
    "o": "0.0010",  // Open price
    "c": "0.0020",  // Close price
    "h": "0.0025",  // High price
    "l": "0.0015",  // Low price
    "v": "1000",    // Base asset volume
    "n": 100,       // Number of trades
    "x": false,     // Is this kline closed?
    "q": "1.0000",  // Quote asset volume
    "V": "500",     // Taker buy base asset volume
    "Q": "0.500",   // Taker buy quote asset volume
    "B": "123456"   // Ignore
  }
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Get_Funding_Rate_Info.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info#__docusaurus_skipToContent_fallback)

On this page

# Get Funding Rate Info

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info\#api-description "Direct link to API Description")

Query funding rate info for symbols that had FundingRateCap/ FundingRateFloor / fundingIntervalHours adjustment

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/fundingInfo`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info\#request-weight "Direct link to Request Weight")

**0**
share 500/5min/IP rate limit with `GET /fapi/v1/fundingInfo`

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info\#request-parameters "Direct link to Request Parameters")

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
        "symbol": "BLZUSDT",\
        "adjustedFundingRateCap": "0.02500000",\
        "adjustedFundingRateFloor": "-0.02500000",\
        "fundingIntervalHours": 8,\
        "disclaimer": false   // ingore\
    }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Continuous_Contract_Kline_Candlestick_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams#__docusaurus_skipToContent_fallback)

On this page

# Continuous Contract Kline/Candlestick Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams\#stream-description "Direct link to Stream Description")

**Contract type:**

- perpetual
- current\_quarter
- next\_quarter

**Kline/Candlestick chart intervals:**

m -> minutes; h -> hours; d -> days; w -> weeks; M -> months

- 1m
- 3m
- 5m
- 15m
- 30m
- 1h
- 2h
- 4h
- 6h
- 8h
- 12h
- 1d
- 3d
- 1w
- 1M

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams\#stream-name "Direct link to Stream Name")

`<pair>_<contractType>@continuousKline_<interval>`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams\#update-speed "Direct link to Update Speed")

**250ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e":"continuous_kline",	// Event type
  "E":1607443058651,		// Event time
  "ps":"BTCUSDT",			// Pair
  "ct":"PERPETUAL"			// Contract type
  "k":{
    "t":1607443020000,		// Kline start time
    "T":1607443079999,		// Kline close time
    "i":"1m",				// Interval
    "f":116467658886,		// First updateId
    "L":116468012423,		// Last updateId
    "o":"18787.00",			// Open price
    "c":"18804.04",			// Close price
    "h":"18804.04",			// High price
    "l":"18786.54",			// Low price
    "v":"197.664",			// volume
    "n": 543,				// Number of trades
    "x":false,				// Is this kline closed?
    "q":"3715253.19494",	// Quote asset volume
    "V":"184.769",			// Taker buy volume
    "Q":"3472925.84746",	//Taker buy quote asset volume
    "B":"0"					// Ignore
  }
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Continuous-Contract-Kline-Candlestick-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Download_Id_For_Futures_Transaction_History.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History#__docusaurus_skipToContent_fallback)

On this page

# Get Download Id For Futures Transaction History(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History\#api-description "Direct link to API Description")

Get download id for futures transaction history

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/income/asyn`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History\#request-weight "Direct link to Request Weight")

**1000**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| startTime | LONG | YES | Timestamp in ms |
| endTime | LONG | YES | Timestamp in ms |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Request Limitation is 5 times per month, shared by front end download page and rest api
> - The time between `startTime` and `endTime` can not be longer than 1 year

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"avgCostTimestampOfLast30d":7241837, // Average time taken for data download in the past 30 days
  	"downloadId":"546975389218332672",
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Download-Id-For-Futures-Transaction-History#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Contract_Info_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream#__docusaurus_skipToContent_fallback)

On this page

# Contract Info Stream

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream\#stream-description "Direct link to Stream Description")

ContractInfo stream pushes when contract info updates(listing/settlement/contract bracket update). `bks` field only shows up when bracket gets updated.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream\#stream-name "Direct link to Stream Name")

`!contractInfo`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream\#update-speed "Direct link to Update Speed")

**Real-time**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "e":"contractInfo",          // Event Type
    "E":1669356423908,           // Event Time
    "s":"IOTAUSDT",              // Symbol
    "ps":"IOTAUSDT",             // Pair
    "ct":"PERPETUAL",            // Contract type
    "dt":4133404800000,          // Delivery date time
    "ot":1569398400000,          // onboard date time
    "cs":"TRADING",              // Contract status
    "bks":[\
        {\
            "bs":1,              // Notional bracket\
            "bnf":0,             // Floor notional of this bracket\
            "bnc":5000,          // Cap notional of this bracket\
            "mmr":0.01,          // Maintenance ratio for this bracket\
            "cf":0,              // Auxiliary number for quick calculation\
            "mi":21,             // Min leverage for this bracket\
            "ma":50              // Max leverage for this bracket\
        },\
        {\
            "bs":2,\
            "bnf":5000,\
            "bnc":25000,\
            "mmr":0.025,\
            "cf":75,\
            "mi":11,\
            "ma":20\
        }\
    ]
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Contract-Info-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_Margin_Call.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Margin-Call#__docusaurus_skipToContent_fallback)

On this page

# Event: Margin Call

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Margin-Call\#event-description "Direct link to Event Description")

- When the user's position risk ratio is too high, this stream will be pushed.
- This message is only used as risk guidance information and is not recommended for investment strategies.
- In the case of a highly volatile market, there may be the possibility that the user's position has been liquidated at the same time when this stream is pushed out.

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Margin-Call\#event-name "Direct link to Event Name")

`MARGIN_CALL`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Margin-Call\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "e":"MARGIN_CALL",    	// Event Type
    "E":1587727187525,		// Event Time
    "cw":"3.16812045",		// Cross Wallet Balance. Only pushed with crossed position margin call
    "p":[					// Position(s) of Margin Call\
      {\
        "s":"ETHUSDT",		// Symbol\
        "ps":"LONG",		// Position Side\
        "pa":"1.327",		// Position Amount\
        "mt":"CROSSED",		// Margin Type\
        "iw":"0",			// Isolated Wallet (if isolated position)\
        "mp":"187.17127",	// Mark Price\
        "up":"-1.166074",	// Unrealized PnL\
        "mm":"1.614445"		// Maintenance Margin Required\
      }\
    ]
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Margin-Call#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Margin-Call#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Margin-Call#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_websocket_api.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api#__docusaurus_skipToContent_fallback)

On this page

# Order Book

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api\#api-description "Direct link to API Description")

Get current order book. Note that this request returns limited market depth.
If you need to continuously monitor order book updates, please consider using Websocket Market Streams:

- `<symbol>@depth<levels>`
- `<symbol>@depth`

You can use `depth` request together with `<symbol>@depth` streams to maintain a local order book.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api\#method "Direct link to Method")

`depth`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "51e2affb-0aba-4821-ba75-f2625006eb43",
    "method": "depth",
    "params": {
      "symbol": "BTCUSDT"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api\#request-weight "Direct link to Request Weight")

Adjusted based on the limit:

| Limit | Weight |
| --- | --- |
| 5, 10, 20, 50 | 2 |
| 100 | 5 |
| 500 | 10 |
| 1000 | 20 |

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| limit | INT | NO | Default 500; Valid limits:\[5, 10, 20, 50, 100, 500, 1000\] |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "id": "51e2affb-0aba-4821-ba75-f2625006eb43",
  "status": 200,
  "result": {
    "lastUpdateId": 1027024,
    "E": 1589436922972,   // Message output time
    "T": 1589436922959,   // Transaction time
    "bids": [\
      [\
        "4.00000000",     // PRICE\
        "431.00000000"    // QTY\
      ]\
    ],
    "asks": [\
      [\
        "4.00000200",\
        "12.00000000"\
      ]\
    ]
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 5\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Current_Position_Mode.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode#__docusaurus_skipToContent_fallback)

On this page

# Get Current Position Mode(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode\#api-description "Direct link to API Description")

Get user's position mode (Hedge Mode or One-way Mode ) on _**EVERY symbol**_

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/positionSide/dual`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode\#request-weight "Direct link to Request Weight")

30

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"dualSidePosition": true // "true": Hedge Mode; "false": One-way Mode
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Modify_Multiple_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders#__docusaurus_skipToContent_fallback)

On this page

# Modify Multiple Orders(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders\#api-description "Direct link to API Description")

Modify Multiple Orders (TRADE)

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders\#http-request "Direct link to HTTP Request")

PUT `/fapi/v1/batchOrders`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders\#request-weight "Direct link to Request Weight")

5 on 10s order rate limit(X-MBX-ORDER-COUNT-10S);
1 on 1min order rate limit(X-MBX-ORDER-COUNT-1M);
5 on IP rate limit(x-mbx-used-weight-1m);

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| batchOrders | list<JSON> | YES | order list. Max 5 orders |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

**Where `batchOrders` is the list of order parameters in JSON**

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| symbol | STRING | YES |  |
| side | ENUM | YES | `SELL`, `BUY` |
| quantity | DECIMAL | YES | Order quantity, cannot be sent with `closePosition=true` |
| price | DECIMAL | YES |  |
| priceMatch | ENUM | NO | only avaliable for `LIMIT`/ `STOP`/ `TAKE_PROFIT` order; can be set to `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`: / `QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`; Can't be passed together with `price` |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Parameter rules are same with `Modify Order`
> - Batch modify orders are processed concurrently, and the order of matching is not guaranteed.
> - The order of returned contents for batch modify orders is the same as the order of the order list.
> - One order can only be modfied for less than 10000 times

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
		"orderId": 20072994037,\
		"symbol": "BTCUSDT",\
		"pair": "BTCUSDT",\
		"status": "NEW",\
		"clientOrderId": "LJ9R4QZDihCaS8UAOOLpgW",\
		"price": "30005",\
		"avgPrice": "0.0",\
		"origQty": "1",\
		"executedQty": "0",\
		"cumQty": "0",\
		"cumBase": "0",\
		"timeInForce": "GTC",\
		"type": "LIMIT",\
		"reduceOnly": false,\
		"closePosition": false,\
		"side": "BUY",\
		"positionSide": "LONG",\
		"stopPrice": "0",\
		"workingType": "CONTRACT_PRICE",\
		"priceProtect": false,\
		"origType": "LIMIT",\
        "priceMatch": "NONE",              //price match mode\
        "selfTradePreventionMode": "NONE", //self trading preventation mode\
        "goodTillDate": 0,                 //order pre-set auot cancel time for TIF GTD order\
		"updateTime": 1629182711600\
	},\
	{\
		"code": -2022,\
		"msg": "ReduceOnly Order is rejected."\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Multiple-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Continuous_Contract_Kline_Candlestick_Data.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data#__docusaurus_skipToContent_fallback)

On this page

# Continuous Contract Kline/Candlestick Data

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data\#api-description "Direct link to API Description")

Kline/candlestick bars for a specific contract type.
Klines are uniquely identified by their open time.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/continuousKlines`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data\#request-weight "Direct link to Request Weight")

based on parameter `LIMIT`

| LIMIT | weight |
| --- | --- |
| \[1,100) | 1 |\
| \[100, 500) | 2 |\
| \[500, 1000\] | 5 |\
| \> 1000 | 10 |\
\
## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data\#request-parameters "Direct link to Request Parameters")\
\
| Name | Type | Mandatory | Description |\
| --- | --- | --- | --- |\
| pair | STRING | YES |  |\
| contractType | ENUM | YES |  |\
| interval | ENUM | YES |  |\
| startTime | LONG | NO |  |\
| endTime | LONG | NO |  |\
| limit | INT | NO | Default 500; max 1500. |\
\
> - If startTime and endTime are not sent, the most recent klines are returned.\
\
> - Contract type:\
>   - PERPETUAL\
>   - CURRENT\_QUARTER\
>   - NEXT\_QUARTER\
\
## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data\#response-example "Direct link to Response Example")\
\
```codeBlockLines_aHhF\
[\
  [\
    1607444700000,      	// Open time\
    "18879.99",       	 	// Open\
    "18900.00",       	 	// High\
    "18878.98",       	 	// Low\
    "18896.13",      	 	// Close (or latest price)\
    "492.363", 			 	// Volume\
    1607444759999,       	// Close time\
    "9302145.66080",    	// Quote asset volume\
    1874,             		// Number of trades\
    "385.983",    			// Taker buy volume\
    "7292402.33267",      	// Taker buy quote asset volume\
    "0" 					// Ignore.\
  ]\
]\
\
```\
\
- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data#api-description)\
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data#http-request)\
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data#request-weight)\
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data#request-parameters)\
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Candlestick-Data#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Cancel_All_Open_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders#__docusaurus_skipToContent_fallback)

On this page

# Cancel All Open Orders (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders\#api-description "Direct link to API Description")

Cancel All Open Orders

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders\#http-request "Direct link to HTTP Request")

DELETE `/fapi/v1/allOpenOrders`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"code": 200,
	"msg": "The operation of cancel all open order is done."
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Users_Force_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders#__docusaurus_skipToContent_fallback)

On this page

# User's Force Orders (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders\#api-description "Direct link to API Description")

Query user's Force Orders

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/forceOrders`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders\#request-weight "Direct link to Request Weight")

**20** with symbol, **50** without symbol

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| autoCloseType | ENUM | NO | "LIQUIDATION" for liquidation orders, "ADL" for ADL orders. |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |
| limit | INT | NO | Default 50; max 100. |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - If "autoCloseType" is not sent, orders with both of the types will be returned
> - If "startTime" is not sent, data within 7 days before "endTime" can be queried

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
  	"orderId": 6071832819,\
  	"symbol": "BTCUSDT",\
  	"status": "FILLED",\
  	"clientOrderId": "autoclose-1596107620040000020",\
  	"price": "10871.09",\
  	"avgPrice": "10913.21000",\
  	"origQty": "0.001",\
  	"executedQty": "0.001",\
  	"cumQuote": "10.91321",\
  	"timeInForce": "IOC",\
  	"type": "LIMIT",\
  	"reduceOnly": false,\
  	"closePosition": false,\
  	"side": "SELL",\
  	"positionSide": "BOTH",\
  	"stopPrice": "0",\
  	"workingType": "CONTRACT_PRICE",\
  	"origType": "LIMIT",\
  	"time": 1596107620044,\
  	"updateTime": 1596107620087\
  }\
  {\
   	"orderId": 6072734303,\
   	"symbol": "BTCUSDT",\
   	"status": "FILLED",\
   	"clientOrderId": "adl_autoclose",\
   	"price": "11023.14",\
   	"avgPrice": "10979.82000",\
   	"origQty": "0.001",\
   	"executedQty": "0.001",\
   	"cumQuote": "10.97982",\
   	"timeInForce": "GTC",\
   	"type": "LIMIT",\
   	"reduceOnly": false,\
   	"closePosition": false,\
   	"side": "BUY",\
   	"positionSide": "SHORT",\
   	"stopPrice": "0",\
   	"workingType": "CONTRACT_PRICE",\
   	"origType": "LIMIT",\
   	"time": 1596110725059,\
   	"updateTime": 1596110725071\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Users-Force-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_api_general_info.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#__docusaurus_skipToContent_fallback)

On this page

# WebSocket API General Info

- The base endpoint is: **`wss://ws-fapi.binance.com/ws-fapi/v1`**
  - The base endpoint for testnet is: `wss://testnet.binancefuture.com/ws-fapi/v1`
- A single connection to the API is only valid for 24 hours; expect to be disconnected after the 24-hour mark.
- Websocket server will send a ping frame every 3 minutes.
  - If the websocket server does not receive a `pong frame` back from the connection within a 10 minute period, the connection will be disconnected.
  - When you receive a ping, you must send a pong with a copy of ping's payload as soon as possible.
  - Unsolicited pong frames are allowed, but will not prevent disconnection. **It is recommended that the payload for these pong frames are empty.**
- Signature payload must be generated by taking all request params except for the signature and sorting them by name in alphabetical order.
- Lists are returned in **chronological order**, unless noted otherwise.
- All timestamps are in **milliseconds in UTC**, unless noted otherwise.
- All field names and values are **case-sensitive**, unless noted otherwise.
- **`INT` parameters such as timestamp are expected as JSON integers, not strings.**
- **`DECIMAL` parameters such as price are expected as JSON strings, not floats.**
- **User Data Stream requests - you will need to establish a separate WebSocket connection to listen to [user data streams](https://binance-docs.github.io/apidocs/futures/en/#user-data-streams)**

## WebSocket API Request format [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#websocket-api-request-format "Direct link to WebSocket API Request format")

Requests must be sent as JSON in **text frames**, one request per frame.

> Example of request:

```codeBlockLines_aHhF
{
  "id": "9ca10e58-7452-467e-9454-f669bb9c764e",
  "method": "order.place",
  "params": {
    "apiKey": "yeqKcXjtA9Eu4Tr3nJk61UJAGzXsEmFqqfVterxpMpR4peNfqE7Zl7oans8Qj089",
    "price": "42088.0",
    "quantity": "0.1",
    "recvWindow": 5000,
    "side": "BUY",
    "signature": "996962a19802b5a09d7bc6ab1524227894533322a2f8a1f8934991689cabf8fe",
    "symbol": "BTCUSDT",
    "timeInForce": "GTC",
    "timestamp": 1705311512994,
    "type": "LIMIT"
  }
}

```

Request fields:

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| `id` | INT/STRING/null | YES | Arbitrary ID used to match responses to requests |
| `method` | STRING | YES | Request method name |
| `params` | OBJECT | NO | Request parameters. May be omitted if there are no parameters |
|  |  |  |  |

- Request `id` is truly arbitrary. You can use UUIDs, sequential IDs, current timestamp, etc. The server does not interpret `id` in any way, simply echoing it back in the response.

You can freely reuse IDs within a session. However, be careful to not send more than one request at a time with the same ID, since otherwise it might be impossible to tell the responses apart.

- Request method names may be prefixed with explicit version: e.g., " `v3/order.place`".
- The order of `params` is not significant.

## Response format [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#response-format "Direct link to Response format")

Responses are returned as JSON in text frames, one response per frame.

> Example of successful response:

```codeBlockLines_aHhF
{
  "id": "43a3843a-2321-4e45-8f79-351e5c354563",
  "status": 200,
  "result": {
    "orderId": 336829446,
    "symbol": "BTCUSDT",
    "status": "NEW",
    "clientOrderId": "FqEw6cn0vDhrkmfiwLYPeo",
    "price": "42088.00",
    "avgPrice": "0.00",
    "origQty": "0.100",
    "executedQty": "0.000",
    "cumQty": "0.000",
    "cumQuote": "0.00000",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "BOTH",
    "stopPrice": "0.00",
    "workingType": "CONTRACT_PRICE",
    "priceProtect": false,
    "origType": "LIMIT",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "NONE",
    "goodTillDate": 0,
    "updateTime": 1705385954229
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 1\
    },\
    {\
      "rateLimitType": "ORDERS",\
      "interval": "SECOND",\
      "intervalNum": 10,\
      "limit": 300,\
      "count": 1\
    },\
    {\
      "rateLimitType": "ORDERS",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 1200,\
      "count": 0\
    }\
  ]
}

```

> Example of failed response:

```codeBlockLines_aHhF
{
  "id": "5761b939-27b1-4948-ab87-4a372a3f6b72",
  "status": 400,
  "error": {
    "code": -1102,
    "msg": "Mandatory parameter 'quantity' was not sent, was empty/null, or malformed."
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 1\
    },\
    {\
      "rateLimitType": "ORDERS",\
      "interval": "SECOND",\
      "intervalNum": 10,\
      "limit": 300,\
      "count": 1\
    },\
    {\
      "rateLimitType": "ORDERS",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 1200,\
      "count": 1\
    }\
  ]
}

```

Response fields:

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| `id` | INT/STRING/null | YES | Same as in the original request |
| `status` | INT | YES | Response status. See status codes |
| `result` | OBJECT/ARRAY | YES | Response content. Present if request succeeded |
| `error` | OBJECT | YES | Error description. Present if request failed |
| `rateLimits` | ARRAY | NO | Rate limiting status. See Rate limits |

## WebSocket API Rate limits [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#websocket-api-rate-limits "Direct link to WebSocket API Rate limits")

- Rate limits are the same as on REST API and are shared with REST API.
- WebSocket handshake attempt costs 5 weight.
- Rate limit for ping/pong frames: maximum 5 per second.
- Rate limit information is included in responses by default, see the `rateLimits` field.
- `rateLimits` field visibility can be controlled with `returnRateLimits` boolean parameter in connection string or individual requests.
- E.g., use `wss://ws-fapi.binance.com/ws-fapi/v1?returnRateLimits=false` to hide `rateLimits` in responses by default. With that, you can pass extra `"returnRateLimits": true` parameter in requests to show rate limit in response when it is otherwise hidden by default.

## WebSocket API Authenticate after connection [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#websocket-api-authenticate-after-connection "Direct link to WebSocket API Authenticate after connection")

You can authenticate an already established connection using session authentication requests:

- `session.logon` \- authenticate, or change the API key associated with the connection
- `session.status` \- check connection status and the current API key
- `session.logout` \- forget the API key associated with the connection

## WebSocket API API key revocation [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#websocket-api-api-key-revocation "Direct link to WebSocket API API key revocation")

If during an active session the API key becomes invalid for any reason (e.g. IP address is not whitelisted, API key was deleted, API key doesn't have correct permissions, etc), after the next request the session will be revoked with the following error message:

```codeBlockLines_aHhF
{
  "id": null,
  "status": 401,
  "error": {
    "code": -2015,
    "msg": "Invalid API-key, IP, or permissions for action."
  }
}

```

## WebSocket API Authorize ad hoc requests [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#websocket-api-authorize-ad-hoc-requests "Direct link to WebSocket API Authorize ad hoc requests")

Only one API key can be authenticated with the WebSocket connection. The authenticated API key is used by default for requests that require an apiKey parameter. However, you can always specify the apiKey and signature explicitly for individual requests, overriding the authenticated API key and using a different one to authorize a specific request.

For example, you might want to authenticate your USER\_DATA key to be used by default, but specify the TRADE key with an explicit signature when placing orders.

## WebSocket API Authentication request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#websocket-api-authentication-request "Direct link to WebSocket API Authentication request")

**Note**:

> Only _Ed25519_ keys are supported for this feature.

### Log in with API key (SIGNED) [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#log-in-with-api-key-signed "Direct link to Log in with API key (SIGNED)")

> **Request**

```codeBlockLines_aHhF
{
  "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
  "method": "session.logon",
  "params": {
    "apiKey": "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A",
    "signature": "1cf54395b336b0a9727ef27d5d98987962bc47aca6e13fe978612d0adee066ed",
    "timestamp": 1649729878532
  }
}

```

> **Response**

```codeBlockLines_aHhF
{
  "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
  "status": 200,
  "result": {
    "apiKey": "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A",
    "authorizedSince": 1649729878532,
    "connectedSince": 1649729873021,
    "returnRateLimits": false,
    "serverTime": 1649729878630
  }
}

```

Authenticate WebSocket connection using the provided API key.

After calling `session.logon`, you can omit `apiKey` and `signature` parameters for future requests that require them.

Note that only one API key can be authenticated. Calling `session.logon` multiple times changes the current authenticated API key.

**Weight:** 2

**Method**: "session.logon"

**Parameters**

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| `apiKey` | STRING | YES |  |
| `recvWindow` | INT | NO |  |
| `signature` | STRING | YES |  |
| `timestamp` | INT | YES |  |

### Query session status [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#query-session-status "Direct link to Query session status")

> **Request**

```codeBlockLines_aHhF
{
  "id": "b50c16cd-62c9-4e29-89e4-37f10111f5bf",
  "method": "session.status"
}

```

> **Response**

```codeBlockLines_aHhF
{
  "id": "b50c16cd-62c9-4e29-89e4-37f10111f5bf",
  "status": 200,
  "result": {
    // if the connection is not authenticated, "apiKey" and "authorizedSince" will be shown as null
    "apiKey": "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A",
    "authorizedSince": 1649729878532,
    "connectedSince": 1649729873021,
    "returnRateLimits": false,
    "serverTime": 1649730611671
  }
}

```

Query the status of the WebSocket connection, inspecting which API key (if any) is used to authorize requests.

**Weight:** 2

**Method**: "session.status"

**Parameters**: None

### Log out of the session [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#log-out-of-the-session "Direct link to Log out of the session")

> **Request**

```codeBlockLines_aHhF
{
  "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
  "method": "session.logout"
}

```

> **Response**

```codeBlockLines_aHhF
{
  "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
  "status": 200,
  "result": {
    "apiKey": null,
    "authorizedSince": null,
    "connectedSince": 1649729873021,
    "returnRateLimits": false,
    "serverTime": 1649730611671
  }
}

```

Forget the API key previously authenticated. If the connection is not authenticated, this request does nothing.

Note that the WebSocket connection stays open after `session.logout` request. You can continue using the connection, but now you will have to explicitly provide the `apiKey` and `signature` parameters where needed.

**Weight:** 2

**Method**: "session.logout"

**Parameters**: None

## SIGNED (TRADE and USER\_DATA) Endpoint Security [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#signed-trade-and-user_data-endpoint-security "Direct link to SIGNED (TRADE and USER_DATA) Endpoint Security")

### SIGNED request example (Ed25519) [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info\#signed-request-example-ed25519 "Direct link to SIGNED request example (Ed25519)")

| Parameter | Value |
| --- | --- |
| symbol | BTCUSDT |
| side | SELL |
| type | LIMIT |
| timeInForce | GTC |
| quantity | 1 |
| price | 0.2 |
| timestamp | 1668481559918 |

```codeBlockLines_aHhF
#!/usr/bin/env python3

import base64
import time
import json
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from websocket import create_connection

# Set up authentication
API_KEY='put your own API Key here'
PRIVATE_KEY_PATH='test-prv-key.pem'

# Load the private key.
# In this example the key is expected to be stored without encryption,
# but we recommend using a strong password for improved security.
with open(PRIVATE_KEY_PATH, 'rb') as f:
    private_key = load_pem_private_key(data=f.read(),
                                       password=None)

# Set up the request parameters
params = {
    'apiKey':        API_KEY,
    'symbol':       'BTCUSDT',
    'side':         'SELL',
    'type':         'LIMIT',
    'timeInForce':  'GTC',
    'quantity':     '1.0000000',
    'price':        '0.20'
}

# Timestamp the request
timestamp = int(time.time() * 1000) # UNIX timestamp in milliseconds
params['timestamp'] = timestamp

# Sign the request
payload = '&'.join([f'{param}={value}' for param, value in sorted(params.items())])

signature = base64.b64encode(private_key.sign(payload.encode('ASCII')))
params['signature'] = signature.decode('ASCII')

# Send the request
request = {
    'id': 'my_new_order',
    'method': 'order.place',
    'params': params
}

ws = create_connection("wss://ws-fapi.binance.com/ws-fapi/v1")
ws.send(json.dumps(request))
result =  ws.recv()
ws.close()

print(result)

```

A sample code in Python to show how to sign the payload with an Ed25519 key is available on the right side.

- [WebSocket API Request format](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#websocket-api-request-format)
- [Response format](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#response-format)
- [WebSocket API Rate limits](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#websocket-api-rate-limits)
- [WebSocket API Authenticate after connection](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#websocket-api-authenticate-after-connection)
- [WebSocket API API key revocation](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#websocket-api-api-key-revocation)
- [WebSocket API Authorize ad hoc requests](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#websocket-api-authorize-ad-hoc-requests)
- [WebSocket API Authentication request](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#websocket-api-authentication-request)
  - [Log in with API key (SIGNED)](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#log-in-with-api-key-signed)
  - [Query session status](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#query-session-status)
  - [Log out of the session](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#log-out-of-the-session)
- [SIGNED (TRADE and USER\_DATA) Endpoint Security](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#signed-trade-and-user_data-endpoint-security)
  - [SIGNED request example (Ed25519)](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info#signed-request-example-ed25519)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Index_Constituents.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents#__docusaurus_skipToContent_fallback)

On this page

# Query Index Price Constituents

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents\#api-description "Direct link to API Description")

Query index price constituents

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/constituents`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents\#request-weight "Direct link to Request Weight")

**2**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "symbol": "BTCUSDT",
    "time": 1745401553408,
    "constituents": [\
        {\
            "exchange": "binance",\
            "symbol": "BTCUSDT",\
            "price": "94057.03000000",\
            "weight": "0.51282051"\
        },\
        {\
            "exchange": "coinbase",\
            "symbol": "BTC-USDT",\
            "price": "94140.58000000",\
            "weight": "0.15384615"\
        },\
        {\
            "exchange": "gateio",\
            "symbol": "BTC_USDT",\
            "price": "94060.10000000",\
            "weight": "0.02564103"\
        },\
        {\
            "exchange": "kucoin",\
            "symbol": "BTC-USDT",\
            "price": "94096.70000000",\
            "weight": "0.07692308"\
        },\
        {\
            "exchange": "mxc",\
            "symbol": "BTCUSDT",\
            "price": "94057.02000000",\
            "weight": "0.07692308"\
        },\
        {\
            "exchange": "bitget",\
            "symbol": "BTCUSDT",\
            "price": "94064.03000000",\
            "weight": "0.07692308"\
        },\
        {\
            "exchange": "bybit",\
            "symbol": "BTCUSDT",\
            "price": "94067.90000000",\
            "weight": "0.07692308"\
        }\
    ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Constituents#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Keepalive_User_Data_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream#__docusaurus_skipToContent_fallback)

On this page

# Keepalive User Data Stream (USER\_STREAM)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream\#api-description "Direct link to API Description")

Keepalive a user data stream to prevent a time out. User data streams will close after 60 minutes. It's recommended to send a ping about every 60 minutes.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream\#http-request "Direct link to HTTP Request")

PUT `/fapi/v1/listenKey`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream\#request-parameters "Direct link to Request Parameters")

None

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "listenKey": "3HBntNTepshgEdjIwSUIBgB9keLyOCg5qv3n6bYAtktG8ejcaW5HXz9Vx1JgIieg" //the listenkey which got extended
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_websocket_api_Account_Information_V2.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2#__docusaurus_skipToContent_fallback)

On this page

# Account Information V2(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2\#api-description "Direct link to API Description")

Get current account information. User in single-asset/ multi-assets mode will see different value, see comments in response section for detail.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2\#method "Direct link to Method")

`v2/account.status`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "method": "v2/account.status",
    "params": {
        "apiKey": "xTaDyrmvA9XT2oBHHjy39zyPzKCvMdtH3b9q4xadkAg2dNSJXQGCxzui26L823W2",
        "timestamp": 1702620814781,
        "signature": "6bb98ef84170c70ba3d01f44261bfdf50fef374e551e590de22b5c3b729b1d8c"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2\#response-example "Direct link to Response Example")

> Single Asset Mode

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": {
  	"totalInitialMargin": "0.00000000",            // total initial margin required with current mark price (useless with isolated positions), only for USDT asset
  	"totalMaintMargin": "0.00000000",  	           // total maintenance margin required, only for USDT asset
  	"totalWalletBalance": "103.12345678",           // total wallet balance, only for USDT asset
  	"totalUnrealizedProfit": "0.00000000",         // total unrealized profit, only for USDT asset
  	"totalMarginBalance": "103.12345678",           // total margin balance, only for USDT asset
  	"totalPositionInitialMargin": "0.00000000",    // initial margin required for positions with current mark price, only for USDT asset
  	"totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price, only for USDT asset
  	"totalCrossWalletBalance": "103.12345678",      // crossed wallet balance, only for USDT asset
  	"totalCrossUnPnl": "0.00000000",	           // unrealized profit of crossed positions, only for USDT asset
  	"availableBalance": "103.12345678",             // available balance, only for USDT asset
  	"maxWithdrawAmount": "103.12345678"             // maximum amount for transfer out, only for USDT asset
  	"assets": [ // For assets that are quote assets, USDT/USDC/BTC\
  		{\
  			"asset": "USDT",			            // asset name\
  			"walletBalance": "23.72469206",         // wallet balance\
  			"unrealizedProfit": "0.00000000",       // unrealized profit\
  			"marginBalance": "23.72469206",         // margin balance\
  			"maintMargin": "0.00000000",	        // maintenance margin required\
  			"initialMargin": "0.00000000",          // total initial margin required with current mark price\
  			"positionInitialMargin": "0.00000000",  // initial margin required for positions with current mark price\
  			"openOrderInitialMargin": "0.00000000", // initial margin required for open orders with current mark price\
  			"crossWalletBalance": "23.72469206",    // crossed wallet balance\
  			"crossUnPnl": "0.00000000"              // unrealized profit of crossed positions\
  			"availableBalance": "23.72469206",      // available balance\
  			"maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
  			"updateTime": 1625474304765             // last update time\
  		},\
   		{\
  			"asset": "USDC",			            // asset name\
  			"walletBalance": "103.12345678",         // wallet balance\
  			"unrealizedProfit": "0.00000000",       // unrealized profit\
  			"marginBalance": "103.12345678",         // margin balance\
  			"maintMargin": "0.00000000",	        // maintenance margin required\
  			"initialMargin": "0.00000000",          // total initial margin required with current mark price\
  			"positionInitialMargin": "0.00000000",  // initial margin required for positions with current mark price\
  			"openOrderInitialMargin": "0.00000000", // initial margin required for open orders with current mark price\
  			"crossWalletBalance": "103.12345678",    // crossed wallet balance\
  			"crossUnPnl": "0.00000000"              // unrealized profit of crossed positions\
  			"availableBalance": "126.72469206",      // available balance\
  			"maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
  			"updateTime": 1625474304765             // last update time\
  		},\
      ],
  	"positions": [  // positions of all symbols user had position/ open orders are returned\
  		            // only "BOTH" positions will be returned with One-way mode\
  		            // only "LONG" and "SHORT" positions will be returned with Hedge mode\
     	  {\
             "symbol": "BTCUSDT",\
             "positionSide": "BOTH",            // position side\
             "positionAmt": "1.000",\
             "unrealizedProfit": "0.00000000",  // unrealized profit\
             "isolatedMargin": "0.00000000",\
             "notional": "0",\
             "isolatedWallet": "0",\
             "initialMargin": "0",              // initial margin required with current mark price\
             "maintMargin": "0",                // maintenance margin required\
             "updateTime": 0\
    	  }\
  	]
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

> Multi-Asset Mode

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": {
  	"totalInitialMargin": "0.00000000",            // the sum of USD value of all cross positions/open order initial margin
  	"totalMaintMargin": "0.00000000",  	           // the sum of USD value of all cross positions maintenance margin
  	"totalWalletBalance": "126.72469206",          // total wallet balance in USD
  	"totalUnrealizedProfit": "0.00000000",         // total unrealized profit in USD
  	"totalMarginBalance": "126.72469206",          // total margin balance in USD
  	"totalPositionInitialMargin": "0.00000000",    // the sum of USD value of all cross positions initial margin
  	"totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price in USD
  	"totalCrossWalletBalance": "126.72469206",     // crossed wallet balance in USD
  	"totalCrossUnPnl": "0.00000000",	           // unrealized profit of crossed positions in USD
  	"availableBalance": "126.72469206",            // available balance in USD
  	"maxWithdrawAmount": "126.72469206"            // maximum virtual amount for transfer out in USD
  	"assets": [\
  		{\
  			"asset": "USDT",			         // asset name\
  			"walletBalance": "23.72469206",      // wallet balance\
  			"unrealizedProfit": "0.00000000",    // unrealized profit\
  			"marginBalance": "23.72469206",      // margin balance\
  			"maintMargin": "0.00000000",	     // maintenance margin required\
  			"initialMargin": "0.00000000",       // total initial margin required with current mark price\
  			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
  			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
  			"crossWalletBalance": "23.72469206",      // crossed wallet balance\
  			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
  			"availableBalance": "126.72469206",       // available balance\
  			"maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
  			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
  			"updateTime": 1625474304765 // last update time\
  		},\
  		{\
  			"asset": "BUSD",			// asset name\
  			"walletBalance": "103.12345678",      // wallet balance\
  			"unrealizedProfit": "0.00000000",    // unrealized profit\
  			"marginBalance": "103.12345678",      // margin balance\
  			"maintMargin": "0.00000000",	    // maintenance margin required\
  			"initialMargin": "0.00000000",    // total initial margin required with current mark price\
  			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
  			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
  			"crossWalletBalance": "103.12345678",      // crossed wallet balance\
  			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
  			"availableBalance": "126.72469206",       // available balance\
  			"maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
  			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
  			"updateTime": 1625474304765 // last update time\
  		}\
  	],
   	"positions": [  // positions of all symbols user had position are returned\
                      // only "BOTH" positions will be returned with One-way mode\
  		            // only "LONG" and "SHORT" positions will be returned with Hedge mode\
     	  {\
             "symbol": "BTCUSDT",\
             "positionSide": "BOTH",            // position side\
             "positionAmt": "1.000",\
             "unrealizedProfit": "0.00000000",  // unrealized profit\
             "isolatedMargin": "0.00000000",\
             "notional": "0",\
             "isolatedWallet": "0",\
             "initialMargin": "0",              // initial margin required with current mark price\
             "maintMargin": "0",                // maintenance margin required\
             "updateTime": 0\
    	  }\
  	]
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information-V2#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_New_Order_Test.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test#__docusaurus_skipToContent_fallback)

On this page

# Test Order(TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test\#api-description "Direct link to API Description")

Testing order request, this order will not be submitted to matching engine

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/order/test`

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| side | ENUM | YES |  |
| positionSide | ENUM | NO | Default `BOTH` for One-way Mode ; `LONG` or `SHORT` for Hedge Mode. It must be sent in Hedge Mode. |
| type | ENUM | YES |  |
| timeInForce | ENUM | NO |  |
| quantity | DECIMAL | NO | Cannot be sent with `closePosition` = `true`(Close-All) |
| reduceOnly | STRING | NO | "true" or "false". default "false". Cannot be sent in Hedge Mode; cannot be sent with `closePosition` = `true` |
| price | DECIMAL | NO |  |
| newClientOrderId | STRING | NO | A unique id among open orders. Automatically generated if not sent. Can only be string following the rule: `^[\.A-Z\:/a-z0-9_-]{1,36}$` |
| stopPrice | DECIMAL | NO | Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| closePosition | STRING | NO | `true`, `false`；Close-All，used with `STOP_MARKET` or `TAKE_PROFIT_MARKET`. |
| activationPrice | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, default as the latest price(supporting different `workingType`) |
| callbackRate | DECIMAL | NO | Used with `TRAILING_STOP_MARKET` orders, min 0.1, max 5 where 1 for 1% |
| workingType | ENUM | NO | stopPrice triggered by: "MARK\_PRICE", "CONTRACT\_PRICE". Default "CONTRACT\_PRICE" |
| priceProtect | STRING | NO | "TRUE" or "FALSE", default "FALSE". Used with `STOP/STOP_MARKET` or `TAKE_PROFIT/TAKE_PROFIT_MARKET` orders. |
| newOrderRespType | ENUM | NO | "ACK", "RESULT", default "ACK" |
| priceMatch | ENUM | NO | only avaliable for `LIMIT`/ `STOP`/ `TAKE_PROFIT` order; can be set to `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`: / `QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`; Can't be passed together with `price` |
| selfTradePreventionMode | ENUM | NO | `NONE`:No STP / `EXPIRE_TAKER`:expire taker order when STP triggers/ `EXPIRE_MAKER`:expire taker order when STP triggers/ `EXPIRE_BOTH`:expire both orders when STP triggers; default `NONE` |
| goodTillDate | LONG | NO | order cancel time for timeInForce `GTD`, mandatory when `timeInforce` set to `GTD`; order the timestamp only retains second-level precision, ms part will be ignored; The goodTillDate timestamp must be greater than the current time plus 600 seconds and smaller than 253402300799000 |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

Additional mandatory parameters based on `type`:

| Type | Additional mandatory parameters |
| --- | --- |
| `LIMIT` | `timeInForce`, `quantity`, `price` |
| `MARKET` | `quantity` |
| `STOP/TAKE_PROFIT` | `quantity`, `price`, `stopPrice` |
| `STOP_MARKET/TAKE_PROFIT_MARKET` | `stopPrice` |
| `TRAILING_STOP_MARKET` | `callbackRate` |

> - Order with type `STOP`, parameter `timeInForce` can be sent ( default `GTC`).
>
> - Order with type `TAKE_PROFIT`, parameter `timeInForce` can be sent ( default `GTC`).
>
> - Condition orders will be triggered when:
>   - If parameter `priceProtect` is sent as true:
>
>     - when price reaches the `stopPrice` ，the difference rate between "MARK\_PRICE" and "CONTRACT\_PRICE" cannot be larger than the "triggerProtect" of the symbol
>     - "triggerProtect" of a symbol can be got from `GET /fapi/v1/exchangeInfo`
>   - `STOP`, `STOP_MARKET`:
>
>     - BUY: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") >= `stopPrice`
>     - SELL: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") <= `stopPrice`
>   - `TAKE_PROFIT`, `TAKE_PROFIT_MARKET`:
>
>     - BUY: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") <= `stopPrice`
>     - SELL: latest price ("MARK\_PRICE" or "CONTRACT\_PRICE") >= `stopPrice`
>   - `TRAILING_STOP_MARKET`:
>
>     - BUY: the lowest price after order placed `<= ` activationPrice `, and the latest price >` = the lowest price \* (1 + `callbackRate`)
>     - SELL: the highest price after order placed >= `activationPrice`, and the latest price <= the highest price \* (1 - `callbackRate`)
> - For `TRAILING_STOP_MARKET`, if you got such error code.
>
>   `{"code": -2021, "msg": "Order would immediately trigger."}`
>
>
>   means that the parameters you send do not meet the following requirements:
>   - BUY: `activationPrice` should be smaller than latest price.
>   - SELL: `activationPrice` should be larger than latest price.
> - If `newOrderRespType ` is sent as `RESULT` :
>   - `MARKET` order: the final FILLED result of the order will be return directly.
>   - `LIMIT` order with special `timeInForce`: the final status result of the order(FILLED or EXPIRED) will be returned directly.
> - `STOP_MARKET`, `TAKE_PROFIT_MARKET` with `closePosition` = `true`:
>   - Follow the same rules for condition orders.
>   - If triggered， **close all** current long position( if `SELL`) or current short position( if `BUY`).
>   - Cannot be used with `quantity` paremeter
>   - Cannot be used with `reduceOnly` parameter
>   - In Hedge Mode,cannot be used with `BUY` orders in `LONG` position side. and cannot be used with `SELL` orders in `SHORT` position side
> - `selfTradePreventionMode` is only effective when `timeInForce` set to `IOC` or `GTC` or `GTD`.
>
> - In extreme market conditions, timeInForce `GTD` order auto cancel time might be delayed comparing to `goodTillDate`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
 	"clientOrderId": "testOrder",
 	"cumQty": "0",
 	"cumQuote": "0",
 	"executedQty": "0",
 	"orderId": 22542179,
 	"avgPrice": "0.00000",
 	"origQty": "10",
 	"price": "0",
  	"reduceOnly": false,
  	"side": "BUY",
  	"positionSide": "SHORT",
  	"status": "NEW",
  	"stopPrice": "9300",		// please ignore when order type is TRAILING_STOP_MARKET
  	"closePosition": false,   // if Close-All
  	"symbol": "BTCUSDT",
  	"timeInForce": "GTD",
  	"type": "TRAILING_STOP_MARKET",
  	"origType": "TRAILING_STOP_MARKET",
  	"activatePrice": "9020",	// activation price, only return with TRAILING_STOP_MARKET order
  	"priceRate": "0.3",			// callback rate, only return with TRAILING_STOP_MARKET order
 	"updateTime": 1566818724722,
 	"workingType": "CONTRACT_PRICE",
 	"priceProtect": false,      // if conditional order trigger is protected
 	"priceMatch": "NONE",              //price match mode
 	"selfTradePreventionMode": "NONE", //self trading preventation mode
 	"goodTillDate": 1693207680000      //order pre-set auot cancel time for TIF GTD order
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test#http-request)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Future_Account_Transaction_History_List.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Future-Account-Transaction-History-List#__docusaurus_skipToContent_fallback)

# Get Future Account Transaction History List(USER\_DATA)

Please find details from [here](https://developers.binance.com/docs/wallet/asset/query-user-universal-transfer).


[developers_binance_com_docs_derivatives_usds_margined_futures_portfolio_margin_endpoints.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints#__docusaurus_skipToContent_fallback)

On this page

# Classic Portfolio Margin Account Information (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints\#api-description "Direct link to API Description")

Get Classic Portfolio Margin current account information.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/pmAccountInfo`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| asset | STRING | YES |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - maxWithdrawAmount is for asset transfer out to the spot wallet.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"maxWithdrawAmountUSD": "1627523.32459208",   // Classic Portfolio margin maximum virtual amount for transfer out in USD
	"asset": "BTC",            // asset name
	"maxWithdrawAmount": "27.43689636",        // maximum amount for transfer out
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/portfolio-margin-endpoints#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Position_ADL_Quantile_Estimation.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation#__docusaurus_skipToContent_fallback)

On this page

# Position ADL Quantile Estimation(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation\#api-description "Direct link to API Description")

Position ADL Quantile Estimation

> - Values update every 30s.
> - Values 0, 1, 2, 3, 4 shows the queue position and possibility of ADL from low to high.
> - For positions of the symbol are in One-way Mode or isolated margined in Hedge Mode, "LONG", "SHORT", and "BOTH" will be returned to show the positions' adl quantiles of different position sides.
> - If the positions of the symbol are crossed margined in Hedge Mode:
>   - "HEDGE" as a sign will be returned instead of "BOTH";
>   - A same value caculated on unrealized pnls on long and short sides' positions will be shown for "LONG" and "SHORT" when there are positions in both of long and short sides.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/adlQuantile`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
		"symbol": "ETHUSDT",\
		"adlQuantile":\
			{\
				// if the positions of the symbol are crossed margined in Hedge Mode, "LONG" and "SHORT" will be returned a same quantile value, and "HEDGE" will be returned instead of "BOTH".\
				"LONG": 3,\
				"SHORT": 3,\
				"HEDGE": 0   // only a sign, ignore the value\
			}\
		},\
 	{\
 		"symbol": "BTCUSDT",\
 		"adlQuantile":\
 			{\
 				// for positions of the symbol are in One-way Mode or isolated margined in Hedge Mode\
 				"LONG": 1, 	// adl quantile for "LONG" position in hedge mode\
 				"SHORT": 2, 	// adl qauntile for "SHORT" position in hedge mode\
 				"BOTH": 0		// adl qunatile for position in one-way mode\
 			}\
 	}\
 ]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-ADL-Quantile-Estimation#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_Balance_and_Position_Update.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update#__docusaurus_skipToContent_fallback)

On this page

# Event: Balance and Position Update

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update\#event-description "Direct link to Event Description")

Event type is `ACCOUNT_UPDATE`.

- When balance or position get updated, this event will be pushed.
  - `ACCOUNT_UPDATE` will be pushed only when update happens on user's account, including changes on balances, positions, or margin type.
  - Unfilled orders or cancelled orders will not make the event `ACCOUNT_UPDATE` pushed, since there's no change on positions.
  - "position" in `ACCOUNT_UPDATE`: Only symbols of changed positions will be pushed.
- When "FUNDING FEE" changes to the user's balance, the event will be pushed with the brief message:
  - When "FUNDING FEE" occurs in a **crossed position**, `ACCOUNT_UPDATE` will be pushed with only the balance `B`(including the "FUNDING FEE" asset only), without any position `P` message.
  - When "FUNDING FEE" occurs in an **isolated position**, `ACCOUNT_UPDATE` will be pushed with only the balance `B`(including the "FUNDING FEE" asset only) and the relative position message `P`( including the isolated position on which the "FUNDING FEE" occurs only, without any other position message).
- The field "m" represents the reason type for the event and may shows the following possible types:
  - DEPOSIT
  - WITHDRAW
  - ORDER
  - FUNDING\_FEE
  - WITHDRAW\_REJECT
  - ADJUSTMENT
  - INSURANCE\_CLEAR
  - ADMIN\_DEPOSIT
  - ADMIN\_WITHDRAW
  - MARGIN\_TRANSFER
  - MARGIN\_TYPE\_CHANGE
  - ASSET\_TRANSFER
  - OPTIONS\_PREMIUM\_FEE
  - OPTIONS\_SETTLE\_PROFIT
  - AUTO\_EXCHANGE
  - COIN\_SWAP\_DEPOSIT
  - COIN\_SWAP\_WITHDRAW
- The field "bc" represents the balance change except for PnL and commission.


## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update\#event-name "Direct link to Event Name")

`ACCOUNT_UPDATE`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e": "ACCOUNT_UPDATE",				// Event Type
  "E": 1564745798939,            		// Event Time
  "T": 1564745798938 ,           		// Transaction
  "a":                          		// Update Data
    {
      "m":"ORDER",						// Event reason type
      "B":[                     		// Balances\
        {\
          "a":"USDT",           		// Asset\
          "wb":"122624.12345678",    	// Wallet Balance\
          "cw":"100.12345678",			// Cross Wallet Balance\
          "bc":"50.12345678"			// Balance Change except PnL and Commission\
        },\
        {\
          "a":"BUSD",\
          "wb":"1.00000000",\
          "cw":"0.00000000",\
          "bc":"-49.12345678"\
        }\
      ],
      "P":[\
        {\
          "s":"BTCUSDT",          	// Symbol\
          "pa":"0",               	// Position Amount\
          "ep":"0.00000",            // Entry Price\
          "bep":"0",                // breakeven price\
		  "cr":"200",             	// (Pre-fee) Accumulated Realized\
          "up":"0",						// Unrealized PnL\
          "mt":"isolated",				// Margin Type\
          "iw":"0.00000000",			// Isolated Wallet (if isolated position)\
          "ps":"BOTH"					// Position Side\
        }，\
        {\
        	"s":"BTCUSDT",\
        	"pa":"20",\
        	"ep":"6563.66500",\
        	"bep":"0",                // breakeven price\
        	"cr":"0",\
        	"up":"2850.21200",\
        	"mt":"isolated",\
        	"iw":"13200.70726908",\
        	"ps":"LONG"\
      	 },\
        {\
        	"s":"BTCUSDT",\
        	"pa":"-10",\
        	"ep":"6563.86000",\
        	"bep":"6563.6",          // breakeven price\
        	"cr":"-45.04000000",\
        	"up":"-1423.15600",\
        	"mt":"isolated",\
        	"iw":"6570.42511771",\
        	"ps":"SHORT"\
        }\
      ]
    }
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Balance-and-Position-Update#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Order_Book.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book#__docusaurus_skipToContent_fallback)

On this page

# Order Book

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book\#api-description "Direct link to API Description")

Query symbol orderbook

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/depth`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book\#request-weight "Direct link to Request Weight")

Adjusted based on the limit:

| Limit | Weight |
| --- | --- |
| 5, 10, 20, 50 | 2 |
| 100 | 5 |
| 500 | 10 |
| 1000 | 20 |

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| limit | INT | NO | Default 500; Valid limits:\[5, 10, 20, 50, 100, 500, 1000\] |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "lastUpdateId": 1027024,
  "E": 1589436922972,   // Message output time
  "T": 1589436922959,   // Transaction time
  "bids": [\
    [\
      "4.00000000",     // PRICE\
      "431.00000000"    // QTY\
    ]\
  ],
  "asks": [\
    [\
      "4.00000200",\
      "12.00000000"\
    ]\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Open_Interest.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest#__docusaurus_skipToContent_fallback)

On this page

# Open Interest

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest\#api-description "Direct link to API Description")

Get present open interest of a specific symbol.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/openInterest`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"openInterest": "10659.509",
	"symbol": "BTCUSDT",
	"time": 1589437530011   // Transaction time
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Multi_Assets_Mode_Asset_Index.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index#__docusaurus_skipToContent_fallback)

On this page

# Multi-Assets Mode Asset Index

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index\#stream-description "Direct link to Stream Description")

Asset index for multi-assets mode user

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index\#stream-name "Direct link to Stream Name")

`!assetIndex@arr` OR `<assetSymbol>@assetIndex`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index\#update-speed "Direct link to Update Speed")

**1s**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
      "e":"assetIndexUpdate",\
      "E":1686749230000,\
      "s":"ADAUSD",           // asset index symbol\
      "i":"0.27462452",       // index price\
      "b":"0.10000000",       // bid buffer\
      "a":"0.10000000",       // ask buffer\
      "B":"0.24716207",       // bid rate\
      "A":"0.30208698",       // ask rate\
      "q":"0.05000000",       // auto exchange bid buffer\
      "g":"0.05000000",       // auto exchange ask buffer\
      "Q":"0.26089330",       // auto exchange bid rate\
      "G":"0.28835575"        // auto exchange ask rate\
    },\
    {\
      "e":"assetIndexUpdate",\
      "E":1686749230000,\
      "s":"USDTUSD",\
      "i":"0.99987691",\
      "b":"0.00010000",\
      "a":"0.00010000",\
      "B":"0.99977692",\
      "A":"0.99997689",\
      "q":"0.00010000",\
      "g":"0.00010000",\
      "Q":"0.99977692",\
      "G":"0.99997689"\
    }\
]

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Multi-Assets-Mode-Asset-Index#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_How_to_manage_a_local_order_book_correctly.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly#__docusaurus_skipToContent_fallback)

# How to manage a local order book correctly

1. Open a stream to **wss://fstream.binance.com/stream?streams=btcusdt@depth**.
2. Buffer the events you receive from the stream. For same price, latest received update covers the previous one.
3. Get a depth snapshot from **[https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000](https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000)** .
4. Drop any event where `u` is < `lastUpdateId` in the snapshot.
5. The first processed event should have `U` `<= ` lastUpdateId `**AND**` u ` >` = `lastUpdateId`
6. While listening to the stream, each new event's `pu` should be equal to the previous event's `u`, otherwise initialize the process from step 3.
7. The data in each event is the **absolute** quantity for a price level.
8. If the quantity is 0, **remove** the price level.
9. Receiving an event that removes a price level that is not in your local order book can happen and is normal.


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Position_Information_V2.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2#__docusaurus_skipToContent_fallback)

On this page

# Position Information V2 (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2\#api-description "Direct link to API Description")

Get current position information.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2\#http-request "Direct link to HTTP Request")

GET `/fapi/v2/positionRisk`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

**Note**

> Please use with user data stream `ACCOUNT_UPDATE` to meet your timeliness and accuracy needs.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2\#response-example "Direct link to Response Example")

> For One-way position mode:

```codeBlockLines_aHhF
[\
  	{\
  		"entryPrice": "0.00000",\
        "breakEvenPrice": "0.0",\
  		"marginType": "isolated",\
  		"isAutoAddMargin": "false",\
  		"isolatedMargin": "0.00000000",\
  		"leverage": "10",\
  		"liquidationPrice": "0",\
  		"markPrice": "6679.50671178",\
  		"maxNotionalValue": "20000000",\
  		"positionAmt": "0.000",\
  		"notional": "0",,\
  		"isolatedWallet": "0",\
  		"symbol": "BTCUSDT",\
  		"unRealizedProfit": "0.00000000",\
  		"positionSide": "BOTH",\
  		"updateTime": 0\
  	}\
]

```

> For Hedge position mode:

```codeBlockLines_aHhF
[\
    {\
        "symbol": "BTCUSDT",\
        "positionAmt": "0.001",\
        "entryPrice": "22185.2",\
        "breakEvenPrice": "0.0",\
        "markPrice": "21123.05052574",\
        "unRealizedProfit": "-1.06214947",\
        "liquidationPrice": "19731.45529116",\
        "leverage": "4",\
        "maxNotionalValue": "100000000",\
        "marginType": "cross",\
        "isolatedMargin": "0.00000000",\
        "isAutoAddMargin": "false",\
        "positionSide": "LONG",\
        "notional": "21.12305052",\
        "isolatedWallet": "0",\
        "updateTime": 1655217461579\
    },\
    {\
        "symbol": "BTCUSDT",\
        "positionAmt": "0.000",\
        "entryPrice": "0.0",\
        "breakEvenPrice": "0.0",\
        "markPrice": "21123.05052574",\
        "unRealizedProfit": "0.00000000",\
        "liquidationPrice": "0",\
        "leverage": "4",\
        "maxNotionalValue": "100000000",\
        "marginType": "cross",\
        "isolatedMargin": "0.00000000",\
        "isAutoAddMargin": "false",\
        "positionSide": "SHORT",\
        "notional": "0",\
        "isolatedWallet": "0",\
        "updateTime": 0\
    }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Income_History.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History#__docusaurus_skipToContent_fallback)

On this page

# Get Income History (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History\#api-description "Direct link to API Description")

Query income history

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/income`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History\#request-weight "Direct link to Request Weight")

**30**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| incomeType | STRING | NO | TRANSFER, WELCOME\_BONUS, REALIZED\_PNL, FUNDING\_FEE, COMMISSION, INSURANCE\_CLEAR, REFERRAL\_KICKBACK, COMMISSION\_REBATE, API\_REBATE, CONTEST\_REWARD, CROSS\_COLLATERAL\_TRANSFER, OPTIONS\_PREMIUM\_FEE, OPTIONS\_SETTLE\_PROFIT, INTERNAL\_TRANSFER, AUTO\_EXCHANGE, DELIVERED\_SETTELMENT, COIN\_SWAP\_DEPOSIT, COIN\_SWAP\_WITHDRAW, POSITION\_LIMIT\_INCREASE\_FEE, STRATEGY\_UMFUTURES\_TRANSFER，FEE\_RETURN，BFUSD\_REWARD |
| startTime | LONG | NO | Timestamp in ms to get funding from INCLUSIVE. |
| endTime | LONG | NO | Timestamp in ms to get funding until INCLUSIVE. |
| page | INT | NO |  |
| limit | INT | NO | Default 100; max 1000 |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - If neither `startTime` nor `endTime` is sent, the recent 7-day data will be returned.
> - If `incomeType ` is not sent, all kinds of flow will be returned
> - "trandId" is unique in the same incomeType for a user
> - Income history only contains data for the last three months

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
    	"symbol": "",					// trade symbol, if existing\
    	"incomeType": "TRANSFER",	// income type\
    	"income": "-0.37500000",  // income amount\
    	"asset": "USDT",				// income asset\
    	"info":"TRANSFER",			// extra information\
    	"time": 1570608000000,\
    	"tranId":9689322392,		// transaction id\
    	"tradeId":""					// trade id, if existing\
	},\
	{\
   		"symbol": "BTCUSDT",\
    	"incomeType": "COMMISSION",\
    	"income": "-0.01000000",\
    	"asset": "USDT",\
    	"info":"COMMISSION",\
    	"time": 1570636800000,\
    	"tranId":9689322392,\
    	"tradeId":"2059192"\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Income-History#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api#__docusaurus_skipToContent_fallback)

On this page

# Test Connectivity

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api\#api-description "Direct link to API Description")

Test connectivity to the Rest API.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/ping`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api\#request-weight "Direct link to Request Weight")

1

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api\#request-parameters "Direct link to Request Parameters")

NONE

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Open_Interest_Statistics.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics#__docusaurus_skipToContent_fallback)

On this page

# Open Interest Statistics

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics\#api-description "Direct link to API Description")

Open Interest Statistics

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics\#http-request "Direct link to HTTP Request")

GET `/futures/data/openInterestHist`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics\#request-weight "Direct link to Request Weight")

**0**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| period | ENUM | YES | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit | LONG | NO | default 30, max 500 |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |

> - If startTime and endTime are not sent, the most recent data is returned.
> - Only the data of the latest 1 month is available.
> - IP rate limit 1000 requests/5min

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
         "symbol":"BTCUSDT",\
	      "sumOpenInterest":"20403.63700000",  // total open interest\
	      "sumOpenInterestValue": "150570784.07809979",   // total open interest value\
	      "timestamp":"1583127900000"\
    },\
    {\
         "symbol":"BTCUSDT",\
         "sumOpenInterest":"20401.36700000",\
         "sumOpenInterestValue":"149940752.14464448",\
         "timestamp":"1583128200000"\
    },\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Current_All_Open_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders#__docusaurus_skipToContent_fallback)

On this page

# Current All Open Orders (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders\#api-description "Direct link to API Description")

Get all open orders on a symbol.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/openOrders`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders\#request-weight "Direct link to Request Weight")

**1** for a single symbol; **40** when the symbol parameter is omitted

**Careful** when accessing this with no symbol.

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - If the symbol is not sent, orders for all symbols will be returned in an array.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
  	"avgPrice": "0.00000",\
  	"clientOrderId": "abc",\
  	"cumQuote": "0",\
  	"executedQty": "0",\
  	"orderId": 1917641,\
  	"origQty": "0.40",\
  	"origType": "TRAILING_STOP_MARKET",\
  	"price": "0",\
  	"reduceOnly": false,\
  	"side": "BUY",\
  	"positionSide": "SHORT",\
  	"status": "NEW",\
  	"stopPrice": "9300",				// please ignore when order type is TRAILING_STOP_MARKET\
  	"closePosition": false,   // if Close-All\
  	"symbol": "BTCUSDT",\
  	"time": 1579276756075,				// order time\
  	"timeInForce": "GTC",\
  	"type": "TRAILING_STOP_MARKET",\
  	"activatePrice": "9020",			// activation price, only return with TRAILING_STOP_MARKET order\
  	"priceRate": "0.3",					// callback rate, only return with TRAILING_STOP_MARKET order\
  	"updateTime": 1579276756075,		// update time\
  	"workingType": "CONTRACT_PRICE",\
  	"priceProtect": false,            // if conditional order trigger is protected\
	"priceMatch": "NONE",              //price match mode\
    "selfTradePreventionMode": "NONE", //self trading preventation mode\
    "goodTillDate": 0      //order pre-set auot cancel time for TIF GTD order\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Top_Long_Short_Account_Ratio.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio#__docusaurus_skipToContent_fallback)

On this page

# Top Trader Long/Short Ratio (Accounts)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio\#api-description "Direct link to API Description")

The proportion of net long and net short accounts to total accounts of the top 20% users with the highest margin balance. Each account is counted once only.
Long Account % = Accounts of top traders with net long positions / Total accounts of top traders with open positions
Short Account % = Accounts of top traders with net short positions / Total accounts of top traders with open positions
Long/Short Ratio (Accounts) = Long Account % / Short Account %

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio\#http-request "Direct link to HTTP Request")

GET `/futures/data/topLongShortAccountRatio`

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| period | ENUM | YES | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit | LONG | NO | default 30, max 500 |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |

> - If startTime and endTime are not sent, the most recent data is returned.
> - Only the data of the latest 30 days is available.
> - IP rate limit 1000 requests/5min

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
         "symbol":"BTCUSDT",\
	      "longShortRatio":"1.8105",  // long/short account num ratio of top traders\
	      "longAccount": "0.6442",   // long account num ratio of top traders\
	      "shortAccount":"0.3558",   // long account num ratio of top traders\
	      "timestamp":"1583139600000"\
    },\
    {\
         "symbol":"BTCUSDT",\
	      "longShortRatio":"0.5576",\
	      "longAccount": "0.3580",\
	      "shortAccount":"0.6420",\
	      "timestamp":"1583139900000"\
    }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio#http-request)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Account_Information_V2.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2#__docusaurus_skipToContent_fallback)

On this page

# Account Information V2(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2\#api-description "Direct link to API Description")

Get current account information. User in single-asset/ multi-assets mode will see different value, see comments in response section for detail.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2\#http-request "Direct link to HTTP Request")

GET `/fapi/v2/account`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2\#response-example "Direct link to Response Example")

> single-asset mode

```codeBlockLines_aHhF
{
	"feeTier": 0,  		// account commission tier
	"feeBurn": true,  	// "true": Fee Discount On; "false": Fee Discount Off	"canTrade": true,  	// if can trade
	"canDeposit": true,  	// if can transfer in asset
	"canWithdraw": true, 	// if can transfer out asset
	"updateTime": 0,        // reserved property, please ignore
	"multiAssetsMargin": false,
	"tradeGroupId": -1,
	"totalInitialMargin": "0.00000000",    // total initial margin required with current mark price (useless with isolated positions), only for USDT asset
	"totalMaintMargin": "0.00000000",  	  // total maintenance margin required, only for USDT asset
	"totalWalletBalance": "23.72469206",     // total wallet balance, only for USDT asset
	"totalUnrealizedProfit": "0.00000000",   // total unrealized profit, only for USDT asset
	"totalMarginBalance": "23.72469206",     // total margin balance, only for USDT asset
	"totalPositionInitialMargin": "0.00000000",    // initial margin required for positions with current mark price, only for USDT asset
	"totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price, only for USDT asset
	"totalCrossWalletBalance": "23.72469206",      // crossed wallet balance, only for USDT asset
	"totalCrossUnPnl": "0.00000000",	  // unrealized profit of crossed positions, only for USDT asset
	"availableBalance": "23.72469206",       // available balance, only for USDT asset
	"maxWithdrawAmount": "23.72469206"     // maximum amount for transfer out, only for USDT asset
	"assets": [\
		{\
			"asset": "USDT",			// asset name\
			"walletBalance": "23.72469206",      // wallet balance\
			"unrealizedProfit": "0.00000000",    // unrealized profit\
			"marginBalance": "23.72469206",      // margin balance\
			"maintMargin": "0.00000000",	    // maintenance margin required\
			"initialMargin": "0.00000000",    // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
			"crossWalletBalance": "23.72469206",      // crossed wallet balance\
			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
			"availableBalance": "23.72469206",       // available balance\
			"maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
			"updateTime": 1625474304765 // last update time\
		},\
		{\
			"asset": "BUSD",			// asset name\
			"walletBalance": "103.12345678",      // wallet balance\
			"unrealizedProfit": "0.00000000",    // unrealized profit\
			"marginBalance": "103.12345678",      // margin balance\
			"maintMargin": "0.00000000",	    // maintenance margin required\
			"initialMargin": "0.00000000",    // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
			"crossWalletBalance": "103.12345678",      // crossed wallet balance\
			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
			"availableBalance": "103.12345678",       // available balance\
			"maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
			"updateTime": 1625474304765 // last update time\
		}\
	],
	"positions": [  // positions of all symbols in the market are returned\
		// only "BOTH" positions will be returned with One-way mode\
		// only "LONG" and "SHORT" positions will be returned with Hedge mode\
		{\
			"symbol": "BTCUSDT",  	// symbol name\
			"initialMargin": "0",	// initial margin required with current mark price\
			"maintMargin": "0",		// maintenance margin required\
			"unrealizedProfit": "0.00000000",  // unrealized profit\
			"positionInitialMargin": "0",      // initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0",     // initial margin required for open orders with current mark price\
			"leverage": "100",		// current initial leverage\
			"isolated": true,  		// if the position is isolated\
			"entryPrice": "0.00000",  	// average entry price\
			"maxNotional": "250000",  	// maximum available notional with current leverage\
			"bidNotional": "0",  // bids notional, ignore\
			"askNotional": "0",  // ask notional, ignore\
			"positionSide": "BOTH",  	// position side\
			"positionAmt": "0",			// position amount\
			"updateTime": 0           // last update time\
		}\
	]
}

```

> OR multi-assets mode

```codeBlockLines_aHhF
{
	"feeTier": 0,  		// account commission tier
	"feeBurn": true,  	// "true": Fee Discount On; "false": Fee Discount Off	"canTrade": true,  	// if can trade
	"canTrade": true,  	// if can trade
	"canDeposit": true,  	// if can transfer in asset
	"canWithdraw": true, 	// if can transfer out asset
	"updateTime": 0,        // reserved property, please ignore
	"multiAssetsMargin": true,
	"tradeGroupId": -1,
	"totalInitialMargin": "0.00000000",    // the sum of USD value of all cross positions/open order initial margin
	"totalMaintMargin": "0.00000000",  	  // the sum of USD value of all cross positions maintenance margin
	"totalWalletBalance": "126.72469206",     // total wallet balance in USD
	"totalUnrealizedProfit": "0.00000000",   // total unrealized profit in USD
	"totalMarginBalance": "126.72469206",     // total margin balance in USD
	"totalPositionInitialMargin": "0.00000000",    // the sum of USD value of all cross positions initial margin
	"totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price in USD
	"totalCrossWalletBalance": "126.72469206",      // crossed wallet balance in USD
	"totalCrossUnPnl": "0.00000000",	  // unrealized profit of crossed positions in USD
	"availableBalance": "126.72469206",       // available balance in USD
	"maxWithdrawAmount": "126.72469206"     // maximum virtual amount for transfer out in USD
	"assets": [\
		{\
			"asset": "USDT",			// asset name\
			"walletBalance": "23.72469206",      // wallet balance\
			"unrealizedProfit": "0.00000000",    // unrealized profit\
			"marginBalance": "23.72469206",      // margin balance\
			"maintMargin": "0.00000000",	    // maintenance margin required\
			"initialMargin": "0.00000000",    // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
			"crossWalletBalance": "23.72469206",      // crossed wallet balance\
			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
			"availableBalance": "126.72469206",       // available balance\
			"maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
			"updateTime": 1625474304765 // last update time\
		},\
		{\
			"asset": "BUSD",			// asset name\
			"walletBalance": "103.12345678",      // wallet balance\
			"unrealizedProfit": "0.00000000",    // unrealized profit\
			"marginBalance": "103.12345678",      // margin balance\
			"maintMargin": "0.00000000",	    // maintenance margin required\
			"initialMargin": "0.00000000",    // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
			"crossWalletBalance": "103.12345678",      // crossed wallet balance\
			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
			"availableBalance": "126.72469206",       // available balance\
			"maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
			"updateTime": 1625474304765 // last update time\
		}\
	],
	"positions": [  // positions of all symbols in the market are returned\
		// only "BOTH" positions will be returned with One-way mode\
		// only "LONG" and "SHORT" positions will be returned with Hedge mode\
		{\
			"symbol": "BTCUSDT",  	// symbol name\
			"initialMargin": "0",	// initial margin required with current mark price\
			"maintMargin": "0",		// maintenance margin required\
			"unrealizedProfit": "0.00000000",  // unrealized profit\
			"positionInitialMargin": "0",      // initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0",     // initial margin required for open orders with current mark price\
			"leverage": "100",		// current initial leverage\
			"isolated": true,  		// if the position is isolated\
			"entryPrice": "0.00000",  	// average entry price\
			"maxNotional": "250000",  	// maximum available notional with current leverage\
			"bidNotional": "0",  // bids notional, ignore\
			"askNotional": "0",  // ask notional, ignore\
			"positionSide": "BOTH",  	// position side\
			"positionAmt": "0",			// position amount\
			"updateTime": 0           // last update time\
		}\
	]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Individual_Symbol_Mini_Ticker_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream#__docusaurus_skipToContent_fallback)

On this page

# Individual Symbol Mini Ticker Stream

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream\#stream-description "Direct link to Stream Description")

24hr rolling window mini-ticker statistics for a single symbol. These are NOT the statistics of the UTC day, but a 24hr rolling window from requestTime to 24hrs before.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream\#stream-name "Direct link to Stream Name")

`<symbol>@miniTicker`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream\#update-speed "Direct link to Update Speed")

**2s**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
  {
    "e": "24hrMiniTicker",  // Event type
    "E": 123456789,         // Event time
    "s": "BTCUSDT",         // Symbol
    "c": "0.0025",          // Close price
    "o": "0.0010",          // Open price
    "h": "0.0025",          // High price
    "l": "0.0010",          // Low price
    "v": "10000",           // Total traded base asset volume
    "q": "18"               // Total traded quote asset volume
  }

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Mini-Ticker-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Futures_Account_Balance_V3.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3#__docusaurus_skipToContent_fallback)

On this page

# Futures Account Balance V3 (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3\#api-description "Direct link to API Description")

Query account balance info

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3\#http-request "Direct link to HTTP Request")

GET `/fapi/v3/balance`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
 {\
   "accountAlias": "SgsR",              // unique account code\
   "asset": "USDT",  	                // asset name\
   "balance": "122607.35137903",        // wallet balance\
   "crossWalletBalance": "23.72469206", // crossed wallet balance\
   "crossUnPnl": "0.00000000"           // unrealized profit of crossed positions\
   "availableBalance": "23.72469206",   // available balance\
   "maxWithdrawAmount": "23.72469206",  // maximum amount for transfer out\
   "marginAvailable": true,             // whether the asset can be used as margin in Multi-Assets mode\
   "updateTime": 1617939110373\
 }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V3#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_convert_Send_quote_request.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request#__docusaurus_skipToContent_fallback)

On this page

# Send Quote Request(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request\#api-description "Direct link to API Description")

Request a quote for the requested token pairs

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/convert/getQuote`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request\#request-weight "Direct link to Request Weight")

**50(IP)**

**360/hour，500/day**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| fromAsset | STRING | YES |  |
| toAsset | STRING | YES |  |
| fromAmount | DECIMAL | EITHER | When specified, it is the amount you will be debited after the conversion |
| toAmount | DECIMAL | EITHER | When specified, it is the amount you will be credited after the conversion |
| validTime | ENUM | NO | 10s, default 10s |
| recvWindow | LONG | NO | The value cannot be greater than 60000 |
| timestamp | LONG | YES |  |

- Either fromAmount or toAmount should be sent
- `quoteId` will be returned only if you have enough funds to convert

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
   "quoteId":"12415572564",
   "ratio":"38163.7",
   "inverseRatio":"0.0000262",
   "validTimestamp":1623319461670,
   "toAmount":"3816.37",
   "fromAmount":"0.1"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Send-quote-request#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Close_User_Data_Stream_Wsp.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp#__docusaurus_skipToContent_fallback)

On this page

# Close User Data Stream (USER\_STREAM)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp\#api-description "Direct link to API Description")

Close out a user data stream.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp\#method "Direct link to Method")

`userDataStream.stop`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp\#request "Direct link to Request")

```codeBlockLines_aHhF
{
  "id": "819e1b1b-8c06-485b-a13e-131326c69599",
  "method": "userDataStream.stop",
  "params": {
    "apiKey": "vmPUZE6mv9SD5VNHk9HlWFsOr9aLE2zvsw0MuIgwCIPy8atIco14y7Ju91duEh8A"
  }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp\#request-parameters "Direct link to Request Parameters")

None

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "id": "819e1b1b-8c06-485b-a13e-131326c69599",
  "status": 200,
  "result": {},
   "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 2\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream-Wsp#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Account_Config.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config#__docusaurus_skipToContent_fallback)

On this page

# Futures Account Configuration(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config\#api-description "Direct link to API Description")

Query account configuration

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/accountConfig`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "feeTier": 0,               // account commission tier
    "canTrade": true,           // if can trade
    "canDeposit": true,         // if can transfer in asset
    "canWithdraw": true,        // if can transfer out asset
    "dualSidePosition": true,
    "updateTime": 0,            // reserved property, please ignore
    "multiAssetsMargin": false,
    "tradeGroupId": -1
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Config#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Taker_BuySell_Volume.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume#__docusaurus_skipToContent_fallback)

On this page

# Taker Buy/Sell Volume

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume\#api-description "Direct link to API Description")

Taker Buy/Sell Volume

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume\#http-request "Direct link to HTTP Request")

GET `/futures/data/takerlongshortRatio`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume\#request-weight "Direct link to Request Weight")

**0**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| period | ENUM | YES | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit | LONG | NO | default 30, max 500 |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |

> - If startTime and endTime are not sent, the most recent data is returned.
> - Only the data of the latest 30 days is available.
> - IP rate limit 1000 requests/5min

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
	    "buySellRatio":"1.5586",\
	    "buyVol": "387.3300",\
	    "sellVol":"248.5030",\
	    "timestamp":"1585614900000"\
    },\
    {\
	    "buySellRatio":"1.3104",\
	    "buyVol": "343.9290",\
	    "sellVol":"248.5030",\
	    "timestamp":"1583139900000"\
    },\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Taker-BuySell-Volume#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_error_code.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#__docusaurus_skipToContent_fallback)

On this page

# Error Codes

> Here is the error JSON payload:

```codeBlockLines_aHhF
{
  "code":-1121,
  "msg":"Invalid symbol."
}

```

Errors consist of two parts: an error code and a message.

Codes are universal,but messages can vary.

## 10xx - General Server or Network issues [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#10xx---general-server-or-network-issues "Direct link to 10xx - General Server or Network issues")

### -1000 UNKNOWN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1000-unknown "Direct link to -1000 UNKNOWN")

- An unknown error occured while processing the request.

### -1001 DISCONNECTED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1001-disconnected "Direct link to -1001 DISCONNECTED")

- Internal error; unable to process your request. Please try again.

### -1002 UNAUTHORIZED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1002-unauthorized "Direct link to -1002 UNAUTHORIZED")

- You are not authorized to execute this request.

### -1003 TOO\_MANY\_REQUESTS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1003-too_many_requests "Direct link to -1003 TOO_MANY_REQUESTS")

- Too many requests; current limit is %s requests per minute. Please use the websocket for live updates to avoid polling the API.
- Way too many requests; IP banned until %s. Please use the websocket for live updates to avoid bans.

### -1004 DUPLICATE\_IP [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1004-duplicate_ip "Direct link to -1004 DUPLICATE_IP")

- This IP is already on the white list

### -1005 NO\_SUCH\_IP [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1005-no_such_ip "Direct link to -1005 NO_SUCH_IP")

- No such IP has been white listed

### -1006 UNEXPECTED\_RESP [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1006-unexpected_resp "Direct link to -1006 UNEXPECTED_RESP")

- An unexpected response was received from the message bus. Execution status unknown.

### -1007 TIMEOUT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1007-timeout "Direct link to -1007 TIMEOUT")

- Timeout waiting for response from backend server. Send status unknown; execution status unknown.

### -1010 ERROR\_MSG\_RECEIVED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1010-error_msg_received "Direct link to -1010 ERROR_MSG_RECEIVED")

- ERROR\_MSG\_RECEIVED.

### -1011 NON\_WHITE\_LIST [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1011-non_white_list "Direct link to -1011 NON_WHITE_LIST")

- This IP cannot access this route.

### -1013 INVALID\_MESSAGE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1013-invalid_message "Direct link to -1013 INVALID_MESSAGE")

- INVALID\_MESSAGE.

### -1014 UNKNOWN\_ORDER\_COMPOSITION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1014-unknown_order_composition "Direct link to -1014 UNKNOWN_ORDER_COMPOSITION")

- Unsupported order combination.

### -1015 TOO\_MANY\_ORDERS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1015-too_many_orders "Direct link to -1015 TOO_MANY_ORDERS")

- Too many new orders.
- Too many new orders; current limit is %s orders per %s.

### -1016 SERVICE\_SHUTTING\_DOWN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1016-service_shutting_down "Direct link to -1016 SERVICE_SHUTTING_DOWN")

- This service is no longer available.

### -1020 UNSUPPORTED\_OPERATION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1020-unsupported_operation "Direct link to -1020 UNSUPPORTED_OPERATION")

- This operation is not supported.

### -1021 INVALID\_TIMESTAMP [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1021-invalid_timestamp "Direct link to -1021 INVALID_TIMESTAMP")

- Timestamp for this request is outside of the recvWindow.
- Timestamp for this request was 1000ms ahead of the server's time.

### -1022 INVALID\_SIGNATURE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1022-invalid_signature "Direct link to -1022 INVALID_SIGNATURE")

- Signature for this request is not valid.

### -1023 START\_TIME\_GREATER\_THAN\_END\_TIME [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1023-start_time_greater_than_end_time "Direct link to -1023 START_TIME_GREATER_THAN_END_TIME")

- Start time is greater than end time.

### -1099 NOT\_FOUND [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1099-not_found "Direct link to -1099 NOT_FOUND")

- Not found, unauthenticated, or unauthorized.

## 11xx - Request issues [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#11xx---request-issues "Direct link to 11xx - Request issues")

### -1100 ILLEGAL\_CHARS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1100-illegal_chars "Direct link to -1100 ILLEGAL_CHARS")

- Illegal characters found in a parameter.
- Illegal characters found in parameter '%s'; legal range is '%s'.

### -1101 TOO\_MANY\_PARAMETERS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1101-too_many_parameters "Direct link to -1101 TOO_MANY_PARAMETERS")

- Too many parameters sent for this endpoint.
- Too many parameters; expected '%s' and received '%s'.
- Duplicate values for a parameter detected.

### -1102 MANDATORY\_PARAM\_EMPTY\_OR\_MALFORMED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1102-mandatory_param_empty_or_malformed "Direct link to -1102 MANDATORY_PARAM_EMPTY_OR_MALFORMED")

- A mandatory parameter was not sent, was empty/null, or malformed.
- Mandatory parameter '%s' was not sent, was empty/null, or malformed.
- Param '%s' or '%s' must be sent, but both were empty/null!

### -1103 UNKNOWN\_PARAM [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1103-unknown_param "Direct link to -1103 UNKNOWN_PARAM")

- An unknown parameter was sent.

### -1104 UNREAD\_PARAMETERS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1104-unread_parameters "Direct link to -1104 UNREAD_PARAMETERS")

- Not all sent parameters were read.
- Not all sent parameters were read; read '%s' parameter(s) but was sent '%s'.

### -1105 PARAM\_EMPTY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1105-param_empty "Direct link to -1105 PARAM_EMPTY")

- A parameter was empty.
- Parameter '%s' was empty.

### -1106 PARAM\_NOT\_REQUIRED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1106-param_not_required "Direct link to -1106 PARAM_NOT_REQUIRED")

- A parameter was sent when not required.
- Parameter '%s' sent when not required.

### -1108 BAD\_ASSET [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1108-bad_asset "Direct link to -1108 BAD_ASSET")

- Invalid asset.

### -1109 BAD\_ACCOUNT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1109-bad_account "Direct link to -1109 BAD_ACCOUNT")

- Invalid account.

### -1110 BAD\_INSTRUMENT\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1110-bad_instrument_type "Direct link to -1110 BAD_INSTRUMENT_TYPE")

- Invalid symbolType.

### -1111 BAD\_PRECISION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1111-bad_precision "Direct link to -1111 BAD_PRECISION")

- Precision is over the maximum defined for this asset.

### -1112 NO\_DEPTH [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1112-no_depth "Direct link to -1112 NO_DEPTH")

- No orders on book for symbol.

### -1113 WITHDRAW\_NOT\_NEGATIVE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1113-withdraw_not_negative "Direct link to -1113 WITHDRAW_NOT_NEGATIVE")

- Withdrawal amount must be negative.

### -1114 TIF\_NOT\_REQUIRED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1114-tif_not_required "Direct link to -1114 TIF_NOT_REQUIRED")

- TimeInForce parameter sent when not required.

### -1115 INVALID\_TIF [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1115-invalid_tif "Direct link to -1115 INVALID_TIF")

- Invalid timeInForce.

### -1116 INVALID\_ORDER\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1116-invalid_order_type "Direct link to -1116 INVALID_ORDER_TYPE")

- Invalid orderType.

### -1117 INVALID\_SIDE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1117-invalid_side "Direct link to -1117 INVALID_SIDE")

- Invalid side.

### -1118 EMPTY\_NEW\_CL\_ORD\_ID [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1118-empty_new_cl_ord_id "Direct link to -1118 EMPTY_NEW_CL_ORD_ID")

- New client order ID was empty.

### -1119 EMPTY\_ORG\_CL\_ORD\_ID [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1119-empty_org_cl_ord_id "Direct link to -1119 EMPTY_ORG_CL_ORD_ID")

- Original client order ID was empty.

### -1120 BAD\_INTERVAL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1120-bad_interval "Direct link to -1120 BAD_INTERVAL")

- Invalid interval.

### -1121 BAD\_SYMBOL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1121-bad_symbol "Direct link to -1121 BAD_SYMBOL")

- Invalid symbol.

### -1122 INVALID\_SYMBOL\_STATUS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1122-invalid_symbol_status "Direct link to -1122 INVALID_SYMBOL_STATUS")

- Invalid symbol status.

### -1125 INVALID\_LISTEN\_KEY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1125-invalid_listen_key "Direct link to -1125 INVALID_LISTEN_KEY")

- This listenKey does not exist. Please use `POST /fapi/v1/listenKey` to recreate `listenKey`

### -1126 ASSET\_NOT\_SUPPORTED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1126-asset_not_supported "Direct link to -1126 ASSET_NOT_SUPPORTED")

- This asset is not supported.

### -1127 MORE\_THAN\_XX\_HOURS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1127-more_than_xx_hours "Direct link to -1127 MORE_THAN_XX_HOURS")

- Lookup interval is too big.
- More than %s hours between startTime and endTime.

### -1128 OPTIONAL\_PARAMS\_BAD\_COMBO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1128-optional_params_bad_combo "Direct link to -1128 OPTIONAL_PARAMS_BAD_COMBO")

- Combination of optional parameters invalid.

### -1130 INVALID\_PARAMETER [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1130-invalid_parameter "Direct link to -1130 INVALID_PARAMETER")

- Invalid data sent for a parameter.
- Data sent for parameter '%s' is not valid.

### -1136 INVALID\_NEW\_ORDER\_RESP\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-1136-invalid_new_order_resp_type "Direct link to -1136 INVALID_NEW_ORDER_RESP_TYPE")

- Invalid newOrderRespType.

## 20xx - Processing Issues [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#20xx---processing-issues "Direct link to 20xx - Processing Issues")

### -2010 NEW\_ORDER\_REJECTED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2010-new_order_rejected "Direct link to -2010 NEW_ORDER_REJECTED")

- NEW\_ORDER\_REJECTED

### -2011 CANCEL\_REJECTED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2011-cancel_rejected "Direct link to -2011 CANCEL_REJECTED")

- CANCEL\_REJECTED

### -2012 CANCEL\_ALL\_FAIL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2012-cancel_all_fail "Direct link to -2012 CANCEL_ALL_FAIL")

- Batch cancel failure.

### -2013 NO\_SUCH\_ORDER [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2013-no_such_order "Direct link to -2013 NO_SUCH_ORDER")

- Order does not exist.

### -2014 BAD\_API\_KEY\_FMT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2014-bad_api_key_fmt "Direct link to -2014 BAD_API_KEY_FMT")

- API-key format invalid.

### -2015 REJECTED\_MBX\_KEY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2015-rejected_mbx_key "Direct link to -2015 REJECTED_MBX_KEY")

- Invalid API-key, IP, or permissions for action.

### -2016 NO\_TRADING\_WINDOW [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2016-no_trading_window "Direct link to -2016 NO_TRADING_WINDOW")

- No trading window could be found for the symbol. Try ticker/24hrs instead.

### -2017 API\_KEYS\_LOCKED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2017-api_keys_locked "Direct link to -2017 API_KEYS_LOCKED")

- API Keys are locked on this account.

### -2018 BALANCE\_NOT\_SUFFICIENT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2018-balance_not_sufficient "Direct link to -2018 BALANCE_NOT_SUFFICIENT")

- Balance is insufficient.

### -2019 MARGIN\_NOT\_SUFFICIEN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2019-margin_not_sufficien "Direct link to -2019 MARGIN_NOT_SUFFICIEN")

- Margin is insufficient.

### -2020 UNABLE\_TO\_FILL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2020-unable_to_fill "Direct link to -2020 UNABLE_TO_FILL")

- Unable to fill.

### -2021 ORDER\_WOULD\_IMMEDIATELY\_TRIGGER [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2021-order_would_immediately_trigger "Direct link to -2021 ORDER_WOULD_IMMEDIATELY_TRIGGER")

- Order would immediately trigger.

### -2022 REDUCE\_ONLY\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2022-reduce_only_reject "Direct link to -2022 REDUCE_ONLY_REJECT")

- ReduceOnly Order is rejected.

### -2023 USER\_IN\_LIQUIDATION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2023-user_in_liquidation "Direct link to -2023 USER_IN_LIQUIDATION")

- User in liquidation mode now.

### -2024 POSITION\_NOT\_SUFFICIENT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2024-position_not_sufficient "Direct link to -2024 POSITION_NOT_SUFFICIENT")

- Position is not sufficient.

### -2025 MAX\_OPEN\_ORDER\_EXCEEDED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2025-max_open_order_exceeded "Direct link to -2025 MAX_OPEN_ORDER_EXCEEDED")

- Reach max open order limit.

### -2026 REDUCE\_ONLY\_ORDER\_TYPE\_NOT\_SUPPORTED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2026-reduce_only_order_type_not_supported "Direct link to -2026 REDUCE_ONLY_ORDER_TYPE_NOT_SUPPORTED")

- This OrderType is not supported when reduceOnly.

### -2027 MAX\_LEVERAGE\_RATIO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2027-max_leverage_ratio "Direct link to -2027 MAX_LEVERAGE_RATIO")

- Exceeded the maximum allowable position at current leverage.

### -2028 MIN\_LEVERAGE\_RATIO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-2028-min_leverage_ratio "Direct link to -2028 MIN_LEVERAGE_RATIO")

- Leverage is smaller than permitted: insufficient margin balance.

## 40xx - Filters and other Issues [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#40xx---filters-and-other-issues "Direct link to 40xx - Filters and other Issues")

### -4000 INVALID\_ORDER\_STATUS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4000-invalid_order_status "Direct link to -4000 INVALID_ORDER_STATUS")

- Invalid order status.

### -4001 PRICE\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4001-price_less_than_zero "Direct link to -4001 PRICE_LESS_THAN_ZERO")

- Price less than 0.

### -4002 PRICE\_GREATER\_THAN\_MAX\_PRICE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4002-price_greater_than_max_price "Direct link to -4002 PRICE_GREATER_THAN_MAX_PRICE")

- Price greater than max price.

### -4003 QTY\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4003-qty_less_than_zero "Direct link to -4003 QTY_LESS_THAN_ZERO")

- Quantity less than zero.

### -4004 QTY\_LESS\_THAN\_MIN\_QTY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4004-qty_less_than_min_qty "Direct link to -4004 QTY_LESS_THAN_MIN_QTY")

- Quantity less than min quantity.

### -4005 QTY\_GREATER\_THAN\_MAX\_QTY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4005-qty_greater_than_max_qty "Direct link to -4005 QTY_GREATER_THAN_MAX_QTY")

- Quantity greater than max quantity.

### -4006 STOP\_PRICE\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4006-stop_price_less_than_zero "Direct link to -4006 STOP_PRICE_LESS_THAN_ZERO")

- Stop price less than zero.

### -4007 STOP\_PRICE\_GREATER\_THAN\_MAX\_PRICE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4007-stop_price_greater_than_max_price "Direct link to -4007 STOP_PRICE_GREATER_THAN_MAX_PRICE")

- Stop price greater than max price.

### -4008 TICK\_SIZE\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4008-tick_size_less_than_zero "Direct link to -4008 TICK_SIZE_LESS_THAN_ZERO")

- Tick size less than zero.

### -4009 MAX\_PRICE\_LESS\_THAN\_MIN\_PRICE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4009-max_price_less_than_min_price "Direct link to -4009 MAX_PRICE_LESS_THAN_MIN_PRICE")

- Max price less than min price.

### -4010 MAX\_QTY\_LESS\_THAN\_MIN\_QTY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4010-max_qty_less_than_min_qty "Direct link to -4010 MAX_QTY_LESS_THAN_MIN_QTY")

- Max qty less than min qty.

### -4011 STEP\_SIZE\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4011-step_size_less_than_zero "Direct link to -4011 STEP_SIZE_LESS_THAN_ZERO")

- Step size less than zero.

### -4012 MAX\_NUM\_ORDERS\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4012-max_num_orders_less_than_zero "Direct link to -4012 MAX_NUM_ORDERS_LESS_THAN_ZERO")

- Max mum orders less than zero.

### -4013 PRICE\_LESS\_THAN\_MIN\_PRICE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4013-price_less_than_min_price "Direct link to -4013 PRICE_LESS_THAN_MIN_PRICE")

- Price less than min price.

### -4014 PRICE\_NOT\_INCREASED\_BY\_TICK\_SIZE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4014-price_not_increased_by_tick_size "Direct link to -4014 PRICE_NOT_INCREASED_BY_TICK_SIZE")

- Price not increased by tick size.

### -4015 INVALID\_CL\_ORD\_ID\_LEN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4015-invalid_cl_ord_id_len "Direct link to -4015 INVALID_CL_ORD_ID_LEN")

- Client order id is not valid.
- Client order id length should not be more than 36 chars

### -4016 PRICE\_HIGHTER\_THAN\_MULTIPLIER\_UP [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4016-price_highter_than_multiplier_up "Direct link to -4016 PRICE_HIGHTER_THAN_MULTIPLIER_UP")

- Price is higher than mark price multiplier cap.

### -4017 MULTIPLIER\_UP\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4017-multiplier_up_less_than_zero "Direct link to -4017 MULTIPLIER_UP_LESS_THAN_ZERO")

- Multiplier up less than zero.

### -4018 MULTIPLIER\_DOWN\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4018-multiplier_down_less_than_zero "Direct link to -4018 MULTIPLIER_DOWN_LESS_THAN_ZERO")

- Multiplier down less than zero.

### -4019 COMPOSITE\_SCALE\_OVERFLOW [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4019-composite_scale_overflow "Direct link to -4019 COMPOSITE_SCALE_OVERFLOW")

- Composite scale too large.

### -4020 TARGET\_STRATEGY\_INVALID [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4020-target_strategy_invalid "Direct link to -4020 TARGET_STRATEGY_INVALID")

- Target strategy invalid for orderType '%s',reduceOnly '%b'.

### -4021 INVALID\_DEPTH\_LIMIT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4021-invalid_depth_limit "Direct link to -4021 INVALID_DEPTH_LIMIT")

- Invalid depth limit.
- '%s' is not valid depth limit.

### -4022 WRONG\_MARKET\_STATUS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4022-wrong_market_status "Direct link to -4022 WRONG_MARKET_STATUS")

- market status sent is not valid.

### -4023 QTY\_NOT\_INCREASED\_BY\_STEP\_SIZE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4023-qty_not_increased_by_step_size "Direct link to -4023 QTY_NOT_INCREASED_BY_STEP_SIZE")

- Qty not increased by step size.

### -4024 PRICE\_LOWER\_THAN\_MULTIPLIER\_DOWN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4024-price_lower_than_multiplier_down "Direct link to -4024 PRICE_LOWER_THAN_MULTIPLIER_DOWN")

- Price is lower than mark price multiplier floor.

### -4025 MULTIPLIER\_DECIMAL\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4025-multiplier_decimal_less_than_zero "Direct link to -4025 MULTIPLIER_DECIMAL_LESS_THAN_ZERO")

- Multiplier decimal less than zero.

### -4026 COMMISSION\_INVALID [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4026-commission_invalid "Direct link to -4026 COMMISSION_INVALID")

- Commission invalid.
- `%s` less than zero.
- `%s` absolute value greater than `%s`

### -4027 INVALID\_ACCOUNT\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4027-invalid_account_type "Direct link to -4027 INVALID_ACCOUNT_TYPE")

- Invalid account type.

### -4028 INVALID\_LEVERAGE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4028-invalid_leverage "Direct link to -4028 INVALID_LEVERAGE")

- Invalid leverage
- Leverage `%s` is not valid
- Leverage `%s` already exist with `%s`

### -4029 INVALID\_TICK\_SIZE\_PRECISION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4029-invalid_tick_size_precision "Direct link to -4029 INVALID_TICK_SIZE_PRECISION")

- Tick size precision is invalid.

### -4030 INVALID\_STEP\_SIZE\_PRECISION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4030-invalid_step_size_precision "Direct link to -4030 INVALID_STEP_SIZE_PRECISION")

- Step size precision is invalid.

### -4031 INVALID\_WORKING\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4031-invalid_working_type "Direct link to -4031 INVALID_WORKING_TYPE")

- Invalid parameter working type
- Invalid parameter working type: `%s`

### -4032 EXCEED\_MAX\_CANCEL\_ORDER\_SIZE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4032-exceed_max_cancel_order_size "Direct link to -4032 EXCEED_MAX_CANCEL_ORDER_SIZE")

- Exceed maximum cancel order size.
- Invalid parameter working type: `%s`

### -4033 INSURANCE\_ACCOUNT\_NOT\_FOUND [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4033-insurance_account_not_found "Direct link to -4033 INSURANCE_ACCOUNT_NOT_FOUND")

- Insurance account not found.

### -4044 INVALID\_BALANCE\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4044-invalid_balance_type "Direct link to -4044 INVALID_BALANCE_TYPE")

- Balance Type is invalid.

### -4045 MAX\_STOP\_ORDER\_EXCEEDED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4045-max_stop_order_exceeded "Direct link to -4045 MAX_STOP_ORDER_EXCEEDED")

- Reach max stop order limit.

### -4046 NO\_NEED\_TO\_CHANGE\_MARGIN\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4046-no_need_to_change_margin_type "Direct link to -4046 NO_NEED_TO_CHANGE_MARGIN_TYPE")

- No need to change margin type.

### -4047 THERE\_EXISTS\_OPEN\_ORDERS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4047-there_exists_open_orders "Direct link to -4047 THERE_EXISTS_OPEN_ORDERS")

- Margin type cannot be changed if there exists open orders.

### -4048 THERE\_EXISTS\_QUANTITY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4048-there_exists_quantity "Direct link to -4048 THERE_EXISTS_QUANTITY")

- Margin type cannot be changed if there exists position.

### -4049 ADD\_ISOLATED\_MARGIN\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4049-add_isolated_margin_reject "Direct link to -4049 ADD_ISOLATED_MARGIN_REJECT")

- Add margin only support for isolated position.

### -4050 CROSS\_BALANCE\_INSUFFICIENT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4050-cross_balance_insufficient "Direct link to -4050 CROSS_BALANCE_INSUFFICIENT")

- Cross balance insufficient.

### -4051 ISOLATED\_BALANCE\_INSUFFICIENT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4051-isolated_balance_insufficient "Direct link to -4051 ISOLATED_BALANCE_INSUFFICIENT")

- Isolated balance insufficient.

### -4052 NO\_NEED\_TO\_CHANGE\_AUTO\_ADD\_MARGIN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4052-no_need_to_change_auto_add_margin "Direct link to -4052 NO_NEED_TO_CHANGE_AUTO_ADD_MARGIN")

- No need to change auto add margin.

### -4053 AUTO\_ADD\_CROSSED\_MARGIN\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4053-auto_add_crossed_margin_reject "Direct link to -4053 AUTO_ADD_CROSSED_MARGIN_REJECT")

- Auto add margin only support for isolated position.

### -4054 ADD\_ISOLATED\_MARGIN\_NO\_POSITION\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4054-add_isolated_margin_no_position_reject "Direct link to -4054 ADD_ISOLATED_MARGIN_NO_POSITION_REJECT")

- Cannot add position margin: position is 0.

### -4055 AMOUNT\_MUST\_BE\_POSITIVE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4055-amount_must_be_positive "Direct link to -4055 AMOUNT_MUST_BE_POSITIVE")

- Amount must be positive.

### -4056 INVALID\_API\_KEY\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4056-invalid_api_key_type "Direct link to -4056 INVALID_API_KEY_TYPE")

- Invalid api key type.

### -4057 INVALID\_RSA\_PUBLIC\_KEY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4057-invalid_rsa_public_key "Direct link to -4057 INVALID_RSA_PUBLIC_KEY")

- Invalid api public key

### -4058 MAX\_PRICE\_TOO\_LARGE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4058-max_price_too_large "Direct link to -4058 MAX_PRICE_TOO_LARGE")

- maxPrice and priceDecimal too large,please check.

### -4059 NO\_NEED\_TO\_CHANGE\_POSITION\_SIDE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4059-no_need_to_change_position_side "Direct link to -4059 NO_NEED_TO_CHANGE_POSITION_SIDE")

- No need to change position side.

### -4060 INVALID\_POSITION\_SIDE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4060-invalid_position_side "Direct link to -4060 INVALID_POSITION_SIDE")

- Invalid position side.

### -4061 POSITION\_SIDE\_NOT\_MATCH [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4061-position_side_not_match "Direct link to -4061 POSITION_SIDE_NOT_MATCH")

- Order's position side does not match user's setting.

### -4062 REDUCE\_ONLY\_CONFLICT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4062-reduce_only_conflict "Direct link to -4062 REDUCE_ONLY_CONFLICT")

- Invalid or improper reduceOnly value.

### -4063 INVALID\_OPTIONS\_REQUEST\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4063-invalid_options_request_type "Direct link to -4063 INVALID_OPTIONS_REQUEST_TYPE")

- Invalid options request type

### -4064 INVALID\_OPTIONS\_TIME\_FRAME [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4064-invalid_options_time_frame "Direct link to -4064 INVALID_OPTIONS_TIME_FRAME")

- Invalid options time frame

### -4065 INVALID\_OPTIONS\_AMOUNT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4065-invalid_options_amount "Direct link to -4065 INVALID_OPTIONS_AMOUNT")

- Invalid options amount

### -4066 INVALID\_OPTIONS\_EVENT\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4066-invalid_options_event_type "Direct link to -4066 INVALID_OPTIONS_EVENT_TYPE")

- Invalid options event type

### -4067 POSITION\_SIDE\_CHANGE\_EXISTS\_OPEN\_ORDERS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4067-position_side_change_exists_open_orders "Direct link to -4067 POSITION_SIDE_CHANGE_EXISTS_OPEN_ORDERS")

- Position side cannot be changed if there exists open orders.

### -4068 POSITION\_SIDE\_CHANGE\_EXISTS\_QUANTITY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4068-position_side_change_exists_quantity "Direct link to -4068 POSITION_SIDE_CHANGE_EXISTS_QUANTITY")

- Position side cannot be changed if there exists position.

### -4069 INVALID\_OPTIONS\_PREMIUM\_FEE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4069-invalid_options_premium_fee "Direct link to -4069 INVALID_OPTIONS_PREMIUM_FEE")

- Invalid options premium fee

### -4070 INVALID\_CL\_OPTIONS\_ID\_LEN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4070-invalid_cl_options_id_len "Direct link to -4070 INVALID_CL_OPTIONS_ID_LEN")

- Client options id is not valid.
- Client options id length should be less than 32 chars

### -4071 INVALID\_OPTIONS\_DIRECTION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4071-invalid_options_direction "Direct link to -4071 INVALID_OPTIONS_DIRECTION")

- Invalid options direction

### -4072 OPTIONS\_PREMIUM\_NOT\_UPDATE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4072-options_premium_not_update "Direct link to -4072 OPTIONS_PREMIUM_NOT_UPDATE")

- premium fee is not updated, reject order

### -4073 OPTIONS\_PREMIUM\_INPUT\_LESS\_THAN\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4073-options_premium_input_less_than_zero "Direct link to -4073 OPTIONS_PREMIUM_INPUT_LESS_THAN_ZERO")

- input premium fee is less than 0, reject order

### -4074 OPTIONS\_AMOUNT\_BIGGER\_THAN\_UPPER [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4074-options_amount_bigger_than_upper "Direct link to -4074 OPTIONS_AMOUNT_BIGGER_THAN_UPPER")

- Order amount is bigger than upper boundary or less than 0, reject order

### -4075 OPTIONS\_PREMIUM\_OUTPUT\_ZERO [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4075-options_premium_output_zero "Direct link to -4075 OPTIONS_PREMIUM_OUTPUT_ZERO")

- output premium fee is less than 0, reject order

### -4076 OPTIONS\_PREMIUM\_TOO\_DIFF [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4076-options_premium_too_diff "Direct link to -4076 OPTIONS_PREMIUM_TOO_DIFF")

- original fee is too much higher than last fee

### -4077 OPTIONS\_PREMIUM\_REACH\_LIMIT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4077-options_premium_reach_limit "Direct link to -4077 OPTIONS_PREMIUM_REACH_LIMIT")

- place order amount has reached to limit, reject order

### -4078 OPTIONS\_COMMON\_ERROR [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4078-options_common_error "Direct link to -4078 OPTIONS_COMMON_ERROR")

- options internal error

### -4079 INVALID\_OPTIONS\_ID [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4079-invalid_options_id "Direct link to -4079 INVALID_OPTIONS_ID")

- invalid options id
- invalid options id: %s
- duplicate options id %d for user %d

### -4080 OPTIONS\_USER\_NOT\_FOUND [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4080-options_user_not_found "Direct link to -4080 OPTIONS_USER_NOT_FOUND")

- user not found
- user not found with id: %s

### -4081 OPTIONS\_NOT\_FOUND [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4081-options_not_found "Direct link to -4081 OPTIONS_NOT_FOUND")

- options not found
- options not found with id: %s

### -4082 INVALID\_BATCH\_PLACE\_ORDER\_SIZE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4082-invalid_batch_place_order_size "Direct link to -4082 INVALID_BATCH_PLACE_ORDER_SIZE")

- Invalid number of batch place orders.
- Invalid number of batch place orders: %s

### -4083 PLACE\_BATCH\_ORDERS\_FAIL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4083-place_batch_orders_fail "Direct link to -4083 PLACE_BATCH_ORDERS_FAIL")

- Fail to place batch orders.

### -4084 UPCOMING\_METHOD [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4084-upcoming_method "Direct link to -4084 UPCOMING_METHOD")

- Method is not allowed currently. Upcoming soon.

### -4085 INVALID\_NOTIONAL\_LIMIT\_COEF [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4085-invalid_notional_limit_coef "Direct link to -4085 INVALID_NOTIONAL_LIMIT_COEF")

- Invalid notional limit coefficient

### -4086 INVALID\_PRICE\_SPREAD\_THRESHOLD [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4086-invalid_price_spread_threshold "Direct link to -4086 INVALID_PRICE_SPREAD_THRESHOLD")

- Invalid price spread threshold

### -4087 REDUCE\_ONLY\_ORDER\_PERMISSION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4087-reduce_only_order_permission "Direct link to -4087 REDUCE_ONLY_ORDER_PERMISSION")

- User can only place reduce only order

### -4088 NO\_PLACE\_ORDER\_PERMISSION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4088-no_place_order_permission "Direct link to -4088 NO_PLACE_ORDER_PERMISSION")

- User can not place order currently

### -4104 INVALID\_CONTRACT\_TYPE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4104-invalid_contract_type "Direct link to -4104 INVALID_CONTRACT_TYPE")

- Invalid contract type

### -4114 INVALID\_CLIENT\_TRAN\_ID\_LEN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4114-invalid_client_tran_id_len "Direct link to -4114 INVALID_CLIENT_TRAN_ID_LEN")

- clientTranId is not valid
- Client tran id length should be less than 64 chars

### -4115 DUPLICATED\_CLIENT\_TRAN\_ID [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4115-duplicated_client_tran_id "Direct link to -4115 DUPLICATED_CLIENT_TRAN_ID")

- clientTranId is duplicated
- Client tran id should be unique within 7 days

### -4116 DUPLICATED\_CLIENT\_ORDER\_ID [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4116-duplicated_client_order_id "Direct link to -4116 DUPLICATED_CLIENT_ORDER_ID")

- clientOrderId is duplicated

### -4117 STOP\_ORDER\_TRIGGERING [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4117-stop_order_triggering "Direct link to -4117 STOP_ORDER_TRIGGERING")

- stop order is triggering

### -4118 REDUCE\_ONLY\_MARGIN\_CHECK\_FAILED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4118-reduce_only_margin_check_failed "Direct link to -4118 REDUCE_ONLY_MARGIN_CHECK_FAILED")

- ReduceOnly Order Failed. Please check your existing position and open orders

### -4131 MARKET\_ORDER\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4131-market_order_reject "Direct link to -4131 MARKET_ORDER_REJECT")

- The counterparty's best price does not meet the PERCENT\_PRICE filter limit

### -4135 INVALID\_ACTIVATION\_PRICE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4135-invalid_activation_price "Direct link to -4135 INVALID_ACTIVATION_PRICE")

- Invalid activation price

### -4137 QUANTITY\_EXISTS\_WITH\_CLOSE\_POSITION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4137-quantity_exists_with_close_position "Direct link to -4137 QUANTITY_EXISTS_WITH_CLOSE_POSITION")

- Quantity must be zero with closePosition equals true

### -4138 REDUCE\_ONLY\_MUST\_BE\_TRUE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4138-reduce_only_must_be_true "Direct link to -4138 REDUCE_ONLY_MUST_BE_TRUE")

- Reduce only must be true with closePosition equals true

### -4139 ORDER\_TYPE\_CANNOT\_BE\_MKT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4139-order_type_cannot_be_mkt "Direct link to -4139 ORDER_TYPE_CANNOT_BE_MKT")

- Order type can not be market if it's unable to cancel

### -4140 INVALID\_OPENING\_POSITION\_STATUS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4140-invalid_opening_position_status "Direct link to -4140 INVALID_OPENING_POSITION_STATUS")

- Invalid symbol status for opening position

### -4141 SYMBOL\_ALREADY\_CLOSED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4141-symbol_already_closed "Direct link to -4141 SYMBOL_ALREADY_CLOSED")

- Symbol is closed

### -4142 STRATEGY\_INVALID\_TRIGGER\_PRICE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4142-strategy_invalid_trigger_price "Direct link to -4142 STRATEGY_INVALID_TRIGGER_PRICE")

- REJECT: take profit or stop order will be triggered immediately

### -4144 INVALID\_PAIR [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4144-invalid_pair "Direct link to -4144 INVALID_PAIR")

- Invalid pair

### -4161 ISOLATED\_LEVERAGE\_REJECT\_WITH\_POSITION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4161-isolated_leverage_reject_with_position "Direct link to -4161 ISOLATED_LEVERAGE_REJECT_WITH_POSITION")

- Leverage reduction is not supported in Isolated Margin Mode with open positions

### -4164 MIN\_NOTIONAL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4164-min_notional "Direct link to -4164 MIN_NOTIONAL")

- Order's notional must be no smaller than 5.0 (unless you choose reduce only)
- Order's notional must be no smaller than %s (unless you choose reduce only)

### -4165 INVALID\_TIME\_INTERVAL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4165-invalid_time_interval "Direct link to -4165 INVALID_TIME_INTERVAL")

- Invalid time interval
- Maximum time interval is %s days

### -4167 ISOLATED\_REJECT\_WITH\_JOINT\_MARGIN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4167-isolated_reject_with_joint_margin "Direct link to -4167 ISOLATED_REJECT_WITH_JOINT_MARGIN")

- Unable to adjust to Multi-Assets mode with symbols of USDⓈ-M Futures under isolated-margin mode.

### -4168 JOINT\_MARGIN\_REJECT\_WITH\_ISOLATED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4168-joint_margin_reject_with_isolated "Direct link to -4168 JOINT_MARGIN_REJECT_WITH_ISOLATED")

- Unable to adjust to isolated-margin mode under the Multi-Assets mode.

### -4169 JOINT\_MARGIN\_REJECT\_WITH\_MB [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4169-joint_margin_reject_with_mb "Direct link to -4169 JOINT_MARGIN_REJECT_WITH_MB")

- Unable to adjust Multi-Assets Mode with insufficient margin balance in USDⓈ-M Futures.

### -4170 JOINT\_MARGIN\_REJECT\_WITH\_OPEN\_ORDER [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4170-joint_margin_reject_with_open_order "Direct link to -4170 JOINT_MARGIN_REJECT_WITH_OPEN_ORDER")

- Unable to adjust Multi-Assets Mode with open orders in USDⓈ-M Futures.

### -4171 NO\_NEED\_TO\_CHANGE\_JOINT\_MARGIN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4171-no_need_to_change_joint_margin "Direct link to -4171 NO_NEED_TO_CHANGE_JOINT_MARGIN")

- Adjusted asset mode is currently set and does not need to be adjusted repeatedly.

### -4172 JOINT\_MARGIN\_REJECT\_WITH\_NEGATIVE\_BALANCE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4172-joint_margin_reject_with_negative_balance "Direct link to -4172 JOINT_MARGIN_REJECT_WITH_NEGATIVE_BALANCE")

- Unable to adjust Multi-Assets Mode with a negative wallet balance of margin available asset in USDⓈ-M Futures account.

### -4183 ISOLATED\_REJECT\_WITH\_JOINT\_MARGIN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4183-isolated_reject_with_joint_margin "Direct link to -4183 ISOLATED_REJECT_WITH_JOINT_MARGIN")

- Price is higher than stop price multiplier cap.
- Limit price can't be higher than %s.

### -4184 PRICE\_LOWER\_THAN\_STOP\_MULTIPLIER\_DOWN [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4184-price_lower_than_stop_multiplier_down "Direct link to -4184 PRICE_LOWER_THAN_STOP_MULTIPLIER_DOWN")

- Price is lower than stop price multiplier floor.
- Limit price can't be lower than %s.

### -4192 COOLING\_OFF\_PERIOD [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4192-cooling_off_period "Direct link to -4192 COOLING_OFF_PERIOD")

- Trade forbidden due to Cooling-off Period.

### -4202 ADJUST\_LEVERAGE\_KYC\_FAILED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4202-adjust_leverage_kyc_failed "Direct link to -4202 ADJUST_LEVERAGE_KYC_FAILED")

- Intermediate Personal Verification is required for adjusting leverage over 20x

### -4203 ADJUST\_LEVERAGE\_ONE\_MONTH\_FAILED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4203-adjust_leverage_one_month_failed "Direct link to -4203 ADJUST_LEVERAGE_ONE_MONTH_FAILED")

- More than 20x leverage is available one month after account registration.

### -4205 ADJUST\_LEVERAGE\_X\_DAYS\_FAILED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4205-adjust_leverage_x_days_failed "Direct link to -4205 ADJUST_LEVERAGE_X_DAYS_FAILED")

- More than 20x leverage is available %s days after Futures account registration.

### -4206 ADJUST\_LEVERAGE\_KYC\_LIMIT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4206-adjust_leverage_kyc_limit "Direct link to -4206 ADJUST_LEVERAGE_KYC_LIMIT")

- Users in this country has limited adjust leverage.
- Users in your location/country can only access a maximum leverage of %s

### -4208 ADJUST\_LEVERAGE\_ACCOUNT\_SYMBOL\_FAILED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4208-adjust_leverage_account_symbol_failed "Direct link to -4208 ADJUST_LEVERAGE_ACCOUNT_SYMBOL_FAILED")

- Current symbol leverage cannot exceed 20 when using position limit adjustment service.

### -4209 ADJUST\_LEVERAGE\_SYMBOL\_FAILED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4209-adjust_leverage_symbol_failed "Direct link to -4209 ADJUST_LEVERAGE_SYMBOL_FAILED")

- The max leverage of Symbol is 20x
- Leverage adjustment failed. Current symbol max leverage limit is %sx

### -4210 STOP\_PRICE\_HIGHER\_THAN\_PRICE\_MULTIPLIER\_LIMIT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4210-stop_price_higher_than_price_multiplier_limit "Direct link to -4210 STOP_PRICE_HIGHER_THAN_PRICE_MULTIPLIER_LIMIT")

- Stop price is higher than price multiplier cap.
- Stop price can't be higher than %s

### -4211 STOP\_PRICE\_LOWER\_THAN\_PRICE\_MULTIPLIER\_LIMIT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4211-stop_price_lower_than_price_multiplier_limit "Direct link to -4211 STOP_PRICE_LOWER_THAN_PRICE_MULTIPLIER_LIMIT")

- Stop price is lower than price multiplier floor.
- Stop price can't be lower than %s

### -4400 TRADING\_QUANTITATIVE\_RULE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4400-trading_quantitative_rule "Direct link to -4400 TRADING_QUANTITATIVE_RULE")

- Futures Trading Quantitative Rules violated, only reduceOnly order is allowed, please try again later.

### -4401 LARGE\_POSITION\_SYM\_RULE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4401-large_position_sym_rule "Direct link to -4401 LARGE_POSITION_SYM_RULE")

- Futures Trading Risk Control Rules of large position holding violated, only reduceOnly order is allowed, please reduce the position.
.

### -4402 COMPLIANCE\_BLACK\_SYMBOL\_RESTRICTION [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4402-compliance_black_symbol_restriction "Direct link to -4402 COMPLIANCE_BLACK_SYMBOL_RESTRICTION")

- Dear user, as per our Terms of Use and compliance with local regulations, this feature is currently not available in your region.

### -4403 ADJUST\_LEVERAGE\_COMPLIANCE\_FAILED [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-4403-adjust_leverage_compliance_failed "Direct link to -4403 ADJUST_LEVERAGE_COMPLIANCE_FAILED")

- Dear user, as per our Terms of Use and compliance with local regulations, the leverage can only up to 10x in your region
- Dear user, as per our Terms of Use and compliance with local regulations, the leverage can only up to %sx in your region

## 50xx - Order Execution Issues [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#50xx---order-execution-issues "Direct link to 50xx - Order Execution Issues")

### -5021 FOK\_ORDER\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5021-fok_order_reject "Direct link to -5021 FOK_ORDER_REJECT")

- Due to the order could not be filled immediately, the FOK order has been rejected.

### -5022 GTX\_ORDER\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5022-gtx_order_reject "Direct link to -5022 GTX_ORDER_REJECT")

- Due to the order could not be executed as maker, the Post Only order will be rejected.

### -5024 MOVE\_ORDER\_NOT\_ALLOWED\_SYMBOL\_REASON [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5024-move_order_not_allowed_symbol_reason "Direct link to -5024 MOVE_ORDER_NOT_ALLOWED_SYMBOL_REASON")

- Symbol is not in trading status. Order amendment is not permitted.

### -5025 LIMIT\_ORDER\_ONLY [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5025-limit_order_only "Direct link to -5025 LIMIT_ORDER_ONLY")

- Only limit order is supported.

### -5026 Exceed\_Maximum\_Modify\_Order\_Limit [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5026-exceed_maximum_modify_order_limit "Direct link to -5026 Exceed_Maximum_Modify_Order_Limit")

- Exceed maximum modify order limit.

### -5027 SAME\_ORDER [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5027-same_order "Direct link to -5027 SAME_ORDER")

- No need to modify the order.

### -5028 ME\_RECVWINDOW\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5028-me_recvwindow_reject "Direct link to -5028 ME_RECVWINDOW_REJECT")

- Timestamp for this request is outside of the ME recvWindow.

### -5029 MODIFICATION\_MIN\_NOTIONAL [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5029-modification_min_notional "Direct link to -5029 MODIFICATION_MIN_NOTIONAL")

- Order's notional must be no smaller than %s

### -5037 INVALID\_PRICE\_MATCH [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5037-invalid_price_match "Direct link to -5037 INVALID_PRICE_MATCH")

- Invalid price match

### -5038 UNSUPPORTED\_ORDER\_TYPE\_PRICE\_MATCH [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5038-unsupported_order_type_price_match "Direct link to -5038 UNSUPPORTED_ORDER_TYPE_PRICE_MATCH")

- Price match only supports order type: LIMIT, STOP AND TAKE\_PROFIT

### -5039 INVALID\_SELF\_TRADE\_PREVENTION\_MODE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5039-invalid_self_trade_prevention_mode "Direct link to -5039 INVALID_SELF_TRADE_PREVENTION_MODE")

- Invalid self trade prevention mode

### -5040 FUTURE\_GOOD\_TILL\_DATE [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5040-future_good_till_date "Direct link to -5040 FUTURE_GOOD_TILL_DATE")

- The goodTillDate timestamp must be greater than the current time plus 600 seconds and smaller than 253402300799000 (UTC 9999-12-31 23:59:59)

### -5041 BBO\_ORDER\_REJECT [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code\#-5041-bbo_order_reject "Direct link to -5041 BBO_ORDER_REJECT")

- No depth matches this BBO order

- [10xx - General Server or Network issues](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#10xx---general-server-or-network-issues)
  - [-1000 UNKNOWN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1000-unknown)
  - [-1001 DISCONNECTED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1001-disconnected)
  - [-1002 UNAUTHORIZED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1002-unauthorized)
  - [-1003 TOO\_MANY\_REQUESTS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1003-too_many_requests)
  - [-1004 DUPLICATE\_IP](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1004-duplicate_ip)
  - [-1005 NO\_SUCH\_IP](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1005-no_such_ip)
  - [-1006 UNEXPECTED\_RESP](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1006-unexpected_resp)
  - [-1007 TIMEOUT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1007-timeout)
  - [-1010 ERROR\_MSG\_RECEIVED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1010-error_msg_received)
  - [-1011 NON\_WHITE\_LIST](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1011-non_white_list)
  - [-1013 INVALID\_MESSAGE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1013-invalid_message)
  - [-1014 UNKNOWN\_ORDER\_COMPOSITION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1014-unknown_order_composition)
  - [-1015 TOO\_MANY\_ORDERS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1015-too_many_orders)
  - [-1016 SERVICE\_SHUTTING\_DOWN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1016-service_shutting_down)
  - [-1020 UNSUPPORTED\_OPERATION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1020-unsupported_operation)
  - [-1021 INVALID\_TIMESTAMP](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1021-invalid_timestamp)
  - [-1022 INVALID\_SIGNATURE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1022-invalid_signature)
  - [-1023 START\_TIME\_GREATER\_THAN\_END\_TIME](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1023-start_time_greater_than_end_time)
  - [-1099 NOT\_FOUND](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1099-not_found)
- [11xx - Request issues](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#11xx---request-issues)
  - [-1100 ILLEGAL\_CHARS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1100-illegal_chars)
  - [-1101 TOO\_MANY\_PARAMETERS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1101-too_many_parameters)
  - [-1102 MANDATORY\_PARAM\_EMPTY\_OR\_MALFORMED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1102-mandatory_param_empty_or_malformed)
  - [-1103 UNKNOWN\_PARAM](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1103-unknown_param)
  - [-1104 UNREAD\_PARAMETERS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1104-unread_parameters)
  - [-1105 PARAM\_EMPTY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1105-param_empty)
  - [-1106 PARAM\_NOT\_REQUIRED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1106-param_not_required)
  - [-1108 BAD\_ASSET](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1108-bad_asset)
  - [-1109 BAD\_ACCOUNT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1109-bad_account)
  - [-1110 BAD\_INSTRUMENT\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1110-bad_instrument_type)
  - [-1111 BAD\_PRECISION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1111-bad_precision)
  - [-1112 NO\_DEPTH](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1112-no_depth)
  - [-1113 WITHDRAW\_NOT\_NEGATIVE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1113-withdraw_not_negative)
  - [-1114 TIF\_NOT\_REQUIRED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1114-tif_not_required)
  - [-1115 INVALID\_TIF](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1115-invalid_tif)
  - [-1116 INVALID\_ORDER\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1116-invalid_order_type)
  - [-1117 INVALID\_SIDE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1117-invalid_side)
  - [-1118 EMPTY\_NEW\_CL\_ORD\_ID](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1118-empty_new_cl_ord_id)
  - [-1119 EMPTY\_ORG\_CL\_ORD\_ID](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1119-empty_org_cl_ord_id)
  - [-1120 BAD\_INTERVAL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1120-bad_interval)
  - [-1121 BAD\_SYMBOL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1121-bad_symbol)
  - [-1122 INVALID\_SYMBOL\_STATUS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1122-invalid_symbol_status)
  - [-1125 INVALID\_LISTEN\_KEY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1125-invalid_listen_key)
  - [-1126 ASSET\_NOT\_SUPPORTED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1126-asset_not_supported)
  - [-1127 MORE\_THAN\_XX\_HOURS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1127-more_than_xx_hours)
  - [-1128 OPTIONAL\_PARAMS\_BAD\_COMBO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1128-optional_params_bad_combo)
  - [-1130 INVALID\_PARAMETER](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1130-invalid_parameter)
  - [-1136 INVALID\_NEW\_ORDER\_RESP\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-1136-invalid_new_order_resp_type)
- [20xx - Processing Issues](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#20xx---processing-issues)
  - [-2010 NEW\_ORDER\_REJECTED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2010-new_order_rejected)
  - [-2011 CANCEL\_REJECTED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2011-cancel_rejected)
  - [-2012 CANCEL\_ALL\_FAIL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2012-cancel_all_fail)
  - [-2013 NO\_SUCH\_ORDER](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2013-no_such_order)
  - [-2014 BAD\_API\_KEY\_FMT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2014-bad_api_key_fmt)
  - [-2015 REJECTED\_MBX\_KEY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2015-rejected_mbx_key)
  - [-2016 NO\_TRADING\_WINDOW](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2016-no_trading_window)
  - [-2017 API\_KEYS\_LOCKED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2017-api_keys_locked)
  - [-2018 BALANCE\_NOT\_SUFFICIENT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2018-balance_not_sufficient)
  - [-2019 MARGIN\_NOT\_SUFFICIEN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2019-margin_not_sufficien)
  - [-2020 UNABLE\_TO\_FILL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2020-unable_to_fill)
  - [-2021 ORDER\_WOULD\_IMMEDIATELY\_TRIGGER](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2021-order_would_immediately_trigger)
  - [-2022 REDUCE\_ONLY\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2022-reduce_only_reject)
  - [-2023 USER\_IN\_LIQUIDATION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2023-user_in_liquidation)
  - [-2024 POSITION\_NOT\_SUFFICIENT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2024-position_not_sufficient)
  - [-2025 MAX\_OPEN\_ORDER\_EXCEEDED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2025-max_open_order_exceeded)
  - [-2026 REDUCE\_ONLY\_ORDER\_TYPE\_NOT\_SUPPORTED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2026-reduce_only_order_type_not_supported)
  - [-2027 MAX\_LEVERAGE\_RATIO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2027-max_leverage_ratio)
  - [-2028 MIN\_LEVERAGE\_RATIO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-2028-min_leverage_ratio)
- [40xx - Filters and other Issues](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#40xx---filters-and-other-issues)
  - [-4000 INVALID\_ORDER\_STATUS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4000-invalid_order_status)
  - [-4001 PRICE\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4001-price_less_than_zero)
  - [-4002 PRICE\_GREATER\_THAN\_MAX\_PRICE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4002-price_greater_than_max_price)
  - [-4003 QTY\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4003-qty_less_than_zero)
  - [-4004 QTY\_LESS\_THAN\_MIN\_QTY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4004-qty_less_than_min_qty)
  - [-4005 QTY\_GREATER\_THAN\_MAX\_QTY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4005-qty_greater_than_max_qty)
  - [-4006 STOP\_PRICE\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4006-stop_price_less_than_zero)
  - [-4007 STOP\_PRICE\_GREATER\_THAN\_MAX\_PRICE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4007-stop_price_greater_than_max_price)
  - [-4008 TICK\_SIZE\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4008-tick_size_less_than_zero)
  - [-4009 MAX\_PRICE\_LESS\_THAN\_MIN\_PRICE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4009-max_price_less_than_min_price)
  - [-4010 MAX\_QTY\_LESS\_THAN\_MIN\_QTY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4010-max_qty_less_than_min_qty)
  - [-4011 STEP\_SIZE\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4011-step_size_less_than_zero)
  - [-4012 MAX\_NUM\_ORDERS\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4012-max_num_orders_less_than_zero)
  - [-4013 PRICE\_LESS\_THAN\_MIN\_PRICE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4013-price_less_than_min_price)
  - [-4014 PRICE\_NOT\_INCREASED\_BY\_TICK\_SIZE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4014-price_not_increased_by_tick_size)
  - [-4015 INVALID\_CL\_ORD\_ID\_LEN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4015-invalid_cl_ord_id_len)
  - [-4016 PRICE\_HIGHTER\_THAN\_MULTIPLIER\_UP](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4016-price_highter_than_multiplier_up)
  - [-4017 MULTIPLIER\_UP\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4017-multiplier_up_less_than_zero)
  - [-4018 MULTIPLIER\_DOWN\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4018-multiplier_down_less_than_zero)
  - [-4019 COMPOSITE\_SCALE\_OVERFLOW](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4019-composite_scale_overflow)
  - [-4020 TARGET\_STRATEGY\_INVALID](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4020-target_strategy_invalid)
  - [-4021 INVALID\_DEPTH\_LIMIT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4021-invalid_depth_limit)
  - [-4022 WRONG\_MARKET\_STATUS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4022-wrong_market_status)
  - [-4023 QTY\_NOT\_INCREASED\_BY\_STEP\_SIZE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4023-qty_not_increased_by_step_size)
  - [-4024 PRICE\_LOWER\_THAN\_MULTIPLIER\_DOWN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4024-price_lower_than_multiplier_down)
  - [-4025 MULTIPLIER\_DECIMAL\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4025-multiplier_decimal_less_than_zero)
  - [-4026 COMMISSION\_INVALID](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4026-commission_invalid)
  - [-4027 INVALID\_ACCOUNT\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4027-invalid_account_type)
  - [-4028 INVALID\_LEVERAGE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4028-invalid_leverage)
  - [-4029 INVALID\_TICK\_SIZE\_PRECISION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4029-invalid_tick_size_precision)
  - [-4030 INVALID\_STEP\_SIZE\_PRECISION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4030-invalid_step_size_precision)
  - [-4031 INVALID\_WORKING\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4031-invalid_working_type)
  - [-4032 EXCEED\_MAX\_CANCEL\_ORDER\_SIZE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4032-exceed_max_cancel_order_size)
  - [-4033 INSURANCE\_ACCOUNT\_NOT\_FOUND](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4033-insurance_account_not_found)
  - [-4044 INVALID\_BALANCE\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4044-invalid_balance_type)
  - [-4045 MAX\_STOP\_ORDER\_EXCEEDED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4045-max_stop_order_exceeded)
  - [-4046 NO\_NEED\_TO\_CHANGE\_MARGIN\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4046-no_need_to_change_margin_type)
  - [-4047 THERE\_EXISTS\_OPEN\_ORDERS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4047-there_exists_open_orders)
  - [-4048 THERE\_EXISTS\_QUANTITY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4048-there_exists_quantity)
  - [-4049 ADD\_ISOLATED\_MARGIN\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4049-add_isolated_margin_reject)
  - [-4050 CROSS\_BALANCE\_INSUFFICIENT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4050-cross_balance_insufficient)
  - [-4051 ISOLATED\_BALANCE\_INSUFFICIENT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4051-isolated_balance_insufficient)
  - [-4052 NO\_NEED\_TO\_CHANGE\_AUTO\_ADD\_MARGIN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4052-no_need_to_change_auto_add_margin)
  - [-4053 AUTO\_ADD\_CROSSED\_MARGIN\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4053-auto_add_crossed_margin_reject)
  - [-4054 ADD\_ISOLATED\_MARGIN\_NO\_POSITION\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4054-add_isolated_margin_no_position_reject)
  - [-4055 AMOUNT\_MUST\_BE\_POSITIVE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4055-amount_must_be_positive)
  - [-4056 INVALID\_API\_KEY\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4056-invalid_api_key_type)
  - [-4057 INVALID\_RSA\_PUBLIC\_KEY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4057-invalid_rsa_public_key)
  - [-4058 MAX\_PRICE\_TOO\_LARGE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4058-max_price_too_large)
  - [-4059 NO\_NEED\_TO\_CHANGE\_POSITION\_SIDE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4059-no_need_to_change_position_side)
  - [-4060 INVALID\_POSITION\_SIDE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4060-invalid_position_side)
  - [-4061 POSITION\_SIDE\_NOT\_MATCH](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4061-position_side_not_match)
  - [-4062 REDUCE\_ONLY\_CONFLICT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4062-reduce_only_conflict)
  - [-4063 INVALID\_OPTIONS\_REQUEST\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4063-invalid_options_request_type)
  - [-4064 INVALID\_OPTIONS\_TIME\_FRAME](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4064-invalid_options_time_frame)
  - [-4065 INVALID\_OPTIONS\_AMOUNT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4065-invalid_options_amount)
  - [-4066 INVALID\_OPTIONS\_EVENT\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4066-invalid_options_event_type)
  - [-4067 POSITION\_SIDE\_CHANGE\_EXISTS\_OPEN\_ORDERS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4067-position_side_change_exists_open_orders)
  - [-4068 POSITION\_SIDE\_CHANGE\_EXISTS\_QUANTITY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4068-position_side_change_exists_quantity)
  - [-4069 INVALID\_OPTIONS\_PREMIUM\_FEE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4069-invalid_options_premium_fee)
  - [-4070 INVALID\_CL\_OPTIONS\_ID\_LEN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4070-invalid_cl_options_id_len)
  - [-4071 INVALID\_OPTIONS\_DIRECTION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4071-invalid_options_direction)
  - [-4072 OPTIONS\_PREMIUM\_NOT\_UPDATE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4072-options_premium_not_update)
  - [-4073 OPTIONS\_PREMIUM\_INPUT\_LESS\_THAN\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4073-options_premium_input_less_than_zero)
  - [-4074 OPTIONS\_AMOUNT\_BIGGER\_THAN\_UPPER](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4074-options_amount_bigger_than_upper)
  - [-4075 OPTIONS\_PREMIUM\_OUTPUT\_ZERO](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4075-options_premium_output_zero)
  - [-4076 OPTIONS\_PREMIUM\_TOO\_DIFF](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4076-options_premium_too_diff)
  - [-4077 OPTIONS\_PREMIUM\_REACH\_LIMIT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4077-options_premium_reach_limit)
  - [-4078 OPTIONS\_COMMON\_ERROR](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4078-options_common_error)
  - [-4079 INVALID\_OPTIONS\_ID](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4079-invalid_options_id)
  - [-4080 OPTIONS\_USER\_NOT\_FOUND](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4080-options_user_not_found)
  - [-4081 OPTIONS\_NOT\_FOUND](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4081-options_not_found)
  - [-4082 INVALID\_BATCH\_PLACE\_ORDER\_SIZE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4082-invalid_batch_place_order_size)
  - [-4083 PLACE\_BATCH\_ORDERS\_FAIL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4083-place_batch_orders_fail)
  - [-4084 UPCOMING\_METHOD](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4084-upcoming_method)
  - [-4085 INVALID\_NOTIONAL\_LIMIT\_COEF](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4085-invalid_notional_limit_coef)
  - [-4086 INVALID\_PRICE\_SPREAD\_THRESHOLD](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4086-invalid_price_spread_threshold)
  - [-4087 REDUCE\_ONLY\_ORDER\_PERMISSION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4087-reduce_only_order_permission)
  - [-4088 NO\_PLACE\_ORDER\_PERMISSION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4088-no_place_order_permission)
  - [-4104 INVALID\_CONTRACT\_TYPE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4104-invalid_contract_type)
  - [-4114 INVALID\_CLIENT\_TRAN\_ID\_LEN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4114-invalid_client_tran_id_len)
  - [-4115 DUPLICATED\_CLIENT\_TRAN\_ID](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4115-duplicated_client_tran_id)
  - [-4116 DUPLICATED\_CLIENT\_ORDER\_ID](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4116-duplicated_client_order_id)
  - [-4117 STOP\_ORDER\_TRIGGERING](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4117-stop_order_triggering)
  - [-4118 REDUCE\_ONLY\_MARGIN\_CHECK\_FAILED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4118-reduce_only_margin_check_failed)
  - [-4131 MARKET\_ORDER\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4131-market_order_reject)
  - [-4135 INVALID\_ACTIVATION\_PRICE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4135-invalid_activation_price)
  - [-4137 QUANTITY\_EXISTS\_WITH\_CLOSE\_POSITION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4137-quantity_exists_with_close_position)
  - [-4138 REDUCE\_ONLY\_MUST\_BE\_TRUE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4138-reduce_only_must_be_true)
  - [-4139 ORDER\_TYPE\_CANNOT\_BE\_MKT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4139-order_type_cannot_be_mkt)
  - [-4140 INVALID\_OPENING\_POSITION\_STATUS](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4140-invalid_opening_position_status)
  - [-4141 SYMBOL\_ALREADY\_CLOSED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4141-symbol_already_closed)
  - [-4142 STRATEGY\_INVALID\_TRIGGER\_PRICE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4142-strategy_invalid_trigger_price)
  - [-4144 INVALID\_PAIR](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4144-invalid_pair)
  - [-4161 ISOLATED\_LEVERAGE\_REJECT\_WITH\_POSITION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4161-isolated_leverage_reject_with_position)
  - [-4164 MIN\_NOTIONAL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4164-min_notional)
  - [-4165 INVALID\_TIME\_INTERVAL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4165-invalid_time_interval)
  - [-4167 ISOLATED\_REJECT\_WITH\_JOINT\_MARGIN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4167-isolated_reject_with_joint_margin)
  - [-4168 JOINT\_MARGIN\_REJECT\_WITH\_ISOLATED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4168-joint_margin_reject_with_isolated)
  - [-4169 JOINT\_MARGIN\_REJECT\_WITH\_MB](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4169-joint_margin_reject_with_mb)
  - [-4170 JOINT\_MARGIN\_REJECT\_WITH\_OPEN\_ORDER](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4170-joint_margin_reject_with_open_order)
  - [-4171 NO\_NEED\_TO\_CHANGE\_JOINT\_MARGIN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4171-no_need_to_change_joint_margin)
  - [-4172 JOINT\_MARGIN\_REJECT\_WITH\_NEGATIVE\_BALANCE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4172-joint_margin_reject_with_negative_balance)
  - [-4183 ISOLATED\_REJECT\_WITH\_JOINT\_MARGIN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4183-isolated_reject_with_joint_margin)
  - [-4184 PRICE\_LOWER\_THAN\_STOP\_MULTIPLIER\_DOWN](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4184-price_lower_than_stop_multiplier_down)
  - [-4192 COOLING\_OFF\_PERIOD](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4192-cooling_off_period)
  - [-4202 ADJUST\_LEVERAGE\_KYC\_FAILED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4202-adjust_leverage_kyc_failed)
  - [-4203 ADJUST\_LEVERAGE\_ONE\_MONTH\_FAILED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4203-adjust_leverage_one_month_failed)
  - [-4205 ADJUST\_LEVERAGE\_X\_DAYS\_FAILED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4205-adjust_leverage_x_days_failed)
  - [-4206 ADJUST\_LEVERAGE\_KYC\_LIMIT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4206-adjust_leverage_kyc_limit)
  - [-4208 ADJUST\_LEVERAGE\_ACCOUNT\_SYMBOL\_FAILED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4208-adjust_leverage_account_symbol_failed)
  - [-4209 ADJUST\_LEVERAGE\_SYMBOL\_FAILED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4209-adjust_leverage_symbol_failed)
  - [-4210 STOP\_PRICE\_HIGHER\_THAN\_PRICE\_MULTIPLIER\_LIMIT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4210-stop_price_higher_than_price_multiplier_limit)
  - [-4211 STOP\_PRICE\_LOWER\_THAN\_PRICE\_MULTIPLIER\_LIMIT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4211-stop_price_lower_than_price_multiplier_limit)
  - [-4400 TRADING\_QUANTITATIVE\_RULE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4400-trading_quantitative_rule)
  - [-4401 LARGE\_POSITION\_SYM\_RULE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4401-large_position_sym_rule)
  - [-4402 COMPLIANCE\_BLACK\_SYMBOL\_RESTRICTION](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4402-compliance_black_symbol_restriction)
  - [-4403 ADJUST\_LEVERAGE\_COMPLIANCE\_FAILED](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-4403-adjust_leverage_compliance_failed)
- [50xx - Order Execution Issues](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#50xx---order-execution-issues)
  - [-5021 FOK\_ORDER\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5021-fok_order_reject)
  - [-5022 GTX\_ORDER\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5022-gtx_order_reject)
  - [-5024 MOVE\_ORDER\_NOT\_ALLOWED\_SYMBOL\_REASON](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5024-move_order_not_allowed_symbol_reason)
  - [-5025 LIMIT\_ORDER\_ONLY](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5025-limit_order_only)
  - [-5026 Exceed\_Maximum\_Modify\_Order\_Limit](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5026-exceed_maximum_modify_order_limit)
  - [-5027 SAME\_ORDER](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5027-same_order)
  - [-5028 ME\_RECVWINDOW\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5028-me_recvwindow_reject)
  - [-5029 MODIFICATION\_MIN\_NOTIONAL](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5029-modification_min_notional)
  - [-5037 INVALID\_PRICE\_MATCH](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5037-invalid_price_match)
  - [-5038 UNSUPPORTED\_ORDER\_TYPE\_PRICE\_MATCH](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5038-unsupported_order_type_price_match)
  - [-5039 INVALID\_SELF\_TRADE\_PREVENTION\_MODE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5039-invalid_self_trade_prevention_mode)
  - [-5040 FUTURE\_GOOD\_TILL\_DATE](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5040-future_good_till_date)
  - [-5041 BBO\_ORDER\_REJECT](https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code#-5041-bbo_order_reject)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Cancel_Multiple_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders#__docusaurus_skipToContent_fallback)

On this page

# Cancel Multiple Orders (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders\#api-description "Direct link to API Description")

Cancel Multiple Orders

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders\#http-request "Direct link to HTTP Request")

DELETE `/fapi/v1/batchOrders`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderIdList | LIST<LONG> | NO | max length 10 <br> e.g. \[1234567,2345678\] |
| origClientOrderIdList | LIST<STRING> | NO | max length 10<br> e.g. \["my\_id\_1","my\_id\_2"\], encode the double quotes. No space after comma. |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Either `orderIdList` or `origClientOrderIdList ` must be sent.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
	 	"clientOrderId": "myOrder1",\
	 	"cumQty": "0",\
	 	"cumQuote": "0",\
	 	"executedQty": "0",\
	 	"orderId": 283194212,\
	 	"origQty": "11",\
	 	"origType": "TRAILING_STOP_MARKET",\
  		"price": "0",\
  		"reduceOnly": false,\
  		"side": "BUY",\
  		"positionSide": "SHORT",\
  		"status": "CANCELED",\
  		"stopPrice": "9300",				// please ignore when order type is TRAILING_STOP_MARKET\
  		"closePosition": false,   // if Close-All\
  		"symbol": "BTCUSDT",\
  		"timeInForce": "GTC",\
  		"type": "TRAILING_STOP_MARKET",\
  		"activatePrice": "9020",			// activation price, only return with TRAILING_STOP_MARKET order\
  		"priceRate": "0.3",					// callback rate, only return with TRAILING_STOP_MARKET order\
	 	"updateTime": 1571110484038,\
	 	"workingType": "CONTRACT_PRICE",\
	 	"priceProtect": false,            // if conditional order trigger is protected\
	 	"priceMatch": "NONE",              //price match mode\
	 	"selfTradePreventionMode": "NONE", //self trading preventation mode\
	 	"goodTillDate": 1693207680000      //order pre-set auot cancel time for TIF GTD order\
	},\
	{\
		"code": -2011,\
		"msg": "Unknown order sent."\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Multiple-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Insurance_Fund_Balance.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance#__docusaurus_skipToContent_fallback)

On this page

# Query Insurance Fund Balance Snapshot

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance\#api-description "Direct link to API Description")

Query Insurance Fund Balance Snapshot

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/insuranceBalance`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance\#response-example "Direct link to Response Example")

pass symbol

```codeBlockLines_aHhF
{
   "symbols":[\
      "BNBUSDT",\
      "BTCUSDT",\
      "BTCUSDT_250627",\
      "BTCUSDT_250926",\
      "ETHBTC",\
      "ETHUSDT",\
      "ETHUSDT_250627",\
      "ETHUSDT_250926"\
   ],
   "assets":[\
      {\
         "asset":"USDC",\
         "marginBalance":"299999998.6497832",\
         "updateTime":1745366402000\
      },\
      {\
         "asset":"USDT",\
         "marginBalance":"793930579.315848",\
         "updateTime":1745366402000\
      },\
      {\
         "asset":"BTC",\
         "marginBalance":"61.73143554",\
         "updateTime":1745366402000\
      },\
      {\
         "asset":"BNFCR",\
         "marginBalance":"633223.99396922",\
         "updateTime":1745366402000\
      }\
   ]
}

```

> or not pass symbol

```codeBlockLines_aHhF
[\
   {\
      "symbols":[\
         "ADAUSDT",\
         "BCHUSDT",\
         "DOTUSDT",\
         "EOSUSDT",\
         "ETCUSDT",\
         "LINKUSDT",\
         "LTCUSDT",\
         "TRXUSDT",\
         "XLMUSDT",\
         "XMRUSDT",\
         "XRPUSDT"\
      ],\
      "assets":[\
         {\
            "asset":"USDT",\
            "marginBalance":"314151411.06482935",\
            "updateTime":1745366402000\
         }\
      ]\
   },\
   {\
      "symbols":[\
         "ACTUSDT",\
         "MUBARAKUSDT",\
         "OMUSDT",\
         "TSTUSDT"\
      ],\
      "assets":[\
         {\
            "asset":"USDT",\
            "marginBalance":"5166686.84431694",\
            "updateTime":1745366402000\
         }\
      ]\
   }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Insurance-Fund-Balance#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Individual_Symbol_Book_Ticker_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams#__docusaurus_skipToContent_fallback)

On this page

# Individual Symbol Book Ticker Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams\#stream-description "Direct link to Stream Description")

Pushes any update to the best bid or ask's price or quantity in real-time for a specified symbol.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@bookTicker`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams\#update-speed "Direct link to Update Speed")

**Real-time**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e":"bookTicker",			// event type
  "u":400900217,     		// order book updateId
  "E": 1568014460893,  		// event time
  "T": 1568014460891,  		// transaction time
  "s":"BNBUSDT",     		// symbol
  "b":"25.35190000", 		// best bid price
  "B":"31.21000000", 		// best bid qty
  "a":"25.36520000", 		// best ask price
  "A":"40.66000000"  		// best ask qty
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Book-Ticker-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_websocket_api_Cancel_Order.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order#__docusaurus_skipToContent_fallback)

On this page

# Cancel Order (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order\#api-description "Direct link to API Description")

Cancel an active order.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order\#method "Direct link to Method")

`order.cancel`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order\#request "Direct link to Request")

```codeBlockLines_aHhF
{
   	"id": "5633b6a2-90a9-4192-83e7-925c90b6a2fd",
    "method": "order.cancel",
    "params": {
        "apiKey": "HsOehcfih8ZRxnhjp2XjGXhsOBd6msAhKz9joQaWwZ7arcJTlD2hGOGQj1lGdTjR",
        "orderId": 283194212,
        "symbol": "BTCUSDT",
        "timestamp": 1703439070722,
        "signature": "b09c49815b4e3f1f6098cd9fbe26a933a9af79803deaaaae03c29f719c08a8a8"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Either `orderId` or `origClientOrderId` must be sent.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "id": "5633b6a2-90a9-4192-83e7-925c90b6a2fd",
  "status": 200,
  "result": {
    "clientOrderId": "myOrder1",
    "cumQty": "0",
    "cumQuote": "0",
    "executedQty": "0",
    "orderId": 283194212,
    "origQty": "11",
    "origType": "TRAILING_STOP_MARKET",
    "price": "0",
    "reduceOnly": false,
    "side": "BUY",
    "positionSide": "SHORT",
    "status": "CANCELED",
    "stopPrice": "9300",
    "closePosition": false,
    "symbol": "BTCUSDT",
    "timeInForce": "GTC",
    "type": "TRAILING_STOP_MARKET",
    "activatePrice": "9020",
    "priceRate": "0.3",
    "updateTime": 1571110484038,
    "workingType": "CONTRACT_PRICE",
    "priceProtect": false,
    "priceMatch": "NONE",
    "selfTradePreventionMode": "NONE",
    "goodTillDate": 0
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 1\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Cancel-Order#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Kline_Candlestick_Data.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data#__docusaurus_skipToContent_fallback)

On this page

# Kline/Candlestick Data

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data\#api-description "Direct link to API Description")

Kline/candlestick bars for a symbol.
Klines are uniquely identified by their open time.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/klines`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data\#request-weight "Direct link to Request Weight")

based on parameter `LIMIT`

| LIMIT | weight |
| --- | --- |
| \[1,100) | 1 |\
| \[100, 500) | 2 |\
| \[500, 1000\] | 5 |\
| \> 1000 | 10 |\
\
## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data\#request-parameters "Direct link to Request Parameters")\
\
| Name | Type | Mandatory | Description |\
| --- | --- | --- | --- |\
| symbol | STRING | YES |  |\
| interval | ENUM | YES |  |\
| startTime | LONG | NO |  |\
| endTime | LONG | NO |  |\
| limit | INT | NO | Default 500; max 1500. |\
\
> - If startTime and endTime are not sent, the most recent klines are returned.\
\
## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data\#response-example "Direct link to Response Example")\
\
```codeBlockLines_aHhF\
[\
  [\
    1499040000000,      // Open time\
    "0.01634790",       // Open\
    "0.80000000",       // High\
    "0.01575800",       // Low\
    "0.01577100",       // Close\
    "148976.11427815",  // Volume\
    1499644799999,      // Close time\
    "2434.19055334",    // Quote asset volume\
    308,                // Number of trades\
    "1756.87402397",    // Taker buy base asset volume\
    "28.46694368",      // Taker buy quote asset volume\
    "17928899.62484339" // Ignore.\
  ]\
]\
\
```\
\
- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data#api-description)\
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data#http-request)\
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data#request-weight)\
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data#request-parameters)\
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Get_Futures_Trade_Download_Link_by_Id.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id#__docusaurus_skipToContent_fallback)

On this page

# Get Futures Trade Download Link by Id(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id\#api-description "Direct link to API Description")

Get futures trade download link by Id

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/trade/asyn/id`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id\#request-weight "Direct link to Request Weight")

**10**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| downloadId | STRING | YES | get by download id api |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Download link expiration: 24h

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
{
	"downloadId":"545923594199212032",
  	"status":"completed",     // Enum：completed，processing
  	"url":"www.binance.com",  // The link is mapped to download id
  	"notified":true,          // ignore
  	"expirationTimestamp":1645009771000,  // The link would expire after this timestamp
  	"isExpired":null,
}

```

> **OR** (Response when server is processing)

```codeBlockLines_aHhF
{
	"downloadId":"545923594199212032",
  	"status":"processing",
  	"url":"",
  	"notified":false,
  	"expirationTimestamp":-1
  	"isExpired":null,

}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Futures-Trade-Download-Link-by-Id#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Modify_Order.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order#__docusaurus_skipToContent_fallback)

On this page

# Modify Order (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order\#api-description "Direct link to API Description")

Order modify function, currently only LIMIT order modification is supported, modified orders will be reordered in the match queue

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order\#http-request "Direct link to HTTP Request")

PUT `/fapi/v1/order`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order\#request-weight "Direct link to Request Weight")

1 on 10s order rate limit(X-MBX-ORDER-COUNT-10S);
1 on 1min order rate limit(X-MBX-ORDER-COUNT-1M);
1 on IP rate limit(x-mbx-used-weight-1m)

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| symbol | STRING | YES |  |
| side | ENUM | YES | `SELL`, `BUY` |
| quantity | DECIMAL | YES | Order quantity, cannot be sent with `closePosition=true` |
| price | DECIMAL | YES |  |
| priceMatch | ENUM | NO | only avaliable for `LIMIT`/ `STOP`/ `TAKE_PROFIT` order; can be set to `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`: / `QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`; Can't be passed together with `price` |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Either `orderId` or `origClientOrderId` must be sent, and the `orderId` will prevail if both are sent.
> - Both `quantity` and `price` must be sent, which is different from dapi modify order endpoint.
> - When the new `quantity` or `price` doesn't satisfy PRICE\_FILTER / PERCENT\_FILTER / LOT\_SIZE, amendment will be rejected and the order will stay as it is.
> - However the order will be cancelled by the amendment in the following situations:
>   - when the order is in partially filled status and the new `quantity` <= `executedQty`
>   - When the order is `GTX` and the new price will cause it to be executed immediately
> - One order can only be modfied for less than 10000 times
> - Modify order will set `selfTradePreventionMode` to `NONE`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
 	"orderId": 20072994037,
 	"symbol": "BTCUSDT",
 	"pair": "BTCUSDT",
 	"status": "NEW",
 	"clientOrderId": "LJ9R4QZDihCaS8UAOOLpgW",
 	"price": "30005",
 	"avgPrice": "0.0",
 	"origQty": "1",
 	"executedQty": "0",
 	"cumQty": "0",
 	"cumBase": "0",
 	"timeInForce": "GTC",
 	"type": "LIMIT",
 	"reduceOnly": false,
 	"closePosition": false,
 	"side": "BUY",
 	"positionSide": "LONG",
 	"stopPrice": "0",
 	"workingType": "CONTRACT_PRICE",
 	"priceProtect": false,
 	"origType": "LIMIT",
    "priceMatch": "NONE",              //price match mode
    "selfTradePreventionMode": "NONE", //self trading preventation mode
    "goodTillDate": 0,                 //order pre-set auot cancel time for TIF GTD order
 	"updateTime": 1629182711600
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Compressed_Aggregate_Trades_List.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List#__docusaurus_skipToContent_fallback)

On this page

# Compressed/Aggregate Trades List

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List\#api-description "Direct link to API Description")

Get compressed, aggregate market trades. Market trades that fill in 100ms with the same price and the same taking side will have the quantity aggregated.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/aggTrades`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List\#request-weight "Direct link to Request Weight")

20

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| fromId | LONG | NO | ID to get aggregate trades from INCLUSIVE. |
| startTime | LONG | NO | Timestamp in ms to get aggregate trades from INCLUSIVE. |
| endTime | LONG | NO | Timestamp in ms to get aggregate trades until INCLUSIVE. |
| limit | INT | NO | Default 500; max 1000. |

> - support querying futures trade histories that are not older than one year
> - If both `startTime` and `endTime` are sent, time between `startTime` and `endTime` must be less than 1 hour.
> - If `fromId`, `startTime`, and `endTime` are not sent, the most recent aggregate trades will be returned.
> - Only market trades will be aggregated and returned, which means the insurance fund trades and ADL trades won't be aggregated.
> - Sending both `startTime`/ `endTime` and `fromId` might cause response timeout, please send either `fromId` or `startTime`/ `endTime`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
    "a": 26129,         // Aggregate tradeId\
    "p": "0.01633102",  // Price\
    "q": "4.70443515",  // Quantity\
    "f": 27781,         // First tradeId\
    "l": 27781,         // Last tradeId\
    "T": 1498793709153, // Timestamp\
    "m": true,          // Was the buyer the maker?\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Query_Order.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order#__docusaurus_skipToContent_fallback)

On this page

# Query Order (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order\#api-description "Direct link to API Description")

Check an order's status.

- These orders will not be found:
  - order status is `CANCELED` or `EXPIRED` **AND** order has NO filled trade **AND** created time + 3 days < current time
  - order create time + 90 days < current time

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/order`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

Notes:

> - Either `orderId` or `origClientOrderId` must be sent.
> - `orderId` is self-increment for each specific `symbol`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  	"avgPrice": "0.00000",
  	"clientOrderId": "abc",
  	"cumQuote": "0",
  	"executedQty": "0",
  	"orderId": 1917641,
  	"origQty": "0.40",
  	"origType": "TRAILING_STOP_MARKET",
  	"price": "0",
  	"reduceOnly": false,
  	"side": "BUY",
  	"positionSide": "SHORT",
  	"status": "NEW",
  	"stopPrice": "9300",				// please ignore when order type is TRAILING_STOP_MARKET
  	"closePosition": false,   // if Close-All
  	"symbol": "BTCUSDT",
  	"time": 1579276756075,				// order time
  	"timeInForce": "GTC",
  	"type": "TRAILING_STOP_MARKET",
  	"activatePrice": "9020",			// activation price, only return with TRAILING_STOP_MARKET order
  	"priceRate": "0.3",					// callback rate, only return with TRAILING_STOP_MARKET order
  	"updateTime": 1579276756075,		// update time
  	"workingType": "CONTRACT_PRICE",
  	"priceProtect": false,              // if conditional order trigger is protected
    "priceMatch": "NONE",              //price match mode
    "selfTradePreventionMode": "NONE", //self trading preventation mode
    "goodTillDate": 0                  //order pre-set auot cancel time for TIF GTD order
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Order#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Basis.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis#__docusaurus_skipToContent_fallback)

On this page

# Basis

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis\#api-description "Direct link to API Description")

Query future basis

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis\#http-request "Direct link to HTTP Request")

GET `/futures/data/basis`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis\#request-weight "Direct link to Request Weight")

**0**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| pair | STRING | YES | BTCUSDT |
| contractType | ENUM | YES | CURRENT\_QUARTER, NEXT\_QUARTER, PERPETUAL |
| period | ENUM | YES | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit | LONG | YES | Default 30,Max 500 |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |

> - If startTime and endTime are not sent, the most recent data is returned.
> - Only the data of the latest 30 days is available.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
        "indexPrice": "34400.15945055",\
        "contractType": "PERPETUAL",\
        "basisRate": "0.0004",\
        "futuresPrice": "34414.10",\
        "annualizedBasisRate": "",\
        "basis": "13.94054945",\
        "pair": "BTCUSDT",\
        "timestamp": 1698742800000\
    }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Aggregate_Trade_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams#__docusaurus_skipToContent_fallback)

On this page

# Aggregate Trade Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams\#stream-description "Direct link to Stream Description")

The Aggregate Trade Streams push market trade information that is aggregated for fills with same price and taking side every 100 milliseconds. Only market trades will be aggregated, which means the insurance fund trades and ADL trades won't be aggregated.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@aggTrade`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams\#update-speed "Direct link to Update Speed")

**100ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e": "aggTrade",  // Event type
  "E": 123456789,   // Event time
  "s": "BTCUSDT",    // Symbol
  "a": 5933014,		// Aggregate trade ID
  "p": "0.001",     // Price
  "q": "100",       // Quantity
  "f": 100,         // First trade ID
  "l": 105,         // Last trade ID
  "T": 123456785,   // Trade time
  "m": true,        // Is the buyer the market maker?
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Aggregate-Trade-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Symbol_Config.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config#__docusaurus_skipToContent_fallback)

On this page

# Symbol Configuration(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config\#api-description "Direct link to API Description")

Get current account symbol configuration.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/symbolConfig`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
  "symbol": "BTCUSDT",\
  "marginType": "CROSSED",\
  "isAutoAddMargin": "false",\
  "leverage": 21,\
  "maxNotionalValue": "1000000",\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Symbol-Config#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Mark_Price.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price#__docusaurus_skipToContent_fallback)

On this page

# Mark Price

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price\#api-description "Direct link to API Description")

Mark Price and Funding Rate

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/premiumIndex`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
{
	"symbol": "BTCUSDT",
	"markPrice": "11793.63104562",	// mark price
	"indexPrice": "11781.80495970",	// index price
	"estimatedSettlePrice": "11781.16138815", // Estimated Settle Price, only useful in the last hour before the settlement starts.
	"lastFundingRate": "0.00038246",  // This is the Latest funding rate
	"interestRate": "0.00010000",
	"nextFundingTime": 1597392000000,
	"time": 1597370495002
}

```

> **OR (when symbol not sent)**

```codeBlockLines_aHhF
[\
	{\
	    "symbol": "BTCUSDT",\
	    "markPrice": "11793.63104562",	// mark price\
	    "indexPrice": "11781.80495970",	// index price\
	    "estimatedSettlePrice": "11781.16138815", // Estimated Settle Price, only useful in the last hour before the settlement starts.\
	    "lastFundingRate": "0.00038246",  // This is the Latest funding rate\
	    "interestRate": "0.00010000",\
	    "nextFundingTime": 1597392000000,\
	    "time": 1597370495002\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Liquidation_Order_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams#__docusaurus_skipToContent_fallback)

On this page

# Liquidation Order Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams\#stream-description "Direct link to Stream Description")

The Liquidation Order Snapshot Streams push force liquidation order information for specific symbol.
For each symbol，only the latest one liquidation order within 1000ms will be pushed as the snapshot. If no liquidation happens in the interval of 1000ms, no stream will be pushed.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@forceOrder`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams\#update-speed "Direct link to Update Speed")

1000ms

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{

	"e":"forceOrder",                   // Event Type
	"E":1568014460893,                  // Event Time
	"o":{

		"s":"BTCUSDT",                   // Symbol
		"S":"SELL",                      // Side
		"o":"LIMIT",                     // Order Type
		"f":"IOC",                       // Time in Force
		"q":"0.014",                     // Original Quantity
		"p":"9910",                      // Price
		"ap":"9910",                     // Average Price
		"X":"FILLED",                    // Order Status
		"l":"0.014",                     // Order Last Filled Quantity
		"z":"0.014",                     // Order Filled Accumulated Quantity
		"T":1568014460893,          	 // Order Trade Time

	}

}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Account_Trade_List.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List#__docusaurus_skipToContent_fallback)

On this page

# Account Trade List (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List\#api-description "Direct link to API Description")

Get trades for a specific account and symbol.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/userTrades`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO | This can only be used in combination with `symbol` |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |
| fromId | LONG | NO | Trade id to fetch from. Default gets most recent trades. |
| limit | INT | NO | Default 500; max 1000. |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - If `startTime` and `endTime` are both not sent, then the last 7 days' data will be returned.
> - The time between `startTime` and `endTime` cannot be longer than 7 days.
> - The parameter `fromId` cannot be sent with `startTime` or `endTime`.
> - Only support querying trade in the past 6 months

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
  	"buyer": false,\
  	"commission": "-0.07819010",\
  	"commissionAsset": "USDT",\
  	"id": 698759,\
  	"maker": false,\
  	"orderId": 25851813,\
  	"price": "7819.01",\
  	"qty": "0.002",\
  	"quoteQty": "15.63802",\
  	"realizedPnl": "-0.91539999",\
  	"side": "SELL",\
  	"positionSide": "SHORT",\
  	"symbol": "BTCUSDT",\
  	"time": 1569514978020\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_websocket_api_Position_Info_V2.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2#__docusaurus_skipToContent_fallback)

On this page

# Position Information V2 (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2\#api-description "Direct link to API Description")

Get current position information(only symbol that has position or open orders will be returned).

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2\#method "Direct link to Method")

`v2/account.position`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2\#request "Direct link to Request")

```codeBlockLines_aHhF
{
   	"id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "method": "v2/account.position",
    "params": {
        "apiKey": "xTaDyrmvA9XT2oBHHjy39zyPzKCvMdtH3b9q4xadkAg2dNSJXQGCxzui26L823W2",
        "symbol": "BTCUSDT",
        "timestamp": 1702920680303,
        "signature": "31ab02a51a3989b66c29d40fcdf78216978a60afc6d8dc1c753ae49fa3164a2a"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

**Note**

> - Please use with user data stream `ACCOUNT_UPDATE` to meet your timeliness and accuracy needs.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2\#response-example "Direct link to Response Example")

> For One-way position mode:

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": [\
    {\
	    "symbol": "BTCUSDT",\
	    "positionSide": "BOTH",            // 持仓方向\
	    "positionAmt": "1.000",\
	    "entryPrice": "0.00000",\
	    "breakEvenPrice": "0.0",\
	    "markPrice": "6679.50671178",\
	    "unrealizedProfit": "0.00000000",  // 持仓未实现盈亏\
	    "liquidationPrice": "0",\
	    "isolatedMargin": "0.00000000",\
	    "notional": "0",\
	    "marginAsset": "USDT",\
	    "isolatedWallet": "0",\
	    "initialMargin": "0",              // 初始保证金\
	    "maintMargin": "0",                // 维持保证金\
	    "positionInitialMargin": "0",      // 仓位初始保证金\
	    "openOrderInitialMargin": "0",     // 订单初始保证金\
	    "adl": 0,\
	    "bidNotional": "0",\
	    "askNotional": "0",\
	    "updateTime": 0                    // 更新时间\
    }\
],
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

> For Hedge position mode:

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": [\
   {\
	    "symbol": "BTCUSDT",\
	    "positionSide": "LONG",\
	    "positionAmt": "1.000",\
	    "entryPrice": "0.00000",\
	    "breakEvenPrice": "0.0",\
	    "markPrice": "6679.50671178",\
	    "unrealizedProfit": "0.00000000",\
	    "liquidationPrice": "0",\
	    "isolatedMargin": "0.00000000",\
	    "notional": "0",\
	    "marginAsset": "USDT",\
	    "isolatedWallet": "0",\
	    "initialMargin": "0",\
	    "maintMargin": "0",\
	    "positionInitialMargin": "0",\
	    "openOrderInitialMargin": "0",\
	    "adl": 0,\
	    "bidNotional": "0",\
	    "askNotional": "0",\
	    "updateTime": 0\
    },\
    {\
	    "symbol": "BTCUSDT",\
	    "positionSide": "SHORT",\
	    "positionAmt": "1.000",\
	    "entryPrice": "0.00000",\
	    "breakEvenPrice": "0.0",\
	    "markPrice": "6679.50671178",\
	    "unrealizedProfit": "0.00000000",\
	    "liquidationPrice": "0",\
	    "isolatedMargin": "0.00000000",\
	    "notional": "0",\
	    "marginAsset": "USDT",\
	    "isolatedWallet": "0",\
	    "initialMargin": "0",\
	    "maintMargin": "0",\
	    "positionInitialMargin": "0",\
	    "openOrderInitialMargin": "0",\
	    "adl": 0,\
	    "bidNotional": "0",\
	    "askNotional": "0",\
	    "updateTime": 0\
    }\
  ],
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Info-V2#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_websocket_api_Symbol_Price_Ticker.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker#__docusaurus_skipToContent_fallback)

On this page

# Symbol Price Ticker

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker\#api-description "Direct link to API Description")

Latest price for a symbol or symbols.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker\#method "Direct link to Method")

`ticker.price`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker\#request "Direct link to Request")

```codeBlockLines_aHhF
{
   	"id": "9d32157c-a556-4d27-9866-66760a174b57",
    "method": "ticker.price",
    "params": {
        "symbol": "BTCUSDT"
    }
}

```

**Weight:**

**1** for a single symbol;

**2** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

> - If the symbol is not sent, prices for all symbols will be returned in an array.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "id": "9d32157c-a556-4d27-9866-66760a174b57",
  "status": 200,
  "result": {
	"symbol": "BTCUSDT",
	"price": "6000.01",
	"time": 1589437530011   // Transaction time
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 2\
    }\
  ]
}

```

> OR

```codeBlockLines_aHhF
{
  "id": "9d32157c-a556-4d27-9866-66760a174b57",
  "status": 200,
  "result": [\
	{\
    	"symbol": "BTCUSDT",\
      	"price": "6000.01",\
      	"time": 1589437530011\
  	}\
  ],
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 2\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker#request)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/websocket-api/Symbol-Price-Ticker#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_websocket_api_Futures_Account_Balance.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance#__docusaurus_skipToContent_fallback)

On this page

# Futures Account Balance(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance\#api-description "Direct link to API Description")

Query account balance info

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance\#method "Direct link to Method")

`account.balance`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "method": "account.balance",
    "params": {
        "apiKey": "xTaDyrmvA9XT2oBHHjy39zyPzKCvMdtH3b9q4xadkAg2dNSJXQGCxzui26L823W2",
        "timestamp": 1702561978458,
        "signature": "208bb94a26f99aa122b1319490ca9cb2798fccc81d9b6449521a26268d53217a"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "status": 200,
    "result": [\
        {\
            "accountAlias": "SgsR",    // unique account code\
            "asset": "USDT",    // asset name\
            "balance": "122607.35137903", // wallet balance\
            "crossWalletBalance": "23.72469206", // crossed wallet balance\
            "crossUnPnl": "0.00000000"  // unrealized profit of crossed positions\
            "availableBalance": "23.72469206",       // available balance\
            "maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
            "marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
            "updateTime": 1617939110373\
        }\
    ],
    "rateLimits": [\
      {\
        "rateLimitType": "REQUEST_WEIGHT",\
        "interval": "MINUTE",\
        "intervalNum": 1,\
        "limit": 2400,\
        "count": 20\
      }\
    ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Futures-Account-Balance#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_convert.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert#__docusaurus_skipToContent_fallback)

On this page

# List All Convert Pairs

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert\#api-description "Direct link to API Description")

Query for all convertible token pairs and the tokens’ respective upper/lower limits

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/convert/exchangeInfo`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert\#request-weight "Direct link to Request Weight")

**20(IP)**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| fromAsset | STRING | EITHER OR BOTH | User spends coin |
| toAsset | STRING | EITHER OR BOTH | User receives coin |

> - User needs to supply either or both of the input parameter
> - If not defined for both fromAsset and toAsset, only partial token pairs will be returned
> - Asset BNFCR is only available to convert for MICA region users.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
    "fromAsset":"BTC",\
    "toAsset":"USDT",\
    "fromAssetMinAmount":"0.0004",\
    "fromAssetMaxAmount":"50",\
    "toAssetMinAmount":"20",\
    "toAssetMaxAmount":"2500000"\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_GRID_UPDATE.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-GRID-UPDATE#__docusaurus_skipToContent_fallback)

On this page

# Event: GRID\_UPDATE

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-GRID-UPDATE\#event-description "Direct link to Event Description")

`GRID_UPDATE` update when a sub order of a grid is filled or partially filled.
**Strategy Status**

- NEW
- WORKING
- CANCELLED
- EXPIRED

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-GRID-UPDATE\#event-name "Direct link to Event Name")

`GRID_UPDATE`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-GRID-UPDATE\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"e": "GRID_UPDATE", // Event Type
	"T": 1669262908216, // Transaction Time
	"E": 1669262908218, // Event Time
	"gu": {
			"si": 176057039, // Strategy ID
			"st": "GRID", // Strategy Type
			"ss": "WORKING", // Strategy Status
			"s": "BTCUSDT", // Symbol
			"r": "-0.00300716", // Realized PNL
			"up": "16720", // Unmatched Average Price
			"uq": "-0.001", // Unmatched Qty
			"uf": "-0.00300716", // Unmatched Fee
			"mp": "0.0", // Matched PNL
			"ut": 1669262908197 // Update Time
		   }
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-GRID-UPDATE#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-GRID-UPDATE#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-GRID-UPDATE#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_websocket_api.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api#__docusaurus_skipToContent_fallback)

On this page

# Futures Account Balance V2(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api\#api-description "Direct link to API Description")

Query account balance info

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api\#method "Direct link to Method")

`v2/account.balance`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "method": "v2/account.balance",
    "params": {
        "apiKey": "xTaDyrmvA9XT2oBHHjy39zyPzKCvMdtH3b9q4xadkAg2dNSJXQGCxzui26L823W2",
        "timestamp": 1702561978458,
        "signature": "208bb94a26f99aa122b1319490ca9cb2798fccc81d9b6449521a26268d53217a"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "status": 200,
    "result": [\
      {\
        "accountAlias": "SgsR",              // unique account code\
        "asset": "USDT",  	                // asset name\
        "balance": "122607.35137903",        // wallet balance\
        "crossWalletBalance": "23.72469206", // crossed wallet balance\
        "crossUnPnl": "0.00000000"           // unrealized profit of crossed positions\
        "availableBalance": "23.72469206",   // available balance\
        "maxWithdrawAmount": "23.72469206",  // maximum amount for transfer out\
        "marginAvailable": true,             // whether the asset can be used as margin in Multi-Assets mode\
        "updateTime": 1617939110373\
      }\
    ],
    "rateLimits": [\
      {\
        "rateLimitType": "REQUEST_WEIGHT",\
        "interval": "MINUTE",\
        "intervalNum": 1,\
        "limit": 2400,\
        "count": 20\
      }\
    ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Auto_Cancel_All_Open_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Auto-Cancel-All-Open-Orders#__docusaurus_skipToContent_fallback)

On this page

# Auto-Cancel All Open Orders (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Auto-Cancel-All-Open-Orders\#api-description "Direct link to API Description")

Cancel all open orders of the specified symbol at the end of the specified countdown.
The endpoint should be called repeatedly as heartbeats so that the existing countdown time can be canceled and replaced by a new one.

> - Example usage:
>
>
>   Call this endpoint at 30s intervals with an countdownTime of 120000 (120s).
>
>
>   If this endpoint is not called within 120 seconds, all your orders of the specified symbol will be automatically canceled.
>
>
>   If this endpoint is called with an countdownTime of 0, the countdown timer will be stopped.

The system will check all countdowns **approximately every 10 milliseconds**, so please note that sufficient redundancy should be considered when using this function. We do not recommend setting the countdown time to be too precise or too small.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Auto-Cancel-All-Open-Orders\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/countdownCancelAll`

**Weight:** **10**

**Parameters:**

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| countdownTime | LONG | YES | countdown time, 1000 for 1 second. 0 to cancel the timer |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Auto-Cancel-All-Open-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"symbol": "BTCUSDT",
	"countdownTime": "100000"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Auto-Cancel-All-Open-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Auto-Cancel-All-Open-Orders#http-request)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Auto-Cancel-All-Open-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Start_User_Data_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream#__docusaurus_skipToContent_fallback)

On this page

# Start User Data Stream (USER\_STREAM)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream\#api-description "Direct link to API Description")

Start a new user data stream. The stream will close after 60 minutes unless a keepalive is sent. If the account has an active `listenKey`, that `listenKey` will be returned and its validity will be extended for 60 minutes.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/listenKey`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream\#request-parameters "Direct link to Request Parameters")

None

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "listenKey": "pqia91ma19a5s61cv6a81va65sdf19v8a65a1a5s61cv6a81va65sdf19v8a65a1"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Toggle_BNB_Burn_On_Futures_Trade.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade#__docusaurus_skipToContent_fallback)

On this page

# Toggle BNB Burn On Futures Trade (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade\#api-description "Direct link to API Description")

Change user's BNB Fee Discount (Fee Discount On or Fee Discount Off ) on _**EVERY symbol**_

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/feeBurn`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| feeBurn | STRING | YES | "true": Fee Discount On; "false": Fee Discount Off |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"code": 200,
	"msg": "success"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Toggle-BNB-Burn-On-Futures-Trade#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_User_Data_Stream_Expired.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-User-Data-Stream-Expired#__docusaurus_skipToContent_fallback)

On this page

# Event: User Data Stream Expired

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-User-Data-Stream-Expired\#event-description "Direct link to Event Description")

When the `listenKey` used for the user data stream turns expired, this event will be pushed.

**Notice:**

> - This event is not related to the websocket disconnection.
> - This event will be received only when a valid `listenKey` in connection got expired.
> - No more user data event will be updated after this event received until a new valid `listenKey` used.

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-User-Data-Stream-Expired\#event-name "Direct link to Event Name")

`listenKeyExpired`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-User-Data-Stream-Expired\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "e": "listenKeyExpired",    // event type
    "E": "1736996475556",       // event time
    "listenKey":"WsCMN0a4KHUPTQuX6IUnqEZfB1inxmv1qR4kbf1LuEjur5VdbzqvyxqG9TSjVVxv"
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-User-Data-Stream-Expired#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-User-Data-Stream-Expired#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-User-Data-Stream-Expired#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Account_Information_V3.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3#__docusaurus_skipToContent_fallback)

On this page

# Account Information V3(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3\#api-description "Direct link to API Description")

Get current account information. User in single-asset/ multi-assets mode will see different value, see comments in response section for detail.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3\#http-request "Direct link to HTTP Request")

GET `/fapi/v3/account`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3\#response-example "Direct link to Response Example")

> single-asset mode

```codeBlockLines_aHhF
{
	"totalInitialMargin": "0.00000000",            // total initial margin required with current mark price (useless with isolated positions), only for USDT asset
	"totalMaintMargin": "0.00000000",  	           // total maintenance margin required, only for USDT asset
	"totalWalletBalance": "103.12345678",           // total wallet balance, only for USDT asset
	"totalUnrealizedProfit": "0.00000000",         // total unrealized profit, only for USDT asset
	"totalMarginBalance": "103.12345678",           // total margin balance, only for USDT asset
	"totalPositionInitialMargin": "0.00000000",    // initial margin required for positions with current mark price, only for USDT asset
	"totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price, only for USDT asset
	"totalCrossWalletBalance": "103.12345678",      // crossed wallet balance, only for USDT asset
	"totalCrossUnPnl": "0.00000000",	           // unrealized profit of crossed positions, only for USDT asset
	"availableBalance": "103.12345678",             // available balance, only for USDT asset
	"maxWithdrawAmount": "103.12345678"             // maximum amount for transfer out, only for USDT asset
	"assets": [ // For assets that are quote assets, USDT/USDC/BTC\
		{\
			"asset": "USDT",			            // asset name\
			"walletBalance": "23.72469206",         // wallet balance\
			"unrealizedProfit": "0.00000000",       // unrealized profit\
			"marginBalance": "23.72469206",         // margin balance\
			"maintMargin": "0.00000000",	        // maintenance margin required\
			"initialMargin": "0.00000000",          // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",  // initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000", // initial margin required for open orders with current mark price\
			"crossWalletBalance": "23.72469206",    // crossed wallet balance\
			"crossUnPnl": "0.00000000"              // unrealized profit of crossed positions\
			"availableBalance": "23.72469206",      // available balance\
			"maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
			"updateTime": 1625474304765             // last update time\
		},\
 		{\
			"asset": "USDC",			            // asset name\
			"walletBalance": "103.12345678",         // wallet balance\
			"unrealizedProfit": "0.00000000",       // unrealized profit\
			"marginBalance": "103.12345678",         // margin balance\
			"maintMargin": "0.00000000",	        // maintenance margin required\
			"initialMargin": "0.00000000",          // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",  // initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000", // initial margin required for open orders with current mark price\
			"crossWalletBalance": "103.12345678",    // crossed wallet balance\
			"crossUnPnl": "0.00000000"              // unrealized profit of crossed positions\
			"availableBalance": "126.72469206",      // available balance\
			"maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
			"updateTime": 1625474304765             // last update time\
		},\
    ],
	"positions": [  // positions of all symbols user had position/ open orders are returned\
		            // only "BOTH" positions will be returned with One-way mode\
		            // only "LONG" and "SHORT" positions will be returned with Hedge mode\
   	  {\
           "symbol": "BTCUSDT",\
           "positionSide": "BOTH",            // position side\
           "positionAmt": "1.000",\
           "unrealizedProfit": "0.00000000",  // unrealized profit\
           "isolatedMargin": "0.00000000",\
           "notional": "0",\
           "isolatedWallet": "0",\
           "initialMargin": "0",              // initial margin required with current mark price\
           "maintMargin": "0",                // maintenance margin required\
           "updateTime": 0\
  	  }\
	]
}

```

> OR multi-assets mode

```codeBlockLines_aHhF
{
	"totalInitialMargin": "0.00000000",            // the sum of USD value of all cross positions/open order initial margin
	"totalMaintMargin": "0.00000000",  	           // the sum of USD value of all cross positions maintenance margin
	"totalWalletBalance": "126.72469206",          // total wallet balance in USD
	"totalUnrealizedProfit": "0.00000000",         // total unrealized profit in USD
	"totalMarginBalance": "126.72469206",          // total margin balance in USD
	"totalPositionInitialMargin": "0.00000000",    // the sum of USD value of all cross positions initial margin
	"totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price in USD
	"totalCrossWalletBalance": "126.72469206",     // crossed wallet balance in USD
	"totalCrossUnPnl": "0.00000000",	           // unrealized profit of crossed positions in USD
	"availableBalance": "126.72469206",            // available balance in USD
	"maxWithdrawAmount": "126.72469206"            // maximum virtual amount for transfer out in USD
	"assets": [\
		{\
			"asset": "USDT",			         // asset name\
			"walletBalance": "23.72469206",      // wallet balance\
			"unrealizedProfit": "0.00000000",    // unrealized profit\
			"marginBalance": "23.72469206",      // margin balance\
			"maintMargin": "0.00000000",	     // maintenance margin required\
			"initialMargin": "0.00000000",       // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
			"crossWalletBalance": "23.72469206",      // crossed wallet balance\
			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
			"availableBalance": "126.72469206",       // available balance\
			"maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
			"updateTime": 1625474304765 // last update time\
		},\
		{\
			"asset": "BUSD",			// asset name\
			"walletBalance": "103.12345678",      // wallet balance\
			"unrealizedProfit": "0.00000000",    // unrealized profit\
			"marginBalance": "103.12345678",      // margin balance\
			"maintMargin": "0.00000000",	    // maintenance margin required\
			"initialMargin": "0.00000000",    // total initial margin required with current mark price\
			"positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
			"openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
			"crossWalletBalance": "103.12345678",      // crossed wallet balance\
			"crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
			"availableBalance": "126.72469206",       // available balance\
			"maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
			"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
			"updateTime": 1625474304765 // last update time\
		}\
	],
 	"positions": [  // positions of all symbols user had position are returned\
                    // only "BOTH" positions will be returned with One-way mode\
		            // only "LONG" and "SHORT" positions will be returned with Hedge mode\
   	  {\
           "symbol": "BTCUSDT",\
           "positionSide": "BOTH",            // position side\
           "positionAmt": "1.000",\
           "unrealizedProfit": "0.00000000",  // unrealized profit\
           "isolatedMargin": "0.00000000",\
           "notional": "0",\
           "isolatedWallet": "0",\
           "initialMargin": "0",              // initial margin required with current mark price\
           "maintMargin": "0",                // maintenance margin required\
           "updateTime": 0\
  	  }\
	]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V3#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Premium_Index_Kline_Data.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data#__docusaurus_skipToContent_fallback)

On this page

# Premium index Kline Data

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data\#api-description "Direct link to API Description")

Premium index kline bars of a symbol. Klines are uniquely identified by their open time.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/premiumIndexKlines`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data\#request-weight "Direct link to Request Weight")

based on parameter `LIMIT`

| LIMIT | weight |
| --- | --- |
| \[1,100) | 1 |\
| \[100, 500) | 2 |\
| \[500, 1000\] | 5 |\
| \> 1000 | 10 |\
\
## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data\#request-parameters "Direct link to Request Parameters")\
\
| Name | Type | Mandatory | Description |\
| --- | --- | --- | --- |\
| symbol | STRING | YES |  |\
| interval | ENUM | YES |  |\
| startTime | LONG | NO |  |\
| endTime | LONG | NO |  |\
| limit | INT | NO | Default 500; max 1500. |\
\
> - If startTime and endTime are not sent, the most recent klines are returned.\
\
## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data\#response-example "Direct link to Response Example")\
\
```codeBlockLines_aHhF\
[\
  [\
    1691603820000,          // Open time\
    "-0.00042931",          // Open\
    "-0.00023641",          // High\
    "-0.00059406",          // Low\
    "-0.00043659",          // Close\
    "0",                    // Ignore\
    1691603879999,          // Close time\
    "0",                    // Ignore\
    12,                     // Ignore\
    "0",                    // Ignore\
    "0",                    // Ignore\
    "0"                     // Ignore\
  ]\
]\
\
```\
\
- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data#api-description)\
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data#http-request)\
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data#request-weight)\
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data#request-parameters)\
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_STRATEGY_UPDATE.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-STRATEGY-UPDATE#__docusaurus_skipToContent_fallback)

On this page

# Event: STRATEGY\_UPDATE

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-STRATEGY-UPDATE\#event-description "Direct link to Event Description")

`STRATEGY_UPDATE` update when a strategy is created/cancelled/expired, ...etc.

**Strategy Status**

- NEW
- WORKING
- CANCELLED
- EXPIRED

**opCode**

- 8001: The strategy params have been updated
- 8002: User cancelled the strategy
- 8003: User manually placed or cancelled an order
- 8004: The stop limit of this order reached
- 8005: User position liquidated
- 8006: Max open order limit reached
- 8007: New grid order
- 8008: Margin not enough
- 8009: Price out of bounds
- 8010: Market is closed or paused
- 8011: Close position failed, unable to fill
- 8012: Exceeded the maximum allowable notional value at current leverage
- 8013: Grid expired due to incomplete KYC verification or access from a restricted jurisdiction
- 8014: Violated Futures Trading Quantitative Rules. Strategy stopped
- 8015: User position empty or liquidated

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-STRATEGY-UPDATE\#event-name "Direct link to Event Name")

`STRATEGY_UPDATE`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-STRATEGY-UPDATE\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"e": "STRATEGY_UPDATE", // Event Type
	"T": 1669261797627, // Transaction Time
	"E": 1669261797628, // Event Time
	"su": {
			"si": 176054594, // Strategy ID
			"st": "GRID", // Strategy Type
			"ss": "NEW", // Strategy Status
			"s": "BTCUSDT", // Symbol
			"ut": 1669261797627, // Update Time
			"c": 8007 // opCode
		}
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-STRATEGY-UPDATE#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-STRATEGY-UPDATE#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-STRATEGY-UPDATE#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Check_Server_Time.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time#__docusaurus_skipToContent_fallback)

On this page

# Check Server Time

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time\#api-description "Direct link to API Description")

Test connectivity to the Rest API and get the current server time.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/time`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time\#request-weight "Direct link to Request Weight")

1

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time\#request-parameters "Direct link to Request Parameters")

NONE

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "serverTime": 1499827319559
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Live_Subscribing_Unsubscribing_to_streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams#__docusaurus_skipToContent_fallback)

On this page

# Live Subscribing/Unsubscribing to streams

- The following data can be sent through the websocket instance in order to subscribe/unsubscribe from streams. Examples can be seen below.
- The `id` used in the JSON payloads is an unsigned INT used as an identifier to uniquely identify the messages going back and forth.

## Subscribe to a stream [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams\#subscribe-to-a-stream "Direct link to Subscribe to a stream")

> **Response**

```codeBlockLines_aHhF
{
  "result": null,
  "id": 1
}

```

- **Request**

{


"method": "SUBSCRIBE",


"params":


\[\
\
\
"btcusdt@aggTrade",\
\
\
"btcusdt@depth"\
\
\
\],


"id": 1


}


## Unsubscribe to a stream [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams\#unsubscribe-to-a-stream "Direct link to Unsubscribe to a stream")

> **Response**

```codeBlockLines_aHhF
{
  "result": null,
  "id": 312
}

```

- **Request**

{


"method": "UNSUBSCRIBE",


"params":


\[\
\
\
"btcusdt@depth"\
\
\
\],


"id": 312


}


## Listing Subscriptions [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams\#listing-subscriptions "Direct link to Listing Subscriptions")

> **Response**

```codeBlockLines_aHhF
{
  "result": [\
    "btcusdt@aggTrade"\
  ],
  "id": 3
}

```

- **Request**

{


"method": "LIST\_SUBSCRIPTIONS",


"id": 3


}


## Setting Properties [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams\#setting-properties "Direct link to Setting Properties")

Currently, the only property can be set is to set whether `combined` stream payloads are enabled are not.
The combined property is set to `false` when connecting using `/ws/` ("raw streams") and `true` when connecting using `/stream/`.

> **Response**

```codeBlockLines_aHhF
{
  "result": null,
  "id": 5
}

```

- **Request**

{


"method": "SET\_PROPERTY",


"params":


\[\
\
\
"combined",\
\
\
true\
\
\
\],


"id": 5


}


## Retrieving Properties [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams\#retrieving-properties "Direct link to Retrieving Properties")

> **Response**

```codeBlockLines_aHhF
{
  "result": true, // Indicates that combined is set to true.
  "id": 2
}

```

- **Request**

{


"method": "GET\_PROPERTY",


"params":


\[\
\
\
"combined"\
\
\
\],


"id": 2


}


### Error Messages [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams\#error-messages "Direct link to Error Messages")

| Error Message | Description |
| --- | --- |
| {"code": 0, "msg": "Unknown property"} | Parameter used in the `SET_PROPERTY` or `GET_PROPERTY` was invalid |
| {"code": 1, "msg": "Invalid value type: expected Boolean"} | Value should only be `true` or `false` |
| {"code": 2, "msg": "Invalid request: property name must be a string"} | Property name provided was invalid |
| {"code": 2, "msg": "Invalid request: request ID must be an unsigned integer"} | Parameter `id` had to be provided or the value provided in the `id` parameter is an unsupported type |
| {"code": 2, "msg": "Invalid request: unknown variant %s, expected one of `SUBSCRIBE`, `UNSUBSCRIBE`, `LIST_SUBSCRIPTIONS`, `SET_PROPERTY`, `GET_PROPERTY` at line 1 column 28"} | Possible typo in the provided method or provided method was neither of the expected values |
| {"code": 2, "msg": "Invalid request: too many parameters"} | Unnecessary parameters provided in the data |
| {"code": 2, "msg": "Invalid request: property name must be a string"} | Property name was not provided |
| {"code": 2, "msg": "Invalid request: missing field `method` at line 1 column 73"} | `method` was not provided in the data |
| {"code":3,"msg":"Invalid JSON: expected value at line %s column %s"} | JSON data sent has incorrect syntax. |

- [Subscribe to a stream](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams#subscribe-to-a-stream)
- [Unsubscribe to a stream](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams#unsubscribe-to-a-stream)
- [Listing Subscriptions](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams#listing-subscriptions)
- [Setting Properties](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams#setting-properties)
- [Retrieving Properties](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams#retrieving-properties)
  - [Error Messages](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams#error-messages)


[developers_binance_com_docs_derivatives_usds_margined_futures_general_info.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#__docusaurus_skipToContent_fallback)

On this page

# General Info

## testnet [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#testnet "Direct link to testnet")

- Most of the endpoints can be used in the testnet platform.
- The REST baseurl for **testnet** is " [https://testnet.binancefuture.com](https://testnet.binancefuture.com/)"
- The Websocket baseurl for **testnet** is "wss://fstream.binancefuture.com"

## SDK and Code Demonstration [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#sdk-and-code-demonstration "Direct link to SDK and Code Demonstration")

**Disclaimer:**

- The following SDKs are provided by partners and users, and are **not officially** produced. They are only used to help users become familiar with the API endpoint. Please use it with caution and expand R&D according to your own situation.
- Binance does not make any commitment to the safety and performance of the SDKs, nor will be liable for the risks or even losses caused by using the SDKs.

### Python3 [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#python3 "Direct link to Python3")

**SDK:**
To get the provided SDK for Binance Futures Connector,

please visit [https://github.com/binance/binance-futures-connector-python](https://github.com/binance/binance-futures-connector-python),

or use the command below:

`pip install binance-futures-connector`

### Java [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#java "Direct link to Java")

To get the provided SDK for Binance Futures,

please visit [https://github.com/binance/binance-futures-connector-java](https://github.com/binance/binance-futures-connector-java),

or use the command below:

`git clone https://github.com/binance/binance-futures-connector-java.git`

## General API Information [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#general-api-information "Direct link to General API Information")

- Some endpoints will require an API Key. Please refer to [this page](https://www.binance.com/en/support/articles/360002502072)
- The base endpoint is: **[https://fapi.binance.com](https://fapi.binance.com/)**
- All endpoints return either a JSON object or array.
- Data is returned in **ascending** order. Oldest first, newest last.
- All time and timestamp related fields are in milliseconds.
- All data types adopt definition in JAVA.

### HTTP Return Codes [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#http-return-codes "Direct link to HTTP Return Codes")

- HTTP `4XX` return codes are used for for malformed requests;
the issue is on the sender's side.
- HTTP `403` return code is used when the WAF Limit (Web Application Firewall) has been violated.
- HTTP `408` return code is used when a timeout has occurred while waiting for a response from the backend server.
- HTTP `429` return code is used when breaking a request rate limit.
- HTTP `418` return code is used when an IP has been auto-banned for continuing to send requests after receiving `429` codes.
- HTTP `5XX` return codes are used for internal errors; the issue is on
Binance's side.

1. If there is an error message **"Request occur unknown error."**, please retry later.
- HTTP `503` return code is used when:

1. If there is an error message **"Unknown error, please check your request or try again later."** returned in the response, the API successfully sent the request but not get a response within the timeout period.


     It is important to **NOT** treat this as a failure operation; the execution status is **UNKNOWN** and could have been a success;
2. If there is an error message **"Service Unavailable."** returned in the response, it means this is a failure API operation and the service might be unavailable at the moment, you need to retry later.
3. If there is an error message **"Internal error; unable to process your request. Please try again."** returned in the response, it means this is a failure API operation and you can resend your request if you need.

### Error Codes and Messages [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#error-codes-and-messages "Direct link to Error Codes and Messages")

- Any endpoint can return an ERROR

> **_The error payload is as follows:_**

```codeBlockLines_aHhF
{
  "code": -1121,
  "msg": "Invalid symbol."
}

```

- Specific error codes and messages defined in [Error Codes](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#error-codes).

### General Information on Endpoints [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#general-information-on-endpoints "Direct link to General Information on Endpoints")

- For `GET` endpoints, parameters must be sent as a `query string`.
- For `POST`, `PUT`, and `DELETE` endpoints, the parameters may be sent as a
`query string` or in the `request body` with content type
`application/x-www-form-urlencoded`. You may mix parameters between both the
`query string` and `request body` if you wish to do so.
- Parameters may be sent in any order.
- If a parameter sent in both the `query string` and `request body`, the
`query string` parameter will be used.

## LIMITS [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#limits "Direct link to LIMITS")

- The `/fapi/v1/exchangeInfo` `rateLimits` array contains objects related to the exchange's `RAW_REQUEST`, `REQUEST_WEIGHT`, and `ORDER` rate limits. These are further defined in the `ENUM definitions` section under `Rate limiters (rateLimitType)`.
- A `429` will be returned when either rate limit is violated.

### IP Limits [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#ip-limits "Direct link to IP Limits")

- Every request will contain `X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)` in the response headers which has the current used weight for the IP for all request rate limiters defined.
- Each route has a `weight` which determines for the number of requests each endpoint counts for. Heavier endpoints and endpoints that do operations on multiple symbols will have a heavier `weight`.
- When a 429 is received, it's your obligation as an API to back off and not spam the API.
- **Repeatedly violating rate limits and/or failing to back off after receiving 429s will result in an automated IP ban (HTTP status 418).**
- IP bans are tracked and **scale in duration** for repeat offenders, **from 2 minutes to 3 days**.
- **The limits on the API are based on the IPs, not the API keys.**

### Order Rate Limits [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#order-rate-limits "Direct link to Order Rate Limits")

- Every order response will contain a `X-MBX-ORDER-COUNT-(intervalNum)(intervalLetter)` header which has the current order count for the account for all order rate limiters defined.
- Rejected/unsuccessful orders are not guaranteed to have `X-MBX-ORDER-COUNT-**` headers in the response.
- **The order rate limit is counted against each account**.

## Endpoint Security Type [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#endpoint-security-type "Direct link to Endpoint Security Type")

- Each endpoint has a security type that determines the how you will
interact with it.
- API-keys are passed into the Rest API via the `X-MBX-APIKEY`
header.
- API-keys and secret-keys **are case sensitive**.
- API-keys can be configured to only access certain types of secure endpoints.
For example, one API-key could be used for TRADE only, while another API-key
can access everything except for TRADE routes.
- By default, API-keys can access all secure routes.

| Security Type | Description |
| --- | --- |
| NONE | Endpoint can be accessed freely. |
| TRADE | Endpoint requires sending a valid API-Key and signature. |
| USER\_DATA | Endpoint requires sending a valid API-Key and signature. |
| USER\_STREAM | Endpoint requires sending a valid API-Key. |
| MARKET\_DATA | Endpoint requires sending a valid API-Key. |

- `TRADE` and `USER_DATA` endpoints are `SIGNED` endpoints.

## SIGNED (TRADE and USER\_DATA) Endpoint Security [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#signed-trade-and-user_data-endpoint-security "Direct link to SIGNED (TRADE and USER_DATA) Endpoint Security")

- `SIGNED` endpoints require an additional parameter, `signature`, to be
sent in the `query string` or `request body`.
- Endpoints use `HMAC SHA256` signatures. The `HMAC SHA256 signature` is a keyed `HMAC SHA256` operation.
Use your `secretKey` as the key and `totalParams` as the value for the HMAC operation.
- The `signature` is **not case sensitive**.
- Please make sure the `signature` is the end part of your `query string` or `request body`.
- `totalParams` is defined as the `query string` concatenated with the
`request body`.

### Timing Security [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#timing-security "Direct link to Timing Security")

- A `SIGNED` endpoint also requires a parameter, `timestamp`, to be sent which
should be the millisecond timestamp of when the request was created and sent.
- An additional parameter, `recvWindow`, may be sent to specify the number of
milliseconds after `timestamp` the request is valid for. If `recvWindow`
is not sent, **it defaults to 5000**.

> The logic is as follows:

```codeBlockLines_aHhF
if (timestamp < serverTime + 1000 && serverTime - timestamp <= recvWindow) {
  // process request
} else {
  // reject request
}

```

**Serious trading is about timing.** Networks can be unstable and unreliable,
which can lead to requests taking varying amounts of time to reach the
servers. With `recvWindow`, you can specify that the request must be
processed within a certain number of milliseconds or be rejected by the
server.

### SIGNED Endpoint Examples for POST /fapi/v1/order - HMAC Keys [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#signed-endpoint-examples-for-post-fapiv1order---hmac-keys "Direct link to SIGNED Endpoint Examples for POST /fapi/v1/order - HMAC Keys")

Here is a step-by-step example of how to send a vaild signed payload from the
Linux command line using `echo`, `openssl`, and `curl`.

| Key | Value |
| --- | --- |
| apiKey | dbefbc809e3e83c283a984c3a1459732ea7db1360ca80c5c2c8867408d28cc83 |
| secretKey | 2b5eb11e18796d12d88f13dc27dbbd02c2cc51ff7059765ed9821957d82bb4d9 |

| Parameter | Value |
| --- | --- |
| symbol | BTCUSDT |
| side | BUY |
| type | LIMIT |
| timeInForce | GTC |
| quantity | 1 |
| price | 9000 |
| recvWindow | 5000 |
| timestamp | 1591702613943 |

#### Example 1: As a query string [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#example-1-as-a-query-string "Direct link to Example 1: As a query string")

> **Example 1**

> **HMAC SHA256 signature:**

```codeBlockLines_aHhF
    $ echo -n "symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=1&price=9000&timeInForce=GTC&recvWindow=5000&timestamp=1591702613943" | openssl dgst -sha256 -hmac "2b5eb11e18796d12d88f13dc27dbbd02c2cc51ff7059765ed9821957d82bb4d9"
    (stdin)= 3c661234138461fcc7a7d8746c6558c9842d4e10870d2ecbedf7777cad694af9

```

> **curl command:**

```codeBlockLines_aHhF
    (HMAC SHA256)
    $ curl -H "X-MBX-APIKEY: dbefbc809e3e83c283a984c3a1459732ea7db1360ca80c5c2c8867408d28cc83" -X POST 'https://fapi/binance.com/fapi/v1/order?symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=1&price=9000&timeInForce=GTC&recvWindow=5000&timestamp=1591702613943&signature= 3c661234138461fcc7a7d8746c6558c9842d4e10870d2ecbedf7777cad694af9'

```

- **queryString:**

symbol=BTCUSDT


&side=BUY


&type=LIMIT


&timeInForce=GTC


&quantity=1


&price=9000


&recvWindow=5000


&timestamp=1591702613943


#### Example 2: As a request body [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#example-2-as-a-request-body "Direct link to Example 2: As a request body")

> **Example 2**

> **HMAC SHA256 signature:**

```codeBlockLines_aHhF
    $ echo -n "symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=1&price=9000&timeInForce=GTC&recvWindow=5000&timestamp=1591702613943" | openssl dgst -sha256 -hmac "2b5eb11e18796d12d88f13dc27dbbd02c2cc51ff7059765ed9821957d82bb4d9"
    (stdin)= 3c661234138461fcc7a7d8746c6558c9842d4e10870d2ecbedf7777cad694af9

```

> **curl command:**

```codeBlockLines_aHhF
    (HMAC SHA256)
    $ curl -H "X-MBX-APIKEY: dbefbc809e3e83c283a984c3a1459732ea7db1360ca80c5c2c8867408d28cc83" -X POST 'https://fapi/binance.com/fapi/v1/order' -d 'symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=1&price=9000&timeInForce=GTC&recvWindow=5000&timestamp=1591702613943&signature= 3c661234138461fcc7a7d8746c6558c9842d4e10870d2ecbedf7777cad694af9'

```

- **requestBody:**

symbol=BTCUSDT


&side=BUY


&type=LIMIT


&timeInForce=GTC


&quantity=1


&price=9000


&recvWindow=5000


&timestamp=1591702613943


#### Example 3: Mixed query string and request body [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#example-3-mixed-query-string-and-request-body "Direct link to Example 3: Mixed query string and request body")

> **Example 3**

> **HMAC SHA256 signature:**

```codeBlockLines_aHhF
    $ echo -n "symbol=BTCUSDT&side=BUY&type=LIMIT&timeInForce=GTCquantity=1&price=9000&recvWindow=5000&timestamp= 1591702613943" | openssl dgst -sha256 -hmac "2b5eb11e18796d12d88f13dc27dbbd02c2cc51ff7059765ed9821957d82bb4d9"
    (stdin)= f9d0ae5e813ef6ccf15c2b5a434047a0181cb5a342b903b367ca6d27a66e36f2

```

> **curl command:**

```codeBlockLines_aHhF
    (HMAC SHA256)
    $ curl -H "X-MBX-APIKEY: dbefbc809e3e83c283a984c3a1459732ea7db1360ca80c5c2c8867408d28cc83" -X POST 'https://fapi.binance.com/fapi/v1/order?symbol=BTCUSDT&side=BUY&type=LIMIT&timeInForce=GTC' -d 'quantity=1&price=9000&recvWindow=5000&timestamp=1591702613943&signature=f9d0ae5e813ef6ccf15c2b5a434047a0181cb5a342b903b367ca6d27a66e36f2'

```

- **queryString:** symbol=BTCUSDT&side=BUY&type=LIMIT&timeInForce=GTC
- **requestBody:** quantity=1&price=9000&recvWindow=5000&timestamp= 1591702613943

Note that the signature is different in example 3.

There is no & between "GTC" and "quantity=1".

### SIGNED Endpoint Examples for POST /fapi/v1/order - RSA Keys [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#signed-endpoint-examples-for-post-fapiv1order---rsa-keys "Direct link to SIGNED Endpoint Examples for POST /fapi/v1/order - RSA Keys")

- This will be a step by step process how to create the signature payload to send a valid signed payload.
- We support `PKCS#8` currently.
- To get your API key, you need to upload your RSA Public Key to your account and a corresponding API key will be provided for you.

For this example, the private key will be referenced as `test-prv-key.pem`

| Key | Value |
| --- | --- |
| apiKey | vE3BDAL1gP1UaexugRLtteaAHg3UO8Nza20uexEuW1Kh3tVwQfFHdAiyjjY428o2 |

| Parameter | Value |
| --- | --- |
| symbol | BTCUSDT |
| side | SELL |
| type | MARKET |
| quantity | 1.23 |
| recvWindow | 9999999 |
| timestamp | 1671090801999 |

> **Signature payload (with the listed parameters):**

```codeBlockLines_aHhF
timestamp=1671090801999&recvWindow=9999999&symbol=BTCUSDT&side=SELL&type=MARKET&quantity=1.23

```

**Step 1: Construct the payload**

Arrange the list of parameters into a string. Separate each parameter with a `&`.

**Step 2: Compute the signature:**

2.1 - Encode signature payload as ASCII data.

> **Step 2.2**

```codeBlockLines_aHhF
 $ echo -n 'timestamp=1671090801999&recvWindow=9999999&symbol=BTCUSDT&side=SELL&type=MARKET&quantity=1.23' | openssl dgst -keyform PEM -sha256 -sign ./test-prv-key.pem

```

2.2 - Sign payload using RSASSA-PKCS1-v1\_5 algorithm with SHA-256 hash function.

> **Step 2.3**

```codeBlockLines_aHhF
$ echo -n 'timestamp=1671090801999&recvWindow=9999999&symbol=BTCUSDT&side=SELL&type=MARKET&quantity=1.23' | openssl dgst -keyform PEM -sha256 -sign ./test-prv-key.pem | openssl enc -base64
aap36wD5loVXizxvvPI3wz9Cjqwmb3KVbxoym0XeWG1jZq8umqrnSk8H8dkLQeySjgVY91Ufs%2BBGCW%2B4sZjQEpgAfjM76riNxjlD3coGGEsPsT2lG39R%2F1q72zpDs8pYcQ4A692NgHO1zXcgScTGgdkjp%2Brp2bcddKjyz5XBrBM%3D

```

2.3 - Encode output as base64 string.

> **Step 2.4**

```codeBlockLines_aHhF
$  echo -n 'timestamp=1671090801999&recvWindow=9999999&symbol=BTCUSDT&side=SELL&type=MARKET&quantity=1.23' | openssl dgst -keyform PEM -sha256 -sign ./test-prv-key.pem | openssl enc -base64 | tr -d '\n'
aap36wD5loVXizxvvPI3wz9Cjqwmb3KVbxoym0XeWG1jZq8umqrnSk8H8dkLQeySjgVY91Ufs%2BBGCW%2B4sZjQEpgAfjM76riNxjlD3coGGEsPsT2lG39R%2F1q72zpDs8pYcQ4A692NgHO1zXcgScTGgdkjp%2Brp2bcddKjyz5XBrBM%3D

```

2.4 - Delete any newlines in the signature.

> **Step 2.5**

```codeBlockLines_aHhF
aap36wD5loVXizxvvPI3wz9Cjqwmb3KVbxoym0XeWG1jZq8umqrnSk8H8dkLQeySjgVY91Ufs%2BBGCW%2B4sZjQEpgAfjM76riNxjlD3coGGEsPsT2lG39R%2F1q72zpDs8pYcQ4A692NgHO1zXcgScTGgdkjp%2Brp2bcddKjyz5XBrBM%3D

```

2.5 - Since the signature may contain `/` and `=`, this could cause issues with sending the request. So the signature has to be URL encoded.

> **Step 2.6**

```codeBlockLines_aHhF
 curl -H "X-MBX-APIKEY: vE3BDAL1gP1UaexugRLtteaAHg3UO8Nza20uexEuW1Kh3tVwQfFHdAiyjjY428o2" -X POST 'https://fapi.binance.com/fapi/v1/order?timestamp=1671090801999&recvWindow=9999999&symbol=BTCUSDT&side=SELL&type=MARKET&quantity=1.23&signature=aap36wD5loVXizxvvPI3wz9Cjqwmb3KVbxoym0XeWG1jZq8umqrnSk8H8dkLQeySjgVY91Ufs%2BBGCW%2B4sZjQEpgAfjM76riNxjlD3coGGEsPsT2lG39R%2F1q72zpDs8pYcQ4A692NgHO1zXcgScTGgdkjp%2Brp2bcddKjyz5XBrBM%3D'

```

2.6 - curl command

> **Bash script**

```codeBlockLines_aHhF
#!/usr/bin/env bash

# Set up authentication:
apiKey="vE3BDAL1gP1UaexugRLtteaAHg3UO8Nza20uexEuW1Kh3tVwQfFHdAiyjjY428o2"   ### REPLACE THIS WITH YOUR API KEY

# Set up the request:
apiMethod="POST"
apiCall="v1/order"
apiParams="timestamp=1671090801999&recvWindow=9999999&symbol=BTCUSDT&side=SELL&type=MARKET&quantity=1.23"
function rawurlencode {
    local value="$1"
    local len=${#value}
    local encoded=""
    local pos c o
    for (( pos=0 ; pos<len ; pos++ ))
    do
        c=${value:$pos:1}
        case "$c" in
            [-_.~a-zA-Z0-9] ) o="${c}" ;;
            * )   printf -v o '%%%02x' "'$c"
        esac
        encoded+="$o"
    done
    echo "$encoded"
}
ts=$(date +%s000)
paramsWithTs="$apiParams&timestamp=$ts"
rawSignature=$(echo -n "$paramsWithTs" \
               | openssl dgst -keyform PEM -sha256 -sign ./test-prv-key.pem \  ### THIS IS YOUR PRIVATE KEY. DO NOT SHARE THIS FILE WITH ANYONE.
               | openssl enc -base64 \
               | tr -d '\n')
signature=$(rawurlencode "$rawSignature")
curl -H "X-MBX-APIKEY: $apiKey" -X $apiMethod \
    "https://fapi.binance.com/fapi/$apiCall?$paramsWithTs&signature=$signature"

```

A sample Bash script containing similar steps is available in the right side.

* * *

## Postman Collections [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info\#postman-collections "Direct link to Postman Collections")

There is now a Postman collection containing the API endpoints for quick and easy use.

For more information please refer to this page: [Binance API Postman](https://github.com/binance-exchange/binance-api-postman)

- [testnet](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#testnet)
- [SDK and Code Demonstration](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#sdk-and-code-demonstration)
  - [Python3](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#python3)
  - [Java](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#java)
- [General API Information](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#general-api-information)
  - [HTTP Return Codes](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#http-return-codes)
  - [Error Codes and Messages](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#error-codes-and-messages)
  - [General Information on Endpoints](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#general-information-on-endpoints)
- [LIMITS](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#limits)
  - [IP Limits](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#ip-limits)
  - [Order Rate Limits](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#order-rate-limits)
- [Endpoint Security Type](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#endpoint-security-type)
- [SIGNED (TRADE and USER\_DATA) Endpoint Security](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#signed-trade-and-user_data-endpoint-security)
  - [Timing Security](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#timing-security)
  - [SIGNED Endpoint Examples for POST /fapi/v1/order - HMAC Keys](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#signed-endpoint-examples-for-post-fapiv1order---hmac-keys)
  - [SIGNED Endpoint Examples for POST /fapi/v1/order - RSA Keys](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#signed-endpoint-examples-for-post-fapiv1order---rsa-keys)
- [Postman Collections](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info#postman-collections)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_Account_Configuration_Update_previous_Leverage_Update.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Account-Configuration-Update-previous-Leverage-Update#__docusaurus_skipToContent_fallback)

On this page

# Event: Account Configuration Update previous Leverage Update

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Account-Configuration-Update-previous-Leverage-Update\#event-description "Direct link to Event Description")

When the account configuration is changed, the event type will be pushed as `ACCOUNT_CONFIG_UPDATE`
When the leverage of a trade pair changes, the payload will contain the object `ac` to represent the account configuration of the trade pair, where `s` represents the specific trade pair and `l` represents the leverage
When the user Multi-Assets margin mode changes the payload will contain the object `ai` representing the user account configuration, where `j` represents the user Multi-Assets margin mode

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Account-Configuration-Update-previous-Leverage-Update\#event-name "Direct link to Event Name")

`ACCOUNT_CONFIG_UPDATE`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Account-Configuration-Update-previous-Leverage-Update\#response-example "Direct link to Response Example")

> **Payload:**

```codeBlockLines_aHhF
{
    "e":"ACCOUNT_CONFIG_UPDATE",       // Event Type
    "E":1611646737479,		           // Event Time
    "T":1611646737476,		           // Transaction Time
    "ac":{
    "s":"BTCUSDT",					   // symbol
    "l":25						       // leverage

    }
}


```

> **Or**

```codeBlockLines_aHhF
{
    "e":"ACCOUNT_CONFIG_UPDATE",       // Event Type
    "E":1611646737479,		           // Event Time
    "T":1611646737476,		           // Transaction Time
    "ai":{							   // User's Account Configuration
    "j":true						   // Multi-Assets Mode
    }
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Account-Configuration-Update-previous-Leverage-Update#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Account-Configuration-Update-previous-Leverage-Update#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Account-Configuration-Update-previous-Leverage-Update#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Get_Funding_Rate_History.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History#__docusaurus_skipToContent_fallback)

On this page

# Get Funding Rate History

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History\#api-description "Direct link to API Description")

Get Funding Rate History

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/fundingRate`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History\#request-weight "Direct link to Request Weight")

share 500/5min/IP rate limit with GET /fapi/v1/fundingInfo

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| startTime | LONG | NO | Timestamp in ms to get funding rate from INCLUSIVE. |
| endTime | LONG | NO | Timestamp in ms to get funding rate until INCLUSIVE. |
| limit | INT | NO | Default 100; max 1000 |

> - If `startTime` and `endTime` are not sent, the most recent `limit` datas are returned.
> - If the number of data between `startTime` and `endTime` is larger than `limit`, return as `startTime` \+ `limit`.
> - In ascending order.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
    	"symbol": "BTCUSDT",\
    	"fundingRate": "-0.03750000",\
    	"fundingTime": 1570608000000,\
		"markPrice": "34287.54619963"   // mark price associated with a particular funding fee charge\
	},\
	{\
   		"symbol": "BTCUSDT",\
    	"fundingRate": "0.00010000",\
    	"fundingTime": 1570636800000,\
		"markPrice": "34287.54619963"\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Get_Position_Margin_Change_History.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History#__docusaurus_skipToContent_fallback)

On this page

# Get Position Margin Change History (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History\#api-description "Direct link to API Description")

Get Position Margin Change History

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/positionMargin/history`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| type | INT | NO | 1: Add position margin，2: Reduce position margin |
| startTime | LONG | NO |  |
| endTime | LONG | NO | Default current time if not pass |
| limit | INT | NO | Default: 500 |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Support querying future histories that are not older than 30 days
> - The time between `startTime` and `endTime` can't be more than 30 days

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
	  	"symbol": "BTCUSDT",\
	  	"type": 1,\
		"deltaType": "USER_ADJUST",\
		"amount": "23.36332311",\
	  	"asset": "USDT",\
	  	"time": 1578047897183,\
	  	"positionSide": "BOTH"\
	},\
	{\
		"symbol": "BTCUSDT",\
	  	"type": 1,\
		"deltaType": "USER_ADJUST",\
		"amount": "100",\
	  	"asset": "USDT",\
	  	"time": 1578047900425,\
	  	"positionSide": "LONG"\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Get-Position-Margin-Change-History#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Keepalive_User_Data_Stream_Wsp.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp#__docusaurus_skipToContent_fallback)

On this page

# Keepalive User Data Stream (USER\_STREAM)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp\#api-description "Direct link to API Description")

Keepalive a user data stream to prevent a time out. User data streams will close after 60 minutes. It's recommended to send a ping about every 60 minutes.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp\#method "Direct link to Method")

`userDataStream.ping`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp\#request "Direct link to Request")

```codeBlockLines_aHhF
{
  "id": "815d5fce-0880-4287-a567-80badf004c74",
  "method": "userDataStream.ping",
  "params": {
    "apiKey": "vmPUZE6mv9SD5VNHk9HlWFsOr9aLE2zvsw0MuIgwCIPy8atIco14y7Ju91duEh8A"
   }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp\#request-parameters "Direct link to Request Parameters")

None

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "id": "815d5fce-0880-4287-a567-80badf004c74",
  "status": 200,
  "result": {
    "listenKey": "3HBntNTepshgEdjIwSUIBgB9keLyOCg5qv3n6bYAtktG8ejcaW5HXz9Vx1JgIieg"
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 2\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream-Wsp#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Position_Information_V3.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3#__docusaurus_skipToContent_fallback)

On this page

# Position Information V3 (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3\#api-description "Direct link to API Description")

Get current position information(only symbol that has position or open orders will be returned).

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3\#http-request "Direct link to HTTP Request")

GET `/fapi/v3/positionRisk`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

**Note**

> Please use with user data stream `ACCOUNT_UPDATE` to meet your timeliness and accuracy needs.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3\#response-example "Direct link to Response Example")

> For One-way position mode:

```codeBlockLines_aHhF
[\
  {\
        "symbol": "ADAUSDT",\
        "positionSide": "BOTH",               // position side\
        "positionAmt": "30",\
        "entryPrice": "0.385",\
        "breakEvenPrice": "0.385077",\
        "markPrice": "0.41047590",\
        "unRealizedProfit": "0.76427700",     // unrealized profit\
        "liquidationPrice": "0",\
        "isolatedMargin": "0",\
        "notional": "12.31427700",\
        "marginAsset": "USDT",\
        "isolatedWallet": "0",\
        "initialMargin": "0.61571385",        // initial margin required with current mark price\
        "maintMargin": "0.08004280",          // maintenance margin required\
        "positionInitialMargin": "0.61571385",// initial margin required for positions with current mark price\
        "openOrderInitialMargin": "0",        // initial margin required for open orders with current mark price\
        "adl": 2,\
        "bidNotional": "0",                   // bids notional, ignore\
        "askNotional": "0",                   // ask notional, ignore\
        "updateTime": 1720736417660\
  }\
]

```

> For Hedge position mode:

```codeBlockLines_aHhF
[\
  {\
        "symbol": "ADAUSDT",\
        "positionSide": "LONG",               // position side\
        "positionAmt": "30",\
        "entryPrice": "0.385",\
        "breakEvenPrice": "0.385077",\
        "markPrice": "0.41047590",\
        "unRealizedProfit": "0.76427700",     // unrealized profit\
        "liquidationPrice": "0",\
        "isolatedMargin": "0",\
        "notional": "12.31427700",\
        "marginAsset": "USDT",\
        "isolatedWallet": "0",\
        "initialMargin": "0.61571385",        // initial margin required with current mark price\
        "maintMargin": "0.08004280",          // maintenance margin required\
        "positionInitialMargin": "0.61571385",// initial margin required for positions with current mark price\
        "openOrderInitialMargin": "0",        // initial margin required for open orders with current mark price\
        "adl": 2,\
        "bidNotional": "0",                   // bids notional, ignore\
        "askNotional": "0",                   // ask notional, ignore\
        "updateTime": 1720736417660\
  },\
  {\
        "symbol": "COMPUSDT",\
        "positionSide": "SHORT",\
        "positionAmt": "-1.000",\
        "entryPrice": "70.92841",\
        "breakEvenPrice": "70.900038636",\
        "markPrice": "49.72023376",\
        "unRealizedProfit": "21.20817624",\
        "liquidationPrice": "2260.56757210",\
        "isolatedMargin": "0",\
        "notional": "-49.72023376",\
        "marginAsset": "USDT",\
        "isolatedWallet": "0",\
        "initialMargin": "2.48601168",\
        "maintMargin": "0.49720233",\
        "positionInitialMargin": "2.48601168",\
        "openOrderInitialMargin": "0",\
        "adl": 2,\
        "bidNotional": "0",\
        "askNotional": "0",\
        "updateTime": 1708943511656\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Index_Price_Kline_Candlestick_Data.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data#__docusaurus_skipToContent_fallback)

On this page

# Index Price Kline/Candlestick Data

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data\#api-description "Direct link to API Description")

Kline/candlestick bars for the index price of a pair.
Klines are uniquely identified by their open time.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/indexPriceKlines`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data\#request-weight "Direct link to Request Weight")

based on parameter `LIMIT`

| LIMIT | weight |
| --- | --- |
| \[1,100) | 1 |\
| \[100, 500) | 2 |\
| \[500, 1000\] | 5 |\
| \> 1000 | 10 |\
\
## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data\#request-parameters "Direct link to Request Parameters")\
\
| Name | Type | Mandatory | Description |\
| --- | --- | --- | --- |\
| pair | STRING | YES |  |\
| interval | ENUM | YES |  |\
| startTime | LONG | NO |  |\
| endTime | LONG | NO |  |\
| limit | INT | NO | Default 500; max 1500. |\
\
- If startTime and endTime are not sent, the most recent klines are returned.\
\
## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data\#response-example "Direct link to Response Example")\
\
```codeBlockLines_aHhF\
[\
  [\
    1591256400000,      	// Open time\
    "9653.69440000",    	// Open\
    "9653.69640000",     	// High\
    "9651.38600000",     	// Low\
    "9651.55200000",     	// Close (or latest price)\
    "0	", 					// Ignore\
    1591256459999,      	// Close time\
    "0",    				// Ignore\
    60,                		// Ignore\
    "0",    				// Ignore\
    "0",      				// Ignore\
    "0" 					// Ignore\
  ]\
]\
\
```\
\
- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data#api-description)\
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data#http-request)\
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data#request-weight)\
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data#request-parameters)\
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_convert_Accept_Quote.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote#__docusaurus_skipToContent_fallback)

On this page

# Accept the offered quote (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote\#api-description "Direct link to API Description")

Accept the offered quote by quote ID.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/convert/acceptQuote`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote\#request-weight "Direct link to Request Weight")

**200(IP)**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| quoteId | STRING | YES |  |
| recvWindow | LONG | NO | The value cannot be greater than 60000 |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "orderId":"933256278426274426",
  "createTime":1623381330472,
  "orderStatus":"PROCESS" //PROCESS/ACCEPT_SUCCESS/SUCCESS/FAIL
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Accept-Quote#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Individual_Symbol_Ticker_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams#__docusaurus_skipToContent_fallback)

On this page

# Individual Symbol Ticker Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams\#stream-description "Direct link to Stream Description")

24hr rolling window ticker statistics for a single symbol. These are NOT the statistics of the UTC day, but a 24hr rolling window from requestTime to 24hrs before.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@ticker`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams\#update-speed "Direct link to Update Speed")

**2000ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e": "24hrTicker",  // Event type
  "E": 123456789,     // Event time
  "s": "BTCUSDT",     // Symbol
  "p": "0.0015",      // Price change
  "P": "250.00",      // Price change percent
  "w": "0.0018",      // Weighted average price
  "c": "0.0025",      // Last price
  "Q": "10",          // Last quantity
  "o": "0.0010",      // Open price
  "h": "0.0025",      // High price
  "l": "0.0010",      // Low price
  "v": "10000",       // Total traded base asset volume
  "q": "18",          // Total traded quote asset volume
  "O": 0,             // Statistics open time
  "C": 86400000,      // Statistics close time
  "F": 0,             // First trade ID
  "L": 18150,         // Last trade Id
  "n": 18151          // Total number of trades
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Individual-Symbol-Ticker-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Top_Trader_Long_Short_Ratio.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio#__docusaurus_skipToContent_fallback)

On this page

# Top Trader Long/Short Ratio (Positions)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio\#api-description "Direct link to API Description")

The proportion of net long and net short positions to total open positions of the top 20% users with the highest margin balance.
Long Position % = Long positions of top traders / Total open positions of top traders
Short Position % = Short positions of top traders / Total open positions of top traders
Long/Short Ratio (Positions) = Long Position % / Short Position %

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio\#http-request "Direct link to HTTP Request")

GET `/futures/data/topLongShortPositionRatio`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio\#request-weight "Direct link to Request Weight")

**0**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| period | ENUM | YES | "5m","15m","30m","1h","2h","4h","6h","12h","1d" |
| limit | LONG | NO | default 30, max 500 |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |

> - If startTime and endTime are not sent, the most recent data is returned.
> - Only the data of the latest 30 days is available.
> - IP rate limit 1000 requests/5min

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
    {\
         "symbol":"BTCUSDT",\
	      "longShortRatio":"1.4342",// long/short position ratio of top traders\
	      "longAccount": "0.5891", // long positions ratio of top traders\
	      "shortAccount":"0.4108", // short positions ratio of top traders\
	      "timestamp":"1583139600000"\
\
     },\
\
     {\
\
         "symbol":"BTCUSDT",\
	      "longShortRatio":"1.4337",\
	      "longAccount": "0.3583",\
	      "shortAccount":"0.6417",\
	      "timestamp":"1583139900000"\
\
        },\
\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_websocket_api_Position_Information.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information#__docusaurus_skipToContent_fallback)

On this page

# Position Information (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information\#api-description "Direct link to API Description")

Get current position information.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information\#method "Direct link to Method")

`account.position`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information\#request "Direct link to Request")

```codeBlockLines_aHhF
{
   	"id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "method": "account.position",
    "params": {
        "apiKey": "xTaDyrmvA9XT2oBHHjy39zyPzKCvMdtH3b9q4xadkAg2dNSJXQGCxzui26L823W2",
        "symbol": "BTCUSDT",
        "timestamp": 1702920680303,
        "signature": "31ab02a51a3989b66c29d40fcdf78216978a60afc6d8dc1c753ae49fa3164a2a"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

**Note**

> - Please use with user data stream `ACCOUNT_UPDATE` to meet your timeliness and accuracy needs.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information\#response-example "Direct link to Response Example")

> For One-way position mode:

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": [\
    {\
        "entryPrice": "0.00000",\
        "breakEvenPrice": "0.0",\
        "marginType": "isolated",\
        "isAutoAddMargin": "false",\
        "isolatedMargin": "0.00000000",\
        "leverage": "10",\
        "liquidationPrice": "0",\
        "markPrice": "6679.50671178",\
        "maxNotionalValue": "20000000",\
        "positionAmt": "0.000",\
        "notional": "0",\
        "isolatedWallet": "0",\
        "symbol": "BTCUSDT",\
        "unRealizedProfit": "0.00000000",\
        "positionSide": "BOTH",\
        "updateTime": 0\
    }\
],
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

> For Hedge position mode:

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": [\
    {\
        "symbol": "BTCUSDT",\
        "positionAmt": "0.001",\
        "entryPrice": "22185.2",\
        "breakEvenPrice": "0.0",\
        "markPrice": "21123.05052574",\
        "unRealizedProfit": "-1.06214947",\
        "liquidationPrice": "19731.45529116",\
        "leverage": "4",\
        "maxNotionalValue": "100000000",\
        "marginType": "cross",\
        "isolatedMargin": "0.00000000",\
        "isAutoAddMargin": "false",\
        "positionSide": "LONG",\
        "notional": "21.12305052",\
        "isolatedWallet": "0",\
        "updateTime": 1655217461579\
    },\
    {\
        "symbol": "BTCUSDT",\
        "positionAmt": "0.000",\
        "entryPrice": "0.0",\
        "breakEvenPrice": "0.0",\
        "markPrice": "21123.05052574",\
        "unRealizedProfit": "0.00000000",\
        "liquidationPrice": "0",\
        "leverage": "4",\
        "maxNotionalValue": "100000000",\
        "marginType": "cross",\
        "isolatedMargin": "0.00000000",\
        "isAutoAddMargin": "false",\
        "positionSide": "SHORT",\
        "notional": "0",\
        "isolatedWallet": "0",\
        "updateTime": 0\
    }\
],
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Position-Information#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Symbol_Price_Ticker.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker#__docusaurus_skipToContent_fallback)

On this page

# Symbol Price Ticker

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker\#api-description "Direct link to API Description")

Latest price for a symbol or symbols.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/ticker/price`

**Weight:**

**1** for a single symbol;

**2** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

> - If the symbol is not sent, prices for all symbols will be returned in an array.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "symbol": "BTCUSDT",
  "price": "6000.01",
  "time": 1589437530011   // Transaction time
}

```

> OR

```codeBlockLines_aHhF
[\
	{\
  		"symbol": "BTCUSDT",\
  		"price": "6000.01",\
  		"time": 1589437530011\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker#http-request)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_Change_Multi_Assets_Mode.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode#__docusaurus_skipToContent_fallback)

On this page

# Change Multi-Assets Mode (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode\#api-description "Direct link to API Description")

Change user's Multi-Assets mode (Multi-Assets Mode or Single-Asset Mode) on _**Every symbol**_

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode\#http-request "Direct link to HTTP Request")

POST `/fapi/v1/multiAssetsMargin`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| multiAssetsMargin | STRING | YES | "true": Multi-Assets Mode; "false": Single-Asset Mode |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"code": 200,
	"msg": "success"
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Change-Multi-Assets-Mode#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Mark_Price_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream#__docusaurus_skipToContent_fallback)

On this page

# Mark Price Stream

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream\#stream-description "Direct link to Stream Description")

Mark price and funding rate for a single symbol pushed every 3 seconds or every second.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream\#stream-name "Direct link to Stream Name")

`<symbol>@markPrice` or `<symbol>@markPrice@1s`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream\#update-speed "Direct link to Update Speed")

**3000ms** or **1000ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
  {
    "e": "markPriceUpdate",  	// Event type
    "E": 1562305380000,      	// Event time
    "s": "BTCUSDT",          	// Symbol
    "p": "11794.15000000",   	// Mark price
    "i": "11784.62659091",		// Index price
    "P": "11784.25641265",		// Estimated Settle Price, only useful in the last hour before the settlement starts
    "r": "0.00038167",       	// Funding rate
    "T": 1562306400000       	// Next funding time
  }

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Close_User_Data_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream#__docusaurus_skipToContent_fallback)

On this page

# Close User Data Stream (USER\_STREAM)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream\#api-description "Direct link to API Description")

Close out a user data stream.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream\#http-request "Direct link to HTTP Request")

DELETE `/fapi/v1/listenKey`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream\#request-weight "Direct link to Request Weight")

1

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream\#request-parameters "Direct link to Request Parameters")

None

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Close-User-Data-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_Partial_Book_Depth_Streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams#__docusaurus_skipToContent_fallback)

On this page

# Partial Book Depth Streams

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams\#stream-description "Direct link to Stream Description")

Top **<levels>** bids and asks, Valid **<levels>** are 5, 10, or 20.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams\#stream-name "Direct link to Stream Name")

`<symbol>@depth<levels>` OR `<symbol>@depth<levels>@500ms` OR `<symbol>@depth<levels>@100ms`.

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams\#update-speed "Direct link to Update Speed")

**250ms**, **500ms** or **100ms**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e": "depthUpdate", // Event type
  "E": 1571889248277, // Event time
  "T": 1571889248276, // Transaction time
  "s": "BTCUSDT",
  "U": 390497796,     // First update ID in event
  "u": 390497878,     // Final update ID in event
  "pu": 390497794,    // Final update Id in last stream(ie `u` in last stream)
  "b": [              // Bids to be updated\
    [\
      "7403.89",      // Price Level to be updated\
      "0.002"         // Quantity\
    ],\
    [\
      "7403.90",\
      "3.906"\
    ],\
    [\
      "7404.00",\
      "1.428"\
    ],\
    [\
      "7404.85",\
      "5.239"\
    ],\
    [\
      "7405.43",\
      "2.562"\
    ]\
  ],
  "a": [              // Asks to be updated\
    [\
      "7405.96",      // Price level to be\
      "3.340"         // Quantity\
    ],\
    [\
      "7406.63",\
      "4.525"\
    ],\
    [\
      "7407.08",\
      "2.475"\
    ],\
    [\
      "7407.15",\
      "4.800"\
    ],\
    [\
      "7407.20",\
      "0.175"\
    ]\
  ]
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api#__docusaurus_skipToContent_fallback)

# New Future Account Transfer

Please find details from [here](https://developers.binance.com/docs/wallet/asset/user-universal-transfer).


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Futures_Account_Balance_V2.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2#__docusaurus_skipToContent_fallback)

On this page

# Futures Account Balance V2 (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2\#api-description "Direct link to API Description")

Query account balance info

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2\#http-request "Direct link to HTTP Request")

GET `/fapi/v2/balance`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
 	{\
 		"accountAlias": "SgsR",    // unique account code\
 		"asset": "USDT",  	// asset name\
 		"balance": "122607.35137903", // wallet balance\
 		"crossWalletBalance": "23.72469206", // crossed wallet balance\
  		"crossUnPnl": "0.00000000"  // unrealized profit of crossed positions\
  		"availableBalance": "23.72469206",       // available balance\
  		"maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
  		"marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
  		"updateTime": 1617939110373\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Futures-Account-Balance-V2#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams_All_Book_Tickers_Stream.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream#__docusaurus_skipToContent_fallback)

On this page

# All Book Tickers Stream

## Stream Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream\#stream-description "Direct link to Stream Description")

Pushes any update to the best bid or ask's price or quantity in real-time for all symbols.

## Stream Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream\#stream-name "Direct link to Stream Name")

`!bookTicker`

## Update Speed [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream\#update-speed "Direct link to Update Speed")

**5s**

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "e":"bookTicker",			// event type
  "u":400900217,     		// order book updateId
  "E": 1568014460893,  	// event time
  "T": 1568014460891,  	// transaction time
  "s":"BNBUSDT",     		// symbol
  "b":"25.35190000", 		// best bid price
  "B":"31.21000000", 		// best bid qty
  "a":"25.36520000", 		// best ask price
  "A":"40.66000000"  		// best ask qty
}

```

- [Stream Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream#stream-description)
- [Stream Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream#stream-name)
- [Update Speed](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream#update-speed)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Book-Tickers-Stream#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Composite_Index_Symbol_Information.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information#__docusaurus_skipToContent_fallback)

On this page

# Composite Index Symbol Information

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information\#api-description "Direct link to API Description")

Query composite index symbol information

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/indexInfo`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

> - Only for composite index symbols

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
	{\
		"symbol": "DEFIUSDT",\
		"time": 1589437530011,    // Current time\
		"component": "baseAsset", //Component asset\
		"baseAssetList":[\
			{\
				"baseAsset":"BAL",\
				"quoteAsset": "USDT",\
				"weightInQuantity":"1.04406228",\
				"weightInPercentage":"0.02783900"\
			},\
			{\
				"baseAsset":"BAND",\
				"quoteAsset": "USDT",\
				"weightInQuantity":"3.53782729",\
				"weightInPercentage":"0.03935200"\
			}\
		]\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Composite-Index-Symbol-Information#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_User_Commission_Rate.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate#__docusaurus_skipToContent_fallback)

On this page

# User Commission Rate (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate\#api-description "Direct link to API Description")

Get User Commission Rate

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/commissionRate`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate\#request-weight "Direct link to Request Weight")

**20**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
	"symbol": "BTCUSDT",
  	"makerCommissionRate": "0.0002",  // 0.02%
  	"takerCommissionRate": "0.0004"   // 0.04%
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/User-Commission-Rate#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_websocket_api_Account_Information.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information#__docusaurus_skipToContent_fallback)

On this page

# Account Information(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information\#api-description "Direct link to API Description")

Get current account information. User in single-asset/ multi-assets mode will see different value, see comments in response section for detail.

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information\#method "Direct link to Method")

`account.status`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
    "method": "account.status",
    "params": {
        "apiKey": "xTaDyrmvA9XT2oBHHjy39zyPzKCvMdtH3b9q4xadkAg2dNSJXQGCxzui26L823W2",
        "timestamp": 1702620814781,
        "signature": "6bb98ef84170c70ba3d01f44261bfdf50fef374e551e590de22b5c3b729b1d8c"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information\#response-example "Direct link to Response Example")

> Single Asset Mode

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": {
    "feeTier": 0,       // account commission tier
    "canTrade": true,   // if can trade
    "canDeposit": true,     // if can transfer in asset
    "canWithdraw": true,    // if can transfer out asset
    "updateTime": 0,        // reserved property, please ignore
    "multiAssetsMargin": false,
    "tradeGroupId": -1,
    "totalInitialMargin": "0.00000000",    // total initial margin required with current mark price (useless with isolated positions), only for USDT asset
    "totalMaintMargin": "0.00000000",     // total maintenance margin required, only for USDT asset
    "totalWalletBalance": "23.72469206",     // total wallet balance, only for USDT asset
    "totalUnrealizedProfit": "0.00000000",   // total unrealized profit, only for USDT asset
    "totalMarginBalance": "23.72469206",     // total margin balance, only for USDT asset
    "totalPositionInitialMargin": "0.00000000",    // initial margin required for positions with current mark price, only for USDT asset
    "totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price, only for USDT asset
    "totalCrossWalletBalance": "23.72469206",      // crossed wallet balance, only for USDT asset
    "totalCrossUnPnl": "0.00000000",      // unrealized profit of crossed positions, only for USDT asset
    "availableBalance": "23.72469206",       // available balance, only for USDT asset
    "maxWithdrawAmount": "23.72469206"     // maximum amount for transfer out, only for USDT asset
    "assets": [\
        {\
            "asset": "USDT",            // asset name\
            "walletBalance": "23.72469206",      // wallet balance\
            "unrealizedProfit": "0.00000000",    // unrealized profit\
            "marginBalance": "23.72469206",      // margin balance\
            "maintMargin": "0.00000000",        // maintenance margin required\
            "initialMargin": "0.00000000",    // total initial margin required with current mark price\
            "positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
            "openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
            "crossWalletBalance": "23.72469206",      // crossed wallet balance\
            "crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
            "availableBalance": "23.72469206",       // available balance\
            "maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
            "marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
            "updateTime": 1625474304765 // last update time\
        },\
        {\
            "asset": "BUSD",            // asset name\
            "walletBalance": "103.12345678",      // wallet balance\
            "unrealizedProfit": "0.00000000",    // unrealized profit\
            "marginBalance": "103.12345678",      // margin balance\
            "maintMargin": "0.00000000",        // maintenance margin required\
            "initialMargin": "0.00000000",    // total initial margin required with current mark price\
            "positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
            "openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
            "crossWalletBalance": "103.12345678",      // crossed wallet balance\
            "crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
            "availableBalance": "103.12345678",       // available balance\
            "maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
            "marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
            "updateTime": 1625474304765 // last update time\
        }\
    ],
    "positions": [  // positions of all symbols in the market are returned\
        // only "BOTH" positions will be returned with One-way mode\
        // only "LONG" and "SHORT" positions will be returned with Hedge mode\
        {\
            "symbol": "BTCUSDT",    // symbol name\
            "initialMargin": "0",   // initial margin required with current mark price\
            "maintMargin": "0",     // maintenance margin required\
            "unrealizedProfit": "0.00000000",  // unrealized profit\
            "positionInitialMargin": "0",      // initial margin required for positions with current mark price\
            "openOrderInitialMargin": "0",     // initial margin required for open orders with current mark price\
            "leverage": "100",      // current initial leverage\
            "isolated": true,       // if the position is isolated\
            "entryPrice": "0.00000",    // average entry price\
            "maxNotional": "250000",    // maximum available notional with current leverage\
            "bidNotional": "0",  // bids notional, ignore\
            "askNotional": "0",  // ask notional, ignore\
            "positionSide": "BOTH",     // position side\
            "positionAmt": "0",         // position amount\
            "updateTime": 0           // last update time\
        }\
    ]
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

> Multi-Asset Mode

```codeBlockLines_aHhF
{
  "id": "605a6d20-6588-4cb9-afa0-b0ab087507ba",
  "status": 200,
  "result": {
      "feeTier": 0,       // account commission tier
      "canTrade": true,   // if can trade
      "canDeposit": true,     // if can transfer in asset
      "canWithdraw": true,    // if can transfer out asset
      "updateTime": 0,        // reserved property, please ignore
      "multiAssetsMargin": true,
      "tradeGroupId": -1,
      "totalInitialMargin": "0.00000000",    // the sum of USD value of all cross positions/open order initial margin
      "totalMaintMargin": "0.00000000",     // the sum of USD value of all cross positions maintenance margin
      "totalWalletBalance": "126.72469206",     // total wallet balance in USD
      "totalUnrealizedProfit": "0.00000000",   // total unrealized profit in USD
      "totalMarginBalance": "126.72469206",     // total margin balance in USD
      "totalPositionInitialMargin": "0.00000000",    // the sum of USD value of all cross positions initial margin
      "totalOpenOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price in USD
      "totalCrossWalletBalance": "126.72469206",      // crossed wallet balance in USD
      "totalCrossUnPnl": "0.00000000",      // unrealized profit of crossed positions in USD
      "availableBalance": "126.72469206",       // available balance in USD
      "maxWithdrawAmount": "126.72469206"     // maximum virtual amount for transfer out in USD
      "assets": [\
          {\
              "asset": "USDT",            // asset name\
              "walletBalance": "23.72469206",      // wallet balance\
              "unrealizedProfit": "0.00000000",    // unrealized profit\
              "marginBalance": "23.72469206",      // margin balance\
              "maintMargin": "0.00000000",        // maintenance margin required\
              "initialMargin": "0.00000000",    // total initial margin required with current mark price\
              "positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
              "openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
              "crossWalletBalance": "23.72469206",      // crossed wallet balance\
              "crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
              "availableBalance": "126.72469206",       // available balance\
              "maxWithdrawAmount": "23.72469206",     // maximum amount for transfer out\
              "marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
              "updateTime": 1625474304765 // last update time\
          },\
          {\
              "asset": "BUSD",            // asset name\
              "walletBalance": "103.12345678",      // wallet balance\
              "unrealizedProfit": "0.00000000",    // unrealized profit\
              "marginBalance": "103.12345678",      // margin balance\
              "maintMargin": "0.00000000",        // maintenance margin required\
              "initialMargin": "0.00000000",    // total initial margin required with current mark price\
              "positionInitialMargin": "0.00000000",    //initial margin required for positions with current mark price\
              "openOrderInitialMargin": "0.00000000",   // initial margin required for open orders with current mark price\
              "crossWalletBalance": "103.12345678",      // crossed wallet balance\
              "crossUnPnl": "0.00000000"       // unrealized profit of crossed positions\
              "availableBalance": "126.72469206",       // available balance\
              "maxWithdrawAmount": "103.12345678",     // maximum amount for transfer out\
              "marginAvailable": true,    // whether the asset can be used as margin in Multi-Assets mode\
              "updateTime": 1625474304765 // last update time\
          }\
      ],
      "positions": [  // positions of all symbols in the market are returned\
          // only "BOTH" positions will be returned with One-way mode\
          // only "LONG" and "SHORT" positions will be returned with Hedge mode\
          {\
              "symbol": "BTCUSDT",    // symbol name\
              "initialMargin": "0",   // initial margin required with current mark price\
              "maintMargin": "0",     // maintenance margin required\
              "unrealizedProfit": "0.00000000",  // unrealized profit\
              "positionInitialMargin": "0",      // initial margin required for positions with current mark price\
              "openOrderInitialMargin": "0",     // initial margin required for open orders with current mark price\
              "leverage": "100",      // current initial leverage\
              "isolated": true,       // if the position is isolated\
              "entryPrice": "0.00000",    // average entry price\
              "breakEvenPrice": "0.0",    // average entry price\
              "maxNotional": "250000",    // maximum available notional with current leverage\
              "bidNotional": "0",  // bids notional, ignore\
              "askNotional": "0",  // ask notional, ignore\
              "positionSide": "BOTH",     // position side\
              "positionAmt": "0",         // position amount\
              "updateTime": 0           // last update time\
          }\
      ]
  },
  "rateLimits": [\
    {\
      "rateLimitType": "REQUEST_WEIGHT",\
      "interval": "MINUTE",\
      "intervalNum": 1,\
      "limit": 2400,\
      "count": 20\
    }\
  ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/websocket-api/Account-Information#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_rest_api_All_Orders.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders#__docusaurus_skipToContent_fallback)

On this page

# All Orders (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders\#api-description "Direct link to API Description")

Get all account orders; active, canceled, or filled.

- These orders will not be found:
  - order status is `CANCELED` or `EXPIRED` **AND** order has NO filled trade **AND** created time + 3 days < current time
  - order create time + 90 days < current time

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/allOrders`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders\#request-weight "Direct link to Request Weight")

**5**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | YES |  |
| orderId | LONG | NO |  |
| startTime | LONG | NO |  |
| endTime | LONG | NO |  |
| limit | INT | NO | Default 500; max 1000. |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

**Notes:**

> - If `orderId` is set, it will get orders >= that `orderId`. Otherwise most recent orders are returned.
> - The query time period must be less then 7 days( default as the recent 7 days).

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
[\
  {\
   	"avgPrice": "0.00000",\
  	"clientOrderId": "abc",\
  	"cumQuote": "0",\
  	"executedQty": "0",\
  	"orderId": 1917641,\
  	"origQty": "0.40",\
  	"origType": "TRAILING_STOP_MARKET",\
  	"price": "0",\
  	"reduceOnly": false,\
  	"side": "BUY",\
  	"positionSide": "SHORT",\
  	"status": "NEW",\
  	"stopPrice": "9300",				// please ignore when order type is TRAILING_STOP_MARKET\
  	"closePosition": false,   // if Close-All\
  	"symbol": "BTCUSDT",\
  	"time": 1579276756075,				// order time\
  	"timeInForce": "GTC",\
  	"type": "TRAILING_STOP_MARKET",\
  	"activatePrice": "9020",			// activation price, only return with TRAILING_STOP_MARKET order\
  	"priceRate": "0.3",					// callback rate, only return with TRAILING_STOP_MARKET order\
  	"updateTime": 1579276756075,		// update time\
  	"workingType": "CONTRACT_PRICE",\
  	"priceProtect": false,              // if conditional order trigger is protected\
  	"priceMatch": "NONE",              //price match mode\
  	"selfTradePreventionMode": "NONE", //self trading preventation mode\
  	"goodTillDate": 0      //order pre-set auot cancel time for TIF GTD order\
  }\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/All-Orders#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams#__docusaurus_skipToContent_fallback)

# User Data Streams Connect

- The base API endpoint is: **[https://fapi.binance.com](https://fapi.binance.com/)**

- A User Data Stream `listenKey` is valid for 60 minutes after creation.

- Doing a `PUT` on a `listenKey` will extend its validity for 60 minutes, if response `-1125` error "This listenKey does not exist." Please use `POST /fapi/v1/listenKey` to recreate `listenKey`.

- Doing a `DELETE` on a `listenKey` will close the stream and invalidate the `listenKey`.

- Doing a `POST` on an account with an active `listenKey` will return the currently active `listenKey` and extend its validity for 60 minutes.

- The connection method for Websocket：
  - Base Url: **wss://fstream.binance.com**
  - User Data Streams are accessed at **/ws/<listenKey>**
  - Example: `wss://fstream.binance.com/ws/XaEAKTsQSRLZAGH9tuIu37plSRsdjmlAVBoNYPUITlTAko1WI22PgmBMpI1rS8Yh`
- For one connection(one user data), the user data stream payloads can guaranteed to be in order during heavy periods; **Strongly recommend you order your updates using E**

- A single connection is only valid for 24 hours; expect to be disconnected at the 24 hour mark


[developers_binance_com_docs_derivatives_usds_margined_futures_trade_websocket_api_Modify_Order.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order#__docusaurus_skipToContent_fallback)

On this page

# Modify Order (TRADE)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order\#api-description "Direct link to API Description")

Order modify function, currently only LIMIT order modification is supported, modified orders will be reordered in the match queue

## Method [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order\#method "Direct link to Method")

`order.modify`

## Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order\#request "Direct link to Request")

```codeBlockLines_aHhF
{
    "id": "c8c271ba-de70-479e-870c-e64951c753d9",
    "method": "order.modify",
    "params": {
        "apiKey": "HMOchcfiT9ZRZnhjp2XjGXhsOBd6msAhKz9joQaWwZ7arcJTlD2hGPHQj1lGdTjR",
        "orderId": 328971409,
        "origType": "LIMIT",
        "positionSide": "SHORT",
        "price": "43769.1",
        "priceMatch": "NONE",
        "quantity": "0.11",
        "side": "SELL",
        "symbol": "BTCUSDT",
        "timestamp": 1703426755754,
        "signature": "d30c9f0736a307f5a9988d4a40b688662d18324b17367d51421da5484e835923"
    }
}

```

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order\#request-weight "Direct link to Request Weight")

1 on 10s order rate limit(X-MBX-ORDER-COUNT-10S);
1 on 1min order rate limit(X-MBX-ORDER-COUNT-1M);
1 on IP rate limit(x-mbx-used-weight-1m)

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| orderId | LONG | NO |  |
| origClientOrderId | STRING | NO |  |
| symbol | STRING | YES |  |
| side | ENUM | YES | `SELL`, `BUY` |
| quantity | DECIMAL | YES | Order quantity, cannot be sent with `closePosition=true` |
| price | DECIMAL | YES |  |
| priceMatch | ENUM | NO | only avaliable for `LIMIT`/ `STOP`/ `TAKE_PROFIT` order; can be set to `OPPONENT`/ `OPPONENT_5`/ `OPPONENT_10`/ `OPPONENT_20`: / `QUEUE`/ `QUEUE_5`/ `QUEUE_10`/ `QUEUE_20`; Can't be passed together with `price` |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

> - Either `orderId` or `origClientOrderId` must be sent, and the `orderId` will prevail if both are sent.
> - Both `quantity` and `price` must be sent, which is different from dapi modify order endpoint.
> - When the new `quantity` or `price` doesn't satisfy PRICE\_FILTER / PERCENT\_FILTER / LOT\_SIZE, amendment will be rejected and the order will stay as it is.
> - However the order will be cancelled by the amendment in the following situations:
>   - when the order is in partially filled status and the new `quantity` <= `executedQty`
>   - When the order is `GTX` and the new price will cause it to be executed immediately
> - One order can only be modfied for less than 10000 times

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "id": "c8c271ba-de70-479e-870c-e64951c753d9",
    "status": 200,
    "result": {
        "orderId": 328971409,
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "xGHfltUMExx0TbQstQQfRX",
        "price": "43769.10",
        "avgPrice": "0.00",
        "origQty": "0.110",
        "executedQty": "0.000",
        "cumQty": "0.000",
        "cumQuote": "0.00000",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "reduceOnly": false,
        "closePosition": false,
        "side": "SELL",
        "positionSide": "SHORT",
        "stopPrice": "0.00",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": false,
        "origType": "LIMIT",
        "priceMatch": "NONE",
        "selfTradePreventionMode": "NONE",
        "goodTillDate": 0,
        "updateTime": 1703426756190
    },
    "rateLimits": [\
        {\
            "rateLimitType": "ORDERS",\
            "interval": "SECOND",\
            "intervalNum": 10,\
            "limit": 300,\
            "count": 1\
        },\
        {\
            "rateLimitType": "ORDERS",\
            "interval": "MINUTE",\
            "intervalNum": 1,\
            "limit": 1200,\
            "count": 1\
        },\
        {\
            "rateLimitType": "REQUEST_WEIGHT",\
            "interval": "MINUTE",\
            "intervalNum": 1,\
            "limit": 2400,\
            "count": 1\
        }\
    ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order#api-description)
- [Method](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order#method)
- [Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order#request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/websocket-api/Modify-Order#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_market_data_rest_api_Symbol_Price_Ticker_v2.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2#__docusaurus_skipToContent_fallback)

On this page

# Symbol Price Ticker V2

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2\#api-description "Direct link to API Description")

Latest price for a symbol or symbols.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2\#http-request "Direct link to HTTP Request")

GET `/fapi/v2/ticker/price`

**Weight:**

**1** for a single symbol;

**2** when the symbol parameter is omitted

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |

> - If the symbol is not sent, prices for all symbols will be returned in an array.
> - The field `X-MBX-USED-WEIGHT-1M` in response header is not accurate from this endpoint, please ignore.

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "symbol": "BTCUSDT",
  "price": "6000.01",
  "time": 1589437530011   // Transaction time
}

```

> OR

```codeBlockLines_aHhF
[\
	{\
  		"symbol": "BTCUSDT",\
  		"price": "6000.01",\
  		"time": 1589437530011\
	}\
]

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2#http-request)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_user_data_streams_Event_Conditional_Order_Trigger_Reject.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Conditional-Order-Trigger-Reject#__docusaurus_skipToContent_fallback)

On this page

# Event: Conditional\_Order\_Trigger\_Reject

## Event Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Conditional-Order-Trigger-Reject\#event-description "Direct link to Event Description")

`CONDITIONAL_ORDER_TRIGGER_REJECT` update when a triggered TP/SL order got rejected.

## Event Name [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Conditional-Order-Trigger-Reject\#event-name "Direct link to Event Name")

`CONDITIONAL_ORDER_TRIGGER_REJECT`

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Conditional-Order-Trigger-Reject\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
    "e":"CONDITIONAL_ORDER_TRIGGER_REJECT",      // Event Type
    "E":1685517224945,      // Event Time
    "T":1685517224955,      // me message send Time
    "or":{
      "s":"ETHUSDT",      // Symbol
      "i":155618472834,      // orderId
      "r":"Due to the order could not be filled immediately, the FOK order has been rejected. The order will not be recorded in the order history",      // reject reason
     }
}

```

- [Event Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Conditional-Order-Trigger-Reject#event-description)
- [Event Name](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Conditional-Order-Trigger-Reject#event-name)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Event-Conditional-Order-Trigger-Reject#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_account_rest_api_Notional_and_Leverage_Brackets.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets#__docusaurus_skipToContent_fallback)

On this page

# Notional and Leverage Brackets (USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets\#api-description "Direct link to API Description")

Query user notional and leverage bracket on speicfic symbol

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/leverageBracket`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets\#request-weight "Direct link to Request Weight")

**1**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| symbol | STRING | NO |  |
| recvWindow | LONG | NO |  |
| timestamp | LONG | YES |  |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets\#response-example "Direct link to Response Example")

> **Response:**

```codeBlockLines_aHhF
[\
    {\
        "symbol": "ETHUSDT",\
	    "notionalCoef": 1.50,  //user symbol bracket multiplier, only appears when user's symbol bracket is adjusted\
        "brackets": [\
            {\
                "bracket": 1,   // Notional bracket\
                "initialLeverage": 75,  // Max initial leverage for this bracket\
                "notionalCap": 10000,  // Cap notional of this bracket\
                "notionalFloor": 0,  // Notional threshold of this bracket\
                "maintMarginRatio": 0.0065, // Maintenance ratio for this bracket\
                "cum":0 // Auxiliary number for quick calculation\
\
            },\
        ]\
    }\
]

```

> **OR** (if symbol sent)

```codeBlockLines_aHhF

{
    "symbol": "ETHUSDT",
    "notionalCoef": 1.50,
    "brackets": [\
        {\
            "bracket": 1,\
            "initialLeverage": 75,\
            "notionalCap": 10000,\
            "notionalFloor": 0,\
            "maintMarginRatio": 0.0065,\
            "cum":0\
        },\
    ]
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets#response-example)


[developers_binance_com_docs_derivatives_usds_margined_futures_websocket_market_streams.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams#__docusaurus_skipToContent_fallback)

# Websocket Market Streams

- The connection method for Websocket is：
  - Base Url: **wss://fstream.binance.com**
  - Streams can be access either in a single raw stream or a combined stream
  - Raw streams are accessed at **/ws/<streamName>**
  - Combined streams are accessed at **/stream?streams=<streamName1>/<streamName2>/<streamName3>**
  - Example:
  - `wss://fstream.binance.com/ws/bnbusdt@aggTrade`
  - `wss://fstream.binance.com/stream?streams=bnbusdt@aggTrade/btcusdt@markPrice`
- Combined stream events are wrapped as follows: **{"stream":"<streamName>","data":<rawPayload>}**

- All symbols for streams are **lowercase**

- A single connection is only valid for 24 hours; expect to be disconnected at the 24 hour mark

- The websocket server will send a `ping frame` every 3 minutes. If the websocket server does not receive a `pong frame` back from the connection within a 10 minute period, the connection will be disconnected. Unsolicited `pong frames` are allowed(the client can send pong frames at a frequency higher than every 15 minutes to maintain the connection).

- WebSocket connections have a limit of 10 incoming messages per second.

- A connection that goes beyond the limit will be disconnected; IPs that are repeatedly disconnected may be banned.

- A single connection can listen to a maximum of **1024** streams.

- Considering the possible data latency from RESTful endpoints during an extremely volatile market, it is highly recommended to get the order status, position, etc from the Websocket user data stream.


[developers_binance_com_docs_derivatives_usds_margined_futures_convert_Order_Status.md]

[Skip to main content](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status#__docusaurus_skipToContent_fallback)

On this page

# Order status(USER\_DATA)

## API Description [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status\#api-description "Direct link to API Description")

Query order status by order ID.

## HTTP Request [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status\#http-request "Direct link to HTTP Request")

GET `/fapi/v1/convert/orderStatus`

## Request Weight [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status\#request-weight "Direct link to Request Weight")

**50(IP)**

## Request Parameters [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status\#request-parameters "Direct link to Request Parameters")

| Name | Type | Mandatory | Description |
| --- | --- | --- | --- |
| orderId | STRING | NO | Either orderId or quoteId is required |
| quoteId | STRING | NO | Either orderId or quoteId is required |

## Response Example [​](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status\#response-example "Direct link to Response Example")

```codeBlockLines_aHhF
{
  "orderId":933256278426274426,
  "orderStatus":"SUCCESS",
  "fromAsset":"BTC",
  "fromAmount":"0.00054414",
  "toAsset":"USDT",
  "toAmount":"20",
  "ratio":"36755",
  "inverseRatio":"0.00002721",
  "createTime":1623381330472
}

```

- [API Description](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status#api-description)
- [HTTP Request](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status#http-request)
- [Request Weight](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status#request-weight)
- [Request Parameters](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status#request-parameters)
- [Response Example](https://developers.binance.com/docs/derivatives/usds-margined-futures/convert/Order-Status#response-example)

