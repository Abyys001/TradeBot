<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HistoryDataset } from '../../api/client'
import { useHistoryStore } from '../../stores/history'

const props = defineProps<{ dataset: HistoryDataset | null }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const history = useHistoryStore()
const loading = ref(false)
const gaps = ref<Array<Record<string, unknown>>>([])
const quality = ref<Record<string, unknown> | null>(null)
const coverage = ref<Record<string, unknown> | null>(null)
const funding = ref<Array<{ time: number; funding_rate: number }>>([])

function fmtTs(ms: number) {
  return new Date(ms).toISOString().slice(0, 19).replace('T', ' ')
}

onMounted(async () => {
  const d = props.dataset
  if (!d) return
  loading.value = true
  try {
    const network = d.network || 'mainnet'
    const kind = d.kind || 'ohlcv'
    if (kind === 'ohlcv') {
      ;[gaps.value, quality.value, coverage.value] = await Promise.all([
        history.fetchGaps(d.coin, d.interval, network),
        history.fetchQuality(d.coin, d.interval, network, kind),
        history.fetchCoverage(d.coin, d.interval, network, kind),
      ])
    } else if (kind === 'funding') {
      funding.value = await history.fetchFunding(d.coin, network, d.start_ts, d.end_ts)
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div
    v-if="dataset"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    @click.self="emit('close')"
  >
    <div class="scrollbar-styled scrollbar-thin w-full max-w-lg rounded-xl border border-zinc-800 bg-zinc-950 shadow-xl max-h-[80vh] overflow-y-auto">
      <div class="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <h3 class="text-sm font-medium text-zinc-200">
          {{ dataset.coin }} / {{ dataset.interval || dataset.kind }}
        </h3>
        <button type="button" class="text-zinc-500 hover:text-zinc-300" @click="emit('close')">×</button>
      </div>
      <div class="p-4 space-y-4 text-sm">
        <div v-if="loading" class="text-zinc-500">{{ t('data.loading') }}</div>
        <template v-else>
          <div v-if="coverage" class="space-y-1">
            <div class="text-xs text-zinc-500">{{ t('data.detailCoverage') }}</div>
            <div class="text-zinc-300 font-mono text-xs">{{ JSON.stringify(coverage, null, 2) }}</div>
          </div>
          <div v-if="quality" class="space-y-1">
            <div class="text-xs text-zinc-500">{{ t('data.detailQuality') }}</div>
            <div class="text-zinc-300 font-mono text-xs">{{ JSON.stringify(quality, null, 2) }}</div>
          </div>
          <div v-if="gaps.length" class="space-y-1">
            <div class="text-xs text-zinc-500">{{ t('data.detailGaps', { count: gaps.length }) }}</div>
            <ul class="scrollbar-styled scrollbar-thin text-xs text-amber-300 space-y-1 max-h-32 overflow-y-auto">
              <li v-for="(g, i) in gaps.slice(0, 20)" :key="i">
                {{ fmtTs(Number(g.start_ts || g.start)) }} → {{ fmtTs(Number(g.end_ts || g.end)) }}
              </li>
            </ul>
          </div>
          <div v-if="funding.length" class="space-y-1">
            <div class="text-xs text-zinc-500">{{ t('data.detailFunding', { count: funding.length }) }}</div>
            <div class="scrollbar-styled scrollbar-thin text-xs text-zinc-400 max-h-40 overflow-y-auto font-mono">
              <div v-for="(f, i) in funding.slice(-10)" :key="i">
                {{ new Date(f.time * 1000).toISOString().slice(0, 16) }}: {{ f.funding_rate.toExponential(3) }}
              </div>
            </div>
          </div>
          <div v-if="!gaps.length && !quality && !coverage && !funding.length" class="text-zinc-500 text-xs">
            {{ t('data.detailEmpty') }}
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
