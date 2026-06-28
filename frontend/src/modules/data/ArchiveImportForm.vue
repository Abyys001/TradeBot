<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../../api/client'
import { useHistoryStore } from '../../stores/history'
import { useHealthStore } from '../../stores/health'
import { useToast } from '../../composables/useToast'

const emit = defineEmits<{ submitted: [] }>()

const { t } = useI18n()
const history = useHistoryStore()
const healthStore = useHealthStore()
const toast = useToast()

type SourceMode = 'api' | 'archive'

const sourceMode = ref<SourceMode>('api')
const network = ref('mainnet')
const filePath = ref('')
const archiveCoin = ref('')
const archiveInterval = ref('1h')
const archiveFormat = ref<'parquet' | 'csv_gz'>('parquet')
const submitting = ref(false)

const celeryOffline = computed(() => healthStore.health?.celery?.status !== 'ok')

const availableCoins = computed(() => {
  const coins = history.markets?.coins ?? []
  return coins.slice(0, 100)
})

const availableIntervals = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w']

function sanitizeMarket(input: string): string {
  return input.toUpperCase().replace(/[@:]/g, '').replace(/-.*$/, '')
}

function validateFilePath(path: string): boolean {
  if (!path.trim()) return false
  const lower = path.toLowerCase()
  if (archiveFormat.value === 'parquet' && !lower.endsWith('.parquet')) {
    toast.show('File must be a .parquet file', 'error')
    return false
  }
  if (archiveFormat.value === 'csv_gz' && !lower.endsWith('.csv.gz') && !lower.endsWith('.csv')) {
    toast.show('File must be a .csv or .csv.gz file', 'error')
    return false
  }
  return true
}

async function submitArchive() {
  if (celeryOffline.value) {
    toast.show(t('data.celeryOffline'), 'error')
    return
  }
  if (!validateFilePath(filePath.value)) return

  submitting.value = true
  try {
    const { data } = await api.post('/history/import-archive/', {
      file_path: filePath.value.trim(),
      coin: sanitizeMarket(archiveCoin.value) || undefined,
      interval: archiveInterval.value,
      network: network.value,
    })
    history.downloads.unshift(data)
    history.startPollingActiveDownloads()
    toast.show('Archive import queued', 'success')
    emit('submitted')
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Import failed'
    toast.show(msg, 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="rounded-xl border border-zinc-800 p-4 space-y-4">
    <h3 class="text-sm font-medium text-zinc-200">Import Data</h3>

    <div class="flex gap-2 rounded-lg border border-zinc-700 bg-zinc-900 p-1">
      <button
        type="button"
        class="flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
        :class="sourceMode === 'api' ? 'bg-violet-700 text-white' : 'text-zinc-400 hover:text-zinc-200'"
        @click="sourceMode = 'api'"
      >
        {{ t('data.downloadTitle') }}
      </button>
      <button
        type="button"
        class="flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
        :class="sourceMode === 'archive' ? 'bg-violet-700 text-white' : 'text-zinc-400 hover:text-zinc-200'"
        @click="sourceMode = 'archive'"
      >
        Full Archive
      </button>
    </div>

    <div v-if="sourceMode === 'archive'" class="space-y-3">
      <label class="text-xs text-zinc-500">
        File Path
        <input
          v-model="filePath"
          type="text"
          placeholder="/data/archives/BTC-1h-full.parquet"
          class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200 font-mono"
        />
      </label>

      <div class="grid grid-cols-2 gap-2.5">
        <label class="text-xs text-zinc-500">
          Format
          <select v-model="archiveFormat" class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200">
            <option value="parquet">Parquet (.parquet)</option>
            <option value="csv_gz">CSV Gzip (.csv.gz)</option>
          </select>
        </label>
        <label class="text-xs text-zinc-500">
          Network
          <select v-model="network" class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200">
            <option value="mainnet">mainnet</option>
            <option value="testnet">testnet</option>
          </select>
        </label>
      </div>

      <div class="grid grid-cols-2 gap-2.5">
        <label class="text-xs text-zinc-500">
          Market (optional)
          <div class="relative mt-1">
            <input
              v-model="archiveCoin"
              type="text"
              placeholder="BTC"
              class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200"
              @input="archiveCoin = sanitizeMarket(($event.target as HTMLInputElement).value)"
            />
            <div
              v-if="archiveCoin && availableCoins.length"
              class="absolute left-0 right-0 top-full z-10 mt-1 max-h-32 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900"
            >
              <button
                v-for="c in availableCoins.filter((c) => c.startsWith(archiveCoin.toUpperCase())).slice(0, 10)"
                :key="c"
                type="button"
                class="block w-full px-3 py-1 text-start text-xs text-zinc-300 hover:bg-zinc-800"
                @click="archiveCoin = c"
              >
                {{ c }}
              </button>
            </div>
          </div>
        </label>
        <label class="text-xs text-zinc-500">
          Interval
          <select v-model="archiveInterval" class="mt-1 block w-full rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200">
            <option v-for="iv in availableIntervals" :key="iv" :value="iv">{{ iv }}</option>
          </select>
        </label>
      </div>

      <p class="text-[10px] text-zinc-500 leading-relaxed">
        Filename convention: <code class="text-zinc-300">BTC-1h-full.parquet</code>.
        Market and interval are auto-detected from the filename when omitted.
      </p>

      <button
        type="button"
        class="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50 w-full"
        :disabled="submitting || celeryOffline || !filePath.trim()"
        @click="submitArchive"
      >
        {{ submitting ? 'Importing…' : 'Import Archive' }}
      </button>
    </div>

    <slot v-else />
  </div>
</template>
