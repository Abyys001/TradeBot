# Basic Information

## API Basic Information

  * Some endpoints will require an API Key. Please refer to this page regarding API key creation.
  * The base endpoint is: **https://api.toobit.com**
  * All endpoints return either a JSON object or array.
  * All time and timestamp related fields are in milliseconds.

## General Information on Endpoints

  * For `GET` endpoints, parameters must be sent as a `query string`.
  * For `POST`, `PUT`, and `DELETE` endpoints, the parameters may be sent as a query string or in the request body with content type `application/x-www-form-urlencoded`. You may mix parameters between both the `query string` and `request body` if you wish to do so.
  * For SIGNED endpoints, the parameter order in the request must match the order used for signature calculation.
  * If a parameter sent in both the `query string` and `request body`, the `query string` parameter will be used.

### HTTP Return Codes

  * HTTP `4XX` return codes are used for malformed requests; the issue is on the sender's side.
  * HTTP `403` return code is used when the WAF Limit (Web Application Firewall) has been violated.
  * HTTP `429` return code is used when a request triggers rate limiting.
  * HTTP `5XX` return codes are used for internal errors; the issue is on TooBit's side. It is important to NOT treat this as a failure operation; the execution status is UNKNOWN and could have been a success.

## Rate Limits

### General Info on Rate Limits

  * The `/api/v1/exchangeInfo` `rateLimits` array contains objects related to the exchange's `REQUEST_WEIGHT` and `ORDERS` rate limits. These are further defined in the `ENUM definitions` section under `Rate limiters (rateLimitType)`.

WARNING

Note: The `rateLimits` field in the `/api/v1/exchangeInfo` endpoint response will be removed in future iterations. A new endpoint will be provided to retrieve rate limit information.

  * A 429 will be returned when any rate limit is triggered.
  * Each route has a weight which determines for the number of requests each endpoint counts for. Heavier endpoints and endpoints that do operations on multiple symbols will have a heavier weight.
  * When a 429 is received, clients must back off and stop sending high-frequency requests.

### API Key rate limits

The base REST API limits are:

Rate limit type| Description| Limit
---|---|---
`REQUEST_WEIGHT`| Request weight limit. Each request consumes the weight assigned to the endpoint.| 3000 weight per 1 minute
`ORDERS`| Order request limit.| 60 order requests per 2 seconds

For example, an endpoint with weight `5` consumes `5` units of `REQUEST_WEIGHT` per request. An endpoint with weight `1` consumes `1` unit per request.

When the request weight limit is exceeded, the server returns HTTP `429` with error code `-1003 TOO_MANY_REQUESTS`. When the order request limit is exceeded, the server returns HTTP `429` with error code `-1015 TOO_MANY_ORDERS`.

After receiving HTTP `429`, clients should reduce the request rate immediately and retry only after the time indicated by the `X-Api-Limit-Reset-Timestamp` response header. Do not continue high-frequency retries after receiving 429.

TIP

We recommend using websocket streams to retrieve data whenever possible, as this reduces REST request rate limit pressure.

### Rate limit response headers

Every REST response (v1 and v2) includes the following headers so clients can monitor usage:

Header| Description
---|---
`X-Api-Limit-Status`| Remaining requests in the current window
`X-Api-Limit`| Maximum requests allowed in the window
`X-Api-Limit-Reset-Timestamp`| Milliseconds timestamp for the next window reset (or current server time when not limited)

## Endpoint Security Type

  * Each endpoint has a security type that determines how you will interact with it. This is stated next to the NAME of the endpoint.
  * If no security type is stated, assume the security type is NONE.
  * API-keys are passed into the Rest API via the `X-BB-APIKEY` header.
  * API-keys and secret-keys **are case sensitive**.
  * API-keys can be configured to only access certain types of secure endpoints. For example, one API-key could be used for TRADE only, while another API-key can access everything except for TRADE routes.
  * By default, API-keys can access all secure routes.

Security Type| Description
---|---
NONE| Endpoint can be accessed freely.
TRADE| Endpoint requires sending a valid API-Key and signature.
USER_DATA| Endpoint requires sending a valid API-Key and signature.
USER_STREAM| Endpoint requires sending a valid API-Key.
MARKET_DATA| Endpoint requires sending a valid API-Key.

  * `TRADE` and `USER_DATA` endpoints are `SIGNED` endpoints.

## SIGNED (TRADE, USER_DATA) Endpoint Security

  * `SIGNED` endpoints require an additional parameter, `signature`, to be sent in the `query string` or `request body`.
  * Endpoints use `HMAC SHA256` signatures. The `HMAC SHA256` signature is a keyed `HMAC SHA256`operation. Use your `secretKey` as the key and `totalParams` as the value for the HMAC operation.
  * The signature must be a **lowercase hexadecimal** string and is **case sensitive** ; do not use uppercase.
  * **Parameter order** : The parameter order in the request must match the order used for signature calculation.
  * totalParams is defined as the query string concatenated with the request body.

### JSON request body signing (API v2)

For routes under `/api/v2/` where the request uses `Content-Type: application/json` (for example `POST /api/v2/futures/batch-orders`), the **raw JSON string** must be included in the signature **after** the query string, with **no** `&` between them: `queryString + jsonBody`.

  * **The JSON body must be a single-line compact string with no newline characters (`\n`, `\r\n`).** The server reads the body line-by-line and discards line terminators. If you send pretty-printed (formatted) JSON, the string the server uses for verification will differ from what you signed, causing a signature failure.
  * The JSON string used to compute the signature must be **byte-identical** to the body you actually send (including key order and spaces). Any difference will fail verification.
  * If the body is empty or not valid JSON (must start with `{` or `[`), the request is rejected.

### Timing Security

  * A `SIGNED`endpoint also requires a parameter, `timestamp`, to be sent which should be the millisecond timestamp of when the request was created and sent.
  * An additional parameter, `recvWindow`, may be sent to specify the number of milliseconds after `timestamp`the request is valid for. If `recvWindow` is not sent, **it defaults to 5000**.
  * In addition, if the server calculates that the client's timestamp is more than one second "in the future" of the server's time, the request will also be rejected.

> The logic is as follows:

javascript
```
if (timestamp < (serverTime + 1000) && (serverTime - timestamp) <= recvWindow) {
  // process request
} else {
  // reject request
}
```

1
2
3
4
5

**Serious trading is about timing.** Networks can be unstable and unreliable, which can lead to requests taking varying amounts of time to reach the servers. With `recvWindow,` you can specify that the request must be processed within a certain number of milliseconds or be rejected by the server.

TIP

It is recommended to use a small recvWindow of 5000 or less! The max cannot go beyond 60,000!

## Public API Definitions

### Terminology

  * `base asset` refers to the asset that is the `quantity` of a symbol. For the symbol BTCUSDT, BTC would be the base asset.
  * `quote asset` refers to the asset that is the `price` of a symbol. For the symbol BTCUSDT, USDT would be the quote asset.

### ENUM definitions

#### Order status (status):

  * PENDING_NEW - Order request received successfully
  * NEW - New order, no deal yet
  * PARTIALLY_FILLED - Partial Sale
  * FILLED - Full Deal
  * CANCELED - Cancelled
  * PENDING_CANCEL - Waiting for Cancellation
  * REJECTED - Rejected

#### Order types (orderTypes, type):

**Common Types:**

  * LIMIT - Limit Order
  * MARKET - Market List
  * LIMIT_MAKER - maker Limit Order

**Contract Specific:**

  * STOP - Plan Order
  * STOP_SHORT_PROFIT - Take Profit
  * STOP_LONG_PROFIT - Take Profit
  * STOP_LONG_LOSS - Stop Loss
  * STOP_SHORT_LOSS - Stop Loss
  * LIQUI_IOC_ORDER - Liquidation
  * LIQUI_ADL_ORDER - ADL

#### Order side (side):

**Spot:**

  * BUY - buy the bill
  * SELL - sell order

**Contract:**

  * BUY_OPEN - Open long buy order to open a position to buy
  * BUY_CLOSE - Close short buy order to close position and buy
  * SELL_OPEN - Open short sell order to open a position to sell
  * SELL_CLOSE - Close long sell order to close position and sell

**Contract (API v2 —`/api/v2/futures/*`):** use two fields instead of the combined v1 `side`:

  * `side`: `BUY` or `SELL`
  * `positionSide`: `LONG` or `SHORT`

v1 `side`| v2 `side`| v2 `positionSide`
---|---|---
BUY_OPEN| BUY| LONG
SELL_OPEN| SELL| SHORT
BUY_CLOSE| BUY| SHORT
SELL_CLOSE| SELL| LONG

For v2 futures orders, set `type` to values such as `LIMIT`, `MARKET`, `STOP`, or `STOP_MARKET` as documented on each endpoint; limit, market, and conditional behavior follow from `type`.

#### Plan order or stop loss order status (status):

  * ORDER_NEW - New Order
  * ORDER_FILLED - Order Triggered Successfully
  * ORDER_REJECTED - Order Rejected
  * ORDER_CANCELED - Order Canceled
  * ORDER_FAILED - Order Trigger Failed

#### Take profit and stop loss type (type):

  * STOP_LONG_PROFIT - Long position take profit
  * STOP_LONG_LOSS - Long position stop loss
  * STOP_SHORT_PROFIT - Plan order - short position take profit
  * STOP_SHORT_LOSS - Plan order - short position stop loss

#### Symbol type (Contract):

  * FUTURE - Futures

#### Price Type (Contract):

  * INPUT - The system will match the order with the price you entered.
  * MARKET - Orders will be matched at the latest transaction price * (1 ± 5%).

#### Time in force (timeInForce):

  * GTC - Good Till Cancel
  * IOC - Immediate or Cancel
  * FOK - Fill or Kill
  * POST_ONLY - Post-Only (maker only)

#### Kline/Candlestick chart intervals:

m -> minutes; h -> hours; d -> days; w -> weeks; M -> months

  * 1m
  * 3m
  * 5m
  * 15m
  * 30m
  * 1h
  * 2h
  * 4h
  * 6h
  * 8h
  * 12h
  * 1d
  * 1w
  * 1M

#### Rate limiters (rateLimitType)

  * REQUEST_WEIGHT
  * ORDERS

#### Rate limit intervals (interval)

  * SECOND
  * MINUTE
