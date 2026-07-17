import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, type HistoryDataset, type HistoryDownload, type HistoryMarkets } from '../api/client'
import { useHealthStore } from './health'

const TERMINAL_PAIR_STATUSES = new Set(['done', 'partial', 'empty', 'skipped', 'failed'])
const POLL_INTERVAL_MS = 5000

export const useHistoryStore = defineStore('history', () => {
  const datasets = ref<HistoryDataset[]>([])
  const downloads = ref<HistoryDownload[]>([])
  const markets = ref<HistoryMarkets | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const marketsError = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const activeDownloads = computed(() =>
    downloads.value.filter((d) => d.status === 'pending' || d.status === 'running'),
  )

  function findDataset(coin: string, interval: string, network = 'mainnet') {
    const c = coin.toUpperCase().replace(/-.*$/, '')
    const iv = interval.toLowerCase()
    return datasets.value.find(
      (d) =>
        d.coin === c &&
        d.interval.toLowerCase() === iv &&
        (d.network || 'mainnet') === network &&
        (d.kind === 'ohlcv' || !d.kind),
    )
  }

  function hasDataset(coin: string, interval: string, network = 'mainnet') {
    return Boolean(findDataset(coin, interval, network))
  }

  function hasDatasetCoverage(
    coin: string,
    interval: string,
    startMs?: number,
    endMs?: number,
    network = 'mainnet',
  ) {
    const ds = findDataset(coin, interval, network)
    if (!ds) return { ok: false, reason: 'missing' as const, dataset: null }
    if (startMs != null && ds.start_ts > startMs) {
      return { ok: false, reason: 'start' as const, dataset: ds }
    }
    if (endMs != null && ds.end_ts < endMs) {
      return { ok: false, reason: 'end' as const, dataset: ds }
    }
    return { ok: true, reason: null, dataset: ds }
  }

  async function fetchDatasets(network?: string) {
    loading.value = true
    error.value = null
    try {
      const params = network ? { network, include_quality: 'true' } : { include_quality: 'true' }
      let lastErr: unknown
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const { data } = await api.get<{ datasets: HistoryDataset[] }>('/history/datasets/', { params })
          datasets.value = data.datasets
          return data.datasets
        } catch (e) {
          lastErr = e
          const status = (e as { response?: { status?: number } })?.response?.status
          if (status === 502 || status === 503) {
            await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)))
            continue
          }
          throw e
        }
      }
      throw lastErr
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load datasets'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchMarkets(network = 'mainnet') {
    marketsError.value = null
    try {
      const { data } = await api.get<HistoryMarkets>('/history/markets/', { params: { network } })
      markets.value = data
      return data
    } catch (e) {
      marketsError.value = e instanceof Error ? e.message : 'Failed to load markets'
      throw e
    }
  }

  async function fetchDownloads() {
    error.value = null
    try {
      const { data } = await api.get<HistoryDownload[]>('/history/downloads/')
      downloads.value = data
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load downloads'
      throw e
    }
  }

  async function startDownload(payload: {
    coins: string[]
    intervals: string[]
    dataTypes?: string[]
    start?: string
    end?: string
    network?: string
  }) {
    error.value = null
    const healthStore = useHealthStore()
    await healthStore.fetchHealth()
    if (healthStore.health?.celery?.status !== 'ok') {
      const msg = 'Celery worker is offline'
      error.value = msg
      throw new Error(msg)
    }
    try {
      const { dataTypes, ...rest } = payload
      const body = { ...rest, data_types: dataTypes ?? ['ohlcv'] }
      const { data } = await api.post<HistoryDownload>('/history/downloads/', body)
      downloads.value.unshift(data)
      startPollingActiveDownloads()
      return data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to start download'
      throw e
    }
  }

  async function retryDownload(id: number) {
    error.value = null
    const { data } = await api.post<HistoryDownload>(`/history/downloads/${id}/retry/`)
    const idx = downloads.value.findIndex((d) => d.id === id)
    if (idx >= 0) downloads.value[idx] = data
    else downloads.value.unshift(data)
    startPollingActiveDownloads()
    return data
  }

  async function retryStaleDownloads() {
    error.value = null
    const { data } = await api.post<{ retried: number[]; failed: number[]; count: number }>(
      '/history/downloads/retry-stale/',
    )
    await fetchDownloads()
    if (data.count > 0) startPollingActiveDownloads()
    return data
  }

  async function fetchCoverage(coin: string, interval: string, network = 'mainnet', kind = 'ohlcv') {
    const { data } = await api.get<Record<string, unknown>>('/history/coverage/', {
      params: { coin, interval, network, kind },
    })
    return data
  }

  async function fetchGaps(coin: string, interval: string, network = 'mainnet') {
    const { data } = await api.get<{ gaps: Array<Record<string, unknown>> }>('/history/gaps/', {
      params: { coin, interval, network },
    })
    return data.gaps
  }

  async function fetchQuality(coin: string, interval: string, network = 'mainnet', kind = 'ohlcv') {
    const { data } = await api.get<Record<string, unknown>>('/history/quality/', {
      params: { coin, interval, network, kind },
    })
    return data
  }

  async function fetchFunding(coin: string, network = 'mainnet', start?: number, end?: number) {
    const { data } = await api.get<{ funding: Array<{ time: number; funding_rate: number }> }>(
      '/history/funding/',
      { params: { coin, network, start, end } },
    )
    return data.funding
  }

  async function deleteDataset(payload: {
    network: string
    coin: string
    interval: string
    kind: string
  }) {
    await api.delete('/history/datasets/', { params: payload })
    datasets.value = datasets.value.filter(
      (d) =>
        !(
          (d.network || 'mainnet') === payload.network &&
          d.coin === payload.coin &&
          d.interval === payload.interval &&
          (d.kind || 'ohlcv') === payload.kind
        ),
    )
  }

  async function fetchDownload(id: number) {
    const { data } = await api.get<HistoryDownload>(`/history/downloads/${id}/`)
    const idx = downloads.value.findIndex((d) => d.id === id)
    if (idx >= 0) downloads.value[idx] = data
    else downloads.value.unshift(data)
    return data
  }

  function applyWs(payload: Record<string, unknown>) {
    const jobId = payload.job_id as number | undefined
    if (!jobId) return

    const idx = downloads.value.findIndex((d) => d.id === jobId)
    if (idx >= 0) {
      const job = downloads.value[idx]
      if (payload.status) job.status = payload.status as HistoryDownload['status']
      if (payload.error) job.error = String(payload.error)
      if (payload.progress && typeof payload.progress === 'object') {
        job.progress = { ...job.progress, ...(payload.progress as Record<string, HistoryDownload['progress'][string]>) }
      }
    } else {
      void fetchDownload(jobId)
    }

    const status = payload.status as string | undefined
    if (status === 'done' || status === 'partial') {
      void fetchDatasets()
      void fetchDownload(jobId)
    }

    if (activeDownloads.value.length > 0) {
      startPollingActiveDownloads()
    } else {
      stopPollingActiveDownloads()
    }
  }

  function startPollingActiveDownloads() {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      if (activeDownloads.value.length === 0) {
        stopPollingActiveDownloads()
        return
      }
      void fetchDownloads()
    }, POLL_INTERVAL_MS)
  }

  function stopPollingActiveDownloads() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    datasets,
    downloads,
    markets,
    loading,
    error,
    marketsError,
    activeDownloads,
    TERMINAL_PAIR_STATUSES,
    findDataset,
    hasDataset,
    hasDatasetCoverage,
    fetchDatasets,
    fetchMarkets,
    fetchDownloads,
    startDownload,
    retryDownload,
    retryStaleDownloads,
    fetchCoverage,
    fetchGaps,
    fetchQuality,
    fetchFunding,
    deleteDataset,
    fetchDownload,
    applyWs,
    startPollingActiveDownloads,
    stopPollingActiveDownloads,
  }
})
