import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'

export interface StrategyVersion {
  id: number
  version: number
  note: string
  created_at: string
}

export interface JournalEntry {
  id: number
  strategy_id: number | null
  title: string
  body: string
  tags: string[]
  created_at: string
}

export interface MarketplacePackage {
  id: number
  name: string
  description: string
  author_id: number
  source?: string
  params?: Record<string, unknown>
}

export const useProStore = defineStore('pro', () => {
  const versions = ref<StrategyVersion[]>([])
  const journal = ref<JournalEntry[]>([])
  const packages = ref<MarketplacePackage[]>([])
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

  async function fetchJournal() {
    const { data } = await api.get<{ entries: JournalEntry[] }>('/pro/journal/')
    journal.value = data.entries
    return data.entries
  }

  async function createJournalEntry(payload: {
    title: string
    body?: string
    strategy_id?: number
    tags?: string[]
  }) {
    const { data } = await api.post<{ id: number }>('/pro/journal/', payload)
    await fetchJournal()
    return data
  }

  async function fetchMarketplace() {
    const { data } = await api.get<{ packages: MarketplacePackage[] }>('/pro/marketplace/')
    packages.value = data.packages
    return data.packages
  }

  async function publishPackage(payload: {
    name: string
    description?: string
    source: string
    is_public?: boolean
  }) {
    const { data } = await api.post<{ id: number }>('/pro/marketplace/', payload)
    await fetchMarketplace()
    return data
  }

  async function importPackage(packageId: number, name?: string) {
    const { data } = await api.post<{ strategy_id: number }>(`/pro/marketplace/${packageId}/import/`, {
      name,
    })
    return data.strategy_id
  }

  return {
    versions,
    journal,
    packages,
    loading,
    fetchVersions,
    snapshotVersion,
    restoreVersion,
    fetchJournal,
    createJournalEntry,
    fetchMarketplace,
    publishPackage,
    importPackage,
  }
})
