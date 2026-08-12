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

### -1164 ERROR_AUTO_ADD_MARGIN

  * Auto add margin error

### -1165 INVALID_STOP_TYPE

  * Invalid stopType.

### -1166 INVALID_CALLBACK_TYPE

  * Invalid callbackType.

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

  * Transaction amount bigger than the max.

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

## 14xx - API Trial Voucher Issues

### -1400 API_VOUCHER_TYPE_NOT_ALLOWED

  * API voucher type is not allowed.

### -1401 API_USE_VOUCHER_AGENT_NOT_ALLOWED

  * You are not eligible to use API trial voucher.

### -1402 API_VOUCHER_QUERY_FAILED

  * API voucher query failed.

### -1403 API_VOUCHER_RECEIVE_FAILED

  * API voucher receive failed.

### -1404 API_VOUCHER_AGENT_CONFIG_FAILED

  * API voucher agent config failed.

### -1405 API_VOUCHER_NOT_FOUND

  * API voucher not found.

### -1406 API_VOUCHER_USING

  * API voucher is already in use.

### -1407 API_VOUCHER_NOT_REACHING_THE_THRESHOLD

  * API voucher threshold is not met.

### -1408 API_VOUCHER_ASSET_LESS_THAN_ZERO

  * Contract asset is less than zero.

### -1409 API_VOUCHER_STATUS_ERROR

  * API voucher status is invalid.

### -1410 API_VOUCHER_SYSTEM_ACCOUNT_INSUFFICIENT_BALANCE

  * API voucher system account balance is insufficient.

### -1411 API_VOUCHER_TRANSFER_ING

  * API voucher transfer is processing.

### -1412 API_VOUCHER_NON_MERGE

  * API voucher can not be merged.

### -1413 API_VOUCHER_TRADE_RATE_NOT_MATCH

  * API voucher trade rate does not match.

### -1414 API_VOUCHER_FEE_RULE_NOT_MATCH

  * API voucher fee rule does not match.

### -1415 API_VOUCHER_TOKEN_NOT_MATCH

  * API voucher token does not match.

### -1416 API_VOUCHER_BATCH_RECEIVE_INSUFFICIENT_BALANCE

  * Some API vouchers can not be received due to insufficient system balance.

### -1417 API_VOUCHER_BATCH_RECEIVE_NOT_REACHING_THE_THRESHOLD

  * Some API vouchers do not meet the receiving threshold.

### -2010 NEW_ORDER_REJECTED

  * New order rejected

### -2011 CANCEL_REJECTED

  * Cancel order rejected

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

## 3xxx - Filters and other Issues

### -3000 OPTION_NOT_EXIST

  * Option not exist.

### -3001 OPTION_HAS_EXPIRED

  * The option has expired.

### -3002 OPTION_ORDER_POSITION_LIMIT

  * Order failed: position exceeded limit

### -3050 CREATE_API_KEY_EXCEED_LIMIT

  * The ApiKey corresponding to the account already exists

### -3051 SUB_USER_TOTAL_ASSETS_EXCEEDING

  * The sub-user has assets are not allowed to be deleted

### -3052 SUB_USER_ID_ERROR

  * sub-user id error

### -3101 OPEN_MARGIN_ACCOUNT_ERROR

  * Open margin account error

### -3102 GET_MARGIN_SAFETY_ERROR

  * Get margin safety error

### -3103 RISK_IS_NOT_EXIT

  * Risk config is not exit

### -3105 MARGIN_TOKEN_NOT_BORROW

  * Token can not borrow

### -3107 MARGIN_TOKEN_NOT_WITHDRAW

  * Token can not withdraw

### -3108 GET_AVAIL_WITHDRAW_ERROR

  * Get token avail withdraw error

### -3109 MARGIN_WITHDRAW_ERROR

  * Margin withdraw failed

### -3110 MARGIN_AVAIL_WITHDRAW_NOT_ENOUGH_FAILED

  * Margin avail withdraw not enough failed

### -3116 REPAY_ERROR

  * Repay fail

### -3117 GET_MARGIN_ALL_POSITION_ERROR

  * Get margin all position fail

### -3120 GET_REPAY_ORDER_ERROR

  * Get repay order fail

### -3124 POSITION_AND_ORDER_DATA_ERROR

  * Position and order data error

### -3125 POSITION_SIZE_CANNOT_MEET_TARGET_LEVERAGE_ERROR

  * Position size cannot meet target leverage

### -3126 ADJUST_LEVERAGE_FAIL

  * Adjust leverage fail

### -3127 ADJUST_LEVERAGE_TIMEOUT

  * Adjust leverage timeout

### -3128 ADJUST_MARGIN_TYPE_CHECK_FAILED

  * The margin mode cannot be changed while you have an open order/position

### -3129 CONE_FUTURES_CHANGE_POSITION_TYPE_ERROR

  * Cone futures change position type error

### -3130 ORDER_REJECT_FUTURES_ORDER_MARGIN_INSUFFICIENT

  * Order margin insufficient

### -3131 LEVERAGE_REDUCTION_IS_NOT_SUPPORTED

  * Leverage reduction is not supported in Isolated Margin Mode with open positions.

### -3132 ORDER_FUTURES_LEVERAGE_INVALID

  * Maximum allowed leverage reached, please lower your leverage.

### -3133 LEVERAGE_OPEN_ORDERS_EXCEEDS_THE_LIMIT

  * The number of open orders exceeds the limit.

### -3136 QUICK_SYMBOL_ACTIVITY_LIMIT_BUY_IOC_ONLY

  * Quick symbol activity only limit/buy/ioc order is supported

### -3137 OPEN_COUNTDOWN_NOT_OVER

  * Open countdown is not over

### -3138 OPEN_ACTIVITY_PRE_HOLD_HANDLING

  * Open activity pre_hold is handling

### -3139 OPEN_ACTIVITY_MAX_AMOUNT_LIMIT

  * Open activity max amount limit

### -3140 OPEN_ACTIVITY_MIN_AMOUNT_LIMIT

  * Open activity min amount limit

### -3141 ORDER_SPL_ERR_LONG_STOP_PROFIT_PRICE

  * Invalid long stop profit price.

### -3142 ORDER_SPL_ERR_LONG_STOP_LOSS_PRICE

  * Invalid long stop loss price.

### -3143 ORDER_SPL_ERR_SHORT_STOP_PROFIT_PRICE

  * Invalid short stop profit price.

### -3144 ORDER_SPL_ERR_SHORT_STOP_LOSS_PRICE

  * Invalid short stop loss price.

### -3145 NO_POSITION

  * No position, Please confirm your position direction.

### -3147 PREVIOUS_TRANSFER_IS_BEING_PROCESSED

  * previous transfer is being processed. please try again later.

### -3148 POSITION_MAX_FUTURES_RISK_LIMIT

  * create order exceeds max futures risk limit.

### -3149 REDUCE_MARGIN_INVALID

  * The reduction in margin is unlawful.

### -3150 MARGIN_ADJUSTMENT_IS_NOT_SUPPORTED_FOR_CROSS

  * cross position margin adjustments are not supported.

### -3151 SEPARATE_POSITION_MODE_NOT_SUPPORTED

  * Separate position mode is not supported.

### -3152 SEPARATE_POSITION_WITH_WRONG_MODE

  * Separate-position mismatch: position mode must be SEPARATE.

### -3153 WHOLE_POSITION_WITH_WRONG_MODE

  * Whole-position mismatch: position mode must be WHOLE.
