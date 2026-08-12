# Account & Trades (v2)

REST **v2** under `/api/v2/account` for **spot-relevant** account flows (shared with contract accounts where the same key applies). U-margined **futures** v2: Account & Trades (v2).

## Get account balance flow (USER_DATA)

  * `GET /api/v2/account/balance-flow`

### Weight：5

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
accountType| STRING| NO| `MAIN` or `FUTURES` (default `MAIN`)
coin| STRING| NO| token id
flowType| STRING| NO| flow type **enum name** (e.g. `USER_ACCOUNT_TRANSFER`); same naming as in `data[].flowType`
fromId| LONG| NO| from id
endId| LONG| NO| end id
startTime| LONG| NO| start (ms)
endTime| LONG| NO| end (ms)
limit| INT| NO| default `20`, min `1`, max `1000`
timestamp| LONG| YES| —
recvWindow| LONG| NO| —

### flowType Enum Values

Enum name| Description
---|---
`TRADE`| Trade
`FEE`| Trading fee
`TRANSFER`| General transfer flow
`DEPOSIT`| Deposit
`PNL`| Contracts PnL
`LIQUIDATION`| Liquidation
`FUNDING_SETTLEMENT`| Funding fee settlement
`OTC_BUY_COIN`| OTC buy coin
`OTC_SELL_COIN`| OTC sell coin
`USER_ACCOUNT_TRANSFER`| User account transfer

### Response

json
```
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "id": "539870570957903104",
      "accountType": "MAIN",
      "coin": "BTC",
      "symbol": "BTCUSDT",
      "flowType": "USER_ACCOUNT_TRANSFER",
      "flowName": "Transfer",
      "change": "-12.5",
      "total": "379.624059937852365",
      "voucherType": 0,
      "deductionAmount": "",
      "created": "1579093587214"
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

New response fields:

Name| Type| Description
---|---|---
voucherType| INT| Voucher type. Common deduction types: `2` cash voucher, `3` trial voucher, `7` copy-trading trial voucher, and `8` lead-trading trial voucher. `0` means no applicable voucher is associated with the flow
deductionAmount| STRING| Voucher amount deducted by this flow, preserving decimal precision as a string; empty when no deduction applies

> In the response, `id` and `created` are returned as **string** -typed numbers in JSON, consistent with other v2 list APIs. The legacy v1 flow list `GET /api/v1/account/balanceFlow` remains available; the v2 route uses string **accountType** and **flowType** and omits deprecated numeric-only fields in the public reference. See SIGNED for request signing.
