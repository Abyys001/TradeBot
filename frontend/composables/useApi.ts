/**
 * API client. Same-origin: requests go to the panel's own /api, which the Nuxt
 * server proxies to Django (see server/api/[...path].ts).
 */
function readCookie(name: string): string {
  if (import.meta.server) return ''
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`))
  return match ? decodeURIComponent(match[2]) : ''
}

export function useApi() {
  const base = useRuntimeConfig().public.apiBase

  const request = <T>(path: string, options: Record<string, any> = {}) => {
    const method = (options.method ?? 'GET').toUpperCase()
    const headers: Record<string, string> = { ...(options.headers ?? {}) }

    // Django rejects unsafe methods without the CSRF token. It rides in a
    // cookie the server set; we echo it back in the header it expects.
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const token = readCookie('csrftoken')
      if (token) headers['X-CSRFToken'] = token
    }

    return $fetch<T>(`${base}${path}`, { credentials: 'include', ...options, headers })
  }

  return {
    // --- session ---
    csrf: () => request<{ csrf_token: string }>('/accounts/auth/csrf/'),
    login: (username: string, password: string) =>
      request<SessionUser>('/accounts/auth/login/', {
        method: 'POST',
        body: { username, password },
      }),
    logout: () => request<SessionUser>('/accounts/auth/logout/', { method: 'POST' }),
    me: () => request<SessionUser>('/accounts/auth/me/'),

    // --- config ---
    policy: () => request<Policy>('/trading/policy/'),
    // Spec §7 emergency halt.
    stopAllState: () => request<StopAllState>('/trading/stop-all/'),
    setStopAll: (on: boolean, reason = '') =>
      request<StopAllState>('/trading/stop-all/', { method: 'POST', body: { on, reason } }),
    exchanges: () => request<{ exchanges: ExchangeInfo[] }>('/trading/exchanges/'),
    riskPreview: (body: Record<string, unknown>) =>
      request<RiskPreview>('/trading/risk-preview/', { method: 'POST', body }),

    // --- accounts (spec §6) ---
    accounts: () => request<Account[]>('/accounts/accounts/'),
    balances: () => request<BalancesResponse>('/accounts/accounts/balances/'),
    createAccount: (body: Record<string, unknown>) =>
      request<Account>('/accounts/accounts/', { method: 'POST', body }),
    verifyAccount: (id: number) =>
      request<Account>(`/accounts/accounts/${id}/verify/`, { method: 'POST' }),
    pause: (id: number) => request<Account>(`/accounts/accounts/${id}/pause/`, { method: 'POST' }),
    resume: (id: number) =>
      request<Account>(`/accounts/accounts/${id}/resume/`, { method: 'POST' }),
    remove: (id: number) => request<void>(`/accounts/accounts/${id}/`, { method: 'DELETE' }),
    /**
     * `force` is what the button sends: a human asking for fresh numbers gets
     * them. The background poll leaves it off and is rate-limited server-side,
     * so N open tabs do not mean N fan-outs to every exchange.
     */
    refreshBalances: (force = false) =>
      request<{ accounts: unknown[] }>('/trading/balances/refresh/', {
        method: 'POST',
        body: { force },
      }),

    // --- notifications (spec §4) ---
    notifications: () => request<ApiNotification[]>('/accounts/notifications/?active=true'),
    dismiss: (id: number) =>
      request<ApiNotification>(`/accounts/notifications/${id}/dismiss/`, { method: 'POST' }),

    // --- order routing (spec §3, §4) ---
    openOrder: (body: Record<string, unknown>) =>
      request<FanOutResult>('/trading/orders/open/', { method: 'POST', body }),
    amendOrder: (id: number, body: Record<string, unknown>) =>
      request<FanOutResult>(`/trading/orders/${id}/amend/`, { method: 'POST', body }),
    closeOrder: (id: number) =>
      request<FanOutResult>(`/trading/orders/${id}/close/`, { method: 'POST' }),

    // --- market data (spec §3) ---
    candles: (params: { symbol: string; interval: string; market: string; limit?: number }) =>
      request<CandleFeed>(
        `/trading/market/candles/?symbol=${params.symbol}&interval=${params.interval}` +
          `&market=${params.market}&limit=${params.limit ?? 300}`,
      ),
    ticker: (symbol: string, market: string) =>
      request<TickerQuote>(`/trading/market/ticker/?symbol=${symbol}&market=${market}`),
    /** One round trip for the whole watchlist; each quote is cached server-side. */
    tickers: (symbols: string[], market: string) =>
      request<{ tickers: TickerQuote[]; unavailable: string[] }>(
        `/trading/market/tickers/?symbols=${symbols.join(',')}&market=${market}`,
      ),
    symbols: () => request<{ symbols: SymbolInfo[]; intervals: string[] }>('/trading/market/symbols/'),
    /** The open trade marked to market — PnL is computed server-side in Decimal. */
    positions: () => request<PositionSnapshot>('/trading/positions/'),

    // --- history (spec §8) ---
    trades: (accountId?: number | null) =>
      request<Trade[]>(`/trading/trades/${accountId ? `?account=${accountId}` : ''}`),
  }
}

export interface StopAllState {
  stop_all: boolean
  runtime: boolean
  /** True when the environment pinned the halt on — the panel cannot clear it. */
  locked: boolean
  source: 'env' | 'panel' | 'off'
  reason: string
  updated_at: string | null
  updated_by: string
}

export interface ApiCandle {
  t: number
  o: string
  h: string
  l: string
  c: string
  v: string
}

export interface CandleFeed {
  symbol: string
  interval: string
  market: string
  source: string
  /**
   * Always true on a 200: every candle came from an exchange. There is no
   * synthetic series any more — a feed outage is a 503, not a chart.
   */
  live: boolean
  /**
   * The venue the feed is locked to (`MARKET_DATA_PIN`), or '' when it follows
   * the connected accounts. Named separately from `source` so the chart can say
   * which venue is *allowed* to answer, not just which one did.
   */
  pinned: string
  /** Measured engine→exchange round trip in ms, null when nothing was timed. */
  provider_ms: number | null
  candles: ApiCandle[]
}

export interface TickerQuote {
  symbol: string
  price: string
  change_pct: string | null
  at: number
  market: string
  source: string
  live: boolean
  pinned: string
  provider_ms: number | null
}

export interface SymbolInfo {
  symbol: string
  base: string
  quote: string
}

export interface PositionLeg {
  account: number
  account_label: string
  exchange: string
  ok: boolean
  error: string
  error_code: string
  sltp_attached: boolean
  qty: string | null
  entry_price: string | null
  margin: string | null
  notional: string | null
  stop_loss: string | null
  take_profit: string | null
  liquidation_price: string | null
  pnl: string | null
  pnl_pct: string | null
  roe_pct: string | null
}

export interface PositionSnapshot {
  trade: {
    id: number
    symbol: string
    side: string
    market: string
    leverage: number
    sl_pct: string | null
    tp_pct: string | null
    sltp_basis: string
    admin_entry_price: string | null
    opened_at: string
  } | null
  mark: TickerQuote | null
  /** Non-empty when no exchange could be reached: PnL is null, not zero. */
  feed_error?: string
  legs: PositionLeg[]
  totals: {
    accounts: number
    failed: number
    qty: string | null
    margin: string | null
    notional: string | null
    pnl: string | null
    roe_pct: string | null
  } | null
}

export interface SessionUser {
  username?: string
  is_staff?: boolean
  /**
   * Whether this operator may see hidden accounts. Drives the hidden toggle and
   * the hidden badge, and nothing else — the server filters every payload
   * regardless, so a client that flips this to true still receives no hidden
   * account to render.
   */
  can_see_hidden?: boolean
  authenticated: boolean
}

export interface ExchangeInfo {
  exchange: string
  label: string
  has_testnet: boolean
  note: string
  markets: string[]
  native_sltp_amend: boolean
  per_key_rate_limits: boolean
  wallet_based_auth: boolean
}

export interface RiskLine {
  basis: 'price' | 'margin'
  stop_price: string | null
  take_profit_price: string | null
  loss_at_stop: string
  loss_pct_of_account: string
  profit_at_tp: string
  price_move_pct: string
  reachable: boolean
  note: string
}

export interface RiskPreview {
  inputs: Record<string, unknown>
  position: {
    balance_fraction: string
    margin: string
    notional: string
    qty: string
    liquidation_price: string
    liquidation_distance_pct: string
  }
  readings: { price: RiskLine; margin: RiskLine }
  active_basis: 'price' | 'margin'
}

export interface Policy {
  balance_fraction: string
  sltp_basis: string
  sltp_reference: string
  sltp_amend_strategy: string
  sltp_failure_policy: string
  reject_sl_beyond_liquidation: boolean
  fanout_timeout_seconds: number
  leverage_range: [number, number]
  stop_all: boolean
  stop_all_locked: boolean
  stop_all_source: 'env' | 'panel' | 'off'
  stop_all_reason: string
  open_questions: Record<string, string>
}

export interface Account {
  id: number
  label: string
  exchange: string
  exchange_label: string
  status: 'active' | 'paused' | 'error'
  testnet: boolean
  /**
   * Trades like any other account; visible only to the one operator allowed to
   * see it. Never true on a row anyone else receives — the server strips those
   * rows out entirely rather than sending them with a flag to respect.
   */
  hidden?: boolean
  wallet_address?: string
  key_fingerprint?: string
  last_balance: string | null
  last_balance_asset: string
  last_balance_at?: string | null
  balance_is_usdt: boolean
  is_tradeable: boolean
  withdrawal_check_passed: boolean
  /** When the spec §7 check last ran — null means never. Separate from the
   * verdict: five exchanges publish no permission endpoint, so "checked but
   * unprovable" is a real state. */
  withdrawal_checked_at: string | null
  credential_expires_at: string | null
  last_error: string
  created_at?: string
}

export interface BalancesResponse {
  accounts: Account[]
  non_usdt: { id: number; label: string; asset: string }[]
}

/** The wire shape. The store enriches it with the account's label. */
export interface ApiNotification {
  id: number
  account: number | null
  message: string
  code: string
  created_at: string
  dismissed_at: string | null
  is_active: boolean
}

export interface TradeLeg {
  id: number
  account: number
  account_label: string
  exchange: string
  ok: boolean
  error: string
  error_code: string
  dispatch_ms: number | null
  qty: string | null
  entry_price: string | null
  exit_price: string | null
  margin: string | null
  stop_loss: string | null
  take_profit: string | null
  sltp_attached: boolean
  pnl: string | null
  opened_at: string | null
  closed_at: string | null
}

export interface Trade {
  id: number
  symbol: string
  side: string
  market: string
  leverage: number
  sl_pct: string | null
  tp_pct: string | null
  sltp_basis: string
  admin_entry_price: string | null
  status: string
  opened_at: string
  closed_at: string | null
  fanout_ms: number | null
  legs: TradeLeg[]
}
