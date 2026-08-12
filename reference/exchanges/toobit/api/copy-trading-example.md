# Examples

> For general basic information, please refer to the Basic Information documentation.

## Rest API Information

  * All data types are defined by Java data types.
  * Copy Trading OpenAPI endpoints only support data and settings of the leader or follower bound to the current API Key.
  * All Copy Trading endpoints require OpenAPI V2 signed access. The API Key account type must be `COPY_TRADING`.
  * Query endpoints support read-only API Keys. Write endpoints do not support read-only API Keys.

## LIMITS

  * The `REQUEST_WEIGHT` of each Copy Trading endpoint is `1`.
  * Users who repeatedly violate rate limits, or who continue sending requests after receiving 429, will have their IP banned with error code 418.
  * IP bans are tracked and adjusted based on repeated violations. Ban duration ranges from 2 minutes to 3 days.

## SIGNED Endpoint Examples

The following examples show how to call Copy Trading endpoints in a Linux bash environment with `echo`, `openssl`, and `curl`. `apiKey` and `secretKey` are for demonstration only.

Key| Value
---|---
apiKey| SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq
secretKey| 30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2

### GET /api/v2/copy-trading/leader/orders/current Example

Parameter| Value
---|---
recvWindow| 5000
timestamp| 1717200000000

bash
```
HMAC SHA256 signature:
$ echo -n "recvWindow=5000&timestamp=1717200000000" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88
```

1
2
3

bash
```
curl request:
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" \
  -X GET 'https://api.toobit.com/api/v2/copy-trading/leader/orders/current?recvWindow=5000&timestamp=1717200000000&signature=0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88'
```

1
2
3

### GET /api/v2/copy-trading/follower/leaders Example

Parameter| Value
---|---
recvWindow| 5000
timestamp| 1717200000000

bash
```
HMAC SHA256 signature:
$ echo -n "recvWindow=5000&timestamp=1717200000000" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88
```

1
2
3

bash
```
curl request:
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" \
  -X GET 'https://api.toobit.com/api/v2/copy-trading/follower/leaders?recvWindow=5000&timestamp=1717200000000&signature=0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88'
```

1
2
3

### PUT /api/v2/copy-trading/leader/config Example

Write endpoints do not support read-only API Keys. When the request body participates in signing, build the signature payload according to OpenAPI V2 signing rules.

Parameter| Value
---|---
recvWindow| 5000
timestamp| 1717200000000

bash
```
HMAC SHA256 signature:
$ echo -n "recvWindow=5000&timestamp=1717200000000" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88
```

1
2
3

bash
```
curl request:
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" \
  -H "Content-Type: application/json" \
  -X PUT 'https://api.toobit.com/api/v2/copy-trading/leader/config?recvWindow=5000&timestamp=1717200000000&signature=0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88' \
  -d '{
    "unLeadType": 0,
    "leadPositionType": 0,
    "tradeProtect": 1,
    "profitPeriod": 7,
    "profitRate": "10",
    "followAssetLowerLimit": "100",
    "fixedAmountFollowMin": "10",
    "fixedRateFollowMin": "1",
    "isNeedInvite": 0,
    "inviteScope": 0,
    "symbolIds": ["BTC-SWAP-USDT"]
  }'
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

### PUT /api/v2/copy-trading/follower/config Example

Write endpoints do not support read-only API Keys. When the request body participates in signing, build the signature payload according to OpenAPI V2 signing rules.

Parameter| Value
---|---
recvWindow| 5000
timestamp| 1717200000000

bash
```
HMAC SHA256 signature:
$ echo -n "recvWindow=5000&timestamp=1717200000000" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88
```

1
2
3

bash
```
curl request:
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" \
  -H "Content-Type: application/json" \
  -X PUT 'https://api.toobit.com/api/v2/copy-trading/follower/config?recvWindow=5000&timestamp=1717200000000&signature=0b54c7a90b48f1b6c5cc8170f030594f3eb3c7e6dd81b76f65e18fc76f8b1a88' \
  -d '{
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
    "followSymbolIds": "BTC-SWAP-USDT",
    "zeroSlippageSwitch": true
  }'
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
