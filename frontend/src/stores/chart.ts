import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type Candle, type ChartMarker } from '../api/client'

export const useChartStore = defineStore('chart', () => {
  const candles = ref<Candle[]>([])
  const markers = ref<ChartMarker[]>([])
  const pnl = ref<string>('0')
  const loading = ref(false)

  async function fetchCandles(symbol: string, bar: string, limit = 500) {
    loading.value = true
    try {
      const { data } = await api.get<{ candles: Candle[] }>('/candles/', {
        params: { symbol, bar, limit },
      })
      candles.value = data.candles
      return data.candles
    } finally {
      loading.value = false
    }
  }

  async function fetchMarkers(strategyId: number, source = 'live', backtestId?: number) {
    const params: Record<string, string | number> = { strategy_id: strategyId, source }
    if (backtestId) params.backtest_id = backtestId
    const { data } = await api.get<{ markers: ChartMarker[] }>('/markers/', { params })
    markers.value = data.markers
    return data.markers
  }

  async function fetchStoredCandles(
    coin: string,
    interval: string,
    opts?: { start?: number; end?: number; limit?: number },
  ) {
    loading.value = true
    try {
      const params: Record<string, string | number | undefined> = {
        coin,
        interval,
        start: opts?.start,
        end: opts?.end,
      }
      if (opts?.start != null && opts?.end != null) {
        params.limit = opts.limit ?? 50000
      } else {
        params.limit = opts?.limit ?? 2000
      }
      const { data } = await api.get<{ candles: Candle[] }>('/history/candles/', { params })
      candles.value = data.candles
      return data.candles
    } finally {
      loading.value = false
    }
  }

  function applyCandleTick(payload: Record<string, unknown>) {
    if (payload.source !== 'candle_tick') return
    const candle = payload.candle as Candle
    if (!candle) return
    const idx = candles.value.findIndex((c) => c.time === candle.time)
    if (idx >= 0) {
      candles.value[idx] = candle
    } else {
      candles.value.push(candle)
    }
  }

  function applyPnl(payload: Record<string, unknown>) {
    if (payload.source !== 'pnl') return
    pnl.value = String(payload.pnl ?? '0')
  }

  return { candles, markers, pnl, loading, fetchCandles, fetchStoredCandles, fetchMarkers, applyCandleTick, applyPnl }
})
