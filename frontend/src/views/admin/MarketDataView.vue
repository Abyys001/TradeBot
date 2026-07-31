<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useMarketDataStore } from '../../stores/marketdata'
import { useStrategyStore } from '../../stores/strategy'
import { useToast } from '../../composables/useToast'
import type { MarketDataReadiness } from '../../api/client'

// Tabdeal has no candle backfill: history only exists from the moment a symbol is
// switched on here. That makes this page the first step of going live, not a
// diagnostics screen — hence the emphasis on "recording since" and ETA.
const store = useMarketDataStore()
const strategies = useStrategyStore()
const toast = useToast()

const newSymbol = ref('')
const newNote = ref('')
const adding = ref(false)
const busyId = ref<number | null>(null)
const backfilling = ref(false)
const readinessBySymbol = ref<Record<string, MarketDataReadiness>>({})
const checkTimeframe = ref('1h')
const requiredBars = ref(200)

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '3h', '4h', '1d']
let poll: ReturnType<typeof setInterval> | undefined

const activeCount = computed(() => store.recorded.filter((s) => s.is_active).length)

onMounted(async () => {
  await refresh()
  if (!strategies.strategies.length) await strategies.fetchAll().catch(() => {})
  poll = setInterval(refresh, 30_000)
})
onUnmounted(() => clearInterval(poll))

async function refresh() {
  try {
    await store.fetchRecorded()
    await Promise.all(store.recorded.map(loadReadiness))
  } catch {
    /* transient API errors are surfaced by the row state, not a toast storm */
  }
}

async function loadReadiness(row: { symbol: string }) {
  try {
    readinessBySymbol.value[row.symbol] = await store.fetchReadiness({
      symbol: row.symbol,
      tf: checkTimeframe.value,
      requiredBars: requiredBars.value,
    })
  } catch {
    delete readinessBySymbol.value[row.symbol]
  }
}

async function onAdd() {
  if (!newSymbol.value.trim()) return
  adding.value = true
  try {
    await store.addSymbol(newSymbol.value.trim().toUpperCase(), newNote.value.trim())
    toast.show(`Recording ${newSymbol.value.toUpperCase()}`, 'success')
    newSymbol.value = ''
    newNote.value = ''
    await refresh()
  } catch (e: unknown) {
    toast.show(errorText(e, 'Could not add symbol'), 'error')
  } finally {
    adding.value = false
  }
}

async function onToggle(id: number, isActive: boolean) {
  busyId.value = id
  try {
    await store.setActive(id, !isActive)
    await refresh()
  } catch (e: unknown) {
    toast.show(errorText(e, 'Could not update symbol'), 'error')
  } finally {
    busyId.value = null
  }
}

async function onRemove(id: number, symbol: string) {
  busyId.value = id
  try {
    await store.removeSymbol(id)
    toast.show(`Stopped recording ${symbol}. Existing history is kept.`, 'info')
    await refresh()
  } catch (e: unknown) {
    toast.show(errorText(e, 'Could not remove symbol'), 'error')
  } finally {
    busyId.value = null
  }
}

async function onBackfill(symbols?: string[]) {
  backfilling.value = true
  try {
    await store.backfill({
      symbols: symbols ?? store.recorded.filter((s) => s.is_active).map((s) => s.symbol),
      timeframes: [checkTimeframe.value],
    })
    toast.show('Backfill queued — candles are being rebuilt from the trade ledger.', 'success')
  } catch (e: unknown) {
    toast.show(errorText(e, 'Could not start backfill'), 'error')
  } finally {
    backfilling.value = false
  }
}

function errorText(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: Record<string, string[] | string> } })?.response?.data
  if (!detail) return fallback
  const first = Object.values(detail)[0]
  return Array.isArray(first) ? String(first[0]) : String(first ?? fallback)
}

function hoursLabel(hours: number): string {
  if (!hours) return '—'
  if (hours < 48) return `${hours.toFixed(1)}h`
  return `${(hours / 24).toFixed(1)}d`
}

function etaLabel(r?: MarketDataReadiness): string {
  if (!r) return '—'
  if (r.ready) return 'ready'
  if (r.needs_backfill) return 'needs backfill'
  if (r.eta_seconds == null) return 'not recording'
  const hours = r.eta_seconds / 3600
  return hours >= 24 ? `~${(hours / 24).toFixed(1)}d left` : `~${hours.toFixed(1)}h left`
}

function progressPct(r?: MarketDataReadiness): number {
  if (!r || !r.required_bars) return 0
  return Math.min(100, Math.round((r.clean_bars / r.required_bars) * 100))
}
</script>

<template>
  <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-3 sm:p-6">
    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h1 class="text-lg font-semibold text-fg">Market data</h1>
      <button
        type="button"
        class="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-500 disabled:opacity-40"
        :disabled="backfilling || !activeCount"
        @click="onBackfill()"
      >
        {{ backfilling ? 'Queueing…' : 'Backfill candles' }}
      </button>
    </div>
    <p class="mb-6 text-xs text-fg-muted">
      Tabdeal cannot backfill candles from the exchange — history accrues only while a
      symbol is being recorded here. Add a symbol before you need it.
    </p>

    <div
      v-if="store.seededFromEnv"
      class="mb-6 rounded-lg border border-warning/30 bg-warning-bg px-3 py-2 text-sm text-warning"
    >
      No symbols configured yet. Recording currently falls back to
      <code>{{ store.envDefault.join(', ') || 'BTC_USDT' }}</code> from the environment.
      Add one below to manage it from here.
    </div>

    <!-- Add -->
    <form class="mb-6 flex flex-wrap items-end gap-2" @submit.prevent="onAdd">
      <label class="block text-xs text-fg-muted">
        Symbol
        <input
          v-model="newSymbol"
          type="text"
          placeholder="BTC_USDT"
          class="mt-1 block rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-fg"
        />
      </label>
      <label class="block text-xs text-fg-muted">
        Note (optional)
        <input
          v-model="newNote"
          type="text"
          placeholder="why this market"
          class="mt-1 block rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-fg"
        />
      </label>
      <button
        type="submit"
        class="rounded-lg bg-sky-600 px-3 py-1.5 text-xs text-white hover:bg-sky-500 disabled:opacity-40"
        :disabled="adding || !newSymbol.trim()"
      >
        {{ adding ? 'Adding…' : 'Start recording' }}
      </button>
    </form>

    <!-- Readiness controls -->
    <div class="mb-4 flex flex-wrap items-end gap-2 text-xs text-fg-muted">
      <label>
        Check timeframe
        <select
          v-model="checkTimeframe"
          class="mt-1 block rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-fg"
          @change="refresh"
        >
          <option v-for="tf in TIMEFRAMES" :key="tf" :value="tf">{{ tf }}</option>
        </select>
      </label>
      <label>
        Warmup bars
        <input
          v-model.number="requiredBars"
          type="number"
          min="1"
          class="mt-1 block w-24 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-fg"
          @change="refresh"
        />
      </label>
    </div>

    <div
      v-if="!store.recorded.length"
      class="flex min-h-[30vh] flex-col items-center justify-center text-sm text-fg-muted"
    >
      No symbols are being recorded yet.
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[46rem] text-left text-sm">
        <thead class="text-xs uppercase text-fg-muted">
          <tr>
            <th class="py-2 pr-3">Symbol</th>
            <th class="py-2 pr-3">Status</th>
            <th class="py-2 pr-3">Recorded</th>
            <th class="py-2 pr-3">Warmup ({{ checkTimeframe }})</th>
            <th class="py-2 pr-3">Stored</th>
            <th class="py-2 pr-3"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in store.recorded" :key="row.id" class="border-t border-border">
            <td class="py-2 pr-3 font-medium text-fg">
              {{ row.symbol }}
              <span v-if="row.note" class="block text-xs text-fg-muted">{{ row.note }}</span>
            </td>
            <td class="py-2 pr-3">
              <span
                class="rounded px-1.5 py-0.5 text-xs"
                :class="
                  row.is_active
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'bg-zinc-500/15 text-zinc-400'
                "
              >
                {{ row.is_active ? 'recording' : 'paused' }}
              </span>
            </td>
            <td class="py-2 pr-3 text-fg-muted">{{ hoursLabel(row.coverage.hours) }}</td>
            <td class="py-2 pr-3">
              <div class="flex items-center gap-2">
                <div class="h-1.5 w-24 overflow-hidden rounded bg-zinc-700/40">
                  <div
                    class="h-full rounded"
                    :class="
                      readinessBySymbol[row.symbol]?.ready ? 'bg-emerald-500' : 'bg-sky-500'
                    "
                    :style="{ width: progressPct(readinessBySymbol[row.symbol]) + '%' }"
                  />
                </div>
                <span class="text-xs text-fg-muted">{{ etaLabel(readinessBySymbol[row.symbol]) }}</span>
              </div>
            </td>
            <td class="py-2 pr-3 text-xs text-fg-muted">
              {{ readinessBySymbol[row.symbol]?.stored_bars ?? 0 }} /
              {{ readinessBySymbol[row.symbol]?.required_bars ?? requiredBars }}
              <button
                v-if="readinessBySymbol[row.symbol]?.needs_backfill"
                type="button"
                class="ml-1 rounded bg-amber-600/20 px-1.5 py-0.5 text-amber-400 hover:bg-amber-600/30"
                :disabled="backfilling"
                @click="onBackfill([row.symbol])"
              >
                backfill
              </button>
            </td>
            <td class="py-2 pr-3 text-right">
              <button
                type="button"
                class="rounded px-2 py-1 text-xs text-fg-muted hover:text-fg disabled:opacity-40"
                :disabled="busyId === row.id"
                @click="onToggle(row.id, row.is_active)"
              >
                {{ row.is_active ? 'Pause' : 'Resume' }}
              </button>
              <button
                type="button"
                class="rounded px-2 py-1 text-xs text-danger hover:opacity-80 disabled:opacity-40"
                :disabled="busyId === row.id"
                @click="onRemove(row.id, row.symbol)"
              >
                Remove
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
