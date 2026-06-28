<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HistoryDownload } from '../../api/client'
import { useHistoryStore } from '../../stores/history'

const props = defineProps<{ downloads: HistoryDownload[] }>()
const emit = defineEmits<{ retry: [id: number] }>()

const { t } = useI18n()
const history = useHistoryStore()

const expandedId = ref<number | null>(null)
const retryingId = ref<number | null>(null)

const sorted = computed(() =>
  [...props.downloads].sort((a, b) => b.created_at.localeCompare(a.created_at)),
)

function statusClass(status: string) {
  if (status === 'done') return 'text-emerald-400'
  if (status === 'partial') return 'text-amber-400'
  if (status === 'failed') return 'text-red-400'
  if (status === 'running') return 'text-amber-400'
  return 'text-zinc-500'
}

function progressSummary(job: HistoryDownload) {
  const entries = Object.values(job.progress || {})
  if (!entries.length) return '—'
  const finished = entries.filter((e) => history.TERMINAL_PAIR_STATUSES.has(e.status)).length
  const running = entries.filter((e) => e.status === 'running' || e.status === 'queued').length
  if (job.status === 'running' && running > 0) {
    return `${finished}/${entries.length} (${t('data.inProgress')})`
  }
  return `${finished}/${entries.length}`
}

function progressEntries(job: HistoryDownload) {
  return Object.entries(job.progress || {})
}

function pairBadgeClass(status: string) {
  if (status === 'done') return 'bg-emerald-900/50 text-emerald-300'
  if (status === 'partial') return 'bg-amber-900/50 text-amber-300'
  if (status === 'empty') return 'bg-zinc-800 text-zinc-400'
  if (status === 'skipped') return 'bg-zinc-700 text-zinc-400'
  if (status === 'failed') return 'bg-red-900/50 text-red-300'
  if (status === 'queued') return 'bg-zinc-800 text-zinc-500'
  if (status === 'running') return 'bg-amber-900/50 text-amber-300 animate-pulse'
  return 'bg-amber-900/50 text-amber-300'
}

function pairStatusLabel(status: string) {
  if (status === 'done') return t('data.pairDone')
  if (status === 'partial') return t('data.pairPartial')
  if (status === 'empty') return t('data.pairEmpty')
  if (status === 'skipped') return t('data.pairSkipped')
  if (status === 'failed') return t('data.pairFailed')
  if (status === 'queued') return t('data.pairQueued')
  if (status === 'running') return t('data.pairRunning')
  return status
}

function canRetry(job: HistoryDownload) {
  if (job.status === 'failed' || job.status === 'partial') return true
  if (job.status === 'pending' && job.is_stale) return true
  const entries = Object.values(job.progress || {})
  if (entries.some((e) => e.status === 'empty' || e.status === 'failed')) return true
  return false
}

function toggleExpand(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

async function retryJob(job: HistoryDownload, event: Event) {
  event.stopPropagation()
  retryingId.value = job.id
  try {
    emit('retry', job.id)
  } finally {
    retryingId.value = null
  }
}
</script>

<template>
  <div class="rounded-xl border border-zinc-800 overflow-hidden">
    <div class="px-4 py-3 border-b border-zinc-800 bg-zinc-900/50">
      <h3 class="text-sm font-medium text-zinc-200">{{ t('data.jobsTitle') }}</h3>
    </div>
    <div v-if="!sorted.length" class="px-4 py-8 text-center text-sm text-zinc-500">
      {{ t('data.noJobs') }}
    </div>
    <div v-else class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="text-zinc-500 text-xs uppercase">
        <tr class="border-b border-zinc-800">
          <th class="px-4 py-2 text-start">ID</th>
          <th class="px-4 py-2 text-start">{{ t('data.status') }}</th>
          <th class="px-4 py-2 text-start">{{ t('data.pairs') }}</th>
          <th class="px-4 py-2 text-start">{{ t('data.progress') }}</th>
          <th class="px-4 py-2 text-start">{{ t('data.created') }}</th>
          <th class="px-4 py-2 text-end"></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="job in sorted" :key="job.id">
          <tr
            class="border-b border-zinc-800/50 hover:bg-zinc-900/30 cursor-pointer"
            @click="toggleExpand(job.id)"
          >
            <td class="px-4 py-2 text-zinc-400">#{{ job.id }}</td>
            <td class="px-4 py-2 font-medium" :class="statusClass(job.status)">
              <span v-if="job.status === 'partial'">{{ t('data.partial') }}</span>
              <span v-else-if="job.status === 'pending' && job.is_stale">{{ t('data.stale') }}</span>
              <span v-else>{{ job.status }}</span>
            </td>
            <td class="px-4 py-2 text-zinc-400">
              <span>{{ job.coins.join(', ') }}</span>
              <span v-if="job.intervals.length"> × {{ job.intervals.join(', ') }}</span>
              <span v-if="(job.data_types || []).length" class="ml-1 text-zinc-500">
                [{{ (job.data_types || []).join(', ') }}]
              </span>
            </td>
            <td class="px-4 py-2">
              <div class="text-zinc-300 text-xs mb-1">{{ progressSummary(job) }}</div>
              <div v-if="progressEntries(job).length" class="flex flex-wrap gap-1 max-w-md">
                <span
                  v-for="[key, entry] in progressEntries(job)"
                  :key="key"
                  class="rounded px-1.5 py-0.5 text-[10px]"
                  :class="pairBadgeClass(entry.status)"
                  :title="entry.error || entry.note"
                >
                  {{ key }}: {{ pairStatusLabel(entry.status) }}
                </span>
              </div>
            </td>
            <td class="px-4 py-2 text-zinc-500 text-xs">{{ new Date(job.created_at).toLocaleString() }}</td>
            <td class="px-4 py-2 text-end">
              <button
                v-if="canRetry(job)"
                type="button"
                class="rounded px-2 py-0.5 text-xs bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
                :disabled="retryingId === job.id"
                @click="retryJob(job, $event)"
              >
                {{ retryingId === job.id ? t('data.retrying') : t('data.retry') }}
              </button>
            </td>
          </tr>
          <tr v-if="expandedId === job.id" class="border-b border-zinc-800/50 bg-zinc-900/20">
            <td colspan="6" class="px-4 py-3 space-y-2">
              <p v-if="job.error" class="text-xs text-red-300">{{ job.error }}</p>
              <p v-if="job.status === 'pending' && job.is_stale" class="text-xs text-amber-300">
                {{ t('data.staleJobHint') }}
              </p>
              <div v-if="Object.keys(job.progress || {}).length" class="flex flex-wrap gap-1.5">
                <span
                  v-for="(entry, key) in job.progress"
                  :key="key"
                  class="rounded px-2 py-0.5 text-xs"
                  :class="pairBadgeClass(entry.status)"
                  :title="entry.error || entry.note"
                >
                  {{ key }}: {{ pairStatusLabel(entry.status) }}
                  <span v-if="entry.bars"> ({{ entry.bars }})</span>
                  <span v-if="entry.note" class="text-zinc-500"> — {{ entry.note }}</span>
                </span>
              </div>
              <p v-else class="text-xs text-zinc-500">{{ t('data.noPairProgress') }}</p>
            </td>
          </tr>
        </template>
      </tbody>
    </table></div>
  </div>
</template>
