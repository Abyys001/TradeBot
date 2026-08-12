import type {
  AmendAttachedTrailingStop,
  AttachAlgoOrdRequest,
} from '../rest/request/trade.js';
import {
  numberInString,
  OrderSide,
  OrderType,
  PositionSide,
  TradeMode,
} from '../rest/shared.js';

export interface WSAPIPlaceOrderRequestV5 {
  /** Instrument ID. Deprecated March 2026; use instIdCode for lower latency. */
  instId?: string;
  /** Instrument ID code. Takes precedence over instId if both provided. Use Get instruments to map. */
  instIdCode?: number;
  tdMode: TradeMode;
  ccy?: string;
  clOrdId?: string;
  tag?: string;
  side: OrderSide;
  posSide?: PositionSide;
  ordType: OrderType;
  /** Quantity to buy or sell */
  sz: numberInString;
  px?: numberInString;
  pxUsd?: numberInString;
  pxVol?: numberInString;
  reduceOnly?: boolean;
  /** A spot buy on BTC-USDT with "base_ccy" would mean the QTY (sz) is in USDT */
  tgtCcy?: 'base_ccy' | 'quote_ccy';
  /**
   * Maximum acceptable slippage for spot and spot margin market-side orders, where tgtCcy is the received currency (base_ccy for buy, quote_ccy for sell).
   * Range: 0 to 0.05 (0% to 5%, inclusive). Up to 2 decimal places, e.g. 0.01 (1%) and 0.0123 (1.23%). Defaults to 0.00% if not specified.
   * Only applicable to SPOT and SPOT margin market orders. Cannot be amended on an existing order.
   */
  slippagePct?: string;
  banAmend?: boolean;
  tradeQuoteCcy?: string;
  stpMode?: 'cancel_maker' | 'cancel_taker' | 'cancel_both';
  /** ELP taker access. true = can trade with ELP orders (speed bump applied). Default false. Only applicable to ioc orders */
  isElpTakerAccess?: boolean;
  /** EVENTS: `"1"` for non-`post_only` orders when required (error 54086 if missing). */
  speedBump?: string;
  /** EVENTS: `yes` or `no`. */
  outcome?: string;
  attachAlgoOrds?: AttachAlgoOrdRequest[];
}

export interface WSAPIAmendOrderRequestV5 {
  /**
   * If set, ignored  for `amend-order` / `batch-amend-orders` — use `ordId`/`clOrdId` to identify the order.
   * Map codes via Get instruments as needed.
   */
  instId?: string;
  /** Use Get instruments to map. */
  instIdCode?: number;
  cxlOnFail?: boolean;
  ordId?: string;
  clOrdId?: string;
  reqId?: string;
  newSz?: string;
  newPx?: string;
  newPxUsd?: string;
  newPxVol?: string;
  speedBump?: string;
  attachAlgoOrds?: AmendAttachedTrailingStop[];
}

export interface WSAPIMassCancelOrdersRequestV5 {
  instType: string;
  instFamily: string;
  lockInterval?: string;
}

export interface WSAPIPlaceSpreadOrderRequestV5 {
  sprdId: string;
  clOrdId?: string;
  tag?: string;
  side: OrderSide;
  ordType: OrderType;
  sz: numberInString;
  px?: numberInString;
}

export interface WSAPIAmendSpreadOrderRequestV5 {
  ordId?: string;
  clOrdId?: string;
  reqId?: string;
  newSz?: string;
  newPx?: string;
}

export interface WSAPICancelSpreadOrderRequestV5 {
  ordId?: string;
  clOrdId?: string;
}

export interface WSAPISpreadMassCancelOrdersRequestV5 {
  sprdId?: string;
}
