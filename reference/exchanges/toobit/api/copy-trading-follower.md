# Follower Endpoints

Follower OpenAPI endpoints use the `/api/v2/copy-trading/follower` prefix. All endpoints only access copy-trading data or settings of the follower bound to the current API Key. Responses follow the OpenAPI V2 wrapper:

json
```
{ "code": 200, "msg": "success", "data": {} }
```

1

  * All endpoints require a signed request. The API Key account type must be `COPY_TRADING`.
  * Query endpoints support read-only API Keys. Write endpoints do not support read-only API Keys.
  * For shared signing parameters, see Basic Information.
  * 64-bit integer fields are usually serialized as strings in JSON by the existing OpenAPI format.
  * The “query maximum/minimum follow order quantity” endpoint is not provided in this release.

* * *

## Current Follow Orders

Query current follow positions of the current follower.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/follower/orders/current`

### Parameters

No business parameters.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
leaderUserId| string| Leader user ID
leaderNickname| string| Leader nickname
leaderAvatar| string| Leader avatar
symbolId| string| Trading pair ID
isLong| integer| Direction, `0` short, `1` long
positionType| integer| Position type
leverage| string| Leverage
openAvgPrice| string| Average open price
markPrice| string| Mark price
currentPrice| string| Current price
quantity| string| Quantity
margin| string| Margin
liquidationPrice| string| Estimated liquidation price
unrealizedProfit| string| Unrealized PnL
unrealizedProfitRate| string| Unrealized PnL rate
stopProfitRate| string| Take-profit rate
stopLossRate| string| Stop-loss rate

### Example

http
```
GET /api/v2/copy-trading/follower/orders/current
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "leaderUserId": "123456789",
      "leaderNickname": "S5",
      "leaderAvatar": "https://static.example.com/avatar.png",
      "symbolId": "BTC-SWAP-USDT",
      "isLong": 1,
      "positionType": 1,
      "leverage": "20",
      "openAvgPrice": "6805",
      "markPrice": "7121.97",
      "currentPrice": "6805",
      "quantity": "0.01",
      "margin": "3.3854",
      "liquidationPrice": "",
      "unrealizedProfit": "3.17",
      "unrealizedProfitRate": "0.9315",
      "stopProfitRate": "",
      "stopLossRate": ""
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-32045| Copy trading follower not found.| The signed account has no active follow relationship
-1000| unknown| Unknown error

* * *

## History Follow Orders

Query historical follow positions of the current follower.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/follower/orders/history`

### Parameters

Name| Location| Type| Mandatory| Default| Description
---|---|---|---|---|---
page| query| LONG| NO| `1`| Page number, starting from 1
size| query| LONG| NO| `10`| Page size, maximum `100`

### Response

`data` is a page object:

Field| Type| Description
---|---|---
pages| string| Total pages
total| string| Total records
list| array| Historical follow orders

`data.list[]` fields:

Field| Type| Description
---|---|---
symbolId| string| Trading pair ID
positionType| integer| Position type
leverage| string| Leverage
isLong| integer| Direction, `0` short, `1` long
leaderNickname| string| Leader nickname
leaderAvatar| string| Leader avatar
openTimeMs| string| Open time, epoch millis
lastCloseTimeMs| string| Last close time, epoch millis
openAvgPrice| string| Average open price
closeAvgPrice| string| Average close price
maxPositionQuantity| string| Maximum position quantity
closedQuantity| string| Closed quantity
realizedProfit| string| Realized PnL
closeStatus| integer| Close status

### Example

http
```
GET /api/v2/copy-trading/follower/orders/history?page=1&size=10
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "pages": "1",
    "total": "1",
    "list": [
      {
        "symbolId": "BTC-SWAP-USDT",
        "positionType": 1,
        "leverage": "20",
        "isLong": 1,
        "leaderNickname": "S5",
        "leaderAvatar": "https://static.example.com/avatar.png",
        "openTimeMs": "1717200000000",
        "lastCloseTimeMs": "1717203600000",
        "openAvgPrice": "6805",
        "closeAvgPrice": "7100",
        "maxPositionQuantity": "0.02",
        "closedQuantity": "0.02",
        "realizedProfit": "5.9",
        "closeStatus": 2
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
25
26

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter ...| Invalid `page` or `size`; `size` must be no greater than `100`
-32045| Copy trading follower not found.| The signed account has no active follow relationship
-1000| unknown| Unknown error

* * *

## Update Position Take-Profit / Stop-Loss

Update take-profit and stop-loss settings for the follower position under the specified leader and symbol.

### Request Weight

`1`

### Request URL

`PUT /api/v2/copy-trading/follower/positions/stop-profit-loss`

### Parameters

The request body uses JSON.

Field| Type| Mandatory| Description
---|---|---|---
leaderUserId| LONG| YES| Target leader user ID
symbolId| string| YES| Trading pair ID
isLong| integer| YES| Direction, `0` short, `1` long
stopProfitRate| DECIMAL| NO| Take-profit rate
stopLossRate| DECIMAL| NO| Stop-loss rate
stopLossDelay| integer| NO| Stop-loss delay in seconds

### Response

On success, `data` is `null`.

### Example

http
```
PUT /api/v2/copy-trading/follower/positions/stop-profit-loss
```

1

json
```
{
  "leaderUserId": 123456789,
  "symbolId": "BTC-SWAP-USDT",
  "isLong": 1,
  "stopProfitRate": "0.1",
  "stopLossRate": "0.2",
  "stopLossDelay": 30
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1020| This operation is not supported.| Read-only API Key calls a write endpoint
-1102| Mandatory parameter ...| Required field missing or malformed
-1130| Data sent for paramter ...| Invalid range, precision, or format
-32045| Copy trading follower not found.| The signed account has no active follow relationship
-1000| unknown| Unknown error

* * *

## Update Follow Config

Update the current follower’s follow settings for the specified leader.

### Request Weight

`1`

### Request URL

`PUT /api/v2/copy-trading/follower/config`

### Parameters

The request body uses JSON.

Field| Type| Mandatory| Description
---|---|---|---
leaderUserId| LONG| YES| Target leader user ID
investAmount| DECIMAL| YES| Total follow investment
singlePlaceAmount| DECIMAL| YES| Fixed amount per order
dailyMaxInvestAmount| DECIMAL| YES| Maximum daily investment
leverage| DECIMAL| YES| Follow leverage
maxInvestRate| DECIMAL| YES| Maximum investment rate
stopProfitRate| DECIMAL| YES| Take-profit rate
stopLossRate| DECIMAL| YES| Stop-loss rate
realInvestAmount| DECIMAL| YES| Actual invested amount
followAmountMode| integer| YES| Follow amount mode
stopLossDelay| integer| YES| Stop-loss delay in seconds
isolatedReservedAmount| DECIMAL| YES| Isolated margin reserved amount
followMarginType| integer| YES| Follow margin type
followSymbolIds| STRING| YES| `all` or comma-separated symbol IDs
zeroSlippageSwitch| boolean| YES| Zero-slippage switch

### Rules

  * A read-only API Key is rejected when calling this write endpoint.
  * `investAmount`, `singlePlaceAmount`, `dailyMaxInvestAmount`, `leverage`, `stopProfitRate`, `stopLossRate`, `realInvestAmount`, and `isolatedReservedAmount` support up to 8 decimal places and cannot be negative.
  * `maxInvestRate` supports up to 8 decimal places and must be between `0` and `1`; for example, `0.5` means 50%.
  * `followSymbolIds` cannot be blank. `all` means all symbols. To specify multiple symbols, use comma-separated symbol IDs, for example `BTC-SWAP-USDT,ETH-SWAP-USDT`. Empty symbol IDs after splitting are invalid, and `all` cannot be mixed with specific symbols.
  * When `followAmountMode=0`, fixed-amount follow is used; `singlePlaceAmount` cannot be less than the minimum per-order follow amount configured by the current leader or system, and `realInvestAmount` cannot be less than `isolatedReservedAmount + singlePlaceAmount`.
  * When `followAmountMode=1`, fixed-rate follow is used; the actual invested amount must satisfy the minimum investment requirement for fixed-rate mode, and `realInvestAmount` cannot be less than `isolatedReservedAmount + minimum investment amount for fixed-rate mode`.
  * `investAmount` is the total follow investment after the update and is still checked against the minimum investment for the current follow amount mode. Fixed-amount mode fails when it is below the leader’s minimum follow investment, and fixed-rate mode fails when it is below the fixed-rate minimum investment.
  * `dailyMaxInvestAmount=0` means no daily maximum investment limit. When it is greater than `0`, it cannot be less than the minimum per-order follow amount.
  * `leverage` cannot exceed the system-configured maximum follow leverage. If there are active following orders, leverage cannot be modified.
  * `stopProfitRate` and `stopLossRate` set to `0` mean not configured. Non-zero values cannot be less than `0.01`.
  * `followMarginType=0` means following all margin modes; `followMarginType=1` means following cross-margin lead orders only; `followMarginType=2` means following isolated-margin lead orders only.
  * `zeroSlippageSwitch` is the zero-slippage boolean switch.

### Response

On success, `data` is `null`.

### Example

http
```
PUT /api/v2/copy-trading/follower/config
```

1

json
```
{
  "leaderUserId": 123456789,
  "investAmount": "100",
  "singlePlaceAmount": "10",
  "dailyMaxInvestAmount": "50",
  "leverage": "20",
  "maxInvestRate": "0.5",
  "stopProfitRate": "0.1",
  "stopLossRate": "0.2",
  "realInvestAmount": "100",
  "followAmountMode": 1,
  "stopLossDelay": 30,
  "isolatedReservedAmount": "5",
  "followMarginType": 2,
  "followSymbolIds": "BTC-SWAP-USDT,ETH-SWAP-USDT",
  "zeroSlippageSwitch": true
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1020| This operation is not supported.| Read-only API Key calls a write endpoint
-1102| Mandatory parameter ...| Required field missing or malformed
-1130| Data sent for paramter ...| Invalid range, precision, or format
-32045| Copy trading follower not found.| No active follow relationship exists between the signed account and `leaderUserId`
-1000| unknown| Unknown error

* * *

## Query Follow Config

Query the current follower’s follow settings for the specified leader.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/follower/config`

### Parameters

Name| Location| Type| Mandatory| Description
---|---|---|---|---
leaderUserId| query| LONG| YES| Target leader user ID

### Response

`data` contains:

Field| Type| Description
---|---|---
leaderUserId| string| Target leader user ID
investAmount| string| Total follow investment
singlePlaceAmount| string| Fixed amount per order
dailyMaxInvestAmount| string| Maximum daily investment
leverage| string| Follow leverage
maxInvestRate| string| Maximum investment rate
stopProfitRate| string| Take-profit rate
stopLossRate| string| Stop-loss rate
followAmountMode| integer| Follow amount mode
stopLossDelay| integer| Stop-loss delay in seconds
isolatedReservedAmount| string| Isolated margin reserved amount
followMarginType| integer| Follow margin type
followSymbolIds| string| `all` or comma-separated symbol IDs
zeroSlippageSwitch| boolean| Zero-slippage switch

### Example

http
```
GET /api/v2/copy-trading/follower/config?leaderUserId=123456789
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "leaderUserId": "123456789",
    "investAmount": "100",
    "singlePlaceAmount": "10",
    "dailyMaxInvestAmount": "50",
    "leverage": "20",
    "maxInvestRate": "0.5",
    "stopProfitRate": "0.1",
    "stopLossRate": "0.2",
    "followAmountMode": 1,
    "stopLossDelay": 30,
    "isolatedReservedAmount": "5",
    "followMarginType": 2,
    "followSymbolIds": "BTC-SWAP-USDT,ETH-SWAP-USDT",
    "zeroSlippageSwitch": true
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter 'leaderUserId' is not valid.| Invalid `leaderUserId`
-32045| Copy trading follower not found.| No active follow relationship exists between the signed account and `leaderUserId`
-1000| unknown| Unknown error

* * *

## My Leaders

Query leaders currently followed by the current follower.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/follower/leaders`

### Parameters

No business parameters.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
leaderUserId| string| Leader user ID
leaderNickname| string| Leader nickname
leaderAvatar| string| Leader avatar
marginBalance| string| Margin balance
availableMargin| string| Available margin
unrealisedPnl| string| Unrealized PnL
realisedProfit| string| Realized profit
holdingProfitSharing| string| Withheld profit sharing
settledProfitSharing| string| Settled profit sharing
netProfit| string| Net profit

### Example

http
```
GET /api/v2/copy-trading/follower/leaders
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "leaderUserId": "123456789",
      "leaderNickname": "S5",
      "leaderAvatar": "https://static.example.com/avatar.png",
      "marginBalance": "521.64",
      "availableMargin": "518.25",
      "unrealisedPnl": "-0.03",
      "realisedProfit": "0",
      "holdingProfitSharing": "0",
      "settledProfitSharing": "0.58",
      "netProfit": "-0.58"
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-32045| Copy trading follower not found.| The signed account has no active follow relationship
-1000| unknown| Unknown error

* * *

## Cancel Leader

Cancel following the specified leader as the current follower.

### Request Weight

`1`

### Request URL

`DELETE /api/v2/copy-trading/follower/leaders/{leaderUserId}`

### Parameters

Name| Location| Type| Mandatory| Description
---|---|---|---|---
leaderUserId| path| LONG| YES| Target leader user ID. It must be greater than or equal to `1`

### Response

On success, `data` is `null`.

### Example

http
```
DELETE /api/v2/copy-trading/follower/leaders/123456789
```

1

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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1020| This operation is not supported.| Read-only API Key calls a write endpoint
-1130| Data sent for paramter 'leaderUserId' is not valid.| Invalid `leaderUserId`
-32045| Copy trading follower not found.| Follow relationship not found
-120055| The follower currently has copy position, cannot be removed.| The follower currently has copy positions and cannot cancel following
-1000| unknown| Unknown error
