import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type MarketDataReadiness, type MarketDataCoverage } from '../api/client'

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

  return { readiness, coverage, loading, fetchReadiness, fetchCoverage }
})
