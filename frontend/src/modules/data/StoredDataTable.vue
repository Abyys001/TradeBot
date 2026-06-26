<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { HistoryDataset } from '../../api/client'
import { useHistoryStore } from '../../stores/history'
import { useToast } from '../../composables/useToast'
import DatasetDetailModal from './DatasetDetailModal.vue'

const props = defineProps<{ datasets: HistoryDataset[]; loading?: boolean }>()
const emit = defineEmits<{ deleted: [] }>()

const { t } = useI18n()
const history = useHistoryStore()
const toast = useToast()
const deletingKey = ref<string | null>(null)
const detailDataset = ref<HistoryDataset | null>(null)

function fmtTs(ms: number) {
  return new Date(ms).toISOString().slice(0, 10)
}

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const sorted = computed(() =>
  [...props.datasets].sort(
    (a, b) =>
      (a.network || '').localeCompare(b.network || '') ||
      a.coin.localeCompare(b.coin) ||
      a.interval.localeCompare(b.interval),
  ),
)

function rowKey(d: HistoryDataset) {
  return `${d.network || 'mainnet'}-${d.coin}-${d.interval}-${d.kind || 'ohlcv'}`
}

async function deleteDataset(d: HistoryDataset) {
  const key = rowKey(d)
  deletingKey.value = key
  try {
    await history.deleteDataset({
      network: d.network || 'mainnet',
      coin: d.coin,
      interval: d.interval,
      kind: d.kind || 'ohlcv',
    })
    toast.show(t('data.deleted'), 'success')
    emit('deleted')
  } catch (err: unknown) {
    const msg =
      (err as { response?: { data?: { error?: string } } })?.response?.data?.error ||
      t('data.deleteFailed')
    toast.show(msg, 'error')
  } finally {
    deletingKey.value = null
  }
}
</script>

<template>
  <div class="rounded-xl border border-zinc-800 overflow-hidden">
    <div class="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
      <h3 class="text-sm font-medium text-zinc-200">{{ t('data.storedTitle') }}</h3>
    </div>
    <div v-if="loading" class="px-4 py-8 text-center text-sm text-zinc-500">
      {{ t('data.loading') }}
    </div>
    <div v-else-if="!sorted.length" class="px-4 py-8 text-center text-sm text-zinc-500">
      {{ t('data.noDatasets') }}
    </div>
    <table v-else class="w-full text-sm">
      <thead class="text-zinc-500 text-xs uppercase">
        <tr class="border-b border-zinc-800">
          <th class="px-4 py-2 text-start">{{ t('data.network') }}</th>
          <th class="px-4 py-2 text-start">{{ t('data.coin') }}</th>
          <th class="px-4 py-2 text-start">{{ t('data.interval') }}</th>
          <th class="px-4 py-2 text-start">{{ t('data.quality') }}</th>
          <th class="px-4 py-2 text-start">{{ t('data.range') }}</th>
          <th class="px-4 py-2 text-end">{{ t('data.bars') }}</th>
          <th class="px-4 py-2 text-end">{{ t('data.size') }}</th>
          <th class="px-4 py-2 text-end"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="d in sorted"
          :key="rowKey(d)"
          class="border-b border-zinc-800/50 hover:bg-zinc-900/30 cursor-pointer"
          @click="detailDataset = d"
        >
          <td class="px-4 py-2 text-zinc-500 text-xs">{{ d.network || 'mainnet' }}</td>
          <td class="px-4 py-2 text-zinc-200 font-medium">{{ d.coin }}</td>
          <td class="px-4 py-2 text-zinc-400">{{ d.interval }}</td>
          <td class="px-4 py-2">
            <span
              v-if="d.kind === 'ohlcv' || !d.kind"
              class="text-xs rounded px-1.5 py-0.5"
              :class="
                d.healthy === false
                  ? 'bg-amber-900/50 text-amber-300'
                  : d.healthy === true
                    ? 'bg-emerald-900/40 text-emerald-300'
                    : 'text-zinc-600'
              "
            >
              {{
                d.healthy === false
                  ? t('data.gaps', { count: d.gap_count ?? 0 })
                  : d.healthy === true
                    ? t('data.healthy')
                    : '—'
              }}
            </span>
            <span v-else class="text-zinc-600 text-xs">—</span>
          </td>
          <td class="px-4 py-2 text-zinc-400">{{ fmtTs(d.start_ts) }} — {{ fmtTs(d.end_ts) }}</td>
          <td class="px-4 py-2 text-end text-zinc-300">{{ d.bars.toLocaleString() }}</td>
          <td class="px-4 py-2 text-end text-zinc-500">{{ fmtSize(d.size_bytes) }}</td>
          <td class="px-4 py-2 text-end space-x-2">
            <RouterLink
              v-if="d.kind === 'ohlcv' || !d.kind"
              :to="{
                path: '/strategies',
                query: {
                  dataCoin: d.coin,
                  dataInterval: d.interval,
                  dataNetwork: d.network || 'mainnet',
                },
              }"
              class="text-xs text-violet-400 hover:underline"
            >
              {{ t('data.useInBacktest') }}
            </RouterLink>
            <button
              type="button"
              class="text-xs text-red-400 hover:underline disabled:opacity-50"
              :disabled="deletingKey === rowKey(d)"
              @click.stop="deleteDataset(d)"
            >
              {{ deletingKey === rowKey(d) ? t('data.deleting') : t('data.delete') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <DatasetDetailModal v-if="detailDataset" :dataset="detailDataset" @close="detailDataset = null" />
  </div>
</template>
