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
  wallet_address: string
  agent_private_key: string
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
  entry_bar: number
  exit_bar: number | null
  stop_px?: string | null
  limit_px?: string | null
  exit_reason?: string
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
