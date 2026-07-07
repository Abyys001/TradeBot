import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type OverviewPayload } from '../api/client'

export const useOverviewStore = defineStore('overview', () => {
  const data = ref<OverviewPayload | null>(null)
  const loading = ref(false)

  async function fetchOverview() {
    loading.value = true
    try {
      const { data: payload } = await api.get<OverviewPayload>('/overview/')
      data.value = payload
      return payload
    } finally {
      loading.value = false
    }
  }

  return { data, loading, fetchOverview }
})
