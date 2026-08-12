# Affiliate Endpoints

Affiliate OpenAPI endpoints use the `/api/v1/agent` prefix. All endpoints require a signed API Key and are available only to accounts with affiliate access.

  * All endpoints use `GET`, and business parameters are sent in the query string.
  * All endpoints require a signed request. For shared signing rules, see Basic Information.
  * All endpoints have a rate limit of 5 requests per second and a request weight of `1`.
  * Unless otherwise specified, all time fields are millisecond UNIX timestamps.
  * For paginated endpoints, `pageIndex` defaults to `1`, and `pageSize` defaults to `100` with a valid range of `100` to `200`.

## Common Signed Parameters

Name| Type| Mandatory| Description
---|---|---|---
recvWindow| LONG| NO| Request validity window in milliseconds. Defaults to `5000` if omitted
timestamp| LONG| YES| Request timestamp in milliseconds
signature| STRING| YES| HMAC SHA256 signature generated with your API Secret

## Common Response Format

Successful responses use the following wrapper:

json
```
{
  "code": 200,
  "msg": "success",
  "data": {}
}
```

1
2
3
4
5

For paginated endpoints, `data` is a page object:

Field| Type| Description
---|---|---
pages| string| Total pages
total| string| Total records
list| array| Current page items

## Common Error Codes

code| msg| Description
---|---|---
200| success| Success
-1001| Internal error.| Internal error or downstream service error
-1003| Too many requests...| Affiliate endpoint rate limit exceeded
-1020| This operation is not supported.| The current API Key does not support the operation, for example a read-only API Key applying for export
-1021| Timestamp for this request is outside of the recvWindow.| Timestamp is outside the valid request window
-1022| Signature for this request is not valid.| Invalid signature
-1115| Invalid timeInForce.| Invalid time range. Affiliate endpoints also use this code for time-window validation failures
-1130| Data sent for paramter ... is not valid.| Invalid parameter
-1153| User not exist| User does not exist

* * *

## Query Invited Users

Query basic information about users directly or indirectly invited by the current affiliate. You can filter by registration time, UID, or referral code.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/inviteUserList`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
pageIndex| INTEGER| NO| `1`| Page number, starting from 1
pageSize| INTEGER| NO| `100`| Page size, from `100` to `200`
startTime| LONG| NO| `0`| Registration start time. When used with `endTime`, the time span cannot exceed 30 days
endTime| LONG| NO| `0`| Registration end time
uid| LONG| NO| `0`| Invited user UID
referralCode| STRING| NO| -| Referral code

### Response

`data.list[]` fields:

Field| Type| Description
---|---|---
uid| long| Invited user UID
ownInviteCode| string| The invited user's own invite code. Returned for affiliates and may be empty for regular users
inviteSid| long| Parent UID
invitationCode| string| Parent invite code used at registration
registerTime| long| Registration time in milliseconds
directInvitation| boolean| `true` direct invite, `false` indirect invite
deposit| boolean| `true` deposited, `false` not deposited
balanceVolume| string| Net asset value in USDT
trade| boolean| `true` traded, `false` not traded
kycResult| boolean| `true` KYC passed, `false` KYC not passed
level| integer| User level
spotCommissionRatio| string| Spot commission ratio
contractCommissionRatio| string| Futures commission ratio

* * *

## Query Commission Details

Query hourly commission details for invited users. Only data from the last 365 days is available, and each request can cover at most 30 days.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/commissionDataList`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
uid| LONG| NO| `0`| Invited user UID. Omit or send `0` to disable UID filtering
pageIndex| INTEGER| NO| `1`| Page number, starting from 1
pageSize| INTEGER| NO| `100`| Page size, from `100` to `200`
startTime| LONG| YES| -| Statistics start time in milliseconds
endTime| LONG| YES| -| Statistics end time in milliseconds

### Response

`data.list[]` fields:

Field| Type| Description
---|---|---
uid| long| Invited user UID
commissionTime| long| Commission distribution time
tradingVolume| string| Total spot and futures trading volume in USDT
commissionVolume| string| Total commission amount in USDT
spotTradingVolume| string| Spot trading volume in USDT
swapTradingVolume| string| Futures trading volume in USDT
spotCommissionVolume| string| Spot commission amount in USDT
swapCommissionVolume| string| Futures commission amount in USDT

* * *

## Query Commission Summary

Query commission summary by invited user. Only data from the last 365 days is available, and each request can cover at most 30 days.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/commissionDataInfo`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
uid| LONG| NO| `0`| Invited user UID. Omit or send `0` to disable UID filtering
pageIndex| INTEGER| NO| `1`| Page number, starting from 1
pageSize| INTEGER| NO| `100`| Page size, from `100` to `200`
startTime| LONG| YES| -| Statistics start time in milliseconds
endTime| LONG| YES| -| Statistics end time in milliseconds
referralCode| STRING| NO| -| Invite code of the invited user

### Response

`data.list[]` fields:

Field| Type| Description
---|---|---
uid| long| Invited user UID
tradingVolume| string| Total spot and futures trading volume in USDT
commissionVolume| string| Total commission amount in USDT
spotTradingVolume| string| Spot trading volume in USDT
swapTradingVolume| string| Futures trading volume in USDT
spotCommissionVolume| string| Spot commission amount in USDT
swapCommissionVolume| string| Futures commission amount in USDT
fee| string| Total fee
netFee| string| Net fee
spotFee| string| Spot fee
contractFee| string| Futures fee
spotNetFee| string| Spot net fee
contractNetFee| string| Futures net fee

* * *

## Check Invite Relation

Check whether the specified UID has an invite relationship with the current affiliate, and return the user's affiliate-related profile.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/inviteRelationCheck`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
uid| LONG| YES| -| Invited user UID

### Response

`data` fields:

Field| Type| Description
---|---|---
uid| long| Invited user UID
inviteSid| long| Parent UID
registerTime| long| Registration time in milliseconds
directInvitation| boolean| `true` direct invite, `false` indirect invite
deposit| boolean| `true` deposited, `false` not deposited
kycResult| boolean| `true` KYC passed, `false` KYC not passed
balanceVolume| string| Net asset value in USDT
trade| boolean| `true` traded, `false` not traded
level| integer| User level
spotCommissionRatio| string| Spot commission ratio
contractCommissionRatio| string| Futures commission ratio

* * *

## Query Deposit Details

Query deposit details for an invited user. Only data from the last 90 days is available, and each request can cover at most 30 days.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/depositDetailList`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
uid| LONG| YES| -| Invited user UID
pageIndex| INTEGER| NO| `1`| Page number, starting from 1
pageSize| INTEGER| NO| `100`| Page size, from `100` to `200`
startTime| LONG| YES| -| Query start time in milliseconds
endTime| LONG| YES| -| Query end time in milliseconds

### Response

`data.list[]` fields:

Field| Type| Description
---|---|---
uid| long| Invited user UID
directInvitation| boolean| `true` direct invite, `false` indirect invite
bizType| integer| Business type. `1` means deposit
bizTime| long| Deposit time in milliseconds
tokenId| string| Token
quantity| string| Deposit quantity

* * *

## Query Sub-Affiliate Data

Query business metrics for sub-affiliates or invited users in the statistics window. If no time range is sent, the default window is the last 30 days. Only data from the last 90 days is available, and each request can cover at most 30 days.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/querySubAgentData`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
uid| LONG| NO| `0`| Sub-affiliate or invited user UID. Omit or send `0` to disable UID filtering
pageIndex| INTEGER| NO| `1`| Page number, starting from 1
pageSize| INTEGER| NO| `100`| Page size, from `100` to `200`
startTime| LONG| NO| `0`| Query start time in milliseconds
endTime| LONG| NO| `0`| Query end time in milliseconds

### Response

`data.list[]` fields:

Field| Type| Description
---|---|---
uid| long| User UID
email| string| Masked email
phone| string| Masked phone number
directInvitation| boolean| `true` direct invite, `false` indirect invite
newReferees| integer| New referrals in the query window
firstTrade| integer| First-trade user count
branchDeposits| string| Subtree deposit amount
branchTrading| integer| Subtree trading user count
branchTradingVol| string| Subtree trading volume
level| integer| Relative level
spotCommissionRatio| string| Spot commission ratio
contractCommissionRatio| string| Futures commission ratio
commissionAmount| string| Commission amount

* * *

## Query Spot Orders

Query spot orders for users in the affiliate hierarchy. If no time range is sent, the default window is the last 7 days. Only data from the last 180 days is available, and each request can cover at most 30 days.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/spotOrdersList`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
parentAccountId| LONG| YES| -| Parent account ID. Send `0` when querying only by `subAccountId`
subAccountId| LONG| YES| -| Sub-account ID. Send `0` when querying only by `parentAccountId`
fromId| LONG| NO| `0`| Start cursor ID
endId| LONG| NO| `0`| End cursor ID
startTime| LONG| NO| `0`| Query start time in milliseconds
endTime| LONG| NO| `0`| Query end time in milliseconds
limit| INTEGER| NO| `100`| Number of records to return, from `1` to `200`

`parentAccountId` and `subAccountId` cannot both be `0`.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
orderId| long| Order ID
userId| long| User ID
mark| string| Mark field
symbolId| string| Symbol ID
side| integer| Side. `1` buy, `2` sell
time| long| Order time in milliseconds
orderType| integer| Order type. `0` limit, `2` market
origQty| string| Original quantity
executedQty| string| Executed quantity
executedAmount| string| Executed amount in USDT
avgPrice| string| Average execution price
deductedFee| string| Deducted fee
isAgent| boolean| Whether the user is an affiliate
childUserId| long| Child user ID

* * *

## Query Futures Orders

Query futures orders for users in the affiliate hierarchy. If no time range is sent, the default window is the last 7 days. Only data from the last 180 days is available, and each request can cover at most 30 days.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/futuresOrdersList`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
parentAccountId| LONG| YES| -| Parent account ID. Send `0` when querying only by `subAccountId`
subAccountId| LONG| YES| -| Sub-account ID. Send `0` when querying only by `parentAccountId`
fromId| LONG| NO| `0`| Start cursor ID
endId| LONG| NO| `0`| End cursor ID
startTime| LONG| NO| `0`| Query start time in milliseconds
endTime| LONG| NO| `0`| Query end time in milliseconds
limit| INTEGER| NO| `100`| Number of records to return, from `1` to `200`

`parentAccountId` and `subAccountId` cannot both be `0`.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
orderId| long| Order ID
userId| long| User ID
vipLevel| string| VIP level
mark| string| Mark field
symbolId| string| Futures symbol ID
marginType| string| Margin mode
time| long| Order time in milliseconds
orderSide| string| Order side
price| string| Order price
origQty| string| Original quantity
executedQty| string| Executed quantity
avgPrice| string| Average execution price
pnl| string| Profit and loss
deductedFee| string| Deducted fee
isAgent| boolean| Whether the user is an affiliate
feeTokenId| string| Fee token ID
childUserId| long| Child user ID

* * *

## Query Futures Positions

Query futures positions for users in the affiliate hierarchy.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/futuresPositionsList`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
parentAccountId| LONG| YES| -| Parent account ID. Send `0` when querying only by `subAccountId`
subAccountId| LONG| YES| -| Sub-account ID. Send `0` when querying only by `parentAccountId`
fromId| LONG| NO| `0`| Start cursor ID
endId| LONG| NO| `0`| End cursor ID
limit| INTEGER| NO| `100`| Number of records to return, from `1` to `200`

`parentAccountId` and `subAccountId` cannot both be `0`.

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
positionId| long| Position ID
userId| long| User ID
vipLevel| string| VIP level
mark| string| Mark field
symbolId| string| Futures symbol ID
marginType| string| Margin mode
leverage| string| Leverage
isLong| integer| Position direction. `1` long, `0` short
total| string| Total position size
avgPrice| string| Average entry price
margin| string| Margin
riskRate| string| Risk rate
unrealisedPnl| string| Unrealized PnL
profitRate| string| Profit rate
liquidationPrice| string| Liquidation price
childUserId| long| Child user ID

* * *

## Query Invite Commission Detail

Query commission relationship and accumulated commission information for a specified invited user.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/invite-commission-detail`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
uid| LONG| YES| -| Invited user UID
startTime| LONG| NO| `0`| Query start time in milliseconds
endTime| LONG| NO| `0`| Query end time in milliseconds

### Response

`data` fields:

Field| Type| Description
---|---|---
uid| long| Invited user UID
joinTime| string| Commission relationship start time as a millisecond timestamp string
inviteeRebateRate| string| Commission rate generated by this user, in decimal form. For example, `0.01` means 1%
totalCommission| string| Accumulated commission amount. May contain multiple tokens
firstTradeTime| string| First trade time as a millisecond timestamp string. Empty string if the user has not traded
level| string| User level, for example `Lv1`
volMonth| string| Current-month trading volume in USDT
accFee| string| Accumulated trading fee
region| string| Country or region code
affiliateCode| string| Invite code

* * *

## Apply for Trade Detail Export

Create an export task for affiliate trade details. This endpoint creates a task and does not support read-only API Keys. By default it exports the last 7 days of data. The maximum query window is 180 days, and up to 10,000 records can be exported.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/user/export`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
beginTime| STRING| NO| Start date of the last 7 days| Start date in `YYYYMMdd` format, for example `20210623`
endTime| STRING| NO| Current date| End date in `YYYYMMdd` format
uid| LONG| NO| `0`| Trading user UID

### Response

Field| Type| Description
---|---|---
data| boolean| `true` export task submitted, `false` export failed

* * *

## Query Export Tasks

Query trade detail export tasks that have already been requested. Download tasks are usually valid for 7 days.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/export-list`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
limit| INTEGER| NO| `50`| Number of records to return, from `1` to `200`
fromId| LONG| NO| `0`| Start cursor ID
endId| LONG| NO| `0`| End cursor ID
type| INTEGER| NO| `0`| Export type. `0` means trade details

### Response

`data` is an array. Each item contains:

Field| Type| Description
---|---|---
downToken| string| Unique download task token
applyTime| long| Apply time in milliseconds
filterStartTime| long| Export filter start time
filterEndTime| long| Export filter end time
status| integer| Task status. `0` applying, `1` completed, `2` canceled
type| integer| Export type. `0` means trade details

* * *

## Get Export Download URL

Get the download URL for a completed export task. The download URL is valid for 60 seconds. Call this endpoint again after expiration to get a fresh URL.

### Request Weight

`1`

### Request URL

`GET /api/v1/agent/export-url`

### Parameters

Name| Type| Mandatory| Default| Description
---|---|---|---|---
downToken| STRING| NO| -| Unique download task token. Recommended parameter
token| STRING| NO| -| Compatibility parameter. Used when `downToken` is omitted

At least one of `downToken` and `token` must be sent.

### Response

Field| Type| Description
---|---|---
data| string| Download URL
