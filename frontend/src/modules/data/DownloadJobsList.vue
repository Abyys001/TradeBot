<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HistoryDownload } from '../../api/client'
import { useHistoryStore } from '../../stores/history'

const props = defineProps<{ downloads: HistoryDownload[] }>()
const emit = defineEmits<{ retry: [id: number] }>()

const { t } = useI18n()
const history = useHistoryStore()

const manualCollapsed = ref<Set<number>>(new Set())
const retryingId = ref<number | null>(null)

const sorted = computed(() =>
  [...props.downloads].sort((a, b) => b.created_at.localeCompare(a.created_at)),
)

function isExpanded(job: HistoryDownload) {
  if (manualCollapsed.value.has(job.id)) return false
  return job.status === 'running' || job.status === 'pending'
}

function toggleExpand(job: HistoryDownload) {
  const next = new Set(manualCollapsed.value)
  if (isExpanded(job)) {
    next.add(job.id)
  } else {
    next.delete(job.id)
  }
  manualCollapsed.value = next
}

function progressPct(job: HistoryDownload): number {
  const entries = Object.values(job.progress || {})
  if (!entries.length) {
    if (job.status === 'done') return 100
    if (job.status === 'running') return 5
    return 0
  }
  const done = entries.filter((e) => history.TERMINAL_PAIR_STATUSES.has(e.status)).length
  return Math.round((done / entries.length) * 100)
}

function progressText(job: HistoryDownload): string {
  const entries = Object.values(job.progress || {})
  if (!entries.length) {
    if (job.status === 'done') return 'Complete'
    if (job.status === 'pending') return 'Queued…'
    if (job.status === 'running') return 'Starting…'
    return '—'
  }
  const done = entries.filter((e) => history.TERMINAL_PAIR_STATUSES.has(e.status)).length
  const totalBars = entries.reduce((s, e) => s + (e.bars || 0), 0)
  let text = `${done} / ${entries.length} pairs`
  if (totalBars > 0) text += ` · ${totalBars.toLocaleString()} bars`
  return text
}

function pairBadgeClass(status: string) {
  if (status === 'done') return 'bg-success-bg text-positive border border-positive/30'
  if (status === 'partial') return 'bg-warning-bg text-warning border border-warning/40'
  if (status === 'empty') return 'bg-surface-raised text-fg-muted border border-border'
  if (status === 'skipped') return 'bg-surface-raised text-fg-muted border border-border'
  if (status === 'failed') return 'bg-danger-bg text-negative border border-negative/30'
  if (status === 'queued') return 'bg-surface-raised/60 text-fg-muted border border-border/50'
  if (status === 'running') return 'bg-warning-bg text-warning border border-warning/40 animate-pulse'
  return 'bg-warning-bg text-warning border border-warning/40 animate-pulse'
}

function pairIconLabel(status: string) {
  const map: Record<string, string> = {
    done: '✓', partial: '~', empty: '∅', skipped: '–',
    failed: '✗', queued: '…', running: '↓',
  }
  return map[status] ?? status
}

function statusCfg(job: HistoryDownload) {
  const isStale = job.status === 'pending' && !!job.is_stale
  if (isStale) return { label: 'Stale', cls: 'text-warning', bar: 'bg-warning', ping: false }
  if (job.status === 'done') return { label: 'Complete', cls: 'text-positive', bar: 'bg-positive', ping: false }
  if (job.status === 'partial') return { label: 'Partial', cls: 'text-warning', bar: 'bg-warning', ping: false }
  if (job.status === 'failed') return { label: 'Failed', cls: 'text-negative', bar: 'bg-negative', ping: false }
  if (job.status === 'running') return { label: 'Downloading…', cls: 'text-warning', bar: 'bg-warning', ping: true }
  return { label: 'Pending', cls: 'text-fg-muted', bar: 'bg-border', ping: false }
}

function canRetry(job: HistoryDownload) {
  if (job.status === 'failed' || job.status === 'partial') return true
  if (job.status === 'pending' && job.is_stale) return true
  const entries = Object.values(job.progress || {})
  return entries.some((e) => e.status === 'empty' || e.status === 'failed')
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
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-fg">{{ t('data.jobsTitle') }}</h3>
      <span v-if="sorted.length" class="text-xs text-fg-muted">{{ sorted.length }} jobs</span>
    </div>

    <div
      v-if="!sorted.length"
      class="rounded-xl border border-dashed border-border py-10 text-center text-sm text-fg-muted"
    >
      {{ t('data.noJobs') }}
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="job in sorted"
        :key="job.id"
        class="rounded-xl border overflow-hidden"
        :class="
          job.status === 'running'
            ? 'border-warning/40'
            : job.status === 'done'
            ? 'border-positive/30'
            : job.status === 'failed'
            ? 'border-negative/30'
            : 'border-border'
        "
      >
        <!-- clickable header -->
        <button
          type="button"
          class="w-full text-start px-4 py-3 hover:bg-surface-muted/40 transition-colors"
          @click="toggleExpand(job)"
        >
          <div class="flex items-center gap-3">
            <!-- pulsing status dot -->
            <div class="relative shrink-0 h-3 w-3 flex items-center justify-center">
              <span
                class="block h-2.5 w-2.5 rounded-full"
                :class="statusCfg(job).bar"
              />
              <span
                v-if="statusCfg(job).ping"
                class="absolute inset-0 rounded-full animate-ping opacity-60"
                :class="statusCfg(job).bar"
              />
            </div>

            <!-- label + coins -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-xs font-semibold" :class="statusCfg(job).cls">
                  {{ statusCfg(job).label }}
                </span>
                <span class="text-xs text-fg-muted truncate">
                  {{ job.coins.join(', ') }}
                  <template v-if="job.intervals.length"> × {{ job.intervals.join(', ') }}</template>
                  <span class="text-fg-muted"> · {{ job.network }}</span>
                </span>
                <span class="ml-auto text-[11px] text-fg-muted shrink-0">
                  #{{ job.id }} · {{ new Date(job.created_at).toLocaleString() }}
                </span>
              </div>

              <!-- progress bar + text -->
              <div class="mt-2">
                <div class="flex items-center justify-between text-[11px] mb-1">
                  <span class="text-fg-muted">{{ progressText(job) }}</span>
                  <span v-if="job.status !== 'done' && progressPct(job) > 0" class="text-fg-muted">
                    {{ progressPct(job) }}%
                  </span>
                </div>
                <div class="h-1.5 rounded-full bg-surface-raised overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all duration-700"
                    :class="statusCfg(job).bar"
                    :style="{
                      width: `${job.status === 'done' ? 100 : progressPct(job)}%`,
                    }"
                  />
                </div>
              </div>
            </div>

            <!-- retry -->
            <button
              v-if="canRetry(job)"
              type="button"
              class="shrink-0 rounded px-2.5 py-1 text-xs bg-surface-raised text-fg hover:bg-border disabled:opacity-50"
              :disabled="retryingId === job.id"
              @click="retryJob(job, $event)"
            >
              {{ retryingId === job.id ? t('data.retrying') : t('data.retry') }}
            </button>

            <!-- chevron -->
            <svg
              class="shrink-0 h-4 w-4 text-fg-muted transition-transform duration-200"
              :class="isExpanded(job) ? 'rotate-180' : ''"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            >
              <path stroke-linecap="round" d="M6 9l6 6 6-6" />
            </svg>
          </div>
        </button>

        <!-- expanded pair grid -->
        <div v-show="isExpanded(job)" class="border-t border-border/50 bg-surface-muted/20 px-4 py-3 space-y-3">
          <p v-if="job.error" class="text-xs text-negative font-mono bg-danger-bg/30 rounded px-2 py-1.5">
            {{ job.error }}
          </p>
          <p v-if="job.status === 'pending' && job.is_stale" class="text-xs text-warning">
            {{ t('data.staleJobHint') }}
          </p>

          <div v-if="Object.keys(job.progress || {}).length" class="flex flex-wrap gap-2">
            <div
              v-for="(entry, key) in job.progress"
              :key="key"
              class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs"
              :class="pairBadgeClass(entry.status)"
              :title="entry.error || entry.note || undefined"
            >
              <span class="font-mono font-semibold">{{ key }}</span>
              <span class="opacity-60">{{ pairIconLabel(entry.status) }}</span>
              <span v-if="entry.bars" class="opacity-70">{{ entry.bars.toLocaleString() }}b</span>
              <span v-if="entry.note" class="opacity-50 text-[10px] max-w-[120px] truncate">{{ entry.note }}</span>
              <span v-if="entry.error" class="text-[10px] text-negative max-w-[120px] truncate">{{ entry.error }}</span>
            </div>
          </div>

          <p v-else-if="job.status === 'running'" class="text-xs text-warning animate-pulse">
            Initializing pairs…
          </p>
          <p v-else class="text-xs text-fg-muted">{{ t('data.noPairProgress') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
