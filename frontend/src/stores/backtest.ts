import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, type Backtest } from '../api/client'

export const useBacktestStore = defineStore('backtest', () => {
  const backtests = ref<Backtest[]>([])
  const activeId = ref<number | null>(null)
  const loading = ref(false)

  const active = computed(() => backtests.value.find((b) => b.id === activeId.value) ?? null)

  const forStrategy = computed(() => (strategyId: number) =>
    backtests.value.filter((b) => b.strategy === strategyId),
  )

  async function fetchAll(strategyId?: number) {
    loading.value = true
    try {
      const { data } = await api.get<Backtest[]>('/backtests/')
      backtests.value = strategyId ? data.filter((b) => b.strategy === strategyId) : data
      return backtests.value
    } finally {
      loading.value = false
    }
  }

  async function fetchOne(id: number) {
    const { data } = await api.get<Backtest>(`/backtests/${id}/`)
    const idx = backtests.value.findIndex((b) => b.id === id)
    if (idx >= 0) {
      backtests.value[idx] = data
    } else {
      backtests.value.unshift(data)
    }
    return data
  }

  async function runInline(strategyId: number, coin: string, interval: string) {
    const { data: candleResp } = await api.get<{ candles: Array<Record<string, number>> }>('/candles/', {
      params: { symbol: coin, bar: interval, limit: 500 },
    })
    const candles = candleResp.candles.map((c) => ({
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
    }))
    const { data } = await api.post<{ backtest_id: number }>(`/strategies/${strategyId}/backtest/`, {
      symbol: coin,
      timeframe: interval,
      candles,
    })
    const placeholder: Backtest = {
      id: data.backtest_id,
      strategy: strategyId,
      status: 'pending',
      symbol: coin,
      timeframe: interval,
      range_start: null,
      range_end: null,
      metrics: {},
      error: '',
      created_at: new Date().toISOString(),
      trades: [],
    }
    backtests.value.unshift(placeholder)
    activeId.value = data.backtest_id
    return data.backtest_id
  }

  async function runStored(
    strategyId: number,
    payload: { coin: string; interval: string; network?: string; start?: number; end?: number },
  ) {
    const { data } = await api.post<{ backtest_id: number }>(
      `/strategies/${strategyId}/backtest_stored/`,
      {
        coin: payload.coin,
        interval: payload.interval,
        network: payload.network ?? 'mainnet',
        start: payload.start,
        end: payload.end,
      },
    )
    const placeholder: Backtest = {
      id: data.backtest_id,
      strategy: strategyId,
      status: 'pending',
      symbol: payload.coin,
      timeframe: payload.interval,
      network: payload.network ?? 'mainnet',
      range_start: null,
      range_end: null,
      metrics: {},
      error: '',
      created_at: new Date().toISOString(),
      trades: [],
    }
    backtests.value.unshift(placeholder)
    activeId.value = data.backtest_id
    return data.backtest_id
  }

  async function pollUntilDone(id: number, intervalMs = 1500, maxAttempts = 120) {
    for (let i = 0; i < maxAttempts; i++) {
      const bt = await fetchOne(id)
      if (bt.status === 'done' || bt.status === 'failed') return bt
      await new Promise((r) => setTimeout(r, intervalMs))
    }
    return fetchOne(id)
  }

  function select(id: number | null) {
    activeId.value = id
  }

  function applyWs(payload: Record<string, unknown>) {
    const id = payload.backtest_id as number | undefined
    if (!id) return
    const idx = backtests.value.findIndex((b) => b.id === id)
    if (idx >= 0) {
      const bt = backtests.value[idx]
      if (payload.status) bt.status = payload.status as Backtest['status']
      if (payload.error) bt.error = String(payload.error)
      if (payload.metrics) bt.metrics = payload.metrics as Backtest['metrics']
    }
    if (payload.status === 'done' || payload.status === 'failed') {
      void fetchOne(id)
    }
  }

  return {
    backtests,
    activeId,
    active,
    loading,
    forStrategy,
    fetchAll,
    fetchOne,
    runInline,
    runStored,
    pollUntilDone,
    select,
    applyWs,
  }
})
