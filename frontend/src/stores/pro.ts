import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'

export interface StrategyVersion {
  id: number
  version: number
  note: string
  created_at: string
}

export const useProStore = defineStore('pro', () => {
  const versions = ref<StrategyVersion[]>([])
  const loading = ref(false)

  async function fetchVersions(strategyId: number) {
    const { data } = await api.get<{ versions: StrategyVersion[] }>(
      `/pro/strategies/${strategyId}/versions/`,
    )
    versions.value = data.versions
    return data.versions
  }

  async function snapshotVersion(strategyId: number, note = '') {
    const { data } = await api.post<{ id: number; version: number }>(
      `/pro/strategies/${strategyId}/versions/`,
      { note },
    )
    await fetchVersions(strategyId)
    return data
  }

  async function restoreVersion(strategyId: number, version: number) {
    await api.post(`/pro/strategies/${strategyId}/versions/${version}/restore/`)
  }

  return {
    versions,
    loading,
    fetchVersions,
    snapshotVersion,
    restoreVersion,
  }
})
