<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type ExecutionLog } from '../../api/client'
import { useExchangeWebSocket } from '../../composables/useExchangeWebSocket'

const props = defineProps<{
  credentialId?: number
  strategyId?: number
  maxRows?: number
}>()

const limit = computed(() => props.maxRows ?? 100)
const logs = ref<ExecutionLog[]>([])
const loading = ref(true)
const levelFilter = ref<string>('all')
const eventFilter = ref('')
const page = ref(1)
const pageSize = 50
const total = ref(0)

const levels = ['all', 'debug', 'info', 'warning', 'error']

const levelBadge: Record<string, string> = {
  debug: 'bg-surface-raised text-fg-muted',
  info: 'bg-blue-900/40 text-blue-400',
  warning: 'bg-warning-bg text-warning',
  error: 'bg-danger-bg/40 text-negative',
}

async function fetchLogs() {
  loading.value = true
  try {
    const params: Record<string, string | number> = {
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    }
    if (levelFilter.value !== 'all') params.level = levelFilter.value
    if (eventFilter.value.trim()) params.event = eventFilter.value.trim()
    if (props.strategyId) params.strategy = props.strategyId

    const { data } = await api.get<{ results: ExecutionLog[]; count: number }>(
      '/execution/logs/',
      { params },
    )
    logs.value = data.results ?? []
    total.value = data.count ?? 0
  } finally {
    loading.value = false
  }
}

onMounted(fetchLogs)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

function prevPage() {
  if (page.value > 1) { page.value--; fetchLogs() }
}
function nextPage() {
  if (page.value < totalPages.value) { page.value++; fetchLogs() }
}
function applyFilters() {
  page.value = 1
  fetchLogs()
}

const { onEvent } = useExchangeWebSocket(() => props.credentialId ?? null)

onEvent((payload) => {
  const type = String(payload.type ?? '')
  if (type.startsWith('order.') || type.startsWith('risk.') || type.startsWith('twap.') || type.startsWith('eip712.')) {
    // Prepend the incoming event as a transient log row for immediacy.
    const newEntry: ExecutionLog = {
      id: Date.now(),
      strategy: props.strategyId ?? null,
      level: type.includes('rejected') || type.includes('blocked') ? 'warning' : 'info',
      event: type,
      payload: payload as Record<string, unknown>,
      created_at: new Date().toISOString(),
    }
    if (levelFilter.value === 'all' || levelFilter.value === newEntry.level) {
      logs.value = [newEntry, ...logs.value].slice(0, limit.value)
    }
  }
})

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

function payloadSummary(payload: Record<string, unknown>): string {
  const keys = Object.keys(payload).slice(0, 3)
  return keys.map((k) => `${k}=${JSON.stringify(payload[k])}`).join(' ')
}
</script>

<template>
  <div class="rounded-xl border border-border overflow-hidden flex flex-col">
    <!-- Header & filters -->
    <div class="px-4 py-2.5 border-b border-border flex flex-wrap items-center gap-2">
      <span class="text-xs font-semibold text-fg tracking-wide uppercase mr-auto">Execution Log</span>

      <!-- Level filter -->
      <div class="flex gap-1">
        <button
          v-for="lvl in levels"
          :key="lvl"
          type="button"
          class="px-2 py-0.5 rounded text-[10px] font-medium transition-colors"
          :class="levelFilter === lvl ? 'bg-accent text-white' : 'text-fg-muted hover:text-fg'"
          @click="levelFilter = lvl; applyFilters()"
        >
          {{ lvl }}
        </button>
      </div>

      <!-- Event filter -->
      <input
        v-model="eventFilter"
        type="text"
        placeholder="filter by event…"
        class="rounded border border-border bg-surface-muted px-2 py-0.5 text-[10px] text-fg w-32"
        @keydown.enter="applyFilters"
      />

      <button
        type="button"
        class="text-[10px] text-fg-muted hover:text-fg"
        @click="fetchLogs"
      >
        Refresh
      </button>
    </div>

    <!-- Log rows -->
    <div class="overflow-y-auto flex-1" style="max-height: 420px">
      <div v-if="loading && !logs.length" class="px-4 py-6 text-xs text-fg-muted text-center">
        Loading…
      </div>
      <div v-else-if="!logs.length" class="px-4 py-6 text-xs text-fg-muted text-center">
        No log entries
      </div>
      <table v-else class="w-full text-xs">
        <tbody>
          <tr
            v-for="log in logs"
            :key="log.id"
            class="border-b border-border/50 hover:bg-surface-raised/20 transition-colors"
          >
            <td class="px-3 py-1.5 text-fg-muted whitespace-nowrap w-20">{{ fmtTime(log.created_at) }}</td>
            <td class="px-2 py-1.5 w-16">
              <span
                class="inline-block rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase"
                :class="levelBadge[log.level] ?? 'bg-surface-raised text-fg-muted'"
              >
                {{ log.level }}
              </span>
            </td>
            <td class="px-2 py-1.5 text-fg font-mono w-44 truncate max-w-[11rem]">{{ log.event }}</td>
            <td class="px-2 py-1.5 text-fg-muted font-mono truncate max-w-xs">{{ payloadSummary(log.payload) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="px-4 py-2 border-t border-border flex items-center justify-between">
      <span class="text-[10px] text-fg-muted">{{ total }} entries</span>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="text-[10px] text-fg-muted hover:text-fg disabled:opacity-30"
          :disabled="page <= 1"
          @click="prevPage"
        >
          ← Prev
        </button>
        <span class="text-[10px] text-fg-muted">{{ page }} / {{ totalPages }}</span>
        <button
          type="button"
          class="text-[10px] text-fg-muted hover:text-fg disabled:opacity-30"
          :disabled="page >= totalPages"
          @click="nextPage"
        >
          Next →
        </button>
      </div>
    </div>
  </div>
</template>
