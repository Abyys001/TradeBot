import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, type Backtest, type Candle } from '../api/client'

const POLL_INTERVAL_MS = 5000

export const useBacktestStore = defineStore('backtest', () => {
  const backtests = ref<Backtest[]>([])
  const activeId = ref<number | null>(null)
  const loading = ref(false)
  const inlineRunning = ref(false)
  const lastResult = ref<Backtest | null>(null)
  const showResults = ref(false)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const active = computed(() => backtests.value.find((b) => b.id === activeId.value) ?? null)

  const activeBacktests = computed(() =>
    backtests.value.filter((b) => b.status === 'pending' || b.status === 'running'),
  )

  const running = computed(() => inlineRunning.value || activeBacktests.value.length > 0)

  const forStrategy = computed(() => (strategyId: number) =>
    backtests.value.filter((b) => b.strategy === strategyId),
  )

  async function fetchAll(strategyId?: number) {
    loading.value = true
    try {
      const { data } = await api.get<Backtest[]>('/backtests/')
      if (strategyId) {
        const strategyRuns = data.filter((b) => b.strategy === strategyId)
        const other = backtests.value.filter((b) => b.strategy !== strategyId)
        backtests.value = [...strategyRuns, ...other]
        return strategyRuns
      }
      backtests.value = data
      return data
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

  async function fetchBacktest(id: number) {
    return fetchOne(id)
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
    startPollingActive()
    return data.backtest_id
  }

  async function runStored(
    strategyId: number,
    payload: {
      coin: string
      interval: string
      network?: string
      start?: number
      end?: number
      initial_capital?: number
      commission?: number
    },
  ) {
    const { data } = await api.post<{ backtest_id: number; cached?: boolean }>(
      `/strategies/${strategyId}/backtest_stored/`,
      {
        coin: payload.coin,
        interval: payload.interval,
        network: payload.network ?? 'mainnet',
        start: payload.start,
        end: payload.end,
        initial_capital: payload.initial_capital ?? 10_000,
        commission: payload.commission,
      },
    )
    // If cached, fetch the existing result without adding a duplicate placeholder
    if (data.cached) {
      const existing = backtests.value.find((b) => b.id === data.backtest_id)
      if (!existing) await fetchOne(data.backtest_id)
      activeId.value = data.backtest_id
      showResults.value = true
      return data.backtest_id
    }
    const placeholder: Backtest = {
      id: data.backtest_id,
      strategy: strategyId,
      status: 'pending',
      symbol: payload.coin,
      timeframe: payload.interval,
      network: payload.network ?? 'mainnet',
      initial_balance: payload.initial_capital ?? 10_000,
      range_start: null,
      range_end: null,
      metrics: {},
      error: '',
      created_at: new Date().toISOString(),
      trades: [],
    }
    backtests.value.unshift(placeholder)
    activeId.value = data.backtest_id
    startPollingActive()
    return data.backtest_id
  }

  async function runBacktest(
    strategyId: number,
    payload: { symbol: string; timeframe: string; candles: Candle[] },
  ) {
    inlineRunning.value = true
    lastResult.value = null
    try {
      const { data } = await api.post<{ backtest_id: number }>(
        `/strategies/${strategyId}/backtest/`,
        payload,
      )
      activeId.value = data.backtest_id
      const result = await pollUntilDone(data.backtest_id)
      lastResult.value = result
      return result
    } finally {
      inlineRunning.value = false
    }
  }

  async function pollUntilDone(id: number, intervalMs = 1500, maxAttempts = 120) {
    for (let i = 0; i < maxAttempts; i++) {
      const bt = await fetchOne(id)
      if (bt.status === 'done' || bt.status === 'failed') return bt
      await new Promise((r) => setTimeout(r, intervalMs))
    }
    const bt = await fetchOne(id)
    if (bt.status !== 'done' && bt.status !== 'failed') {
      const idx = backtests.value.findIndex((b) => b.id === id)
      if (idx >= 0) {
        backtests.value[idx].status = 'failed'
        backtests.value[idx].error = 'Backtest timed out — Celery worker may be offline'
      }
      if (activeId.value === id) {
        lastResult.value = { ...backtests.value[idx], status: 'failed' }
      }
      stopPollingActive()
    }
    return backtests.value.find((b) => b.id === id) ?? bt
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
      inlineRunning.value = false
      void fetchOne(id).then((bt) => {
        lastResult.value = bt
        if (bt.status === 'done') showResults.value = true
      })
      void import('./analytics').then(({ useAnalyticsStore }) => {
        const astore = useAnalyticsStore()
        if (astore.data) void astore.refreshIfBacktestDone()
      })
    }
    if (activeBacktests.value.length) {
      startPollingActive()
    } else {
      stopPollingActive()
    }
  }

  function applyWsPayload(payload: Record<string, unknown>) {
    applyWs(payload)
  }

  function openResults() {
    showResults.value = true
  }

  function closeResults() {
    showResults.value = false
  }

  function startPollingActive() {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      if (!activeBacktests.value.length) {
        stopPollingActive()
        return
      }
      void fetchAll()
    }, POLL_INTERVAL_MS)
  }

  function stopPollingActive() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function resolveStale(id: number) {
    try {
      await api.post(`/backtests/${id}/resolve-stale/`)
      return fetchOne(id)
    } catch {
      return fetchOne(id)
    }
  }

  async function retryStaleBacktests() {
    try {
      const { data } = await api.post<{ resolved: number }>('/backtests/retry-stale/')
      return data.resolved
    } catch {
      return 0
    }
  }

  return {
    backtests,
    activeId,
    active,
    activeBacktests,
    loading,
    inlineRunning,
    running,
    lastResult,
    showResults,
    forStrategy,
    fetchAll,
    fetchOne,
    fetchBacktest,
    runInline,
    runStored,
    runBacktest,
    pollUntilDone,
    select,
    applyWs,
    applyWsPayload,
    openResults,
    closeResults,
    startPollingActive,
    stopPollingActive,
    resolveStale,
    retryStaleBacktests,
  }
})
