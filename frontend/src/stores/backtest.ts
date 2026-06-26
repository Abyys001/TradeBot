import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type Backtest, type Candle } from '../api/client'

export const useBacktestStore = defineStore('backtest', () => {
  const running = ref(false)
  const currentBacktestId = ref<number | null>(null)
  const lastResult = ref<Backtest | null>(null)
  const showResults = ref(false)

  async function fetchBacktest(id: number) {
    const { data } = await api.get<Backtest>(`/backtests/${id}/`)
    return data
  }

  async function pollUntilDone(id: number, intervalMs = 1500, maxAttempts = 120): Promise<Backtest> {
    for (let i = 0; i < maxAttempts; i++) {
      const bt = await fetchBacktest(id)
      if (bt.status === 'done' || bt.status === 'failed') return bt
      await new Promise((r) => setTimeout(r, intervalMs))
    }
    throw new Error('Backtest timed out')
  }

  async function runBacktest(
    strategyId: number,
    payload: { symbol: string; timeframe: string; candles: Candle[] },
  ) {
    running.value = true
    currentBacktestId.value = null
    lastResult.value = null
    try {
      const { data } = await api.post<{ backtest_id: number }>(
        `/strategies/${strategyId}/backtest/`,
        payload,
      )
      currentBacktestId.value = data.backtest_id
      const result = await pollUntilDone(data.backtest_id)
      lastResult.value = result
      return result
    } finally {
      running.value = false
    }
  }

  function applyWsPayload(payload: Record<string, unknown>) {
    if (payload.source !== 'backtest') return
    const id = payload.backtest_id as number | undefined
    if (id != null) currentBacktestId.value = id
    const status = payload.status as string | undefined
    if (status === 'done' || status === 'failed') {
      running.value = false
      if (id != null) {
        fetchBacktest(id).then((bt) => {
          lastResult.value = bt
          if (bt.status === 'done') showResults.value = true
        })
      }
    }
  }

  function openResults() {
    showResults.value = true
  }

  function closeResults() {
    showResults.value = false
  }

  return {
    running,
    currentBacktestId,
    lastResult,
    showResults,
    runBacktest,
    fetchBacktest,
    applyWsPayload,
    openResults,
    closeResults,
  }
})
