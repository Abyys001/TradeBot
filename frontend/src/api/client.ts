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
  credential: number
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

export interface BacktestMetrics {
  num_trades: number
  net_pnl: number
  win_rate: number
  max_drawdown: number
}

export interface BacktestTrade {
  side: string
  entry_price: number
  exit_price: number
  size: number
  pnl: number
  entry_bar: number
  exit_bar: number | null
}

export interface Backtest {
  id: number
  strategy: number
  status: 'pending' | 'running' | 'done' | 'failed'
  symbol: string
  timeframe: string
  range_start: string | null
  range_end: string | null
  metrics: BacktestMetrics
  error: string
  created_at: string
  trades: BacktestTrade[]
}
