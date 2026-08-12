# Leader Endpoints

Copy Trading OpenAPI uses the `/api/v2/copy-trading/leader` prefix. All endpoints only access data or settings of the leader bound to the current API Key. Responses follow the OpenAPI V2 wrapper:

json
```
{ "code": 200, "msg": "success", "data": {} }
```

1

  * All endpoints require a signed request. The API Key account type must be `COPY_TRADING`.
  * Query endpoints support read-only API Keys. Write endpoints do not support read-only API Keys.
  * For shared signing parameters, see Basic Information.
  * 64-bit integer fields are usually serialized as strings in JSON by the existing OpenAPI format.

* * *

## Current Lead Orders

Query the current lead orders of the current leader.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/leader/orders/current`

### Parameters

No business parameters.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
symbolId| string| Trading pair ID
symbolName| string| Trading pair display name
isLong| integer| Direction, `0` short, `1` long
positionType| integer| Position type
leverage| string| Leverage
openTime| string| Open time, epoch millis
quantity| string| Quantity
newPrice| string| Current price
openPrice| string| Average open price
totalFollowerCount| string| Follower count
totalFollowerMargin| string| Total follower margin
profitRate| string| Profit rate
markPrice| string| Mark price

### Example

http
```
GET /api/v2/copy-trading/leader/orders/current
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "symbolId": "BTC-SWAP-USDT",
      "symbolName": "BTCUSDT Perpetual",
      "isLong": 1,
      "positionType": 0,
      "leverage": "20",
      "openTime": "1717200000000",
      "quantity": "0.000058242",
      "newPrice": "52246.217",
      "openPrice": "51110.77",
      "totalFollowerCount": "12",
      "totalFollowerMargin": "1000",
      "profitRate": "0.0123",
      "markPrice": "68100.2"
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter ...| Invalid parameter
-120041| Copy trading leader is not available.| The signed account is not an active leader
-1000| unknown| Unknown error

* * *

## History Lead Orders

Query historical lead orders of the current leader.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/leader/orders/history`

### Parameters

Name| Location| Type| Mandatory| Default| Description
---|---|---|---|---|---
page| query| LONG| NO| `1`| Page number, starting from 1
size| query| LONG| NO| `10`| Page size

### Response

`data` is a page object:

Field| Type| Description
---|---|---
pages| string| Total pages
total| string| Total records
list| array| Historical lead orders

`data.list[]` fields:

Field| Type| Description
---|---|---
symbolId| string| Trading pair
isLong| number| Direction, `0` short, `1` long
positionType| number| Position type, `0` cross, `1` isolated
leverage| string| Leverage
openPrice| string| Open price
closePrice| string| Close price
openTime| string| Open time, epoch millis
closeTime| string| Close time, epoch millis
profit| string| Realized PnL
status| number| `1` partially closed, `2` fully closed
openQty| string| Maximum position quantity
closeQty| string| Closed quantity
positionProfit| string| Position PnL
openFee| string| Open fee
closeFee| string| Close fee

### Example

http
```
GET /api/v2/copy-trading/leader/orders/history?page=1&size=10
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "pages": "3",
    "total": "21",
    "list": [
      {
        "symbolId": "BTC-SWAP-USDT",
        "isLong": 1,
        "positionType": 0,
        "leverage": "20",
        "openPrice": "51110.77",
        "closePrice": "52246.217",
        "openTime": "1717200000000",
        "closeTime": "1717203600000",
        "profit": "12.34",
        "status": 2,
        "openQty": "0.1",
        "closeQty": "0.1",
        "positionProfit": "12.34",
        "openFee": "0.1",
        "closeFee": "0.1"
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
27

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter ...| Invalid `page` or `size`
-120041| Copy trading leader is not available.| The signed account is not an active leader
-1000| unknown| Unknown error

* * *

## Trade Data

Query trade data of the current leader.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/leader/trade-data`

### Parameters

Name| Location| Type| Mandatory| Default| Description
---|---|---|---|---|---
type| query| INTEGER| NO| `7`| Fixed period. Supported values: `7`, `30`, `90`, `180`, `365`

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
profitRate| string| Profit rate
accumulatedProfit| string| Accumulated profit in USDT
orderCount| integer| Order count
winRate| string| Win rate
currentFollowerCount| string| Current follower count
followerTotalProfit| string| Total follower profit
sharpeRatio| string| Sharpe ratio
totalFollowerCount| string| Total follower count
assetManagementScale| string| Asset management scale
profitLossRatio| string| Profit-loss ratio
tradingFrequency| string| Trading frequency
tradingDays| integer| Trading days

### Example

http
```
GET /api/v2/copy-trading/leader/trade-data?type=30
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "profitRate": "0.1234",
      "accumulatedProfit": "888.1234",
      "orderCount": 18,
      "winRate": "0.6111",
      "currentFollowerCount": "21",
      "followerTotalProfit": "100.1234",
      "sharpeRatio": "1.2345",
      "totalFollowerCount": "89",
      "assetManagementScale": "12345.6789",
      "profitLossRatio": "2.18:1",
      "tradingFrequency": "0.6",
      "tradingDays": 30
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter 'type' is not valid.| Invalid `type`
-120041| Copy trading leader is not available.| The signed account is not an active leader
-1000| unknown| Unknown error

* * *

## Profit Sharing History

Query profit sharing history of the current leader. The endpoint keeps the latest 100 records behavior.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/leader/profit-sharings/history`

### Parameters

No business parameters.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
totalProfitSharing| string| Total profit sharing in the period
weekOfYear| integer| Week number
year| integer| Year
sharingDate| string| Profit sharing date
recommendUserShare| string| Referral share amount
realProfitShare| string| Actual leader share amount

### Example

http
```
GET /api/v2/copy-trading/leader/profit-sharings/history
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "totalProfitSharing": "10.5",
      "weekOfYear": 22,
      "year": 2026,
      "sharingDate": "2026-06-01",
      "recommendUserShare": "1.5",
      "realProfitShare": "9"
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter ...| Invalid parameter
-120041| Copy trading leader is not available.| The signed account is not an active leader
-1000| unknown| Unknown error

* * *

## Leader Symbols

Query OpenAPI-available leader symbols of the current leader.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/leader/symbols`

### Parameters

No business parameters.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
symbolId| string| Leader trading pair ID
leverage| string| Leader leverage
isLead| integer| Whether lead trading is enabled, `0` no, `1` yes

### Example

http
```
GET /api/v2/copy-trading/leader/symbols
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "symbolId": "BTC-SWAP-USDT",
      "leverage": "20",
      "isLead": 1
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter ...| Invalid parameter
-120041| Copy trading leader is not available.| The signed account is not an active leader
-1000| unknown| Unknown error

* * *

## Query Leader Config

Query editable settings of the current leader. Returned fields match the fields that can be submitted to `PUT /api/v2/copy-trading/leader/config`; identity, statistics, nickname, avatar, level, and other extra fields are not returned.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/leader/config`

### Parameters

No business parameters.

### Response

`data` contains:

Field| Type| Description
---|---|---
unLeadType| integer| `0` no cool-down period, `1` custom cool-down period
unLeadStartTime| string| Cool-down start time, epoch millis
unLeadEndTime| string| Cool-down end time, epoch millis
leadPositionType| integer| Leader position type: `-1` all, `0` cross, `1` isolated
tradeProtect| integer| Trade protection switch
profitPeriod| integer| Profit sharing period: `1` daily, `7` weekly
profitRate| string| Profit sharing rate
followAssetLowerLimit| string| Minimum follower asset
fixedAmountFollowMin| string| Minimum fixed-amount follow value
fixedRateFollowMin| string| Minimum fixed-rate follow value
isNeedInvite| integer| Whether private invitation is required
inviteScope| integer| Private invitation scope
symbolIds| array| Current submitted list of leader trading pairs
recommendShare| integer| Whether referral sharing is enabled
recommendShareRate| string| Referral sharing rate
inviteCode| string| Private invitation code

### Example

http
```
GET /api/v2/copy-trading/leader/config
```

1

json
```
{
  "code": 200,
  "msg": "success",
  "data": {
    "unLeadType": 1,
    "unLeadStartTime": "1717200000000",
    "unLeadEndTime": "1717286400000",
    "leadPositionType": 0,
    "tradeProtect": 1,
    "profitPeriod": 7,
    "profitRate": "0.1",
    "followAssetLowerLimit": "100",
    "fixedAmountFollowMin": "10",
    "fixedRateFollowMin": "10",
    "isNeedInvite": 1,
    "inviteScope": 2,
    "symbolIds": ["BTC-SWAP-USDT", "ETH-SWAP-USDT"],
    "recommendShare": 1,
    "recommendShareRate": "0.2",
    "inviteCode": "LEADER2026"
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-120041| Copy trading leader is not available.| The signed account is not an active leader
-1000| unknown| Unknown error

* * *

## Update Leader Config

Update Copy Trading leader settings of the current leader. Trading pairs are submitted through `symbolIds` together with other settings.

### Request Weight

`1`

### Request URL

`PUT /api/v2/copy-trading/leader/config`

### Parameters

The request body uses JSON.

Field| Type| Mandatory| Description
---|---|---|---
unLeadType| integer| YES| `0` no cool-down period, `1` custom cool-down period
unLeadStartTime| LONG| NO| Cool-down start time, epoch millis
unLeadEndTime| LONG| NO| Cool-down end time, epoch millis
leadPositionType| integer| YES| Leader position type: `-1` all, `0` cross, `1` isolated
tradeProtect| integer| YES| Trade protection switch
profitPeriod| integer| YES| Profit sharing period: `1` daily, `7` weekly
profitRate| DECIMAL| YES| Profit sharing rate
followAssetLowerLimit| DECIMAL| YES| Minimum follower asset
fixedAmountFollowMin| DECIMAL| YES| Minimum fixed-amount follow value
fixedRateFollowMin| DECIMAL| YES| Minimum fixed-rate follow value
isNeedInvite| integer| YES| Whether private invitation is required
inviteScope| integer| YES| Private invitation scope
symbolIds| ARRAY| YES| Full submitted list of leader trading pairs
recommendShare| integer| NO| Whether referral sharing is enabled; omit to keep unchanged
recommendShareRate| DECIMAL| NO| Referral sharing rate, up to 8 decimal places
inviteCode| string| NO| Private invitation code, processed only when `isNeedInvite=1`

### Rules

  * When `unLeadType=1`, `unLeadEndTime` must be provided, must not be `0`, and must be greater than or equal to `unLeadStartTime`; when `unLeadType=0`, the server resets both cool-down timestamps to `0`.
  * `profitPeriod` only supports `1` and `7`.
  * `profitRate`, `followAssetLowerLimit`, `fixedAmountFollowMin`, and `fixedRateFollowMin` must satisfy the current leader level configuration in addition to field range and precision limits; the `profitRate` range may also depend on the private-invitation and custom profit-sharing state.
  * A leader that is currently private and has configured a custom profit-sharing ratio cannot switch to public mode.
  * `symbolIds` is the full submitted list. Any currently available leader trading pair omitted from the list is treated as a pair to disable. A trading pair with active lead orders cannot be disabled.
  * Omitting `recommendShare` means keeping the referral sharing switch unchanged. When `recommendShare=1`, `recommendShareRate` must be greater than `0` and less than or equal to `1`.
  * `inviteCode` is processed only when `isNeedInvite=1`. If provided, it must be 6 to 10 characters long, must not contain Chinese characters, and must pass sensitive-word and uniqueness checks.
  * A read-only API Key is rejected when calling this write endpoint.

### Response

On success, `data` is `null`.

### Example

http
```
PUT /api/v2/copy-trading/leader/config
```

1

json
```
{
  "unLeadType": 1,
  "unLeadStartTime": 1717200000000,
  "unLeadEndTime": 1717286400000,
  "leadPositionType": 0,
  "tradeProtect": 1,
  "profitPeriod": 7,
  "profitRate": "0.1",
  "followAssetLowerLimit": "100",
  "fixedAmountFollowMin": "10",
  "fixedRateFollowMin": "10",
  "isNeedInvite": 1,
  "inviteScope": 2,
  "symbolIds": [
    "BTC-SWAP-USDT",
    "ETH-SWAP-USDT"
  ],
  "recommendShare": 1,
  "recommendShareRate": "0.2",
  "inviteCode": "LEADER2026"
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

Successful response:

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
-1102| Mandatory parameter ...| Required field missing or malformed
-1130| Data sent for paramter ...| Invalid range, precision, or format
-120041| Copy trading leader is not available.| The signed account is not an active leader
-120047| Leader does not exist.| Leader does not exist
-120067| Copy trading level config not found.| Level config not found
-120072| Copy trading leader config is invalid.| Leader config business parameter is invalid, such as level limits, profit sharing rate, or referral sharing rate not meeting requirements
-120073| Unable to switch invite setting.| A private leader with a custom profit-sharing ratio cannot switch to public mode
-120078| unLeadStartTime or unLeadEndTime is invalid.| Cool-down time window is invalid
-32090| Trading pair change is not allowed.| The trading pair to disable still has active lead orders
-32093| Copy trading position type cannot be changed.| Current actual positions do not allow switching the position type
-120510| Invite code already exists.| Invitation code already exists
-120511| Invite code contains sensitive content.| Invitation code contains sensitive content
-120512| Invite code is invalid.| Invitation code format is invalid
-1000| unknown| Unknown error

* * *

## My Followers

Query the current followers of the current leader.

### Request Weight

`1`

### Request URL

`GET /api/v2/copy-trading/leader/followers`

### Parameters

Name| Location| Type| Mandatory| Default| Description
---|---|---|---|---|---
page| query| LONG| NO| `1`| Page number, starting from 1
size| query| LONG| NO| `10`| Page size

### Response

`data` is a page object:

Field| Type| Description
---|---|---
pages| string| Total pages
total| string| Total records
list| array| Follower list

`data.list[]` fields:

Field| Type| Description
---|---|---
followerNickname| string| Masked follower display name
followAmountLimit| string| Total follow investment, in USDT
totalFollowMargin| string| Accumulated follow principal
totalProfit| string| Accumulated follow profit, in USDT
followRunningMills| string| Running duration, in milliseconds

### Example

http
```
GET /api/v2/copy-trading/leader/followers?page=1&size=10
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
        "followerNickname": "****644",
        "followAmountLimit": "880",
        "totalFollowMargin": "0",
        "totalProfit": "0",
        "followRunningMills": "61200000"
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

### Errors

code| msg| Description
---|---|---
200| success| Success
-1130| Data sent for paramter ...| Invalid `page` or `size`
-120041| Copy trading leader is not available.| The signed account is not an active leader
-1000| unknown| Unknown error

* * *

## Remove Follower

Remove one follower of the current leader.

### Request Weight

`1`

### Request URL

`DELETE /api/v2/copy-trading/leader/followers/{followerUserId}`

### Parameters

Name| Location| Type| Mandatory| Description
---|---|---|---|---
followerUserId| path| LONG| YES| User ID of the follower to remove. It must be greater than or equal to `1`

### Response

On success, `data` is `null`.

### Example

http
```
DELETE /api/v2/copy-trading/leader/followers/123456789
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
-1130| Data sent for paramter 'followerUserId' is not valid.| Invalid `followerUserId`
-120047| Leader does not exist.| Leader does not exist
-32045| Copy trading follower not found.| Follow relationship not found
-120055| The follower currently has copy position, cannot be removed.| The follower currently has copy positions and cannot be removed
-1000| unknown| Unknown error
