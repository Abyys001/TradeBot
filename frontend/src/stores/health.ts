import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type HealthPayload } from '../api/client'

export const useHealthStore = defineStore('health', () => {
  const health = ref<HealthPayload | null>(null)
  const loading = ref(false)

  async function fetchHealth() {
    loading.value = true
    try {
      const { data } = await api.get<HealthPayload>('/health/')
      health.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  function applyWsPayload(payload: Record<string, unknown>) {
    if (payload.source !== 'health' || !health.value) return
    health.value = {
      ...health.value,
      hl_market_feed: payload.hl_market_feed as HealthPayload['hl_market_feed'],
      celery: payload.celery as HealthPayload['celery'],
      active_strategies: payload.active_strategies as number,
      is_trading_enabled: payload.is_trading_enabled as boolean,
    }
  }

  return { health, loading, fetchHealth, applyWsPayload }
})
