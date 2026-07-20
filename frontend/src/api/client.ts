import axios from 'axios'

let csrfToken = ''

export const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  if (csrfToken && config.method !== 'get') {
    config.headers['X-CSRFToken'] = csrfToken
  }
  return config
})

// On CSRF failure (Django rotates the token on login), refresh and retry once.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config
    if (
      error.response?.status === 403 &&
      typeof error.response?.data?.detail === 'string' &&
      error.response.data.detail.includes('CSRF') &&
      !config._csrfRetried
    ) {
      config._csrfRetried = true
      await fetchCsrf()
      if (csrfToken) config.headers['X-CSRFToken'] = csrfToken
      return api(config)
    }
    return Promise.reject(error)
  },
)

export async function fetchCsrf(): Promise<string> {
  const { data } = await api.get<{ csrfToken: string }>('/auth/csrf/')
  csrfToken = data.csrfToken
  return csrfToken
}

export interface User {
  id: number
  username: string
  email?: string
  is_trading_enabled: boolean
  role: 'admin' | 'investor'
  must_change_password: boolean
}

export interface Investor {
  id: number
  username: string
  email?: string
  role: 'admin' | 'investor'
  is_trading_enabled: boolean
  is_active: boolean
  must_change_password: boolean
  date_joined: string
  last_login: string | null
  created_at: string
}

export interface InvestorCreatePayload {
  username: string
  password: string
  email?: string
  is_trading_enabled?: boolean
}

export interface CopySummary {
  subscriptions: number
  realized_pnl: string
  net_pnl: string
  fees_total: string
  fees_owed: string
  open_trades: number
  closed_trades: number
}

export interface CopyTradeRow {
  id: number
  pair: string
  side: string
  entry_price: string | null
  exit_price: string | null
  status: string
  gross_pnl: string
  platform_share_amount: string
  opened_at: string
  closed_at: string | null
}

export interface CopyEquityPoint {
  balance: string
  equity: string
  captured_at: string
}

export interface HealthPayload {
  hl_market_feed: { status: string; last_bar_ts: number | null }
  celery: { status: string; workers: number; detail?: string }
  credentials: Array<{
    id: number
    label: string
    is_active: boolean
    network: string
    wallet_address: string
    last_verified_at: string | null
  }>
  active_strategies: number
  is_trading_enabled: boolean
}

export interface Strategy {
  id: number
  credential: number | null
  name: string
  type: string
  symbol: string
  params: Record<string, unknown>
  status: string
  source: string
  validation_status: string
  validation_error: string
  timeframe: string
  warmup_bars: number
  live_config: LiveConfig
  state?: {
    position: Record<string, unknown>
    last_signal: string
    pnl: string
    live_started_at: string | null
    last_bar_ts: number | null
    live_error: string
  }
}

export interface LiveConfig {
  symbols?: string[]
  timeframes?: string[]
  copy_trading?: boolean
  risk?: {
    leverage?: number
    position_size_pct?: number
    global_stop_loss_pct?: number
    risk_per_trade_pct?: number
    max_daily_loss_pct?: number
    max_drawdown_pct?: number
    max_open_trades?: number
    max_exposure_pct?: number
    max_leverage?: number
    max_notional_usdt?: number
  }
}

export interface ExecutionLog {
  id: number
  strategy: number | null
  level: string
  event: string
  payload: Record<string, unknown>
  created_at: string
}

export interface Candle {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ChartMarker {
  time: number
  position: string
  color: string
  shape: string
  text: string
  side?: string
}

export interface ChartPriceLevel {
  time: number
  price: number
  type: 'stop' | 'take_profit' | string
}

export interface ChartPositionSide {
  time: number | null
  price: number
  qty: number
  order_id?: number
  reason?: string
}

export interface ChartPosition {
  id: number
  side: string
  entry: ChartPositionSide
  exit: ChartPositionSide | null
  sl: number | null
  tp: number | null
  liq: number | null
  pnl: number
  pnl_pct: number
  leverage: number
}

export type BarQuality = 'CLEAN' | 'FLAT' | 'SUSPECT' | 'MISSING'

export interface ChartQualityPoint {
  time: number
  q: BarQuality | string
}

export interface MarketDataReadiness {
  symbol: string
  timeframe: string
  clean_bars: number
  required_bars: number
  ready: boolean
  eta_seconds: number | null
  recording_since: string | null
  coverage_pct: number
  suspect_bars_24h: number
  error?: string
}

export interface MarketDataCoverage {
  symbol: string
  recording_since: number | null
  recorded_until: number | null
  coverage_pct: number
  intervals: [number, number][]
}

export interface Credential {
  id: number
  exchange: string
  label: string
  wallet_address: string
  agent_address?: string
  network: string
  is_active: boolean
  last_verified_at: string | null
  created_at: string
}

export interface CredentialCreatePayload {
  label: string
  exchange?: string
  // Hyperliquid
  wallet_address?: string
  agent_private_key?: string
  // Tabdeal (Binance-style)
  api_key?: string
  api_secret?: string
  network?: string
}

export interface SignumConfig {
  enabled: boolean
  order_size_default: string
  use_settings_bot_id: boolean
  has_bot_id?: boolean
  has_webhook_url?: boolean
  bot_id?: string
  webhook_url?: string
  updated_at?: string
}

export interface OverviewPayload {
  strategies: {
    total: number
    active: number
    draft: number
    paused: number
    stopped: number
  }
  orders: { total: number; today: number; filled: number }
  pnl: { total_unrealized: string; strategies_with_pnl: number }
  logs: { errors_24h: number; warnings_24h: number }
  credentials: { total: number; active: number }
  recent_orders: OrderRecord[]
  recent_logs: ExecutionLog[]
}

export interface OrderRecord {
  id: number
  strategy: number
  symbol: string
  side: string
  status: string
  size: string
  created_at: string
}

export interface ValidateResult {
  ok: boolean
  error?: string
  line?: number
  column?: number
}

export interface BacktestTrade {
  side: string
  entry_price: string
  exit_price: string | null
  size: string
  pnl: string
  gross_pnl: string
  commission: string
  entry_bar: number
  exit_bar: number | null
  stop_px?: string | null
  limit_px?: string | null
  exit_reason?: string
  entry_time: string | null
  exit_time: string | null
}

export interface BacktestMetrics {
  num_trades?: number
  net_pnl?: number
  gross_pnl?: number
  total_commission?: number
  win_rate?: number
  max_drawdown?: number
  profit_factor?: number | null
  sharpe_ratio?: number
  risk_reward?: number
  expectancy?: number
  funding_paid?: number
  equity_series?: number[]
  leverage?: number
  liquidations?: number
  initial_balance?: number
  final_equity?: number
}

export interface Backtest {
  id: number
  strategy: number
  status: 'pending' | 'running' | 'done' | 'failed'
  symbol: string
  timeframe: string
  network?: string
  initial_balance?: number
  range_start: string | null
  range_end: string | null
  metrics: BacktestMetrics
  error: string
  created_at: string
  trades: BacktestTrade[]
}

export interface HistoryDataset {
  coin: string
  interval: string
  network?: string
  kind?: string
  bars: number
  start_ts: number
  end_ts: number
  size_bytes: number
  healthy?: boolean
  gap_count?: number
  missing_bars?: number
}

export interface HistoryDownloadProgress {
  key: string
  status: string
  bars?: number
  start_ts?: number
  end_ts?: number
  error?: string
  note?: string
  path?: string
}

export interface HistoryDownload {
  id: number
  status: 'pending' | 'running' | 'done' | 'partial' | 'failed'
  network: string
  coins: string[]
  intervals: string[]
  data_types: string[]
  start_ms: number
  end_ms: number
  progress: Record<string, HistoryDownloadProgress>
  error: string
  created_at: string
  is_stale?: boolean
}

export interface HistoryMarkets {
  network: string
  coins: string[]
  intervals: string[]
  error?: string
}

export interface FeeConfig {
  share_pct: string
  destination_exchange: string
  destination_account: string
  updated_at?: string
}

export interface AdminCopyRow {
  subscription_id: number
  investor: string
  signal: string
  is_active: boolean
  trading_enabled: boolean
  high_water_mark: string
  realized_pnl: string
  fees_accrued: string
  open_trades: number
}

export interface AdminCopyOverview {
  investors: AdminCopyRow[]
  totals: {
    investor_count: number
    realized_pnl: string
    fees_accrued: string
    fees_owed: string
  }
}

export interface FeeLedgerRow {
  id: number
  investor: string
  amount: string
  share_pct: string
  status: string
  accrued_at: string
  settled_at: string | null
}

// ---- Copy trading (legacy investor model) --------------------------------
export interface MasterStrategy {
  id: number
  name: string
  symbol: string
  market_type: string
  timeframe: string
  status: string
}

export interface Subscription {
  id: number
  master_strategy: number
  master_name?: string
  master_symbol?: string
  credential: number
  sizing_mode: 'risk_pct' | 'fixed_notional'
  risk_pct: string
  fixed_notional: string
  leverage: number
  is_active: boolean
  created_at?: string
}

export interface InvestorPosition {
  id: number
  subscription: number
  coin: string
  size: string
  entry_price: string
  opened_at: string
}

export interface FeeLedger {
  id: number
  subscription: number
  investor?: string
  realized_pnl: string
  high_water_mark: string
  fee_accrued: string
  fee_rate: string
  updated_at: string
}

export interface AdminInvestor {
  id: number
  username: string
  email?: string
  is_trading_enabled: boolean
  subscriptions: number
}

// ---- Telegram ---------------------------------------------------------
export interface TelegramConfig {
  bot_token: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AlertWhitelistEntry {
  id: number
  chat_id: number
  label: string
  enabled: boolean
  created_at: string
}
