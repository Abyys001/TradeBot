<script setup lang="ts">
/**
 * System log — real-time tail of every backend log entry, filterable and
 * auto-scrolling. Entries arrive over the WebSocket as they're written; the
 * initial page (and every re-filter) comes from the REST API, which caps and
 * cursor-paginates server-side (`apps/logging/views.py`) — the browser never
 * holds more of the table than it's actually looking at.
 *
 * Filters are reactive: each change re-queries the API after a short debounce,
 * so typing in the search box doesn't fire a request per keystroke. The
 * WebSocket stream is *additive* on top of whatever page is loaded — new
 * entries matching current filters appear at the bottom; entries that don't
 * match are silently skipped (the store still holds them, the view filters).
 */
const { t } = useI18n()
const store = useSystemLogStore()
const notifications = useNotificationStore()
const { dateTime } = useFormat()

useHead({ title: t('logs.title') })

const level = ref('')
const category = ref('')
const source = ref('')
const search = ref('')
const autoScroll = ref(true)
const scrollContainer = ref<HTMLElement | null>(null)
const showDetails = ref<Set<number>>(new Set())
const pruneOpen = ref(false)
const pruneDays = ref(30)
const pruning = ref(false)

const LEVELS = ['INFO', 'WARNING', 'ERROR', 'CRITICAL']
const CATEGORIES = ['ENGINE', 'EXCHANGE', 'TRADE', 'ADMIN', 'SYSTEM']

function buildParams(): Record<string, string> {
  const params: Record<string, string> = {}
  if (level.value) params.level = level.value
  if (category.value) params.category = category.value
  if (source.value) params.source = source.value
  if (search.value) params.search = search.value
  return params
}

// The server-loaded page is already filtered; this re-applies the same
// predicate client-side so a live WebSocket entry that doesn't match the
// active filters never flashes into view between one query and the next.
const filtered = computed(() => {
  let rows = store.newestFirst
  if (level.value) rows = rows.filter((e) => e.level === level.value)
  if (category.value) rows = rows.filter((e) => e.category === category.value)
  if (source.value) rows = rows.filter((e) => e.source.toLowerCase().includes(source.value.toLowerCase()))
  if (search.value) rows = rows.filter((e) => e.message.toLowerCase().includes(search.value.toLowerCase()))
  return rows
})

const hasFilters = computed(() => level.value || category.value || source.value || search.value)

let debounceTimer: ReturnType<typeof setTimeout> | undefined
watch([level, category, source, search], () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => store.load(buildParams()), 250)
})

function clearFilters() {
  level.value = ''
  category.value = ''
  source.value = ''
  search.value = ''
}

function toggleDetails(id: number) {
  const next = new Set(showDetails.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  showDetails.value = next
}

function scrollToBottom() {
  nextTick(() => {
    if (autoScroll.value && scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  })
}

/** Typed against UiBadge's own tones, so a level cannot name one it does not have. */
function levelBadge(lv: string): 'short' | 'signal' | 'ok' {
  // Critical shares the error tone: it is the strongest thing the palette says.
  if (lv === 'CRITICAL') return 'short'
  if (lv === 'ERROR') return 'short'
  if (lv === 'WARNING') return 'signal'
  return 'ok'
}

function categoryColor(cat: string) {
  if (cat === 'ENGINE') return 'text-brand'
  if (cat === 'EXCHANGE') return 'text-purple-400'
  if (cat === 'TRADE') return 'text-cyan-400'
  if (cat === 'ADMIN') return 'text-signal'
  return 'text-ink-faint'
}

/** Saves the currently-loaded, currently-filtered rows as a JSON file — the
 * fastest way to hand an incident's exact log slice to whoever's debugging it. */
function exportLogs() {
  if (import.meta.server) return
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const blob = new Blob([JSON.stringify(filtered.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `system-log-${stamp}.json`
  a.click()
  URL.revokeObjectURL(url)
}

async function confirmPrune() {
  pruning.value = true
  try {
    const pruned = await store.prune(pruneDays.value)
    pruneOpen.value = false
    notifications.toast(t('logs.pruned', { n: pruned }), { tone: 'ok' })
    await store.load(buildParams())
  } catch (e: any) {
    notifications.toast(errorMessage(e), { tone: 'signal' })
  } finally {
    pruning.value = false
  }
}

watch(() => store.entries.length, scrollToBottom)

onMounted(async () => {
  await store.load(buildParams())
  scrollToBottom()
})
</script>

<template>
  <div class="max-w-5xl mx-auto p-3 sm:p-4 lg:p-6 space-y-4 sm:space-y-5">
    <!-- Header -->
    <header>
      <h1 class="display text-xl sm:text-2xl">{{ t('logs.title') }}</h1>
      <p class="text-xs text-ink-muted mt-1.5 max-w-2xl leading-relaxed">
        {{ t('logs.subtitle') }}
      </p>
    </header>

    <!-- Filter bar -->
    <section class="panel p-3 sm:p-4">
      <div class="flex flex-wrap items-center gap-2">
        <select v-model="level" class="field h-8 text-xs !py-0 !px-2">
          <option value="">{{ t('logs.all') }} {{ t('logs.level') }}</option>
          <option v-for="lv in LEVELS" :key="lv" :value="lv">{{ lv }}</option>
        </select>
        <select v-model="category" class="field h-8 text-xs !py-0 !px-2">
          <option value="">{{ t('logs.all') }} {{ t('logs.category') }}</option>
          <option v-for="cat in CATEGORIES" :key="cat" :value="cat">{{ cat }}</option>
        </select>
        <input
          v-model="source"
          class="field h-8 text-xs !py-0 !px-2 w-36"
          :placeholder="t('logs.source')"
        />
        <input
          v-model="search"
          class="field h-8 text-xs !py-0 !px-2 flex-1 min-w-[120px]"
          :placeholder="t('logs.search')"
        />
        <button
          v-if="hasFilters"
          class="btn-sm btn-ghost"
          @click="clearFilters"
        >
          {{ t('logs.clear') }}
        </button>

        <div class="flex-1" />

        <!-- Status indicators -->
        <div class="flex items-center gap-3">
          <span v-if="store.loading && !store.loaded" class="text-xs text-ink-faint flex items-center gap-1.5">
            <span class="inline-block w-1.5 h-1.5 rounded-full bg-signal animate-pulse" />
            {{ t('logs.connecting') }}
          </span>
          <span
            v-else-if="store.loaded"
            class="text-xs text-ink-faint tabular-nums"
          >
            {{ filtered.length.toLocaleString() }}
            <template v-if="hasFilters">
              / {{ store.entries.length.toLocaleString() }}
            </template>
            {{ t('logs.entries') }}
          </span>

          <label class="flex items-center gap-1.5 text-xs text-ink-faint cursor-pointer select-none">
            <input
              type="checkbox"
              v-model="autoScroll"
              class="checkbox checkbox-xs"
            />
            {{ t('logs.autoScroll') }}
          </label>

          <button
            class="btn-sm btn-ghost"
            :aria-label="t('logs.refresh')"
            :title="t('logs.refresh')"
            @click="store.load(buildParams())"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 2v6h-6" /><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M3 22v-6h6" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
            </svg>
          </button>

          <button
            class="btn-sm btn-ghost"
            :disabled="filtered.length === 0"
            :title="t('logs.export')"
            @click="exportLogs"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span class="hidden sm:inline">{{ t('logs.export') }}</span>
          </button>

          <button class="btn-sm btn-ghost" @click="pruneOpen = true">
            {{ t('logs.prune') }}
          </button>
        </div>
      </div>
    </section>

    <!-- Table -->
    <section class="panel overflow-hidden">
      <div v-if="store.loading && !store.loaded" class="p-8 space-y-2">
        <div v-for="i in 6" :key="i" class="skeleton h-8" />
      </div>
      <div v-else-if="store.error" class="p-8 text-center">
        <div class="alert inline-flex items-center gap-2 px-4 py-2 text-sm">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ store.error }}
        </div>
      </div>
      <div v-else-if="filtered.length === 0" class="p-8 text-center">
        <UiEmpty icon="logs" :title="hasFilters ? t('logs.noMatch') : t('logs.noEntries')" />
      </div>
      <div v-else ref="scrollContainer" class="overflow-y-auto max-h-[calc(100vh-16rem)]">
        <table class="table table-xs w-full">
          <thead class="sticky top-0 bg-panel z-10 border-b border-line">
            <tr>
              <th class="label text-[0.65rem] !py-2.5 w-40">{{ t('logs.time') }}</th>
              <th class="label text-[0.65rem] !py-2.5 w-20">{{ t('logs.level') }}</th>
              <th class="label text-[0.65rem] !py-2.5 w-24">{{ t('logs.category') }}</th>
              <th class="label text-[0.65rem] !py-2.5 w-28">{{ t('logs.source') }}</th>
              <th class="label text-[0.65rem] !py-2.5">{{ t('logs.message') }}</th>
              <th class="w-6"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            <template v-for="entry in filtered" :key="entry.id">
              <tr
                class="hover:bg-raised/50 cursor-pointer transition-colors"
                @click="toggleDetails(entry.id)"
              >
                <td class="num text-xs text-ink-faint whitespace-nowrap tabular-nums">
                  {{ dateTime(entry.timestamp) }}
                </td>
                <td>
                  <UiBadge :tone="levelBadge(entry.level)" class="text-[0.6rem] !px-1.5 !py-0">
                    {{ entry.level }}
                  </UiBadge>
                </td>
                <td class="num text-xs font-mono" :class="categoryColor(entry.category)">
                  {{ entry.category }}
                </td>
                <td class="text-xs text-ink-faint font-mono truncate max-w-[180px]">
                  {{ entry.source }}
                </td>
                <td class="text-sm text-ink">{{ entry.message }}</td>
                <td class="text-ink-faint/50">
                  <svg
                    class="w-3 h-3 transition-transform duration-150"
                    :class="showDetails.has(entry.id) ? 'rotate-90' : ''"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                  ><path d="M9 6l6 6-6 6" /></svg>
                </td>
              </tr>
              <tr v-if="showDetails.has(entry.id)">
                <td colspan="6" class="bg-sunken/50 !py-0">
                  <div class="px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div v-if="entry.account_id != null">
                      <span class="label text-[0.6rem]">{{ t('logs.account') }}</span>
                      <p class="mt-0.5 num text-ink">{{ entry.account_id }}</p>
                    </div>
                    <div v-if="entry.exchange">
                      <span class="label text-[0.6rem]">{{ t('logs.exchange') }}</span>
                      <p class="mt-0.5 num text-ink">{{ entry.exchange }}</p>
                    </div>
                    <div v-if="entry.trade_id != null">
                      <span class="label text-[0.6rem]">{{ t('logs.trade') }}</span>
                      <p class="mt-0.5 num text-ink">{{ entry.trade_id }}</p>
                    </div>
                    <div v-if="entry.error_code">
                      <span class="label text-[0.6rem]">{{ t('logs.code') }}</span>
                      <p class="mt-0.5 num text-ink">{{ entry.error_code }}</p>
                    </div>
                    <div v-if="entry.context" class="col-span-full">
                      <span class="label text-[0.6rem]">{{ t('logs.context') }}</span>
                      <pre class="mt-1 text-[11px] num text-ink-muted whitespace-pre-wrap bg-panel rounded-lg p-2 border border-line">{{ JSON.stringify(entry.context, null, 2) }}</pre>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot v-if="store.hasMore">
            <tr>
              <td colspan="6" class="text-center py-3">
                <button
                  class="btn-sm btn-ghost"
                  :disabled="store.loadingMore"
                  @click="store.loadMore(buildParams())"
                >
                  {{ store.loadingMore ? t('logs.loadingMore') : t('logs.loadMore') }}
                </button>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <!-- Deletion is permanent, so this asks in a dialog rather than firing on
         a single click. -->
    <UiModal v-model="pruneOpen" :title="t('logs.pruneTitle')" size="sm">
      <div class="space-y-3">
        <p class="text-sm leading-relaxed text-ink-muted">
          {{ t('logs.pruneBody', { n: pruneDays }) }}
        </p>
        <label class="block">
          <span class="label text-[0.65rem]">{{ t('logs.pruneDays') }}</span>
          <input
            v-model.number="pruneDays"
            type="number"
            min="1"
            class="field mt-1 w-28"
          />
        </label>
      </div>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" @click="pruneOpen = false">{{ t('common.cancel') }}</button>
          <button class="btn-danger" :disabled="pruning || pruneDays < 1" @click="confirmPrune">
            {{ t('logs.prune') }}
          </button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
