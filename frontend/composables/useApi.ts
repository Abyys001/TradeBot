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
    /**
     * May not sign you in. With the second factor armed the server answers
     * `{ mfa_required: true, challenge }` with a 200 and no session — the
     * password was right and the sign-in is half done. `remember` is the
     * "don't ask on this browser again" box, and is ignored unless both the
     * second factor and trusted devices are switched on.
     */
    login: (username: string, password: string, remember = false) =>
      request<LoginResult>('/accounts/auth/login/', {
        method: 'POST',
        body: { username, password, remember },
      }),
    /** The second half of a challenged sign-in. The challenge identifies it,
        not the username — the password is not held in the browser meanwhile. */
    mfa: (challenge: string, code: string, remember = false) =>
      request<LoginResult>('/accounts/auth/mfa/', {
        method: 'POST',
        body: { challenge, code, remember },
      }),
    logout: () => request<SessionUser>('/accounts/auth/logout/', { method: 'POST' }),
    me: () => request<SessionUser>('/accounts/auth/me/'),
    /** Who is signed in — everybody shares one login, so this lists sessions. */
    sessions: () => request<{ sessions: PanelSession[]; count: number }>('/accounts/auth/sessions/'),
    /** End another browser's session. Refuses this one — sign out does that. */
    revokeSession: (id: number) =>
      request<{ revoked: number }>(`/accounts/auth/sessions/${id}/revoke/`, { method: 'POST' }),

    // --- config ---
    policy: () => request<Policy>('/trading/policy/'),
    // Spec §7 emergency halt.
    stopAllState: () => request<StopAllState>('/trading/stop-all/'),
    /**
     * `closePositions` makes the halt a flatten as well: stopping new routing
     * does nothing about the leveraged position already running, which is what
     * the admin means by "stop all". Off for every other caller (Q14).
     */
    setStopAll: (on: boolean, reason = '', closePositions = false) =>
      request<StopAllState>('/trading/stop-all/', {
        method: 'POST',
        body: { on, reason, close_positions: closePositions },
      }),
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
    /** Whether this account takes the admin's own manual entries. */
    setManualTrading: (id: number, enabled: boolean) =>
      request<Account>(`/accounts/accounts/${id}/manual-trading/`, {
        method: 'POST',
        body: { enabled },
      }),
    /** Whether a bot's entries may reach this account. Off by default. */
    setBotTrading: (id: number, enabled: boolean) =>
      request<Account>(`/accounts/accounts/${id}/bot-trading/`, {
        method: 'POST',
        body: { enabled },
      }),
    remove: (id: number) => request<void>(`/accounts/accounts/${id}/`, { method: 'DELETE' }),
    /**
     * One account's whole record — connection, money, every leg it was given.
     * One request rather than six, so the page cannot render its balance
     * before its trades and be wrong twice on the way to being right.
     */
    accountReport: (id: number) => request<AccountReport>(`/accounts/accounts/${id}/report/`),
    /**
     * The same record as a printable PDF statement, for one period.
     *
     * `$fetch.raw` rather than `request` because the server names the file —
     * it is the only side that knows the period, the account and the issue
     * time — and a statement whose filename does not say what it covers is one
     * more thing for whoever receives it to get wrong. `start`/`end` are
     * inclusive `YYYY-MM-DD` days; either may be empty for an open side, and
     * `lang` is the language the *recipient* reads — not the panel's own.
     */
    accountStatement: async (id: number, start = '', end = '', lang = 'en') => {
      const query = new URLSearchParams()
      if (start) query.set('start', start)
      if (end) query.set('end', end)
      query.set('lang', lang)
      const suffix = query.toString() ? `?${query}` : ''
      const response = await $fetch.raw<Blob>(
        `${base}/accounts/accounts/${id}/statement/${suffix}`,
        { credentials: 'include', responseType: 'blob' },
      )
      const disposition = response.headers.get('content-disposition') ?? ''
      const named = /filename="?([^"]+)"?/.exec(disposition)
      return {
        blob: response._data as Blob,
        filename: named?.[1] ?? `tradebot-statement-${id}.pdf`,
      }
    },
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
    /** Every open trade at once — what the panel's close button sends. */
    closeAll: () => request<FanOutResult>('/trading/orders/close-all/', { method: 'POST' }),

    // --- market data (spec §3) ---
    /**
     * OHLCV for the chart. `end` (UNIX seconds) asks for the window *before*
     * that moment, which is how scrolling back pages into the stored archive —
     * the backend has accepted it all along and nothing ever sent it.
     */
    candles: (params: {
      symbol: string
      interval: string
      market: string
      limit?: number
      end?: number
    }) =>
      request<CandleFeed>(
        `/trading/market/candles/?symbol=${params.symbol}&interval=${params.interval}` +
          `&market=${params.market}&limit=${params.limit ?? 300}` +
          (params.end ? `&end=${params.end}` : ''),
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
    editMovement: (id: number, body: Record<string, unknown>) =>
      request<FundMovement>(`/accounts/ledger/movements/${id}/`, { method: 'PATCH', body }),
    deleteMovement: (id: number) =>
      request<void>(`/accounts/ledger/movements/${id}/`, { method: 'DELETE' }),
    detections: (status: 'pending' | 'resolved' | 'all' = 'pending') =>
      request<DetectedMovement[]>(`/accounts/ledger/detections/?status=${status}`),
    /** Book it as an investor cash flow — invested capital moves. */
    acceptDetection: (id: number, body: Record<string, unknown> = {}) =>
      request<FundMovement>(`/accounts/ledger/detections/${id}/accept/`, {
        method: 'POST',
        body,
      }),
    /** Book nothing — capital is untouched, so the change stays in PnL. */
    attributeDetection: (id: number, note = '') =>
      request<DetectedMovement>(`/accounts/ledger/detections/${id}/attribute/`, {
        method: 'POST',
        body: { note },
      }),
    /** Undo a decision, the classifier's own included, and requeue the row. */
    reopenDetection: (id: number, note = '') =>
      request<DetectedMovement>(`/accounts/ledger/detections/${id}/reopen/`, {
        method: 'POST',
        body: { note },
      }),
    dismissDetection: (id: number, note = '') =>
      request<DetectedMovement>(`/accounts/ledger/detections/${id}/dismiss/`, {
        method: 'POST',
        body: { note },
      }),
    ledgerEvents: (accountId?: number | null) =>
      request<LedgerEvent[]>(
        `/accounts/ledger/events/${accountId ? `?account=${accountId}` : ''}`,
      ),
    ledgerSplit: () => request<ProfitSplit>('/accounts/ledger/split/'),
    saveLedgerSplit: (body: Record<string, unknown>) =>
      request<ProfitSplit>('/accounts/ledger/split/', { method: 'POST', body }),

    // --- bot mode (docs/bots.md) ---
    /** `settings.BOT` as the panel renders it, including the two stops with no number. */
    botPolicy: () => request<BotPolicy>('/bots/policy/'),
    /**
     * What the editor underlines. Never throws on a bad script — every fault
     * comes back as data, so four mistakes underline four rather than sending
     * the author round the loop four times.
     */
    validatePine: (source: string) =>
      request<PineValidation>('/bots/validate/', { method: 'POST', body: { source } }),
    strategies: () => request<Strategy[]>('/bots/strategies/'),
    createStrategy: (body: Record<string, unknown>) =>
      request<Strategy>('/bots/strategies/', { method: 'POST', body }),
    deleteStrategy: (id: number) => request<void>(`/bots/strategies/${id}/`, { method: 'DELETE' }),
    /** Immutable: saving never rewrites a version, so a running bot cannot change under it. */
    saveVersion: (strategyId: number, source: string) =>
      request<StrategyVersion>(`/bots/strategies/${strategyId}/versions/`, {
        method: 'POST',
        body: { source },
      }),
    bots: () => request<BotSummary[]>('/bots/bots/'),
    bot: (id: number) => request<BotSummary>(`/bots/bots/${id}/`),
    createBot: (body: Record<string, unknown>) =>
      request<BotSummary>('/bots/bots/', { method: 'POST', body }),
    updateBot: (id: number, body: Record<string, unknown>) =>
      request<BotSummary>(`/bots/bots/${id}/`, { method: 'PATCH', body }),
    deleteBot: (id: number) => request<void>(`/bots/bots/${id}/`, { method: 'DELETE' }),
    botRuns: (id: number) => request<BotRun[]>(`/bots/bots/${id}/runs/`),
    botBars: (id: number, limit = 500) =>
      request<BotBar[]>(`/bots/bots/${id}/bars/?limit=${limit}`),
    /** The action log with its fan-out legs — the one bot surface naming accounts. */
    botActions: (id: number) => request<BotAction[]>(`/bots/bots/${id}/actions/`),
    /** The Phase 7 gate with this bot's own measurements filled in. */
    botPromotion: (id: number) => request<PromotionGate>(`/bots/bots/${id}/promotion/`),
    startBot: (id: number, state: 'paper' | 'live') =>
      request<{ bot_id: number; state: string; run_id: number; deactivated: number[] }>(
        `/bots/bots/${id}/start/`,
        { method: 'POST', body: { state } },
      ),
    stopBot: (id: number, reason = '') =>
      request<{ bot_id: number; state: string }>(`/bots/bots/${id}/stop/`, {
        method: 'POST',
        body: { reason },
      }),
    runBacktest: (body: Record<string, unknown>) =>
      request<BacktestResult>('/bots/backtest/', { method: 'POST', body }),
    backtests: () => request<BacktestRun[]>('/bots/backtests/'),

    // --- security (docs/security-plan.md) ---
    /**
     * Every switch, its tunables, and whether the environment has pinned the
     * whole layer off. One request: the Settings card renders nothing until it
     * knows all of it, and two requests would let it render half a policy.
     */
    securityPolicy: () => request<SecurityState>('/security/policy/'),
    /** Only what changed. The server adds the caller's own address when the
        allowlist is being armed, so a save cannot lock its author out. */
    saveSecurityPolicy: (changes: Partial<SecurityPolicy>) =>
      request<SecurityState>('/security/policy/', { method: 'POST', body: changes }),
    securityEvents: (limit = 50) =>
      request<{ events: SecurityEvent[] }>(`/security/events/?limit=${limit}`),

    /** Whether the password has been re-entered recently enough to write. */
    stepUpState: () =>
      request<{ required: boolean; seconds_left: number }>('/security/step-up/'),
    stepUp: (password: string) =>
      request<{ required: boolean; seconds_left: number }>('/security/step-up/', {
        method: 'POST',
        body: { password },
      }),

    totpState: () => request<TotpState>('/security/totp/'),
    /** Start enrolment. Arms nothing — the switch stays refused until the
        code is confirmed and the recovery codes acknowledged. */
    totpBegin: () =>
      request<{ secret: string; uri: string; qr_svg: string }>('/security/totp/begin/', {
        method: 'POST',
      }),
    /** Returns the recovery codes, once. They are not recoverable afterwards. */
    totpConfirm: (code: string) =>
      request<TotpState & { recovery_codes: string[] }>('/security/totp/confirm/', {
        method: 'POST',
        body: { code },
      }),
    totpAcknowledge: () => request<TotpState>('/security/totp/acknowledge/', { method: 'POST' }),
    /** Removing the device also disarms the switch — leaving it on with
        nobody enrolled would demand a code nobody can produce. */
    totpDisable: (password: string) =>
      request<SecurityState>('/security/totp/disable/', { method: 'POST', body: { password } }),
    forgetTrustedDevices: () =>
      request<TotpState & { forgotten: number }>('/security/trusted/forget/', { method: 'POST' }),

    // --- system log ---
    logs: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : ''
      return request<LogEntry[]>(`/logging/logs/${qs}`)
    },
    /** The level/category values the backend writes — the filter dropdowns are
     * built from these rather than a second hardcoded copy. */
    logFacets: () => request<LogFacets>('/logging/logs/facets/'),
    pruneLogs: (days = 30) =>
      request<{ pruned: number }>('/logging/logs/prune/', { method: 'POST', body: { days } }),
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
  /** Present when the halt also flattened: which trades, and whether all legs went. */
  flattened?: {
    trade_ids: number[]
    closed: boolean
    failed: { account_id: number; error: string; code: string }[]
  }
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
   * How many of `candles` came out of the stored archive rather than this
   * call's response from the venue. Real exchange data either way — it was
   * downloaded from a venue and stamped with which one — but older than the
   * live bars beside it, and the depth a chart can scroll into.
   */
  stored_bars?: number
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
  /** True only when a read-back showed the SL/TP resting on the exchange. */
  sltp_verified: boolean
  /**
   * The protection resting on this exchange no longer matches the trade's SL/TP
   * percentages — an amend that did not land here. Computed on the server
   * against the same anchor and basis the amend uses.
   */
  sltp_stale: boolean
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
  /**
   * Open trades this panel is *not* drawing. It renders one trade — one symbol,
   * one side — so a second one running elsewhere would otherwise be invisible.
   */
  other_open_trades?: number
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

export interface PanelSession {
  id: number
  username: string
  ip_address: string | null
  user_agent: string
  /** Coarse "Chrome · Windows"; the raw agent string stays in `user_agent`. */
  device: string
  started_at: string
  last_seen_at: string
  online: boolean
  /** The browser making this request, flagged rather than hidden. */
  current: boolean
}

/**
 * What a sign-in POST comes back with. Two shapes behind one status code: a
 * session, or a challenge. `authenticated` is absent on the challenge, which is
 * how the store tells them apart — a 200 here does not mean you are in.
 */
export type LoginResult = SessionUser & {
  mfa_required?: boolean
  challenge?: string
  recovery_available?: boolean
}

/** `docs/security-plan.md` §2 — the switches, all default off. */
export interface SecurityPolicy {
  two_factor: boolean
  trusted_devices: boolean
  login_rate_limit: boolean
  new_device_notice: boolean
  idle_timeout: boolean
  single_session: boolean
  ip_allowlist: boolean
  step_up: boolean
  audit_log: boolean
  admin_write_rate_limit: boolean
  csp_mode: 'off' | 'report' | 'enforce'
  login_max_attempts: number
  login_window_seconds: number
  login_lockout_seconds: number
  idle_timeout_minutes: number
  session_max_hours: number
  trusted_device_days: number
  step_up_grace_seconds: number
  admin_write_max_per_minute: number
  allowed_ips: string
}

export type SecuritySwitch = keyof Pick<
  SecurityPolicy,
  | 'two_factor'
  | 'trusted_devices'
  | 'login_rate_limit'
  | 'new_device_notice'
  | 'idle_timeout'
  | 'single_session'
  | 'ip_allowlist'
  | 'step_up'
  | 'audit_log'
  | 'admin_write_rate_limit'
>

export type SecurityState = SecurityPolicy & {
  updated_at: string | null
  updated_by: string
  /**
   * False when `SECURITY_FEATURES=false` pins the layer off in the
   * environment. Every row renders locked — no API call will change it, and a
   * switch that appears to move without moving is worse than one that cannot.
   */
  available: boolean
  /** The switch names, in the order the card renders them. Server-owned so a
      new control appears here without a second list to keep in step. */
  switches: SecuritySwitch[]
  totp: TotpState
  step_up_seconds_left: number
}

export interface TotpState {
  enrolled: boolean
  confirmed: boolean
  /** Confirmed *and* the recovery codes acknowledged. The switch needs this. */
  ready: boolean
  recovery_remaining: number
  trusted_devices: number
}

export interface SecurityEvent {
  id: number
  kind: string
  /** The server's own wording for `kind`; the panel never maps codes to prose. */
  label: string
  at: string
  username: string
  ip_address: string | null
  user_agent: string
  detail: Record<string, unknown>
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
  /** Whether this account takes the admin's own manual entries. */
  manual_trading_enabled: boolean
  /** Whether a bot's entries may reach this account. Off by default. */
  bot_trading_enabled: boolean
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
  /** Whole days until `credential_expires_at`; null when no date is recorded.
   * Negative once it has passed, so the panel can say how long an account has
   * been dead rather than clamping at zero. */
  credential_days_left: number | null
  /** '' | 'expiring' | 'expired'. Reported, never enforced — an expiring
   * credential still trades. */
  credential_state: CredentialState
  last_error: string
  created_at?: string
}

export type CredentialState = '' | 'expiring' | 'expired'

/** One account's credential countdown, as the server computed it. */
export interface ExpiringCredential {
  id: number
  label: string
  exchange: string
  expires_at: string
  days_left: number
  state: CredentialState
}

export interface BalancesResponse {
  accounts: Account[]
  non_usdt: { id: number; label: string; asset: string }[]
  /** Spec §7: a Hyperliquid agent approval is pruned at expiry with no error
   * from the exchange, so the countdown is the only warning there is. */
  expiring_credentials: ExpiringCredential[]
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
  /** True only when a read-back showed the SL/TP resting on the exchange. */
  sltp_verified: boolean
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
  /** Which bot run placed this, when a bot did. Null is the manual path. */
  bot_run: number | null
  /** The bot's own name, for the chart marker label. Null on the manual path. */
  bot_name: string | null
  legs: TradeLeg[]
}

// --- the financial ledger ---------------------------------------------------

/** A cash flow. Typed in by hand, or accepted from a detection — never guessed. */
export interface FundMovement {
  id: number
  account: number
  account_label: string
  kind: 'deposit' | 'withdrawal'
  amount: string
  asset: string
  occurred_at: string
  note: string
  source: 'manual' | 'detected'
  created_at: string
  created_by: string
  updated_at: string
  updated_by: string
}

/** Which rule in `apps/accounts/classify.py` decided what this change was. */
export type ClassificationReason =
  | 'emptied'
  | 'funded_from_empty'
  | 'no_trade'
  | 'isolated'
  | 'portfolio_wide'
  | 'trade_residual'
  | 'unclear'
  | ''

/**
 * A balance change the closed trades do not explain, and what it probably was.
 *
 * `delta = trade_pnl + manual_net + unexplained`, so the whole subtraction is
 * on the row: what the exchange's equity did, what the platform's own legs
 * account for, what was already written down, and what is left over.
 *
 * `suggested_class` is the server's answer to the question that follows —
 * trade result, or somebody's cash — with the evidence beside it, because a
 * verdict without its reasoning is something to click past rather than check.
 */
export interface DetectedMovement {
  id: number
  account: number
  account_label: string
  exchange: string
  exchange_label: string
  previous_equity: string
  current_equity: string
  delta: string
  trade_pnl: string
  manual_net: string
  unexplained: string
  /** The proposal as a positive number; the direction is `suggested_kind`. */
  amount: string
  suggested_kind: 'deposit' | 'withdrawal'
  /** Trade result, or an investor moving their own money. */
  suggested_class: 'trade' | 'investor'
  classification_reason: ClassificationReason
  /** Whether the rule that fired is one the platform acts on by itself. */
  confident: boolean
  /** How many other accounts were readable and flat in the same sweep… */
  peers_observed: number
  /** …and how many of those moved the same way. A fan-out moves all of them. */
  peers_moved: number
  traded_in_window: boolean
  /** Decided by the classifier, not by a person. Reopen to overturn it. */
  auto_resolved: boolean
  asset: string
  window_start: string | null
  observed_at: string
  status: 'pending' | 'accepted' | 'trade' | 'dismissed'
  resolved_at: string | null
  resolved_by: string
  movement: number | null
}

/** One entry in the audit trail. `actor` is blank when the platform acted. */
export interface LedgerEvent {
  id: number
  actor: string
  action: 'detected' | 'created' | 'edited' | 'deleted' | 'accepted' | 'dismissed' | 'split'
  account: number | null
  account_label: string
  movement_id: number | null
  detection_id: number | null
  kind: string
  amount: string | null
  before: Record<string, string> | null
  after: Record<string, string> | null
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
  /** How many detections are waiting — a count, so the dashboard can badge it. */
  pending_detections: number
}

export interface ProfitSplit extends SplitPercents {
  updated_at: string
  updated_by: string
}

// --- one account's whole record (the per-account page) ----------------------

/** One leg this account was given, with the trade it belonged to folded in. */
export interface ReportLeg {
  id: number
  trade: number
  symbol: string
  side: string
  market: string
  order_type: string
  leverage: number
  sl_pct: string | null
  tp_pct: string | null
  sltp_basis: string
  trade_status: string
  fanout_ms: number | null
  ok: boolean
  error: string
  error_code: string
  dispatch_ms: number | null
  qty: string | null
  entry_price: string | null
  exit_price: string | null
  margin: string | null
  notional: string | null
  stop_loss: string | null
  take_profit: string | null
  sltp_attached: boolean
  sltp_verified: boolean
  pnl: string | null
  /** Return on the margin this leg locked up — not on the account. */
  roe_pct: string | null
  opened_at: string
  closed_at: string | null
  open: boolean
}

/**
 * What the legs add up to. `null` is unknown, never zero: a leg the venue
 * never priced is counted in neither the wins nor the losses.
 */
export interface ReportTrading {
  legs: number
  filled: number
  failed: number
  open: number
  scored: number
  wins: number
  losses: number
  win_rate: string | null
  realised_pnl: string
  gross_profit: string
  gross_loss: string
  profit_factor: string | null
  average_pnl: string | null
  best: string | null
  worst: string | null
  volume: string
  first_trade_at: string | null
  last_trade_at: string | null
}

export interface ReportCurvePoint {
  at: string
  symbol: string
  pnl: string
  cumulative: string
}

export interface ReportSymbol {
  symbol: string
  legs: number
  wins: number
  pnl: string
}

export interface AccountReport {
  account: Account
  connected_at: string
  /** Spec §6: when this account last became eligible to join a trade. */
  eligible_from: string
  ledger: LedgerRow
  split: SplitPercents
  trading: ReportTrading
  legs: ReportLeg[]
  curve: ReportCurvePoint[]
  symbols: ReportSymbol[]
  movements: FundMovement[]
  detections: DetectedMovement[]
  notifications: ApiNotification[]
  /** How many legs the payload caps at, so the page can say when it is a page. */
  leg_limit: number
}

export interface LogEntry {
  id: number
  timestamp: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  category: string
  source: string
  message: string
  account_id: number | null
  trade_id: number | null
  exchange: string | null
  error_code: string | null
  context: Record<string, unknown> | null
  /** Ties every row written while serving one request together. */
  request_id: string | null
}

export interface LogFacets {
  levels: string[]
  categories: string[]
}

// --- bot mode (docs/bots.md) ------------------------------------------------

/** One located fault or warning from the validator. Never an exception. */
export interface PineDiagnostic {
  kind: 'error' | 'warning'
  code: string
  message: string
  span: { line: number; col: number; end_line: number; end_col: number } | null
}

/** One `input.*` in the script — what the parameter form is built from. */
export interface PineInput {
  name: string
  kind: string
  default: unknown
  title: string
  minval: unknown
  maxval: unknown
  options: unknown[]
  /** The layout half. A form that drops these turns thirty labelled, grouped
   *  controls into thirty rows in declaration order — the same settings, and
   *  unusable. */
  step: unknown
  group: string
  inline: string
  tooltip: string
}

/**
 * TradingView's Properties tab, resolved: platform default → what `strategy()`
 * declared → what the panel overrode. `declared` is which keys the *script*
 * set, which is what lets a field say "from the script" instead of pretending
 * the author chose the default.
 */
export interface PineProperties {
  initial_capital: string
  currency: string
  default_qty_type: 'platform' | 'fixed' | 'cash' | 'percent_of_equity'
  default_qty_value: string
  pyramiding: number
  commission_type: 'percent' | 'cash_per_contract' | 'cash_per_order'
  commission_value: string
  slippage: number | null
  margin_long: string
  margin_short: string
  process_orders_on_close: boolean
  calc_on_every_tick: boolean
  calc_on_order_fills: boolean
  use_bar_magnifier: boolean
  fill_orders_on_standard_ohlc: boolean
  backtest_fill_limits_assumption: number
  declared: string[]
  overridden: string[]
}

/**
 * The two lists that keep a property from being honoured silently:
 * `live_departures` is what the *backtest* will do that live will not, and
 * `inert` is what nothing here does at all.
 */
export interface PinePropertyNotes {
  live_departures: string[]
  inert: string[]
}

export interface PineValidation {
  ok: boolean
  errors: PineDiagnostic[]
  warnings: PineDiagnostic[]
  inputs: PineInput[]
  ta_call_sites: number
  node_count: number
  properties: PineProperties
  property_notes: PinePropertyNotes
}

export interface StrategyVersion {
  id: number
  version: number
  source: string
  parsed_ok: boolean
  validation_errors: PineDiagnostic[]
  validation_warnings: PineDiagnostic[]
  inputs_schema: PineInput[]
  properties: PineProperties | Record<string, never>
  property_notes: PinePropertyNotes | Record<string, never>
  created_at: string
  created_by: string
}

export interface Strategy {
  id: number
  name: string
  description: string
  created_at: string
  created_by: string
  versions: StrategyVersion[]
  latest_version: StrategyVersion | null
}

export type BotState = 'draft' | 'paper' | 'live' | 'stopped'

export interface BotSummary {
  id: number
  strategy_version: number
  strategy_name: string
  version: number
  name: string
  symbol: string
  interval: string
  market: string
  leverage: number
  sl_pct: string | null
  tp_pct: string | null
  input_values: Record<string, unknown>
  risk_config: Record<string, unknown>
  state: BotState
  /** True in every state but `live`. Set by the state, never by hand. */
  dry_run: boolean
  drills_fired: string[]
  created_at: string
  updated_at: string
  latest_run: BotRun | null
}

export interface BotRun {
  id: number
  bot: number
  started_at: string
  stopped_at: string | null
  /** One of the Q25 triggers, `halt`, `manual`, or `risk_gate`. */
  stop_reason: string
  stop_detail: string
  warmup_bars: number
  feed_source: string
  /** 'stream' or 'poll' — named rather than blurred, as the chart's is. */
  feed_transport?: string
  last_bar_time: number | null
  peak_equity: string | null
  consecutive_losses: number
  recoveries: number
  unplanned_recoveries: number
  feed_gaps: number
  feed_gaps_repaired: number
  halt_drills: number
  divergences: number
  bars_evaluated: number
}

export interface BotBar {
  id: number
  bar_time: number
  open: string
  high: string
  low: string
  close: string
  volume: string
  plots: Record<string, string>
  intent: Record<string, unknown>
  evaluation_ms: number | null
  changed: boolean
}

/** One leg of a bot's fan-out. Hidden accounts are stripped server-side (Q27). */
export interface BotActionLeg {
  account_id: number
  account_label?: string
  ok: boolean
  error?: string
  code?: string
}

export interface BotAction {
  id: number
  bar_time: number
  action_type: 'open' | 'amend' | 'close' | 'shadow'
  idempotency_key: string
  payload: Record<string, unknown>
  intent: Record<string, unknown>
  created_at: string
  dispatched_at: string | null
  settled_at: string | null
  trade: number | null
  ok: boolean
  error: string
  legs: BotActionLeg[]
}

/** One row of the Phase 7 gate, with the number behind it. */
export interface PromotionRow {
  key: string
  requirement: string
  threshold: string
  measured: string
  met: boolean
}

export interface PromotionGate {
  ready: boolean
  rows: PromotionRow[]
}

/** What the backtest assumed. Rendered above the metrics, always. */
export interface BacktestAssumptions {
  slippage_bps: string
  fee_bps: string
  entry_rule: string
  ambiguous_bar: string
  balance_fraction: string
  leverage: number
  initial_equity: string
}

export interface BacktestTrade {
  side: string
  entry_time: number
  entry_price: string
  exit_time: number
  exit_price: string
  qty: string
  pnl: string
  fees: string
  bars_held: number
  exit_reason: string
  entry_reason: string
  /** Which line asked for this trade — the chart marker links back to it. */
  entry_span: { line: number; col: number } | null
}

export interface BacktestResult {
  symbol: string
  interval: string
  from_time: number
  to_time: number
  bars: number
  assumptions: BacktestAssumptions
  /** The same assumptions as sentences, so the panel prints one list, not two. */
  assumption_lines: string[]
  metrics: Record<string, string | number | null>
  equity_curve: [number, string][]
  trades: BacktestTrade[]
  /** SHA-256 over the decision sequence. The live loop computes it the same way. */
  intent_digest: string
  warnings: string[]
}

export interface BacktestRun {
  id: number
  strategy_version: number
  strategy_name: string
  symbol: string
  interval: string
  market: string
  from_time: number
  to_time: number
  input_values: Record<string, unknown>
  metrics: Record<string, string | number | null>
  intent_digest: string
  created_at: string
  created_by: string
}

export interface BotPolicy {
  [key: string]: unknown
  non_configurable_stops: Record<string, string>
  decisions: Record<string, string>
}
