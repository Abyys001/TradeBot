# Wallet Endpoints

## Withdraw (USER_DATA)

  * `POST /api/v1/account/withdraw`

Submit a withdraw request.

**Weight** : 1

### Response

json
```
{
  "success": true,
  "needBrokerAudit": false, // Do you need a brokerage review?
  "id": "423885103582776064", // Withdrawal successful order id
  "refuseReason": "" // failure rejection reason
}
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
coin| STRING| YES| asset
clientOrderId| LONG| YES| client id for withdraw
address| STRING| YES| Recipient identifier. When `addressType` is empty or `BLOCK_CHAIN`, this is an on-chain withdrawal address (Note: the on-chain withdrawal address must be maintained in the common address list on the PC or APP). When `addressType` is `PHONE_NUMBER`, this is the phone number used for an internal transfer and must be formatted as `country code phone number` with a space between the country code and phone number, for example `86 13812345678`. When `addressType` is `EMAIL` or `UID`, this is the email address or UID used for an internal transfer
addressExt| STRING| NO| tag
quantity| DECIMAL| YES| Number of coin withdrawals
chainType| STRING| NO| chain type, The chainType of USDT is OMNI ERC20 TRC20 respectively, and the default is OMNI
addressType| STRING| NO| Recipient identifier type. Defaults to `BLOCK_CHAIN` when empty. Supported enum names: `BLOCK_CHAIN`, `PHONE_NUMBER`, `EMAIL`, `UID`. Numeric enum values and lowercase names are not supported. `PHONE_NUMBER`, `EMAIL`, and `UID` indicate internal transfers
vaspCode| STRING| NO| vasp code
targetPersonFirstName| STRING| NO| target person first name
targetPersonLastName| STRING| NO| target person last name

### Request Examples

On-chain withdrawal:

shell
```
POST /api/v1/account/withdraw
Content-Type: application/x-www-form-urlencoded

coin=USDT&clientOrderId=123456&address=0x815bF1c3cc0f49b8FC66B21A7e48fCb476051209&quantity=10&chainType=ERC20&addressType=BLOCK_CHAIN&timestamp=1780000000000&signature=<signature>
```

1
2
3
4

Internal transfer by phone number:

shell
```
POST /api/v1/account/withdraw
Content-Type: application/x-www-form-urlencoded

clientOrderId=123457&address=86 13812345678&coin=USDT&quantity=10&addressType=PHONE_NUMBER&timestamp=1780000000000&signature=<signature>
```

1
2
3
4

> Use `clientOrderId=123457&address=86 13812345678&coin=USDT&quantity=10&addressType=PHONE_NUMBER&timestamp=1780000000000` as the payload when calculating `signature`. The `address` value contains a normal space between the country code and phone number.

Internal transfer by email:

shell
```
POST /api/v1/account/withdraw
Content-Type: application/x-www-form-urlencoded

clientOrderId=123458&address=user@example.com&coin=USDT&quantity=10&addressType=EMAIL&timestamp=1780000000000&signature=<signature>
```

1
2
3
4

Internal transfer by UID:

shell
```
POST /api/v1/account/withdraw
Content-Type: application/x-www-form-urlencoded

clientOrderId=123459&address=10000001&coin=USDT&quantity=10&addressType=UID&timestamp=1780000000000&signature=<signature>
```

1
2
3
4

## Withdrawal records (USER_DATA)

  * `GET /api/v1/account/withdrawOrders (HMAC SHA256)`

**Weight** : 5

### Response

json
```
[
    {
        "time": "1536232111669",
        "id ": "90161227158286336",
        "accountId": "517256161325920",
        "coinId ": "BHC",
        "coinName": "BHC",
        "address": "0x815bF1c3cc0f49b8FC66B21A7e48fCb476051209",
        "addressExt": "address tag",
        "quantity": "14", // Withdrawal amount
        "arriveQuantity": "14", // Amount received
        "statusCode": "PROCESSING_STATUS",
        "status": 3,
        "txId ": "",
        "txIdUrl ": "",
        "walletHandleTime": "1536232111669",
        "feeCoinId ": "BHC",
        "feeCoinName ": "BHC",
        "fee": "0.1",
        "requiredConfirmTimes ": 0, // Number of confirmation requests
        "confirmTimes ": 0, // number of confirmations
        "kernelId": "", // Exclusive to BEAM and GRIN
        "isInternalTransfer": false // Whether internal transfer
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

### `status` enum

`status` is the numeric withdrawal order status. `statusCode` is the corresponding status identifier.

status| statusCode| Description
---|---|---
0| `WITHDRAWAL_STATUS_UNKNOWN`| Withdrawal in progress
1| `BROKER_AUDITING_STATUS`| Under review
2| `BROKER_REJECT_STATUS`| Withdrawal rejected/returned
3| `AUDITING_STATUS`| Withdrawal in progress
6| `WITHDRAWAL_SUCCESS_STATUS`| Withdrawal successful
7| `WITHDRAWAL_FAILURE_STATUS`| Withdrawal failed
9| `WITHDRAWAL_CANCELLED_STATUS`| Withdrawal cancelled
10| `WAIT_MERCHANT_PASS`| Pending unfreeze
11| `APPLY_CANCEL`| Cancellation requested
Other values| -| Withdrawal in progress

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
coin| STRING| NO| asset
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
fromId| LONG| NO| From which OrderId to start fetching
withdrawOrderId| LONG| NO| Withdrawal order ID
limit| INT| NO| default 500; maximum 1000
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

## Deposit Address (USER_DATA)

  * `GET /api/v1/account/deposit/address (HMAC SHA256)`

Fetch deposit address with network.

**Weight** : 1

### Response

json
```
    {
        "canDeposit": false, //Is it possible to recharge
        "address": "0x815bF1c3cc0f49b8FC66B21A7e48fCb476051209",
        "addressExt": "address tag",
        "minQuantity": "100", //minimum amount
        "requiredConfirmTimes ": 1, //Arrival confirmation number
        "canWithdrawConfirmNum ": 12, //Withdrawal confirmation number
        "chainType": "ERC20"
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
coin| STRING| YES| asset
chainType| STRING| YES| chain type, The chainType of USDT is OMNI ERC20 TRC20 respectively, and the default is OMNI

## Deposit History (USER_DATA)

  * `GET /api/v1/account/depositOrders (HMAC SHA256)`

**Weight** : 5

### Response

json
```
[
  {
        "id": 100234,
        "coin": "EOS",
        "coinName": "EOS",
        "address": "deposit2bb",
        "addressTag": "19012584",
        "fromAddress": "clarkkent",
        "fromAddressTag": "19029901",
        "time": 1499865549590,
        "quantity": "1.01",
        "status": "2", // 2=SUCCESS, 11=REJECT, 12=AUDIT
        "statusCode": "DEPOSIT_CAN_WITHDRAW",
        "requiredConfirmTimes": "5",
        "confirmTimes": "5",
        "txId": "98A3EA560C6B3336D348B6C83F0F95ECE4F1F5919E94BD006E5BF3BF264FACFC",
        "txIdUrl": ""
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

### Parameters

Name| Type| Mandatory| Description
---|---|---|---
coin| STRING| NO| asset
startTime| LONG| NO| start timestamp
endTime| LONG| NO| end timestamp
fromId| LONG| NO| From which Id to start crawling
limit| INT| NO| Default 500; Max 1000
recvWindow| LONG| NO| recv window
timestamp| LONG| YES| Timestamp

Notes:

  * If fromId is set, it will filter the orders smaller than id. Otherwise, the most recent order information will be returned.
