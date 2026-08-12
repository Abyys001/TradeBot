export interface StableRewardsProductInfoDetail {
  ccy: string;
  settleCcy: string;
  subFeeRate: string;
  redemptFeeRate: string;
  minSubAmt: string;
  minRedeemAmt: string;
  remainingSubQuota: string;
  remainingRedemptQuota: string;
  canRedeem: boolean;
}

export interface StableRewardsProductInfo {
  details: StableRewardsProductInfoDetail[];
  ts: string;
}

export interface StableRewardsQuote {
  quoteId: string;
  quoteAmt: string;
  quoteCcy: string;
  exchRate: string;
  feeRate: string;
  quoteTime: string;
  ttlMs: string;
}

export interface StableRewardsTradeResult {
  quoteId: string;
  ordId: string;
}

export type StableRewardsBalanceState = 'earning' | 'pending';

export interface StableRewardsBalanceDetail {
  ccy: string;
  amt: string;
  totalEarnAccrual: string;
  state: StableRewardsBalanceState;
}

export interface StableRewardsBalance {
  details: StableRewardsBalanceDetail[];
  ts: string;
}

export interface StableRewardsApyHistoryItem {
  rate: string;
  ts: string;
}

export type StableRewardsSubscribeRedeemType = 'subscribe' | 'redeem';

export type StableRewardsSubscribeRedeemStatus =
  | 'pending'
  | 'success'
  | 'failed';

export interface StableRewardsSubscribeRedeemHistoryItem {
  type: StableRewardsSubscribeRedeemType;
  status: StableRewardsSubscribeRedeemStatus;
  ccy: string;
  settleCcy: string;
  ccyAmt: string;
  settleCcyAmt: string;
  fee: string;
  quoteId: string;
  ordId: string;
  ts: string;
}
