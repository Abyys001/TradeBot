<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHistoryStore } from '../stores/history'
import { useHealthStore } from '../stores/health'
import StoredDataTable from '../modules/data/StoredDataTable.vue'
import DownloadForm from '../modules/data/DownloadForm.vue'
import ArchiveImportForm from '../modules/data/ArchiveImportForm.vue'
import DownloadJobsList from '../modules/data/DownloadJobsList.vue'
import CoverageDashboard from '../modules/data/CoverageDashboard.vue'

const { t } = useI18n()
const history = useHistoryStore()
const healthStore = useHealthStore()

const celeryOffline = computed(() => healthStore.health?.celery?.status !== 'ok')

const staleJobs = computed(() =>
  history.downloads.filter((d) => d.status === 'pending' && d.is_stale),
)

const retryingStale = ref(false)

async function retryAllStale() {
  retryingStale.value = true
  try {
    const result = await history.retryStaleDownloads()
    if (result.count > 0) {
      await history.fetchDownloads()
    }
  } catch {
    // error surfaced via history.error
  } finally {
    retryingStale.value = false
  }
}

onMounted(async () => {
  try {
    await history.fetchDatasets()
    await history.fetchDownloads()
    void healthStore.fetchHealth()
    if (history.activeDownloads.length > 0) {
      history.startPollingActiveDownloads()
    }
  } catch {
    // error surfaced via history.error
  }
})

onUnmounted(() => {
  history.stopPollingActiveDownloads()
})

watch(
  () => history.activeDownloads.length,
  (count) => {
    if (count > 0) history.startPollingActiveDownloads()
    else history.stopPollingActiveDownloads()
  },
)

async function onSubmitted() {
  await history.fetchDownloads()
}

async function onRetry(jobId: number) {
  await history.retryDownload(jobId)
}
</script>

<template>
  <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-3 space-y-4 sm:p-4">
    <h1 class="text-lg font-semibold text-fg">{{ t('data.title') }}</h1>
    <p class="text-sm text-fg-muted -mt-2">{{ t('data.subtitle') }}</p>
    <p class="text-xs text-fg-muted">{{ t('data.noApiRequired') }}</p>

    <div
      v-if="celeryOffline"
      class="rounded-lg border border-negative/30 bg-danger-bg px-3 py-2 text-sm text-negative"
    >
      {{ t('data.celeryOffline') }}
      <code class="block mt-1 text-xs text-negative/80">docker compose up -d celery celery-beat</code>
    </div>

    <div
      v-if="staleJobs.length"
      class="rounded-lg border border-warning/30 bg-warning-bg px-3 py-2 text-sm text-warning flex items-center justify-between gap-2"
    >
      <span>{{ t('data.staleJobs', { count: staleJobs.length }) }}</span>
      <button
        type="button"
        class="shrink-0 rounded bg-warning/30 px-2 py-1 text-xs hover:bg-warning/40 disabled:opacity-50"
        :disabled="retryingStale || celeryOffline"
        @click="retryAllStale"
      >
        {{ retryingStale ? t('data.retrying') : t('data.retryAllStale') }}
      </button>
    </div>

    <div
      v-if="history.error"
      class="rounded-lg border border-negative/30 bg-danger-bg px-3 py-2 text-sm text-negative"
    >
      {{ t('data.loadError') }}: {{ history.error }}
    </div>

    <CoverageDashboard />

    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-2 gap-4 items-start">
      <DownloadForm @submitted="onSubmitted" />
      <ArchiveImportForm @submitted="onSubmitted" />
    </div>
      <DownloadJobsList :downloads="history.downloads" @retry="onRetry" />

    <StoredDataTable
      :datasets="history.datasets"
      :loading="history.loading"
      @deleted="history.fetchDatasets()"
    />
  </div>
</template>
