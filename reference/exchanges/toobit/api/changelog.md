# Change Log

## 2026-07-13

### USDT-M trial vouchers

  * Added **Get API trial vouchers** `GET /api/v2/futures/voucher/list`, with `token` and optional `voucherStatus` filters.
  * Added **Receive an API trial voucher** `POST /api/v2/futures/voucher/receive`, using `relationId` to identify the voucher. Read-only API keys cannot receive vouchers.
  * Added API trial voucher error codes `-1400` through `-1417`.

### Account balance flow

  * Responses from `GET /api/v1/account/balanceFlow`, `GET /api/v1/futures/balanceFlow`, and `GET /api/v2/account/balance-flow` now include `voucherType` and `deductionAmount` to identify the voucher type and the voucher amount deducted by the flow.

* * *

## 2026-07-07

### Wallet endpoints

  * **Withdraw** `POST /api/v1/account/withdraw` — Added optional request parameter `addressType`. It defaults to `BLOCK_CHAIN` when empty and supports enum names `BLOCK_CHAIN`, `PHONE_NUMBER`, `EMAIL`, and `UID`. `PHONE_NUMBER`, `EMAIL`, and `UID` are used for platform internal transfers. `application/x-www-form-urlencoded` request examples have been added.

### Account endpoints

  * **Account balance flow** `GET /api/v2/account/balance-flow` — The `flowType` request parameter uses enum names. Common enum values have been added to the documentation.

* * *

## 2026-04-24

### Documentation (V1)

  * **Account** `GET /api/v1/account` — `balances` items are documented with `coin` only (no `asset` / `assetId` / `assetName` in the reference).
  * **Transfer** `POST /api/v1/subAccount/transfer` — request parameter is documented as `coin` only.
  * **Futures balance** `GET /api/v1/futures/balance` — each balance row is documented with `coin` only (not `asset`).
  * **Deposit address** `GET /api/v1/account/deposit/address` — response documents `chainType` (what you pass in) instead of `coinType`.

### New REST API v2 (dedicated pages + sidebar)

  * **Account** `GET /api/v2/account/balance-flow` — `accountType` / `flowType` as enum **names** ; leaner response fields. See Account & Trades (v2).
  * **U-margined futures** under `/api/v2/futures/...` — regular vs plan-order (and TP/SL) paths, `side` \+ `positionSide`, limit vs market via `LIMIT` / `MARKET`, JSON body batch place + signing rules, numeric leverage in `data`, etc. See Account & Trades (v2).

### Global

  * All signed REST responses include rate-limit headers: `X-Api-Limit-Status`, `X-Api-Limit`, `X-Api-Limit-Reset-Timestamp`.
  * For v2 `POST` with `Content-Type: application/json`, the HMAC input is `queryString + rawJsonBody` (no `&`); the JSON must match the body byte-for-byte. See _Basic information_.

* * *

## 2026-03-30

### Market data and funding

  * `GET /quote/v1/markPrice`: `symbol` is now optional; when omitted, the response is a JSON array of all mark prices.
  * `GET /api/v1/futures/fundingRate`: Response adds fields `interest`, `fundingRateCap`, and `fundingRateFloor`.

### Futures orders

  * Limit orders: optional `timeInForce` value `POST_ONLY` added.

* * *

## 2026-03-11

### Modified Interfaces

  * Funding rate interfaces: `GET /api/v1/futures/fundingRate`, `GET /api/v1/futures/historyFundingRate` \- Added response field `period` (funding rate settlement period, e.g. "8H")
  * Exchange information: `GET /api/v1/exchangeInfo` \- Added response field `categories` in `contracts` list (contract categories, English names; empty array when no category, multiple when belongs to multiple categories)
  * Flash close: `POST /api/v1/futures/flashClose` \- Added parameter `category` (USDC-M Futures=`USDC`, Default=USDT-M Futures)
  * One-click reverse: `POST /api/v1/futures/reversePosition` \- Added parameter `category` (USDC-M Futures=`USDC`, Default=USDT-M Futures)

* * *

## 2026-02-04

### Stock futures

Interface:

  * api/v1/auth/exchangeInfo

Changes:

  * New `closingStartTime`、`closingEndTime`、`isRwa`、`rwaType`Field Added

* * *

## 2026-02-02

### Modified Interfaces

  * Sub-account transfer interface: Added `transferId` field (LONG type, optional), same `transferId` can prevent duplicate transfers.
  * Error message adjustment: When an API returns a permission denied error, the error message will now include specific information about the required permissions for easier troubleshooting.

* * *

## 2026-01-19

### Modified Interfaces

  * Added `traceId` field to request response headers, which can be provided to customer service to assist with troubleshooting.

* * *

## 2025-01-01

### New Interfaces

#### Account Related Interfaces

  * Apply to download file
  * Query download record details

#### Futures Order Related Interfaces

  * Query historical position list
  * Modify order
  * Isolated margin auto-add margin switch
  * Flash close position
  * One-click reverse

#### General Interfaces

  * Get all system risk limit configuration list

### Modified Interfaces

  * Get exchange information: Returns correct symbol status
  * Query contract account balance: Added `coupon` field (sum of experience funds, cash vouchers, etc.)
  * Set position take profit/stop loss: Added support for trailing stop loss

* * *

## 2022-10-16

Create a document
