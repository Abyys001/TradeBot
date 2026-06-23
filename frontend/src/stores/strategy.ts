import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import axios from 'axios'
import { api, type LiveConfig, type Strategy, type ValidateResult } from '../api/client'

const DEFAULT_LIVE_CONFIG: LiveConfig = {
  symbols: ['BTC-USDT'],
  timeframes: ['1m'],
  risk: { leverage: 1, position_size_pct: 5, global_stop_loss_pct: 10 },
}

export const useStrategyStore = defineStore('strategy', () => {
  const strategies = ref<Strategy[]>([])
  const selectedId = ref<number | null>(null)
  const loading = ref(false)

  const selected = computed(() =>
    strategies.value.find((s) => s.id === selectedId.value) ?? null,
  )

  async function fetchAll() {
    loading.value = true
    try {
      const { data } = await api.get<Strategy[]>('/strategies/')
      strategies.value = data
      if (!selectedId.value && data.length) selectedId.value = data[0].id
      return data
    } finally {
      loading.value = false
    }
  }

  async function createStrategy(payload: Partial<Strategy>) {
    const { data } = await api.post<Strategy>('/strategies/', {
      name: 'New Strategy',
      type: 'pine',
      symbol: 'BTC-USDT',
      credential: payload.credential,
      live_config: DEFAULT_LIVE_CONFIG,
      ...payload,
    })
    strategies.value.unshift(data)
    selectedId.value = data.id
    return data
  }

  async function updateStrategy(id: number, patch: Partial<Strategy>) {
    const liveConfig = patch.live_config
    if (liveConfig) {
      patch = {
        ...patch,
        symbol: liveConfig.symbols?.[0] ?? patch.symbol,
        timeframe: liveConfig.timeframes?.[0] ?? patch.timeframe,
      }
    }
    const { data } = await api.patch<Strategy>(`/strategies/${id}/`, patch)
    const idx = strategies.value.findIndex((s) => s.id === id)
    if (idx >= 0) strategies.value[idx] = data
    return data
  }

  async function validate(id: number) {
    try {
      const { data } = await api.post<ValidateResult>(`/strategies/${id}/validate/`)
      await fetchAll()
      return data
    } catch (err: unknown) {
      await fetchAll()
      if (axios.isAxiosError(err) && err.response?.data) {
        return err.response.data as ValidateResult
      }
      throw err
    }
  }

  async function deleteStrategy(id: number) {
    await api.delete(`/strategies/${id}/`)
    strategies.value = strategies.value.filter((s) => s.id !== id)
    if (selectedId.value === id) selectedId.value = strategies.value[0]?.id ?? null
  }

  function select(id: number | null) {
    selectedId.value = id
  }

  async function start(id: number) {
    const { data } = await api.post(`/strategies/${id}/start/`)
    await fetchAll()
    return data
  }

  async function stop(id: number) {
    const { data } = await api.post(`/strategies/${id}/stop/`)
    await fetchAll()
    return data
  }

  const validatedStrategies = computed(() =>
    strategies.value.filter((s) => s.validation_status === 'ok'),
  )

  return {
    strategies,
    selectedId,
    selected,
    loading,
    validatedStrategies,
    fetchAll,
    createStrategy,
    updateStrategy,
    validate,
    start,
    stop,
    deleteStrategy,
    select,
  }
})
