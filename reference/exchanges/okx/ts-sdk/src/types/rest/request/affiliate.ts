export type AffiliatePeriodType =
  | 'last_7d'
  | 'last_30d'
  | 'this_month'
  | 'last_month'
  | 'total'
  | 'today'
  | 'this_week'
  | 'custom';

export type AffiliateCommissionCategory = 'SPOT' | 'DERIVATIVE' | 'BSC';

export type AffiliateKycStatus = 'unverified' | 'verified';

export type AffiliateLinkType = 'standard' | 'co_inviter';

export type AffiliateLinkStatus = 'normal' | 'abnormal';

export type AffiliateInviteeListOrderBy =
  | 'cTime'
  | 'depAmt'
  | 'vol'
  | 'fee'
  | 'rebate';

export type AffiliateSubAffiliateListOrderBy =
  | 'cTime'
  | 'depAmt'
  | 'vol'
  | 'fee'
  | 'rebate';

export type AffiliateOrderDir = 'asc' | 'desc';

export interface GetAffiliatePerformanceSummaryRequest {
  periodType?: AffiliatePeriodType;
  /** Required when periodType=custom, together with end. Inclusive. */
  begin?: string;
  /** Required when periodType=custom, together with begin. Inclusive. */
  end?: string;
}

export interface GetInviteeDetailRequest {
  uid: string;
}

export interface GetAffiliateInviteeListRequest {
  page?: string;
  limit?: string;
  periodType?: AffiliatePeriodType;
  /** Required when periodType=custom, together with end. Inclusive. */
  begin?: string;
  /** Required when periodType=custom, together with begin. Inclusive. */
  end?: string;
  keyword?: string;
  commissionCategory?: AffiliateCommissionCategory;
  orderBy?: AffiliateInviteeListOrderBy;
  orderDir?: AffiliateOrderDir;
  kycStatus?: AffiliateKycStatus;
  subAffiliateUid?: string;
}

export interface GetAffiliateLinkListRequest {
  page?: string;
  limit?: string;
  linkType?: AffiliateLinkType;
  linkStatus?: AffiliateLinkStatus;
}

export interface GetAffiliateCoInviterLinkListRequest {
  page?: string;
  limit?: string;
  linkStatus?: AffiliateLinkStatus;
}

export interface GetAffiliateSubAffiliateListRequest {
  page?: string;
  limit?: string;
  keyword?: string;
  commissionCategory?: AffiliateCommissionCategory;
  orderBy?: AffiliateSubAffiliateListOrderBy;
  orderDir?: AffiliateOrderDir;
}
