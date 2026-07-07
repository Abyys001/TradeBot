import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'

export interface GridResult {
  params: Record<string, unknown>
  metrics: Record<string, number | null>
}

export interface WalkForwardWindow {
  train_start: number
  test_start: number
  best_params: Record<string, unknown>
  train_metrics: Record<string, number | null>
  test_metrics: Record<string, number | null>
}

export const useOptimizerStore = defineStore('optimizer', () => {
  const gridResults = ref<GridResult[]>([])
  const walkForwardWindows = ref<WalkForwardWindow[]>([])
  const monteCarloResult = ref<Record<string, number> | null>(null)
  const portfolioResult = ref<Record<string, unknown> | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function runGrid(payload: {
    strategy_id: number
    coin: string
    interval: string
    network?: string
    param_grid: Record<string, unknown[]>
  }) {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.post<{ results: GridResult[] }>('/optimize/grid/', payload)
      gridResults.value = data.results
      return data.results
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Grid search failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function runWalkForward(payload: {
    strategy_id: number
    coin: string
    interval: string
    network?: string
    param_grid: Record<string, unknown[]>
    train_bars?: number
    test_bars?: number
  }) {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.post<{ windows: WalkForwardWindow[] }>('/optimize/walk-forward/', payload)
      walkForwardWindows.value = data.windows
      return data.windows
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Walk-forward failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function runMonteCarlo(backtestId: number, simulations = 500) {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.post<Record<string, number>>('/optimize/monte-carlo/', {
        backtest_id: backtestId,
        simulations,
      })
      monteCarloResult.value = data
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Monte Carlo failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function runPortfolio(payload: {
    strategies: Array<{ strategy_id: number; symbol: string }>
    network?: string
    interval?: string
  }) {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.post<Record<string, unknown>>('/optimize/portfolio/', payload)
      portfolioResult.value = data
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Portfolio backtest failed'
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    gridResults,
    walkForwardWindows,
    monteCarloResult,
    portfolioResult,
    loading,
    error,
    runGrid,
    runWalkForward,
    runMonteCarlo,
    runPortfolio,
  }
})
