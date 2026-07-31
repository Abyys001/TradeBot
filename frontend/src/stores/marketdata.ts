import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  api,
  type MarketDataReadiness,
  type MarketDataCoverage,
  type RecordedSymbol,
} from '../api/client'

// Market Data Engine readiness/coverage: because Tabdeal has no candle backfill,
// history accrues from when the recorder started, so "can this go live?" is a live
// signal the UI must gate on (candle design §5).
export const useMarketDataStore = defineStore('marketdata', () => {
  const readiness = ref<MarketDataReadiness | null>(null)
  const coverage = ref<MarketDataCoverage | null>(null)
  const loading = ref(false)

  async function fetchReadiness(params: {
    symbol: string
    tf: string
    strategyId?: number
    requiredBars?: number
  }) {
    loading.value = true
    try {
      const q: Record<string, string | number> = { symbol: params.symbol, tf: params.tf }
      if (params.strategyId != null) q.strategy_id = params.strategyId
      if (params.requiredBars != null) q.required_bars = params.requiredBars
      const { data } = await api.get<MarketDataReadiness>('/marketdata/readiness/', { params: q })
      readiness.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function fetchCoverage(symbol: string) {
    const { data } = await api.get<MarketDataCoverage>('/marketdata/coverage/', {
      params: { symbol },
    })
    coverage.value = data
    return data
  }

  // --- recorded symbols (admin) -------------------------------------------
  // The recorder is the long pole: history only exists from the moment a symbol
  // is switched on, and it cannot be backfilled from the exchange afterwards.
  const recorded = ref<RecordedSymbol[]>([])
  const envDefault = ref<string[]>([])
  const seededFromEnv = ref(false)

  async function fetchRecorded() {
    const { data } = await api.get<{
      symbols: RecordedSymbol[]
      seeded_from_env: boolean
      env_default: string[]
    }>('/marketdata/recorded/')
    recorded.value = data.symbols
    seededFromEnv.value = data.seeded_from_env
    envDefault.value = data.env_default
    return data
  }

  async function addSymbol(symbol: string, note = '') {
    const { data } = await api.post<RecordedSymbol>('/marketdata/recorded/', { symbol, note })
    await fetchRecorded()
    return data
  }

  async function setActive(id: number, isActive: boolean) {
    await api.patch(`/marketdata/recorded/${id}/`, { is_active: isActive })
    await fetchRecorded()
  }

  async function removeSymbol(id: number) {
    await api.delete(`/marketdata/recorded/${id}/`)
    await fetchRecorded()
  }

  async function backfill(payload: {
    symbols?: string[]
    timeframes?: string[]
    strategyId?: number
  }) {
    const body: Record<string, unknown> = {}
    if (payload.symbols) body.symbols = payload.symbols
    if (payload.timeframes) body.timeframes = payload.timeframes
    if (payload.strategyId != null) body.strategy_id = payload.strategyId
    const { data } = await api.post<{ task_id: string; status: string }>(
      '/marketdata/backfill/',
      body,
    )
    return data
  }

  return {
    readiness,
    coverage,
    loading,
    recorded,
    envDefault,
    seededFromEnv,
    fetchReadiness,
    fetchCoverage,
    fetchRecorded,
    addSymbol,
    setActive,
    removeSymbol,
    backfill,
  }
})
