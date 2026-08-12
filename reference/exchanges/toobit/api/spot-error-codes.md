# Error Codes

Errors consist of two parts: an error code and a message. Codes are universal, but messages can vary.

> The error JSON payload

json
```
{
  "code": -1121,
  "msg": "Invalid symbol."
}
```

1
2
3
4

## 10xx - General Server or Network issues

### -1000 UNKNOWN

  * An unknown error occurred while processing the request.

### -1001 DISCONNECTED

  * Internal error; unable to process your request. Please try again.

### -1002 UNAUTHORIZED

  * You are not authorized to execute this request.

### -1003 TOO_MANY_REQUESTS

  * Too many requests queued.
  * Too much request weight used; current limit is %s request weight per %s. Please use WebSocket Streams for live updates to avoid polling the API.
  * Way too much request weight used; IP banned until %s. Please use WebSocket Streams for live updates to avoid bans.

### -1005 NO_PERMISSION

  * No Permission

### -1006 UNEXPECTED_RESP

  * An unexpected response was received from the message bus. Execution status unknown.

### -1007 TIMEOUT

  * Timeout waiting for response from backend server. Send status unknown; execution status unknown.

### -1014 UNKNOWN_ORDER_COMPOSITION

  * Unsupported order combination.

### -1015 TOO_MANY_ORDERS

  * Reach the rate limit .Please slow down your request speed.
  * Too many new orders.
  * Too many new orders; current limit is %s orders per %s.

### -1016 SERVICE_SHUTTING_DOWN

  * This service is no longer available.

### -1020 UNSUPPORTED_OPERATION

  * This operation is not supported.

### -1021 INVALID_TIMESTAMP

  * Timestamp for this request is outside of the recvWindow.
  * Timestamp for this request was 1000ms ahead of the server's time.
  * Please check the difference between your local time and server time .

### -1022 INVALID_SIGNATURE

  * Signature for this request is not valid.

### -1023 BIND_IP_WHITE_LIST_FIRST

  * Please set IP whitelist before using API

### -1031 FEATURE_SUSPENDED

  * The feature has been suspended

## 11xx - 2xxx Request issues

### -1100 ILLEGAL_CHARS

  * Illegal characters found in a parameter.
  * Illegal characters found in parameter '%s'; legal range is '%s'.

### -1101 TOO_MANY_PARAMETERS

  * Too many parameters sent for this endpoint.
  * Too many parameters; expected '%s' and received '%s'.
  * Duplicate values for a parameter detected.

### -1102 MANDATORY_PARAM_EMPTY_OR_MALFORMED

  * A mandatory parameter was not sent, was empty/null, or malformed.
  * Mandatory parameter '%s' was not sent, was empty/null, or malformed.
  * Param '%s' or '%s' must be sent, but both were empty/null!

### -1103 UNKNOWN_PARAM

  * An unknown parameter was sent.
  * In BBEx Open Api , each request requires at least one parameter. {Timestamp}.

### -1104 UNREAD_PARAMETERS

  * Not all sent parameters were read.
  * Not all sent parameters were read; read '%s' parameter(s) but was sent '%s'.

### -1105 PARAM_EMPTY

  * A parameter was empty.
  * Parameter '%s' was empty.

### -1106 PARAM_NOT_REQUIRED

  * A parameter was sent when not required.
  * Parameter '%s' sent when not required.

### -1107 API_KEY_EMPTY

  * The accessKey is missing from the request header or parameters, or the accessKey is not in the correct format.

### -1111 BAD_PRECISION

  * Precision is over the maximum defined for this asset.

### -1112 NO_DEPTH

  * No orders on book for symbol.

### -1114 TIF_NOT_REQUIRED

  * TimeInForce parameter sent when not required.

### -1115 INVALID_TIF

  * Invalid timeInForce.
  * In the current version, this parameter is either empty or GTC.

### -1116 INVALID_ORDER_TYPE

  * Invalid orderType.
  * In the current version , ORDER_TYPE values is LIMIT or MARKET.

### -1117 INVALID_SIDE

  * Invalid side.
  * ORDER_SIDE values is BUY or SELL

### -1118 EMPTY_NEW_CL_ORD_ID

  * New client order ID was empty.

### -1119 EMPTY_ORG_CL_ORD_ID

  * Original client order ID was empty.

### -1120 BAD_INTERVAL

  * Invalid interval.

### -1121 BAD_SYMBOL

  * Invalid symbol.

### -1125 INVALID_LISTEN_KEY

  * This listenKey does not exist.

### -1127 MORE_THAN_XX_HOURS

  * Lookup interval is too big.
  * More than %s hours between startTime and endTime.

### -1128 OPTIONAL_PARAMS_BAD_COMBO

  * Combination of optional parameters invalid.

### -1129 ORDER_DOWNLOAD_TIME_RANGE_EXCEED_ONE_YEAR

  * The time range cannot exceed one year.

### -1130 INVALID_PARAMETER

  * Invalid data sent for a parameter.
  * Data sent for paramter '%s' is not valid.

### -1131 INSUFFICIENT_BALANCE

  * Balance insufficient

### -1132 ORDER_PRICE_TOO_HIGH

  * Order price too high.

### -1133 ORDER_PRICE_TOO_SMALL

  * Order price lower than the minimum,please check general broker info.

### -1134 ORDER_PRICE_PRECISION_TOO_LONG

  * Order price decimal too long,please check general broker info.

### -1135 ORDER_QUANTITY_TOO_BIG

  * Order quantity too large.

### -1136 ORDER_QUANTITY_TOO_SMALL

  * Order quantity lower than the minimum.

### -1137 ORDER_QUANTITY_PRECISION_TOO_LONG

  * Order quantity decimal too long.

### -1138 ORDER_PRICE_WAVE_EXCEED

  * Order price exceeds permissible range.

### -1139 ORDER_HAS_FILLED

  * Order has been filled.

### -1140 ORDER_AMOUNT_TOO_SMALL

  * Transaction amount lower than the minimum.

### -1141 ORDER_DUPLICATED

  * Duplicate clientOrderId

### -1142 ORDER_CANCELLED

  * Order has been canceled

### -1143 ORDER_NOT_FOUND_ON_ORDER_BOOK

  * Cannot be found on order book

### -1144 ORDER_LOCKED

  * Order has been locked

### -1145 ORDER_NOT_SUPPORT_CANCELLATION

  * This order type does not support cancellation

### -1146 ORDER_CREATION_TIMEOUT

  * Order creation timeout

### -1147 ORDER_CANCELLATION_TIMEOUT

  * Order cancellation timeout

### -1148 ORDER_AMOUNT_PRECISION_TOO_LONG

  * Market order amount decimal too long

### -1149 CREATE_ORDER_FAILED

  * Create order failed

### -1150 CANCEL_ORDER_FAILED

  * Cancel order failed

### -1151 SYMBOL_PROHIBIT_ORDER

  * The trading pair is not open yet

### -1153 USER_NOT_EXIST

  * User not exist

### -1156 ORDER_QUANTITY_INVALID

  * Order quantity invalid

### -1157 SYMBOL_API_TRADING_NOT_AVAILABLE

  * The trading pair is not available for api trading

### -1158 CREATE_LIMIT_MAKER_ORDER_FAILED

  * create limit maker order failed

### -1161 REDUCE_MARGIN_FORBIDDEN

  * Reduce margin forbidden

### -1170 FINANCE_ACCOUNT_EXIST

  * finance account exist.

### -1171 ACCOUNT_NOT_EXIST

  * account not exist.

### -1172 BALANCE_TRANSFER_FAILED

  * Balance transfer failed.

### -1181 WITHDRAW_NOT_ALLOW

  * Currently not allowed to withdraw.

### -1182 DEPOSIT_NOT_ALLOW

  * Currently not allowed to deposit.

### -1193 ORDER_COUNT_LIMIT

  * Create order count limit

### -1194 MARKET_ORDER_FORBIDDEN

  * Create market order forbidden

### -1195 LIMIT_ORDER_PRICE_TOO_SMALL

  * Create limit order price too small

### -1196 LIMIT_ORDER_PRICE_TOO_BIG

  * Create limit order price too big

### -1197 LIMIT_ORDER_BUY_PRICE_TOO_BIG

  * Create limit order buy price too big

### -1198 LIMIT_ORDER_SELL_PRICE_TOO_SMALL

  * Create limit order sell price too small

### -1199 ORDER_BUY_QUANTITY_TOO_SMALL

  * Create order buy quantity too small

### -1200 ORDER_BUY_QUANTITY_TOO_BIG

  * Create order buy quantity too big

### -1201 LIMIT_ORDER_SELL_PRICE_TOO_BIG

  * Create limit order sell price too big

### -1202 ORDER_SELL_QUANTITY_TOO_SMALL

  * Create order sell quantity too small

### -1203 ORDER_SELL_QUANTITY_TOO_BIG

  * Create order sell quantity too big

### -1204 NOT_AUTHORIZED_ACCOUNT

  * account not authorized

### -1205 SAME_ACCOUNT_NOT_TRANSFER

  * same account not transfer

### -1206 ORDER_AMOUNT_TOO_BIG

  * Orders over the maximum transaction amount

### -1207 PLAN_ORDER_COUNT_LIMIT

  * planOrder count limit.

### -1208 STOP_PROFIT_LOSS_ORDER_COUNT_LIMIT

  * stopProfitLoss order count limit.

### -1209 STOP_PROFIT_LOSS_POSITION_TOTAL_LIMIT

  * stopProfitLoss order position limit.

### -1210 DYNAMIC_STOP_PROFIT_LONG_FALL_QUANTITY_HIGH

  * dynamic stop profit long fallQuantity high.

### -1211 DYNAMIC_STOP_PROFIT_LONG_ACTIVE_PRICE_LOW

  * dynamic stop profit activePrice low.

### -1212 DYNAMIC_STOP_PROFIT_SHORT_ACTIVE_PRICE_HIGH

  * dynamic stop profit activePrice high.

### -1213 ACCOUNT_SYMBOL_NOT_MATCH

  * Account symbol does not match

### -1214 ORDER_FUTURES_TRADE_BAN_OPEN

  * No opening trades

### -1215 ORDER_FUTURES_TRADE_BAN_CLOSE

  * No closing trades

### -1216 TRANSFER_LIMIT_FAILED

  * Trigger transfer limit failed

### -1217 STOP_ORDER_BUY_PRICE_TOO_BIG

  * Create stop order buy price too big

### -1300 DUPLICATED_TRANSFER_ID

  * Duplicate transferId

### -2010 NEW_ORDER_REJECTED

  * NEW_ORDER_REJECTED

### -2011 CANCEL_REJECTED

  * CANCEL_REJECTED

### -2013 NO_SUCH_ORDER

  * Order does not exist.

### -2014 BAD_API_KEY_FMT

  * API-key format invalid.

### -2015 REJECTED_MBX_KEY

  * Invalid API-key, IP, or permissions for action.

### -2016 NO_TRADING_WINDOW

  * No trading window could be found for the symbol. Try ticker/24hrs instead.

### -2017 API_KEY_EXPIRED

  * The API key has expired. Please update your API key immediately.

### -2018 API_KEY_SUSPENDED

  * API triggered risk control restrictions have been suspended, if you have any questions, please contact support@toobit.com.

## Filter failures

Error message| Description
---|---
"Filter failure: PRICE_FILTER"| price is too high, too low, and/or not following the tick size rule for the symbol.
"Filter failure: LOT_SIZE"| quantity is too high, too low, and/or not following the step size rule for the symbol.
"Filter failure: MIN_NOTIONAL"| price* quantity is too low to be a valid order for the symbol.
"Filter failure: MAX_NUM_ORDERS"| Account has too many open orders on the symbol.
"Filter failure: MAX_ALGO_ORDERS"| Account has too many open stop loss and/or take profit orders on the symbol.
"Filter failure: ICEBERG_PARTS"| Iceberg order would break into too many parts; icebergQty is too small.

## Order Rejection Issues

Error message| Description
---|---
"Unknown order sent."| The order (by either orderId, clOrdId, origClOrdId) could not be found
"Duplicate order sent."| The clOrdId is already in use
"Market is closed."| The symbol is not trading
"Account has insufficient balance for requested action."| Not enough funds to complete the action
"Market orders are not supported for this symbol."| MARKET is not enabled on the symbol
"Iceberg orders are not supported for this symbol."| icebergQty is not enabled on the symbol
"Stop loss orders are not supported for this symbol."| STOP_LOSS is not enabled on the symbol
"Stop loss limit orders are not supported for this symbol."| STOP_LOSS_LIMIT is not enabled on the symbol
"Take profit orders are not supported for this symbol."| TAKE_PROFIT is not enabled on the symbol
"Take profit limit orders are not supported for this symbol."| TAKE_PROFIT_LIMIT is not enabled on the symbol
"Price* QTY is zero or less."| price* quantity is too low
"IcebergQty exceeds QTY."| icebergQty must be less than the order quantity
"This action disabled is on this account."| Contact customer support; some actions have been disabled on the account.
"Unsupported order combination"| The orderType, timeInForce, stopPrice, and/or icebergQty combination isn't allowed.
"Order would trigger immediately."| The order's stop price is not valid when compared to the last traded price.
"Cancel order is invalid. Check origClOrdId and orderId."| No origClOrdId or orderId was sent in.
"Order would immediately match and take."| LIMIT_MAKER order type would immediately match and trade, and not be a pure maker order.
