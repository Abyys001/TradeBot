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

    // --- financial management (the ledger) ---
    /** Deposits, withdrawals, per-account PnL and the profit split in one shot. */
    ledger: () => request<LedgerSnapshot>('/accounts/ledger/'),
    movements: (accountId?: number | null) =>
      request<FundMovement[]>(`/accounts/ledger/movements/${accountId ? `?account=${accountId}` : ''}`),
    createMovement: (body: Record<string, unknown>) =>
      request<FundMovement>('/accounts/ledger/movements/', { method: 'POST', body }),
    deleteMovement: (id: number) =>
      request<void>(`/accounts/ledger/movements/${id}/`, { method: 'DELETE' }),
    ledgerSplit: () => request<ProfitSplit>('/accounts/ledger/split/'),
    saveLedgerSplit: (body: Record<string, unknown>) =>
      request<ProfitSplit>('/accounts/ledger/split/', { method: 'POST', body }),
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

export interface HistoryStatus {
  /**
   * Where the pair's own chart-driven download stands:
   *
   *   - `none` — history is off (no public feed configured).
   *   - `ready` — stored bars already span the configured window.
   *   - `downloading` — a download is queued or running; `percent` is how far.
   *   - `failed` — the last attempt failed and is inside its retry cooldown.
   */
  state: 'none' | 'downloading' | 'ready' | 'failed'
  /** The timeframe the chart currently has on screen (fetched first). */
  interval: string
  days: number
  intervals: string[]
  series_done: number
  series_total: number
  percent: number
  /** How many other pairs are waiting behind this one. */
  queued: number
  error: string
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
   * True when the bars came from downloaded history rather than the live feed
   * (`live` is then false too): stored exchange data, merely old.
   */
  stored?: boolean
  /**
   * The venue the feed is locked to (`MARKET_DATA_PIN`), or '' when it follows
   * the connected accounts. Named separately from `source` so the chart can say
   * which venue is *allowed* to answer, not just which one did.
   */
  pinned: string
  /** Measured engine→exchange round trip in ms, null when nothing was timed. */
  provider_ms: number | null
  candles: ApiCandle[]
  /**
   * Present when the live feed was down and the chart turned to the pair's own
   * download: the reason the real-time price is missing.
   */
  feed_error?: string
  /**
   * The pair's on-demand history download. Attached to every success (state
   * `ready` when stored bars cover the window) and to the 202 the endpoint
   * answers while the download is running (state `downloading`).
   */
  history?: HistoryStatus
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

// --- the financial ledger ---------------------------------------------------

/** A cash flow, recorded by hand — the keys are trade-only (spec §7). */
export interface FundMovement {
  id: number
  account: number
  account_label: string
  kind: 'deposit' | 'withdrawal'
  amount: string
  asset: string
  occurred_at: string
  note: string
  created_at: string
}

/** The three roles the profit is split between. Percentages, not dollars. */
export interface SplitPercents {
  investor: string
  trader: string
  programmer: string
}

/** One account's row: what went in, what came out, what it is worth now. */
export interface LedgerRow {
  account: number
  label: string
  exchange: string
  exchange_label: string
  status: string
  testnet: boolean
  hidden: boolean
  asset: string
  balance_is_usdt: boolean
  deposits: string
  withdrawals: string
  net_invested: string
  current_balance: string | null
  pnl: string | null
  pnl_pct: string | null
  shares: SplitPercents
}

/** An exchange's aggregate, or the grand total — same shape, one more key. */
export interface LedgerGroup extends SplitPercents {
  accounts: number
  net_invested: string
  current_balance: string
  pnl: string
  pnl_pct: string | null
  shares: SplitPercents
}

export interface LedgerExchange extends LedgerGroup {
  exchange: string
  label: string
}

export interface LedgerSnapshot {
  accounts: LedgerRow[]
  exchanges: LedgerExchange[]
  totals: LedgerGroup
  split: SplitPercents
  non_usdt: { account: number; label: string; asset: string }[]
}

export interface ProfitSplit extends SplitPercents {
  updated_at: string
  updated_by: string
}
