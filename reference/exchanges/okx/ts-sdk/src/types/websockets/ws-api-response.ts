import { numberInString } from '../rest/shared.js';

export interface WSAPICancelOrderResultV5 {
  clOrdId: string;
  ordId: string;
  ts: numberInString;
  sCode: string;
  subCode?: string;
  sMsg: string;
}

export interface WSAPISpreadPlaceOrderResultV5 {
  clOrdId: string;
  ordId: string;
  tag: string;
  sCode: numberInString;
  subCode?: string;
  sMsg: string;
}

export interface WSAPISpreadAmendOrderResultV5 {
  clOrdId: string;
  ordId: string;
  reqId: string;
  sCode: string;
  subCode?: string;
  sMsg: string;
}

export interface WSAPISpreadCancelOrderResultV5 {
  clOrdId: string;
  ordId: string;
  sCode: string;
  subCode?: string;
  sMsg: string;
}

/**
 * @see Ws public channel: estimated-price
 */
export type WsEstimatedPriceSettleType = 'settlement' | 'delivery' | 'exercise';

export interface WsEstimatedPriceData {
  instId: string;
  instType: string;
  settlePx: string;
  settleType: WsEstimatedPriceSettleType;
  ts: string;
}
