export interface APICredentials {
  apiKey: string;
  apiSecret: string;
  apiPass: string;
}

/**
 * The API Market represents the OKX Domain that you have signed up for. At this time, there are 4 supported domain groups:
 *
 * - GLOBAL, otherwise known as "www.okx.com".
 * - OPENAPI_GLOBAL, OKX Global REST at openapi.okx.com (same WS as GLOBAL).
 * - EEA, otherwise known as "my.okx.com".
 * - US, otherwise known as "app.okx.com".
 */
export type APIMarket =
  | 'prod' // same as GLOBAL. Kept for some backwards compatibility
  // also known as "www.okx.com" or OKX Global: https://www.okx.com/docs-v5/en/#overview-production-trading-services
  | 'GLOBAL'
  // OKX Global REST at https://openapi.okx.com. WebSocket URLs unchanged (same as GLOBAL).
  | 'OPENAPI_GLOBAL'
  // also known as "my.okx.com" https://my.okx.com/docs-v5/en/#overview-production-trading-services
  | 'EEA'
  // also known as "app.okx.com" https://app.okx.com/docs-v5/en/#overview-production-trading-services
  | 'US';
