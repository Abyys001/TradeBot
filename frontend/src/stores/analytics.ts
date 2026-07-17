import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { useBacktestStore } from './backtest'

export interface AnalyticsRun {
  backtest_id: number
  strategy_id: number
  strategy_name: string
  symbol: string
  timeframe?: string
  network?: string
  net_pnl?: number
  sharpe_ratio?: number
  profit_factor?: number
  max_drawdown?: number
  num_trades?: number
  win_rate?: number
  expectancy?: number
  initial_balance?: number
  final_equity?: number
  equity_series?: number[]
  created_at: string
}

export interface MonthlyBucket {
  month: string
  net_pnl: number
  count: number
}

export interface AssetBucket {
  symbol: string
  net_pnl: number
  num_trades: number
  win_rate: number
  funding_paid: number
}

export interface AnalyticsPayload {
  runs: AnalyticsRun[]
  best: AnalyticsRun | null
  worst: AnalyticsRun | null
  count: number
  monthly: MonthlyBucket[]
  by_asset: AssetBucket[]
  total_funding_paid: number
}

const POLL_INTERVAL_MS = 8000

export const useAnalyticsStore = defineStore('analytics', () => {
  const data = ref<AnalyticsPayload | null>(null)
  const loading = ref(false)
  const error = ref('')

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const runs = computed(() => data.value?.runs ?? [])
  const summary = computed(() => {
    const r = runs.value
    if (!r.length) return null
    const totalPnl = r.reduce((s, x) => s + (x.net_pnl ?? 0), 0)
    const sharpes = r.map((x) => x.sharpe_ratio).filter((v): v is number => v != null)
    const drawdowns = r.map((x) => x.max_drawdown).filter((v): v is number => v != null)
    return {
      count: data.value?.count ?? r.length,
      totalPnl,
      avgSharpe: sharpes.length ? sharpes.reduce((a, b) => a + b, 0) / sharpes.length : null,
      worstDrawdown: drawdowns.length ? Math.max(...drawdowns) : null,
      totalFunding: data.value?.total_funding_paid ?? 0,
    }
  })

  async function fetch() {
    loading.value = true
    error.value = ''
    try {
      const { data: payload } = await api.get<AnalyticsPayload>('/analytics/')
      data.value = payload
      return payload
    } catch {
      error.value = 'loadFailed'
      return null
    } finally {
      loading.value = false
    }
  }

  function startPollingWhileActive() {
    if (pollTimer) return
    const backtest = useBacktestStore()
    pollTimer = setInterval(() => {
      if (backtest.activeBacktests.length || !runs.value.length) {
        void fetch()
      } else {
        stopPolling()
      }
    }, POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function refreshIfBacktestDone() {
    await fetch()
  }

  return {
    data,
    runs,
    summary,
    loading,
    error,
    fetch,
    startPollingWhileActive,
    stopPolling,
    refreshIfBacktestDone,
  }
})
