# Examples

> For general basic information, please refer to the Basic Information documentation.

## Rest API Information

  * All data types adopt definition in JAVA.

## Websocket Information

  * Base Url: **wss://stream.toobit.com**

## Rate Limits

  * Users who repeatedly trigger rate limits, or who continue sending requests after receiving 429, may have their IP banned (error code 418)
  * IP bans are tracked, and ban duration is adjusted based on repeated rate limit triggers. The duration can range from 2 minutes to 3 days

## SIGNED Endpoint Examples

### SIGNED Endpoint Examples for POST /api/v1/futures/order

Here is a step-by-step example of how to send a vaild signed payload from the Linux command line using echo, openssl, and curl.

Key| Value
---|---
apiKey| SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq
secretKey| 30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2
Parameter| Value
---|---
symbol| BTC-SWAP-USDT
side| SELL
type| LIMIT
timeInForce| GTC
quantity| 1
price| 400
recvWindow| 100000
timestamp| 1668481902307

#### Example 1: As a query string

bash
```
Example 1:
HMAC SHA256 signature:
$ echo -n "symbol=BTC-SWAP-USDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468
```

1
2
3
4

bash
```
curl command:
(HMAC SHA256)
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" -X POST 'https://api.toobit.com/api/v1/futures/order' -d 'symbol=BTC-SWAP-USDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307&signature=8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468'
```

1
2
3

  * **queryString** symbol=BTC-SWAP-USDT
&side=SELL
&type=LIMIT
&timeInForce=GTC
&quantity=1
&price=400
&recvWindow=100000
&timestamp=1668481902307

#### Example 2: As a request body

bash
```
Example 2:
HMAC SHA256 signature:
$ echo -n "symbol=BTC-SWAP-USDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468
```

1
2
3
4

bash
```
curl command:
(HMAC SHA256)
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" -X POST 'https://api.toobit.com/api/v1/spot/order' -d 'symbol=BTC-SWAP-USDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307&signature=8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468'
```

1
2
3

  * **requestBody** symbol=BTC-SWAP-USDT
&side=SELL
&type=LIMIT
&timeInForce=GTC
&quantity=1
&price=400
&recvWindow=100000
&timestamp=1668481902307

#### Example 3: Mixed query string and request body

  * **queryString** : `symbol=BTC-SWAP-USDT&side=SELL&type=LIMIT&timeInForce=GTC`
  * **requestBody** : `quantity=1&price=400&recvWindow=10000000&timestamp=1668481902307`

bash
```
Example 3:
HMAC SHA256 signature:
$ echo -n "symbol=BTC-SWAP-USDT&side=SELL&type=LIMIT&timeInForce=GTCquantity=1&price=400&recvWindow=10000000&timestamp=1668481902307" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 59ef0b2085ebb99cca5b6445c202d99add17be2d5d1861c0f4aa17bc785ac4d5
```

1
2
3
4

bash
```
curl command:
(HMAC SHA256)
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" -X POST 'https://api.toobit.com/api/v1/spot/order?symbol=BTC-SWAP-USDT&side=SELL&type=LIMIT&timeInForce=GTC' -d 'quantity=1&price=400&recvWindow=10000000&timestamp=1668481902307&signature=59ef0b2085ebb99cca5b6445c202d99add17be2d5d1861c0f4aa17bc785ac4d5'
```

1
2
3

Note that the signature is different in example 3.There is no & between "GTC" and "quantity=1".
