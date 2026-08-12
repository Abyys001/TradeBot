export interface GetStableRewardsProductInfoRequest {
  ccy: string;
}

export interface RequestStableRewardsQuoteRequest {
  ccy: string;
  settleCcy: string;
  action: 'subscribe' | 'redeem';
  amt: string;
}

export interface SubmitStableRewardsTradeRequest {
  quoteId: string;
}

export interface GetStableRewardsBalanceRequest {
  ccy?: string;
}

export interface GetStableRewardsApyHistoryRequest {
  ccy: string;
  days?: string;
}

export interface GetStableRewardsSubscribeRedeemHistoryRequest {
  ccy: string;
  type?: 'subscribe' | 'redeem';
  status?: 'pending' | 'success' | 'failed';
  after?: string;
  before?: string;
  limit?: string;
}
