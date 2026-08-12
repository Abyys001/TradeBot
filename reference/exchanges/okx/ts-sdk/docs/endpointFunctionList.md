
# Endpoint maps

<p align="center">
  <a href="https://www.npmjs.com/package/okx-api">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/tiagosiebler/okx-api/blob/master/docs/images/logoDarkMode2.svg?raw=true#gh-dark-mode-only">
      <img alt="SDK Logo" src="https://github.com/tiagosiebler/okx-api/blob/master/docs/images/logoBrightMode2.svg?raw=true#gh-light-mode-only">
    </picture>
  </a>
</p>

Each REST client is a JavaScript class, which provides functions individually mapped to each endpoint available in the exchange's API offering. 

The following table shows all methods available in each REST client, whether the method requires authentication (automatically handled if API keys are provided), as well as the exact endpoint each method is connected to.

This can be used to easily find which method to call, once you have [found which endpoint you're looking to use](https://github.com/tiagosiebler/awesome-crypto-examples/wiki/How-to-find-SDK-functions-that-match-API-docs-endpoint).

All REST clients are in the [src](/src) folder. For usage examples, make sure to check the [examples](/examples) folder.

List of clients:
- [rest-client](#rest-clientts)
- [websocket-api-client](#websocket-api-clientts)


If anything is missing or wrong, please open an issue or let us know in our [Node.js Traders](https://t.me/nodetraders) telegram group!

## How to use table

Table consists of 4 parts:

- Function name
- AUTH
- HTTP Method
- Endpoint

**Function name** is the name of the function that can be called through the SDK. Check examples folder in the repo for more help on how to use them!

**AUTH** is a boolean value that indicates if the function requires authentication - which means you need to pass your API key and secret to the SDK.

**HTTP Method** shows HTTP method that the function uses to call the endpoint. Sometimes endpoints can have same URL, but different HTTP method so you can use this column to differentiate between them.

**Endpoint** is the URL that the function uses to call the endpoint. Best way to find exact function you need for the endpoint is to search for URL in this table and find corresponding function name.


# rest-client.ts

This table includes all endpoints from the official Exchange API docs and corresponding SDK functions for each endpoint that are found in [rest-client.ts](/src/rest-client.ts). 

| Function | AUTH | HTTP Method | Endpoint |
| -------- | :------: | :------: | -------- |
| [getAccountInstruments()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L486) | :closed_lock_with_key:  | GET | `/api/v5/account/instruments` |
| [getBalance()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L492) | :closed_lock_with_key:  | GET | `/api/v5/account/balance` |
| [getPositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L496) | :closed_lock_with_key:  | GET | `/api/v5/account/positions` |
| [getPositionsHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L500) | :closed_lock_with_key:  | GET | `/api/v5/account/positions-history` |
| [getAccountPositionRisk()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L506) | :closed_lock_with_key:  | GET | `/api/v5/account/account-position-risk` |
| [getBills()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L513) | :closed_lock_with_key:  | GET | `/api/v5/account/bills` |
| [getBillsArchive()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L518) | :closed_lock_with_key:  | GET | `/api/v5/account/bills-archive` |
| [getAccountBillSubtypes()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L526) | :closed_lock_with_key:  | GET | `/api/v5/account/subtypes` |
| [requestBillsHistoryDownloadLink()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L540) | :closed_lock_with_key:  | POST | `/api/v5/account/bills-history-archive` |
| [getRequestedBillsHistoryLink()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L549) | :closed_lock_with_key:  | GET | `/api/v5/account/bills-history-archive` |
| [getAccountConfiguration()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L555) | :closed_lock_with_key:  | GET | `/api/v5/account/config` |
| [setPositionMode()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L559) | :closed_lock_with_key:  | POST | `/api/v5/account/set-position-mode` |
| [setSettleCurrency()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L565) | :closed_lock_with_key:  | POST | `/api/v5/account/set-settle-currency` |
| [setFeeType()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L571) | :closed_lock_with_key:  | POST | `/api/v5/account/set-fee-type` |
| [setLeverage()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L575) | :closed_lock_with_key:  | POST | `/api/v5/account/set-leverage` |
| [getMaxBuySellAmount()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L580) | :closed_lock_with_key:  | GET | `/api/v5/account/max-size` |
| [getMaxAvailableTradableAmount()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L593) | :closed_lock_with_key:  | GET | `/api/v5/account/max-avail-size` |
| [changePositionMargin()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L603) | :closed_lock_with_key:  | POST | `/api/v5/account/position/margin-balance` |
| [movePositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L614) | :closed_lock_with_key:  | POST | `/api/v5/account/move-positions` |
| [getMovePositionsHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L622) | :closed_lock_with_key:  | GET | `/api/v5/account/move-positions-history` |
| [getLeverage()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L628) | :closed_lock_with_key:  | GET | `/api/v5/account/leverage-info` |
| [getLeverageV2()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L640) | :closed_lock_with_key:  | GET | `/api/v5/account/leverage-info` |
| [getLeverageEstimatedInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L648) | :closed_lock_with_key:  | GET | `/api/v5/account/adjust-leverage-info` |
| [getMaxLoan()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L659) | :closed_lock_with_key:  | GET | `/api/v5/account/max-loan` |
| [getFeeRates()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L668) | :closed_lock_with_key:  | GET | `/api/v5/account/trade-fee` |
| [getInterestAccrued()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L679) | :closed_lock_with_key:  | GET | `/api/v5/account/interest-accrued` |
| [getInterestRate()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L691) | :closed_lock_with_key:  | GET | `/api/v5/account/interest-rate` |
| [setGreeksDisplayType()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L695) | :closed_lock_with_key:  | POST | `/api/v5/account/set-greeks` |
| [setIsolatedMode()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L699) | :closed_lock_with_key:  | POST | `/api/v5/account/set-isolated-mode` |
| [getMaxWithdrawals()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L706) | :closed_lock_with_key:  | GET | `/api/v5/account/max-withdrawal` |
| [getAccountRiskState()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L710) | :closed_lock_with_key:  | GET | `/api/v5/account/risk-state` |
| [setAccountCollateralAssets()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L714) | :closed_lock_with_key:  | POST | `/api/v5/account/set-collateral-assets` |
| [getAccountCollateralAssets()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L728) | :closed_lock_with_key:  | GET | `/api/v5/account/collateral-assets` |
| [submitQuickMarginBorrowRepay()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L740) | :closed_lock_with_key:  | POST | `/api/v5/account/quick-margin-borrow-repay` |
| [getQuickMarginBorrowRepayHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L749) | :closed_lock_with_key:  | GET | `/api/v5/account/quick-margin-borrow-repay-history` |
| [borrowRepayVIPLoan()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L758) | :closed_lock_with_key:  | POST | `/api/v5/account/borrow-repay` |
| [getVIPLoanBorrowRepayHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L767) | :closed_lock_with_key:  | GET | `/api/v5/account/borrow-repay-history` |
| [getVIPInterestAccrued()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L771) | :closed_lock_with_key:  | GET | `/api/v5/account/vip-interest-accrued` |
| [getVIPInterestDeducted()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L775) | :closed_lock_with_key:  | GET | `/api/v5/account/vip-interest-deducted` |
| [getVIPLoanOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L781) | :closed_lock_with_key:  | GET | `/api/v5/account/vip-loan-order-list` |
| [getVIPLoanOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L787) | :closed_lock_with_key:  | GET | `/api/v5/account/vip-loan-order-detail` |
| [getBorrowInterestLimits()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L793) | :closed_lock_with_key:  | GET | `/api/v5/account/interest-limits` |
| [getFixedLoanBorrowLimit()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L800) | :closed_lock_with_key:  | GET | `/api/v5/account/fixed-loan/borrowing-limit` |
| [getFixedLoanBorrowQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L804) | :closed_lock_with_key:  | GET | `/api/v5/account/fixed-loan/borrowing-quote` |
| [submitFixedLoanBorrowOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L813) | :closed_lock_with_key:  | POST | `/api/v5/account/fixed-loan/borrowing-order` |
| [updateFixedLoanBorrowOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L826) | :closed_lock_with_key:  | POST | `/api/v5/account/fixed-loan/amend-borrowing-order` |
| [manualRenewFixedLoanBorrowOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L839) | :closed_lock_with_key:  | POST | `/api/v5/account/fixed-loan/manual-reborrow` |
| [repayFixedLoanBorrowOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L853) | :closed_lock_with_key:  | POST | `/api/v5/account/fixed-loan/repay-borrowing-order` |
| [convertFixedLoanToMarketLoan()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L864) | :closed_lock_with_key:  | POST | `/api/v5/account/fixed-loan/convert-to-market-loan` |
| [reduceFixedLoanLiabilities()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L875) | :closed_lock_with_key:  | POST | `/api/v5/account/fixed-loan/reduce-liabilities` |
| [getFixedLoanBorrowOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L890) | :closed_lock_with_key:  | GET | `/api/v5/account/fixed-loan/borrowing-orders-list` |
| [manualBorrowRepay()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L899) | :closed_lock_with_key:  | POST | `/api/v5/account/spot-manual-borrow-repay` |
| [setAutoRepay()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L913) | :closed_lock_with_key:  | POST | `/api/v5/account/set-auto-repay` |
| [getBorrowRepayHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L921) | :closed_lock_with_key:  | GET | `/api/v5/account/spot-borrow-repay-history` |
| [positionBuilder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L927) | :closed_lock_with_key:  | POST | `/api/v5/account/position-builder` |
| [updateRiskOffsetAmount()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L931) | :closed_lock_with_key:  | POST | `/api/v5/account/set-riskOffset-amt` |
| [getGreeks()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L943) | :closed_lock_with_key:  | GET | `/api/v5/account/greeks` |
| [getPMLimitation()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L947) | :closed_lock_with_key:  | GET | `/api/v5/account/position-tiers` |
| [updateRiskOffsetType()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L955) | :closed_lock_with_key:  | POST | `/api/v5/account/set-riskOffset-type` |
| [activateOption()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L963) | :closed_lock_with_key:  | POST | `/api/v5/account/activate-option` |
| [setAutoLoan()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L971) | :closed_lock_with_key:  | POST | `/api/v5/account/set-auto-loan` |
| [presetAccountLevelSwitch()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L975) | :closed_lock_with_key:  | POST | `/api/v5/account/account-level-switch-preset` |
| [getAccountSwitchPrecheck()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L986) | :closed_lock_with_key:  | GET | `/api/v5/account/set-account-switch-precheck` |
| [setAccountMode()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L995) | :closed_lock_with_key:  | POST | `/api/v5/account/set-account-level` |
| [resetMMPStatus()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1001) | :closed_lock_with_key:  | POST | `/api/v5/account/mmp-reset` |
| [setMMPConfig()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1009) | :closed_lock_with_key:  | POST | `/api/v5/account/mmp-config` |
| [getMMPConfig()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1013) | :closed_lock_with_key:  | GET | `/api/v5/account/mmp-config` |
| [setTradingConfig()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1017) | :closed_lock_with_key:  | POST | `/api/v5/account/set-trading-config` |
| [precheckSetDeltaNeutral()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1023) | :closed_lock_with_key:  | GET | `/api/v5/account/precheck-set-delta-neutral` |
| [submitOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1038) | :closed_lock_with_key:  | POST | `/api/v5/trade/order` |
| [submitMultipleOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1042) | :closed_lock_with_key:  | POST | `/api/v5/trade/batch-orders` |
| [cancelOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1046) | :closed_lock_with_key:  | POST | `/api/v5/trade/cancel-order` |
| [cancelMultipleOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1050) | :closed_lock_with_key:  | POST | `/api/v5/trade/cancel-batch-orders` |
| [amendOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1056) | :closed_lock_with_key:  | POST | `/api/v5/trade/amend-order` |
| [amendMultipleOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1060) | :closed_lock_with_key:  | POST | `/api/v5/trade/amend-batch-orders` |
| [closePositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1064) | :closed_lock_with_key:  | POST | `/api/v5/trade/close-position` |
| [getOrderDetails()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1068) | :closed_lock_with_key:  | GET | `/api/v5/trade/order` |
| [getOrderList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1072) | :closed_lock_with_key:  | GET | `/api/v5/trade/orders-pending` |
| [getOrderHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1079) | :closed_lock_with_key:  | GET | `/api/v5/trade/orders-history` |
| [getOrderHistoryArchive()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1086) | :closed_lock_with_key:  | GET | `/api/v5/trade/orders-history-archive` |
| [getFills()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1095) | :closed_lock_with_key:  | GET | `/api/v5/trade/fills` |
| [getFillsHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1102) | :closed_lock_with_key:  | GET | `/api/v5/trade/fills-history` |
| [getEasyConvertCurrencies()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1107) | :closed_lock_with_key:  | GET | `/api/v5/trade/easy-convert-currency-list` |
| [submitEasyConvert()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1120) | :closed_lock_with_key:  | POST | `/api/v5/trade/easy-convert` |
| [getEasyConvertHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1129) | :closed_lock_with_key:  | GET | `/api/v5/trade/easy-convert-history` |
| [getOneClickRepayCurrencyList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1138) | :closed_lock_with_key:  | GET | `/api/v5/trade/one-click-repay-currency-list` |
| [submitOneClickRepay()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1152) | :closed_lock_with_key:  | POST | `/api/v5/trade/one-click-repay` |
| [getOneClickRepayHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1160) | :closed_lock_with_key:  | GET | `/api/v5/trade/one-click-repay-history` |
| [cancelMassOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1164) | :closed_lock_with_key:  | POST | `/api/v5/trade/mass-cancel` |
| [cancelAllAfter()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1176) | :closed_lock_with_key:  | POST | `/api/v5/trade/cancel-all-after` |
| [getAccountRateLimit()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1183) | :closed_lock_with_key:  | GET | `/api/v5/trade/account-rate-limit` |
| [submitOrderPrecheck()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1187) | :closed_lock_with_key:  | POST | `/api/v5/trade/order-precheck` |
| [placeAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1197) | :closed_lock_with_key:  | POST | `/api/v5/trade/order-algo` |
| [cancelAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1201) | :closed_lock_with_key:  | POST | `/api/v5/trade/cancel-algos` |
| [amendAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1207) | :closed_lock_with_key:  | POST | `/api/v5/trade/amend-algos` |
| [cancelAdvanceAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1213) | :closed_lock_with_key:  | POST | `/api/v5/trade/cancel-advance-algos` |
| [getAlgoOrderDetails()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1219) | :closed_lock_with_key:  | GET | `/api/v5/trade/order-algo` |
| [getAlgoOrderList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1225) | :closed_lock_with_key:  | GET | `/api/v5/trade/orders-algo-pending` |
| [getAlgoOrderHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1231) | :closed_lock_with_key:  | GET | `/api/v5/trade/orders-algo-history` |
| [placeGridAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1243) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/order-algo` |
| [amendGridAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1247) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/amend-order-algo` |
| [stopGridAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1264) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/stop-order-algo` |
| [closeGridContractPosition()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1268) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/close-position` |
| [cancelGridContractCloseOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1274) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/cancel-close-order` |
| [instantTriggerGridAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1284) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/order-instant-trigger` |
| [getGridAlgoOrderList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1296) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/grid/orders-algo-pending` |
| [getGridAlgoOrderHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1303) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/grid/orders-algo-history` |
| [getGridAlgoOrderDetails()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1310) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/grid/orders-algo-details` |
| [getGridAlgoSubOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1320) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/grid/sub-orders` |
| [getGridAlgoOrderPositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1332) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/grid/positions` |
| [spotGridWithdrawIncome()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1339) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/withdraw-income` |
| [computeGridMarginBalance()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1343) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/compute-margin-balance` |
| [adjustGridMarginBalance()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1354) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/margin-balance` |
| [adjustGridInvestment()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1363) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/grid/adjust-investment` |
| [getGridAIParameter()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1374) |  | GET | `/api/v5/tradingBot/grid/ai-param` |
| [computeGridMinInvestment()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1383) |  | POST | `/api/v5/tradingBot/grid/min-investment` |
| [getRSIBackTesting()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1390) |  | GET | `/api/v5/tradingBot/public/rsi-back-testing` |
| [getMaxGridQuantity()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1398) |  | GET | `/api/v5/tradingBot/grid/grid-quantity` |
| [createSignal()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1412) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/create-signal` |
| [getSignals()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1416) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/signals` |
| [createSignalBot()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1420) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/order-algo` |
| [cancelSignalBots()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1426) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/stop-order-algo` |
| [updateSignalMargin()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1435) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/margin-balance` |
| [updateSignalTPSL()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1443) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/amendTPSL` |
| [setSignalInstruments()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1451) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/set-instruments` |
| [getSignalBotOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1462) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/orders-algo-details` |
| [getActiveSignalBot()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1472) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/orders-algo-details` |
| [getSignalBotHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1479) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/orders-algo-history` |
| [getSignalBotPositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1486) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/positions` |
| [getSignalBotPositionHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1493) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/positions-history` |
| [closeSignalBotPosition()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1502) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/close-position` |
| [placeSignalBotSubOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1510) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/sub-order` |
| [cancelSubOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1514) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/signal/cancel-sub-order` |
| [getSignalBotSubOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1521) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/sub-orders` |
| [getSignalBotEventHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1525) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/signal/event-history` |
| [submitRecurringBuyOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1537) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/recurring/order-algo` |
| [amendRecurringBuyOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1543) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/recurring/amend-order-algo` |
| [stopRecurringBuyOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1552) | :closed_lock_with_key:  | POST | `/api/v5/tradingBot/recurring/stop-order-algo` |
| [getRecurringBuyOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1561) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/recurring/orders-algo-pending` |
| [getRecurringBuyOrderHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1570) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/recurring/orders-algo-history` |
| [getRecurringBuyOrderDetails()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1579) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/recurring/orders-algo-details` |
| [getRecurringBuySubOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1588) | :closed_lock_with_key:  | GET | `/api/v5/tradingBot/recurring/sub-orders` |
| [getCopytradingSubpositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1600) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/current-subpositions` |
| [getCopytradingSubpositionsHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1606) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/subpositions-history` |
| [submitCopytradingAlgoOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1612) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/algo-order` |
| [closeCopytradingSubposition()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1618) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/close-subposition` |
| [getCopytradingInstruments()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1627) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/instruments` |
| [setCopytradingInstruments()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1636) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/set-instruments` |
| [getCopytradingProfitDetails()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1648) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/profit-sharing-details` |
| [getCopytradingTotalProfit()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1657) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/total-profit-sharing` |
| [getCopytradingUnrealizedProfit()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1663) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/unrealized-profit-sharing-details` |
| [getCopytradingTotalUnrealizedProfit()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1672) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/total-unrealized-profit-sharing` |
| [applyCopytradingLeadTrading()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1684) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/apply-lead-trading` |
| [stopCopytradingLeadTrading()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1695) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/stop-lead-trading` |
| [updateCopytradingProfitSharing()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1703) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/amend-profit-sharing-ratio` |
| [getCopytradingAccount()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1717) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/config` |
| [setCopytradingFirstCopy()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1721) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/first-copy-settings` |
| [updateCopytradingCopySettings()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1729) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/amend-copy-settings` |
| [stopCopytradingCopy()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1737) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/stop-copy-trading` |
| [getCopytradingCopySettings()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1749) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/copy-settings` |
| [getCopytradingBatchLeverageInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1756) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/batch-leverage-info` |
| [setCopytradingBatchLeverage()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1762) | :closed_lock_with_key:  | POST | `/api/v5/copytrading/batch-set-leverage` |
| [getCopytradingMyLeadTraders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1768) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/current-lead-traders` |
| [getCopytradingLeadTradersHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1774) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/lead-traders-history` |
| [getCopytradingConfig()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1780) |  | GET | `/api/v5/copytrading/public-config` |
| [getCopytradingLeadRanks()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1786) |  | GET | `/api/v5/copytrading/public-lead-traders` |
| [getCopytradingLeadWeeklyPnl()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1792) |  | GET | `/api/v5/copytrading/public-weekly-pnl` |
| [getCopytradingLeadDailyPnl()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1799) |  | GET | `/api/v5/copytrading/public-pnl` |
| [getCopytradingLeadStats()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1805) |  | GET | `/api/v5/copytrading/public-stats` |
| [getCopytradingLeadPreferences()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1811) |  | GET | `/api/v5/copytrading/public-preference-currency` |
| [getCopytradingLeadOpenPositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1818) |  | GET | `/api/v5/copytrading/public-current-subpositions` |
| [getCopytradingLeadPositionHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1824) |  | GET | `/api/v5/copytrading/public-subpositions-history` |
| [getCopyTraders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1830) |  | GET | `/api/v5/copytrading/public-copy-traders` |
| [getCopytradingLeadPrivateRanks()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1836) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/lead-traders` |
| [getCopytradingLeadPrivateWeeklyPnl()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1842) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/weekly-pnl` |
| [getCopytradingPLeadPrivateDailyPnl()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1849) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/pnl` |
| [geCopytradingLeadPrivateStats()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1855) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/stats` |
| [getCopytradingLeadPrivatePreferences()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1861) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/preference-currency` |
| [getCopytradingLeadPrivateOpenPositions()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1868) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/performance-current-subpositions` |
| [getCopytradingLeadPrivatePositionHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1877) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/performance-subpositions-history` |
| [getCopyTradersPrivate()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1886) | :closed_lock_with_key:  | GET | `/api/v5/copytrading/copy-traders` |
| [getTickers()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1898) |  | GET | `/api/v5/market/tickers` |
| [getTicker()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1906) |  | GET | `/api/v5/market/ticker` |
| [getOrderBook()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1910) |  | GET | `/api/v5/market/books` |
| [getFullOrderBook()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1917) |  | GET | `/api/v5/market/books-full` |
| [getCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1924) |  | GET | `/api/v5/market/candles` |
| [getHistoricCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1928) |  | GET | `/api/v5/market/history-candles` |
| [getTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1932) |  | GET | `/api/v5/market/trades` |
| [getHistoricTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1936) |  | GET | `/api/v5/market/history-trades` |
| [getOptionTradesByInstrument()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1946) |  | GET | `/api/v5/market/option/instrument-family-trades` |
| [getOptionTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1952) |  | GET | `/api/v5/public/option-trades` |
| [get24hrTotalVolume()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1956) |  | GET | `/api/v5/market/platform-24-volume` |
| [getBlockCounterParties()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1966) | :closed_lock_with_key:  | GET | `/api/v5/rfq/counterparties` |
| [createBlockRFQ()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1970) | :closed_lock_with_key:  | POST | `/api/v5/rfq/create-rfq` |
| [cancelBlockRFQ()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1974) | :closed_lock_with_key:  | POST | `/api/v5/rfq/cancel-rfq` |
| [cancelMultipleBlockRFQs()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1980) | :closed_lock_with_key:  | POST | `/api/v5/rfq/cancel-batch-rfqs` |
| [cancelAllRFQs()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1986) | :closed_lock_with_key:  | POST | `/api/v5/rfq/cancel-all-rfqs` |
| [executeBlockQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1990) | :closed_lock_with_key:  | POST | `/api/v5/rfq/execute-quote` |
| [getQuoteProducts()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L1996) | :closed_lock_with_key:  | GET | `/api/v5/rfq/maker-instrument-settings` |
| [updateBlockQuoteProducts()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2000) | :closed_lock_with_key:  | POST | `/api/v5/rfq/maker-instrument-settings` |
| [resetBlockMmp()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2008) | :closed_lock_with_key:  | POST | `/api/v5/rfq/mmp-reset` |
| [updateBlockMmpConfig()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2016) | :closed_lock_with_key:  | POST | `/api/v5/rfq/mmp-config` |
| [getBlockMmpConfig()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2022) | :closed_lock_with_key:  | GET | `/api/v5/rfq/mmp-config` |
| [createBlockQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2026) | :closed_lock_with_key:  | POST | `/api/v5/rfq/create-quote` |
| [cancelBlockQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2032) | :closed_lock_with_key:  | POST | `/api/v5/rfq/cancel-quote` |
| [cancelMultipleBlockQuotes()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2038) | :closed_lock_with_key:  | POST | `/api/v5/rfq/cancel-batch-quotes` |
| [cancelAllBlockQuotes()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2044) | :closed_lock_with_key:  | POST | `/api/v5/rfq/cancel-all-quotes` |
| [cancelAllBlockAfter()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2048) | :closed_lock_with_key:  | POST | `/api/v5/rfq/cancel-all-after` |
| [getBlockRFQs()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2057) | :closed_lock_with_key:  | GET | `/api/v5/rfq/rfqs` |
| [getBlockQuotes()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2061) | :closed_lock_with_key:  | GET | `/api/v5/rfq/quotes` |
| [getBlockTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2065) | :closed_lock_with_key:  | GET | `/api/v5/rfq/trades` |
| [getPublicRFQBlockTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2069) |  | GET | `/api/v5/rfq/public-trades` |
| [getBlockTickers()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2073) |  | GET | `/api/v5/market/block-tickers` |
| [getBlockTicker()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2080) |  | GET | `/api/v5/market/block-ticker` |
| [getBlockPublicTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2084) |  | GET | `/api/v5/public/block-trades` |
| [submitSpreadOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2096) | :closed_lock_with_key:  | POST | `/api/v5/sprd/order` |
| [cancelSpreadOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2102) | :closed_lock_with_key:  | POST | `/api/v5/sprd/cancel-order` |
| [cancelAllSpreadOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2109) | :closed_lock_with_key:  | POST | `/api/v5/sprd/mass-cancel` |
| [updateSpreadOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2117) | :closed_lock_with_key:  | POST | `/api/v5/sprd/amend-order` |
| [getSpreadOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2123) | :closed_lock_with_key:  | GET | `/api/v5/sprd/order` |
| [getSpreadActiveOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2130) | :closed_lock_with_key:  | GET | `/api/v5/sprd/orders-pending` |
| [getSpreadOrdersRecent()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2136) | :closed_lock_with_key:  | GET | `/api/v5/sprd/orders-history` |
| [getSpreadOrdersArchive()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2142) | :closed_lock_with_key:  | GET | `/api/v5/sprd/orders-history-archive` |
| [getSpreadTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2148) | :closed_lock_with_key:  | GET | `/api/v5/sprd/trades` |
| [getSpreads()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2152) |  | GET | `/api/v5/sprd/spreads` |
| [getSpreadOrderBook()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2156) |  | GET | `/api/v5/sprd/books` |
| [getSpreadTicker()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2163) |  | GET | `/api/v5/market/sprd-ticker` |
| [getSpreadPublicTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2167) |  | GET | `/api/v5/sprd/public-trades` |
| [getSpreadCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2173) |  | GET | `/api/v5/market/sprd-candles` |
| [getSpreadHistoryCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2177) |  | GET | `/api/v5/market/sprd-history-candles` |
| [cancelSpreadAllAfter()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2183) | :closed_lock_with_key:  | POST | `/api/v5/sprd/cancel-all-after` |
| [getInstruments()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2198) |  | GET | `/api/v5/public/instruments` |
| [getEventContractSeries()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2206) |  | GET | `/api/v5/public/event-contract/series` |
| [getEventContractEvents()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2216) |  | GET | `/api/v5/public/event-contract/events` |
| [getEventContractMarkets()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2226) |  | GET | `/api/v5/public/event-contract/markets` |
| [getDeliveryExerciseHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2232) |  | GET | `/api/v5/public/delivery-exercise-history` |
| [getOpenInterest()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2236) |  | GET | `/api/v5/public/open-interest` |
| [getFundingRate()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2240) |  | GET | `/api/v5/public/funding-rate` |
| [getFundingRateHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2244) |  | GET | `/api/v5/public/funding-rate-history` |
| [getMinMaxLimitPrice()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2250) |  | GET | `/api/v5/public/price-limit` |
| [getOptionMarketData()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2254) |  | GET | `/api/v5/public/opt-summary` |
| [getEstimatedDeliveryExercisePrice()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2262) |  | GET | `/api/v5/public/estimated-price` |
| [getDiscountRateAndInterestFreeQuota()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2268) |  | GET | `/api/v5/public/discount-rate-interest-free-quota` |
| [getSystemTime()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2272) |  | GET | `/api/v5/public/time` |
| [getHistoricalMarketData()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2276) |  | GET | `/api/v5/public/market-data-history` |
| [getMarkPrice()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2282) |  | GET | `/api/v5/public/mark-price` |
| [getPositionTiers()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2286) |  | GET | `/api/v5/public/position-tiers` |
| [getInterestRateAndLoanQuota()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2290) |  | GET | `/api/v5/public/interest-rate-loan-quota` |
| [getVIPInterestRateAndLoanQuota()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2294) |  | GET | `/api/v5/public/vip-interest-rate-loan-quota` |
| [getUnderlying()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2298) |  | GET | `/api/v5/public/underlying` |
| [getInsuranceFund()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2302) |  | GET | `/api/v5/public/insurance-fund` |
| [getUnitConvert()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2306) |  | GET | `/api/v5/public/convert-contract-coin` |
| [getOptionTickBands()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2310) |  | GET | `/api/v5/public/instrument-tick-bands` |
| [getPremiumHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2317) |  | GET | `/api/v5/public/premium-history` |
| [getIndexTickers()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2321) |  | GET | `/api/v5/market/index-tickers` |
| [getIndexCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2328) |  | GET | `/api/v5/market/index-candles` |
| [getHistoricIndexCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2332) |  | GET | `/api/v5/market/history-index-candles` |
| [getMarkPriceCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2336) |  | GET | `/api/v5/market/mark-price-candles` |
| [getHistoricMarkPriceCandles()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2340) |  | GET | `/api/v5/market/history-mark-price-candles` |
| [getOracle()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2346) |  | GET | `/api/v5/market/open-oracle` |
| [getExchangeRate()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2350) |  | GET | `/api/v5/market/exchange-rate` |
| [getIndexComponents()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2354) |  | GET | `/api/v5/market/index-components` |
| [getEconomicCalendar()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2358) | :closed_lock_with_key:  | GET | `/api/v5/public/economic-calendar` |
| [getPublicBlockTrades()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2364) |  | GET | `/api/v5/market/block-trades` |
| [getSupportCoin()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2374) |  | GET | `/api/v5/rubik/stat/trading-data/support-coin` |
| [getOpenInterestHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2378) |  | GET | `/api/v5/rubik/stat/contracts/open-interest-history` |
| [getTakerVolume()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2387) |  | GET | `/api/v5/rubik/stat/taker-volume` |
| [getContractTakerVolume()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2397) |  | GET | `/api/v5/rubik/stat/taker-volume-contract` |
| [getMarginLendingRatio()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2403) |  | GET | `/api/v5/rubik/stat/margin/loan-ratio` |
| [getTopTradersAccountRatio()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2412) |  | GET | `/api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader` |
| [getTopTradersContractPositionRatio()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2421) |  | GET | `/api/v5/rubik/stat/contracts/long-short-position-ratio-contract-top-trader` |
| [getLongShortContractRatio()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2430) |  | GET | `/api/v5/rubik/stat/contracts/long-short-account-ratio-contract` |
| [getLongShortRatio()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2439) |  | GET | `/api/v5/rubik/stat/contracts/long-short-account-ratio` |
| [getContractsOpenInterestAndVolume()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2451) |  | GET | `/api/v5/rubik/stat/contracts/open-interest-volume` |
| [getOptionsOpenInterestAndVolume()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2463) |  | GET | `/api/v5/rubik/stat/option/open-interest-volume` |
| [getPutCallRatio()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2470) |  | GET | `/api/v5/rubik/stat/option/open-interest-volume-ratio` |
| [getOpenInterestAndVolumeExpiry()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2480) |  | GET | `/api/v5/rubik/stat/option/open-interest-volume-expiry` |
| [getOpenInterestAndVolumeStrike()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2490) |  | GET | `/api/v5/rubik/stat/option/open-interest-volume-strike` |
| [getTakerFlow()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2501) |  | GET | `/api/v5/rubik/stat/option/taker-block-volume` |
| [getCurrencies()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2511) | :closed_lock_with_key:  | GET | `/api/v5/asset/currencies` |
| [getBalances()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2515) | :closed_lock_with_key:  | GET | `/api/v5/asset/balances` |
| [getNonTradableAssets()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2519) | :closed_lock_with_key:  | GET | `/api/v5/asset/non-tradable-assets` |
| [getAccountAssetValuation()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2523) | :closed_lock_with_key:  | GET | `/api/v5/asset/asset-valuation` |
| [fundsTransfer()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2529) | :closed_lock_with_key:  | POST | `/api/v5/asset/transfer` |
| [getFundsTransferState()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2534) | :closed_lock_with_key:  | GET | `/api/v5/asset/transfer-state` |
| [getAssetBillsDetails()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2545) | :closed_lock_with_key:  | GET | `/api/v5/asset/bills` |
| [getAssetBillsHistoric()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2567) | :closed_lock_with_key:  | GET | `/api/v5/asset/bills-history` |
| [getLightningDeposits()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2581) | :closed_lock_with_key:  | GET | `/api/v5/asset/deposit-lightning` |
| [getDepositAddress()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2589) | :closed_lock_with_key:  | GET | `/api/v5/asset/deposit-address` |
| [getDepositHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2593) | :closed_lock_with_key:  | GET | `/api/v5/asset/deposit-history` |
| [submitWithdraw()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2599) | :closed_lock_with_key:  | POST | `/api/v5/asset/withdrawal` |
| [submitWithdrawLightning()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2603) | :closed_lock_with_key:  | POST | `/api/v5/asset/withdrawal-lightning` |
| [cancelWithdrawal()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2611) | :closed_lock_with_key:  | POST | `/api/v5/asset/cancel-withdrawal` |
| [getWithdrawalHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2615) | :closed_lock_with_key:  | GET | `/api/v5/asset/withdrawal-history` |
| [getDepositWithdrawStatus()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2619) | :closed_lock_with_key:  | GET | `/api/v5/asset/deposit-withdraw-status` |
| [getExchanges()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2625) |  | GET | `/api/v5/asset/exchange-list` |
| [applyForMonthlyStatement()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2629) | :closed_lock_with_key:  | POST | `/api/v5/asset/monthly-statement` |
| [getMonthlyStatement()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2633) | :closed_lock_with_key:  | GET | `/api/v5/asset/monthly-statement` |
| [getConvertCurrencies()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2637) | :closed_lock_with_key:  | GET | `/api/v5/asset/convert/currencies` |
| [getConvertCurrencyPair()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2641) | :closed_lock_with_key:  | GET | `/api/v5/asset/convert/currency-pair` |
| [estimateConvertQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2650) | :closed_lock_with_key:  | POST | `/api/v5/asset/convert/estimate-quote` |
| [convertTrade()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2654) | :closed_lock_with_key:  | POST | `/api/v5/asset/convert/trade` |
| [getConvertHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2658) | :closed_lock_with_key:  | GET | `/api/v5/asset/convert/history` |
| [getSubAccountList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2669) | :closed_lock_with_key:  | GET | `/api/v5/users/subaccount/list` |
| [resetSubAccountAPIKey()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2673) | :closed_lock_with_key:  | POST | `/api/v5/users/subaccount/modify-apikey` |
| [getSubAccountBalances()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2683) | :closed_lock_with_key:  | GET | `/api/v5/account/subaccount/balances` |
| [getSubAccountFundingBalances()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2689) | :closed_lock_with_key:  | GET | `/api/v5/asset/subaccount/balances` |
| [getSubAccountMaxWithdrawal()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2696) | :closed_lock_with_key:  | GET | `/api/v5/account/subaccount/max-withdrawal` |
| [getSubAccountTransferHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2703) | :closed_lock_with_key:  | GET | `/api/v5/asset/subaccount/bills` |
| [getManagedSubAccountTransferHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2714) | :closed_lock_with_key:  | GET | `/api/v5/asset/subaccount/managed-subaccount-bills` |
| [transferSubAccountBalance()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2724) | :closed_lock_with_key:  | POST | `/api/v5/asset/subaccount/transfer` |
| [setSubAccountTransferOutPermission()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2730) | :closed_lock_with_key:  | POST | `/api/v5/users/subaccount/set-transfer-out` |
| [getSubAccountCustodyTradingList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2740) | :closed_lock_with_key:  | GET | `/api/v5/users/entrust-subaccount-list` |
| [setSubAccountLoanAllocation()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2746) | :closed_lock_with_key:  | POST | `/api/v5/account/subaccount/set-loan-allocation` |
| [getSubAccountBorrowInterestAndLimit()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2759) | :closed_lock_with_key:  | GET | `/api/v5/account/subaccount/interest-limits` |
| [getStakingOffers()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2776) | :closed_lock_with_key:  | GET | `/api/v5/finance/staking-defi/offers` |
| [submitStake()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2784) | :closed_lock_with_key:  | POST | `/api/v5/finance/staking-defi/purchase` |
| [redeemStake()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2795) | :closed_lock_with_key:  | POST | `/api/v5/finance/staking-defi/redeem` |
| [cancelStakingRequest()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2803) | :closed_lock_with_key:  | POST | `/api/v5/finance/staking-defi/cancel` |
| [getActiveStakingOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2811) | :closed_lock_with_key:  | GET | `/api/v5/finance/staking-defi/orders-active` |
| [getStakingOrderHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2824) | :closed_lock_with_key:  | GET | `/api/v5/finance/staking-defi/orders-history` |
| [getETHStakingProductInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2844) |  | GET | `/api/v5/finance/staking-defi/eth/product-info` |
| [getSOLStakingProductInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2848) |  | GET | `/api/v5/finance/staking-defi/sol/product-info` |
| [purchaseETHStaking()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2852) | :closed_lock_with_key:  | POST | `/api/v5/finance/staking-defi/eth/purchase` |
| [redeemETHStaking()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2859) | :closed_lock_with_key:  | POST | `/api/v5/finance/staking-defi/eth/redeem` |
| [getETHStakingBalance()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2863) | :closed_lock_with_key:  | GET | `/api/v5/finance/staking-defi/eth/balance` |
| [getETHStakingHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2867) | :closed_lock_with_key:  | GET | `/api/v5/finance/staking-defi/eth/purchase-redeem-history` |
| [cancelRedeemETHStaking()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2880) | :closed_lock_with_key:  | POST | `/api/v5/finance/staking-defi/eth/cancel-redeem` |
| [getAPYHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2891) |  | GET | `/api/v5/finance/staking-defi/eth/apy-history` |
| [getSavingBalance()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2901) | :closed_lock_with_key:  | GET | `/api/v5/finance/savings/balance` |
| [savingsPurchaseRedemption()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2905) | :closed_lock_with_key:  | POST | `/api/v5/finance/savings/purchase-redempt` |
| [setLendingRate()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2914) | :closed_lock_with_key:  | POST | `/api/v5/finance/savings/set-lending-rate` |
| [getLendingHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2921) | :closed_lock_with_key:  | GET | `/api/v5/finance/savings/lending-history` |
| [getPublicBorrowInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2925) |  | GET | `/api/v5/finance/savings/lending-rate-summary` |
| [getPublicBorrowHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2929) |  | GET | `/api/v5/finance/savings/lending-rate-history` |
| [getLendingOffers()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2941) |  | GET | `/api/v5/finance/fixed-loan/lending-offers` |
| [getLendingAPYHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2945) |  | GET | `/api/v5/finance/fixed-loan/lending-apy-history` |
| [getLendingVolume()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2949) |  | GET | `/api/v5/finance/fixed-loan/pending-lending-volume` |
| [placeLendingOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2956) | :closed_lock_with_key:  | POST | `/api/v5/finance/fixed-loan/lending-order` |
| [amendLendingOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2960) | :closed_lock_with_key:  | POST | `/api/v5/finance/fixed-loan/amend-lending-order` |
| [getLendingOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2967) | :closed_lock_with_key:  | GET | `/api/v5/finance/fixed-loan/lending-orders-list` |
| [getLendingSubOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2974) | :closed_lock_with_key:  | GET | `/api/v5/finance/fixed-loan/lending-sub-orders` |
| [getBorrowableCurrencies()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2987) |  | GET | `/api/v5/finance/flexible-loan/borrow-currencies` |
| [getCollateralAssets()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L2995) |  | GET | `/api/v5/finance/flexible-loan/collateral-assets` |
| [getMaxLoanAmount()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3001) | :closed_lock_with_key:  | POST | `/api/v5/finance/flexible-loan/max-loan` |
| [adjustCollateral()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3005) | :closed_lock_with_key:  | POST | `/api/v5/finance/flexible-loan/adjust-collateral` |
| [getLoanInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3012) | :closed_lock_with_key:  | GET | `/api/v5/finance/flexible-loan/loan-info` |
| [getLoanHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3016) | :closed_lock_with_key:  | GET | `/api/v5/finance/flexible-loan/loan-history` |
| [getAccruedInterest()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3023) | :closed_lock_with_key:  | GET | `/api/v5/finance/flexible-loan/interest-accrued` |
| [getDcdCurrencyPairs()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3039) | :closed_lock_with_key:  | GET | `/api/v5/finance/sfp/dcd/currency-pair` |
| [getDcdProducts()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3043) | :closed_lock_with_key:  | GET | `/api/v5/finance/sfp/dcd/products` |
| [requestDcdQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3047) | :closed_lock_with_key:  | POST | `/api/v5/finance/sfp/dcd/quote` |
| [submitDcdTrade()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3051) | :closed_lock_with_key:  | POST | `/api/v5/finance/sfp/dcd/trade` |
| [requestDcdRedeemQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3055) | :closed_lock_with_key:  | POST | `/api/v5/finance/sfp/dcd/redeem-quote` |
| [submitDcdRedeem()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3061) | :closed_lock_with_key:  | POST | `/api/v5/finance/sfp/dcd/redeem` |
| [getDcdOrderStatus()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3065) | :closed_lock_with_key:  | GET | `/api/v5/finance/sfp/dcd/order-status` |
| [getDcdOrderHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3071) | :closed_lock_with_key:  | GET | `/api/v5/finance/sfp/dcd/order-history` |
| [getStableRewardsProductInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3084) | :closed_lock_with_key:  | GET | `/api/v5/finance/stable-rewards/product-info` |
| [requestStableRewardsQuote()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3093) | :closed_lock_with_key:  | POST | `/api/v5/finance/stable-rewards/quote` |
| [submitStableRewardsTrade()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3099) | :closed_lock_with_key:  | POST | `/api/v5/finance/stable-rewards/trade` |
| [getStableRewardsBalance()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3105) | :closed_lock_with_key:  | GET | `/api/v5/finance/stable-rewards/balance` |
| [getStableRewardsApyHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3111) |  | GET | `/api/v5/finance/stable-rewards/apy-history` |
| [getStableRewardsSubscribeRedeemHistory()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3117) | :closed_lock_with_key:  | GET | `/api/v5/finance/stable-rewards/subscribe-redeem-history` |
| [getAffiliatePerformanceSummary()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3133) | :closed_lock_with_key:  | GET | `/api/v5/affiliate/performance/summary` |
| [getInviteeDetail()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3139) | :closed_lock_with_key:  | GET | `/api/v5/affiliate/invitee/detail` |
| [getAffiliateInviteeList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3143) | :closed_lock_with_key:  | GET | `/api/v5/affiliate/invitee/list` |
| [getAffiliateLinkList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3149) | :closed_lock_with_key:  | GET | `/api/v5/affiliate/link/list` |
| [getAffiliateCoInviterLinkList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3155) | :closed_lock_with_key:  | GET | `/api/v5/affiliate/co-inviter/list` |
| [getAffiliateSubAffiliateList()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3161) | :closed_lock_with_key:  | GET | `/api/v5/affiliate/sub-affiliate/list` |
| [getAffiliateRebateInfo()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3167) | :closed_lock_with_key:  | GET | `/api/v5/users/partner/if-rebate` |
| [getSystemStatus()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3177) |  | GET | `/api/v5/system/status` |
| [getAnnouncements()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3189) |  | GET | `/api/v5/support/announcements` |
| [getAnnouncementTypes()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3198) |  | GET | `/api/v5/support/announcement-types` |
| [createSubAccount()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3213) | :closed_lock_with_key:  | POST | `/api/v5/broker/nd/create-subaccount` |
| [deleteSubAccount()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3222) | :closed_lock_with_key:  | POST | `/api/v5/broker/nd/delete-subaccount` |
| [createSubAccountAPIKey()](https://github.com/tiagosiebler/okx-api/blob/master/src/rest-client.ts#L3226) | :closed_lock_with_key:  | POST | `/api/v5/broker/nd/subaccount/apikey` |

# websocket-api-client.ts

This table includes all endpoints from the official Exchange API docs and corresponding SDK functions for each endpoint that are found in [websocket-api-client.ts](/src/websocket-api-client.ts). 

This client provides WebSocket API endpoints which allow for faster interactions with the OKX API via a WebSocket connection.

| Function | AUTH | HTTP Method | Endpoint |
| -------- | :------: | :------: | -------- |
| [submitNewOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L89) | :closed_lock_with_key:  | WS | `order` |
| [submitMultipleOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L104) | :closed_lock_with_key:  | WS | `batch-orders` |
| [cancelOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L119) | :closed_lock_with_key:  | WS | `cancel-order` |
| [cancelMultipleOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L134) | :closed_lock_with_key:  | WS | `batch-cancel-orders` |
| [amendOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L149) | :closed_lock_with_key:  | WS | `amend-order` |
| [amendMultipleOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L164) | :closed_lock_with_key:  | WS | `batch-amend-orders` |
| [massCancelOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L179) | :closed_lock_with_key:  | WS | `mass-cancel` |
| [submitSpreadOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L194) | :closed_lock_with_key:  | WS | `sprd-order` |
| [amendSpreadOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L209) | :closed_lock_with_key:  | WS | `sprd-amend-order` |
| [cancelSpreadOrder()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L226) | :closed_lock_with_key:  | WS | `sprd-cancel-order` |
| [massCancelSpreadOrders()](https://github.com/tiagosiebler/okx-api/blob/master/src/websocket-api-client.ts#L243) | :closed_lock_with_key:  | WS | `sprd-mass-cancel` |