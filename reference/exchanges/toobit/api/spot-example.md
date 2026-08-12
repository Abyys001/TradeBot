# Examples

> For general basic information, please refer to the Basic Information documentation.

## Order Rate Limits

  * When the order count exceeds the limit, you will receive a 429 error without the Retry-After header. Please check the Order Rate Limit rules using `GET` `api/v1/exchangeInfo` and wait for reactivation accordingly.
  * **The order rate limit is counted against each account.**

## Websocket Limits

  * WebSocket connections have a limit of 5 incoming messages per second. A message is considered:

    * A PING frame
    * A PONG frame
    * A JSON controlled message (e.g. subscribe, unsubscribe)
  * If the user sends more messages than the limit, the connection will be disconnected. IPs that are repeatedly disconnected may be blocked by the server.

## SIGNED Endpoint Examples

### SIGNED Endpoint Examples for POST /api/v1/spot/order - HMAC Keys

Here is a step-by-step example of how to send a vaild signed payload from the Linux command line using `echo`, `openssl`, and `curl`.

Key| Value
---|---
apiKey| SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq
secretKey| 30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2
Parameter| Value
---|---
symbol| BTCUSDT
side| SELL
type| LIMIT
timeInForce| GTC
quantity| 1
price| 4000
recvWindow| 100000
timestamp| 1668481902307

#### Example 1: As a query string

> Example 1:

> HMAC SHA256 signature:

bash
```
$ echo -n "symbol=BTCUSDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468
```

1
2

curl command: (HMAC SHA256)

bash
```
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" -X POST 'https://api.toobit.com/api/v1/spot/order' -d 'symbol=BTCUSDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307&signature=8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468'
```

1

  * **queryString** symbol=BTCUSDT
&side=SELL
&type=LIMIT
&timeInForce=GTC
&quantity=1
&price=400
&recvWindow=100000
&timestamp=1668481902307

#### Example 2: As a request body

Example 2: HMAC SHA256 signature:

bash
```
$ echo -n "symbol=BTCUSDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468
```

1
2

curl command: (HMAC SHA256)

bash
```
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" -X POST 'https://api.toobit.com/api/v1/spot/order' -d 'symbol=BTCUSDT&side=SELL&type=LIMIT&timeInForce=GTC&quantity=1&price=400&recvWindow=100000&timestamp=1668481902307&signature=8420e499e71cce4a00946db16543198b6bcae01791bdb75a06b5a7098b156468'
```

1

  * **requestBody** symbol=BTCUSDT
&side=SELL
&type=LIMIT
&timeInForce=GTC
&quantity=1
&price=400
&recvWindow=100000
&timestamp=1668481902307

#### Example 3: Mixed query string and request body

  * **queryString** : `symbol=BTCUSDT&side=SELL&type=LIMIT&timeInForce=GTC`
  * **requestBody** : `quantity=1&price=400&recvWindow=100000&timestamp=1668481902307`

Example 3: HMAC SHA256 signature:

bash
```
$ echo -n "symbol=BTCUSDT&side=SELL&type=LIMIT&timeInForce=GTCquantity=1&price=400&recvWindow=10000000&timestamp=1668481902307" | openssl dgst -sha256 -hmac "30lfjDT51iOG1kYZnDoLNynOyMdIcmQyO1XYfxzYOmQfx9tjiI98Pzio4uhZ0Uk2"
(stdin)= 59ef0b2085ebb99cca5b6445c202d99add17be2d5d1861c0f4aa17bc785ac4d5
```

1
2

curl command: (HMAC SHA256)

bash
```
$ curl -H "X-BB-APIKEY: SRQGN9M8Sr87nbfKsaSxm33Y6CmGVtUu9Erz73g9vHFNn36VROOKSaWBQ8OSOtSq" -X POST 'https://api.toobit.com/api/v1/spot/order?symbol=BTCUSDT&side=SELL&type=LIMIT&timeInForce=GTC' -d 'quantity=1&price=400&recvWindow=10000000&timestamp=1668481902307&signature=59ef0b2085ebb99cca5b6445c202d99add17be2d5d1861c0f4aa17bc785ac4d5'
```

1

Note that the signature is different in example 3. There is no & between "GTC" and "quantity=1".
