<script setup lang="ts">
/**
 * System log — a tail of every backend log row, filterable and followable.
 *
 * The initial page (and every re-filter) comes from the REST API, which caps and
 * cursor-paginates server-side (`apps/logging/views.py`), so the browser never
 * holds more of the table than it is looking at. New rows arrive over the
 * WebSocket and are prepended by the store.
 *
 * **Newest is at the top**, matching the API's ordering — which is why
 * "follow" scrolls to the *top* of the container rather than the bottom. The
 * previous version scrolled to the bottom on every new entry, i.e. away from
 * the row that had just arrived and down to the oldest one on the page.
 *
 * Following is also *cooperative*: it only ever pulls the view back to the top
 * while the reader is already there. Scrolling down to read something suspends
 * it and says so, because a tail that yanks the viewport is unreadable exactly
 * when it matters.
 *
 * Filters are reactive: each change re-queries the API after a short debounce,
 * so typing in the search box does not fire a request per keystroke. The same
 * predicate is re-applied client-side so a live row that does not match the
 * active filters never flashes into view between one query and the next.
 */
const { t, locale } = useI18n()
const store = useSystemLogStore()
const live = useLiveStore()
const notifications = useNotificationStore()

useHead({ title: t('logs.title') })

const level = ref('')
const category = ref('')
const source = ref('')
const search = ref('')
const requestId = ref('')
const accountId = ref('')

const follow = ref(true)
const atTop = ref(true)
const scrollContainer = ref<HTMLElement | null>(null)
const expanded = ref<Set<number>>(new Set())
const pruneOpen = ref(false)
const pruneDays = ref(30)
const pruning = ref(false)
const copied = ref('')

/** The strongest tone in the palette goes to the level that needs it, and each
 * row is tinted so an ERROR is findable while scrolling, not only readable. */
const LEVEL_TONE: Record<string, { badge: 'ok' | 'signal' | 'short'; row: string }> = {
  INFO: { badge: 'ok', row: '' },
  WARNING: { badge: 'signal', row: 'bg-signal-dim/40' },
  ERROR: { badge: 'short', row: 'bg-short-dim/40' },
  CRITICAL: { badge: 'short', row: 'bg-short-dim/70' },
}

// Category is *not* colour-coded. The old version painted it in raw
// `purple-400` / `cyan-400` / `text-signal`, which broke the token doctrine in
// tailwind.config.ts three ways at once: amber is reserved for failure, cyan is
// the `long` direction, and neither hue was themed — both are washed out on the
// light theme. Levels carry the only colour on the row, and the category cell
// is a filter button instead, which scans faster than seven similar hues.

// Served by the backend rather than duplicated here — two of the seven
// categories the backend writes were missing from the old hardcoded list, so
// rows in them could not be filtered at all.
const levels = computed(() => (store.levels.length ? store.levels : Object.keys(LEVEL_TONE)))
const categories = computed(() => store.categories)

function buildParams(): Record<string, string> {
  const params: Record<string, string> = {}
  if (level.value) params.level = level.value
  if (category.value) params.category = category.value
  if (source.value) params.source = source.value
  if (search.value) params.search = search.value
  if (requestId.value) params.request_id = requestId.value
  if (accountId.value) params.account_id = accountId.value
  return params
}

const filtered = computed(() => {
  let rows = store.newestFirst
  if (level.value) rows = rows.filter((e) => e.level === level.value)
  if (category.value) rows = rows.filter((e) => e.category === category.value)
  if (source.value) {
    const needle = source.value.toLowerCase()
    rows = rows.filter((e) => e.source.toLowerCase().includes(needle))
  }
  if (search.value) {
    const needle = search.value.toLowerCase()
    rows = rows.filter((e) => e.message.toLowerCase().includes(needle))
  }
  if (requestId.value) rows = rows.filter((e) => e.request_id === requestId.value)
  if (accountId.value) rows = rows.filter((e) => String(e.account_id ?? '') === accountId.value)
  return rows
})

const hasFilters = computed(
  () =>
    Boolean(level.value) ||
    Boolean(category.value) ||
    Boolean(source.value) ||
    Boolean(search.value) ||
    Boolean(requestId.value) ||
    Boolean(accountId.value),
)

/** How many of each level are in view, so "is anything wrong" is answered
 * without reading the table. Counted over the filtered rows — a count that
 * disagreed with the rows under it would be worse than no count. */
const tally = computed(() => {
  const counts: Record<string, number> = {}
  for (const entry of filtered.value) counts[entry.level] = (counts[entry.level] ?? 0) + 1
  return counts
})

let debounceTimer: ReturnType<typeof setTimeout> | undefined
watch([level, category, source, search, requestId, accountId], () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => store.load(buildParams()), 250)
})
onBeforeUnmount(() => clearTimeout(debounceTimer))

function clearFilters() {
  level.value = ''
  category.value = ''
  source.value = ''
  search.value = ''
  requestId.value = ''
  accountId.value = ''
}

function toggle(id: number) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

function onScroll() {
  const el = scrollContainer.value
  if (!el) return
  atTop.value = el.scrollTop <= 8
  // Reading older rows suspends the follow; coming back to the top resumes it.
  // The checkbox stays the admin's setting — this is the live state of it.
  if (!atTop.value && follow.value) follow.value = false
  else if (atTop.value && !follow.value) follow.value = true
}

/** Newest-first: "follow the tail" means pin to the *top*. */
function followTail() {
  if (!follow.value) return
  nextTick(() => {
    if (scrollContainer.value) scrollContainer.value.scrollTop = 0
  })
}

// Only the live tail moves the viewport. `loadMore()` also grows this array and
// must never scroll — the admin is reading the rows it appended.
watch(() => store.liveCount, followTail)

/** Seconds and milliseconds, because a fan-out writes several rows inside one
 * second and the shared `dateTime()` helper stops at minutes. The date is only
 * shown when the row is not from today, and the full ISO instant is on the
 * cell's tooltip either way. */
function stamp(value: string): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const time = d.toLocaleTimeString('en-GB', { hour12: false })
  const ms = String(d.getMilliseconds()).padStart(3, '0')
  const sameDay = d.toDateString() === new Date().toDateString()
  const day = sameDay ? '' : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) + ' '
  return `${day}${time}.${ms}`
}

async function copy(text: string) {
  if (!import.meta.client || !navigator.clipboard) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = text
    setTimeout(() => {
      if (copied.value === text) copied.value = ''
    }, 1500)
  } catch {
    notifications.toast(t('logs.copyFailed'), { tone: 'signal' })
  }
}

/** Trace every row written while serving one request. */
function traceRequest(id: string) {
  requestId.value = id
  expanded.value = new Set()
}

/**
 * Saves the currently-loaded, currently-filtered rows — the fastest way to hand
 * an incident's exact slice to whoever is debugging it. The filters and the
 * export time travel with the rows, so the file cannot be misread later as the
 * whole log.
 */
function exportLogs() {
  if (!import.meta.client) return
  const payload = {
    exported_at: new Date().toISOString(),
    filters: buildParams(),
    rows_exported: filtered.value.length,
    rows_loaded: store.entries.length,
    complete: !store.hasMore && !hasFilters.value,
    entries: filtered.value,
  }
  const stampText = new Date().toISOString().replace(/[:.]/g, '-')
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `system-log-${stampText}.json`
  // Attached and revoked on the next tick: Firefox drops a download whose
  // anchor is detached, and Safari cancels one whose URL is revoked mid-write.
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
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

const n = (value: number) => value.toLocaleString(locale.value === 'fa' ? 'fa-IR' : 'en-US')

onMounted(async () => {
  await Promise.all([store.load(buildParams()), store.loadFacets()])
  followTail()
})
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-3 sm:space-y-4">
    <!-- Header -->
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div class="min-w-0">
        <h1 class="display text-xl sm:text-2xl">{{ t('logs.title') }}</h1>
        <p class="text-xs text-ink-muted mt-1.5 max-w-2xl leading-relaxed">
          {{ t('logs.subtitle') }}
        </p>
      </div>
      <!-- "Real-time" is a claim, so the page shows whether the channel that
           makes it true is actually up. Without this a dead socket looked
           exactly like a quiet system. -->
      <UiBadge :tone="live.status === 'live' ? 'ok' : live.status === 'connecting' ? 'neutral' : 'signal'" dot>
        {{ live.status === 'live' ? t('logs.streaming') : t(`common.${live.status}`) }}
      </UiBadge>
    </header>

    <!-- Filter bar -->
    <section class="panel p-2.5 sm:p-3 space-y-2.5">
      <div class="flex flex-wrap items-center gap-2">
        <select v-model="level" class="field h-8 w-auto text-xs !py-0 !px-2" :aria-label="t('logs.level')">
          <option value="">{{ t('logs.allLevels') }}</option>
          <option v-for="lv in levels" :key="lv" :value="lv">{{ lv }}</option>
        </select>
        <select v-model="category" class="field h-8 w-auto text-xs !py-0 !px-2" :aria-label="t('logs.category')">
          <option value="">{{ t('logs.allCategories') }}</option>
          <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
        </select>
        <input
          v-model="source"
          class="field h-8 text-xs !py-0 !px-2 w-32 sm:w-40"
          :aria-label="t('logs.source')"
          :placeholder="t('logs.source')"
        />
        <div class="relative flex-1 min-w-[10rem]">
          <UiIcon
            name="search"
            :size="13"
            class="absolute start-2 top-1/2 -translate-y-1/2 text-ink-faint pointer-events-none"
          />
          <input
            v-model="search"
            class="field h-8 text-xs !py-0 !ps-7 !pe-2"
            :aria-label="t('logs.search')"
            :placeholder="t('logs.search')"
          />
        </div>

        <label class="flex items-center gap-2 text-xs text-ink-muted cursor-pointer select-none ms-auto">
          <!-- Drawn rather than a bare browser checkbox: the old `checkbox
               checkbox-xs` classes were DaisyUI leftovers this project never
               had, so the control rendered as an unstyled system box. -->
          <span
            class="w-8 h-[18px] rounded-full border relative transition-colors shrink-0"
            :class="follow ? 'bg-brand border-brand' : 'bg-raised border-line'"
          >
            <span
              class="absolute top-[2px] start-[2px] w-3 h-3 rounded-full transition-transform"
              :class="follow ? 'bg-white translate-x-[14px] rtl:-translate-x-[14px]' : 'bg-ink-muted'"
            />
          </span>
          <input v-model="follow" type="checkbox" class="sr-only" @change="followTail" />
          {{ t('logs.follow') }}
        </label>

        <button
          class="btn-sm btn-ghost btn-icon"
          :aria-label="t('logs.refresh')"
          :title="t('logs.refresh')"
          :disabled="store.loading"
          @click="store.load(buildParams())"
        >
          <UiIcon name="refresh" :size="14" :class="store.loading ? 'animate-spin' : ''" />
        </button>
        <button
          class="btn-sm btn-ghost"
          :disabled="filtered.length === 0"
          :title="t('logs.exportHint')"
          @click="exportLogs"
        >
          <UiIcon name="download" :size="14" />
          <span class="hidden sm:inline">{{ t('logs.export') }}</span>
        </button>
        <button class="btn-sm btn-danger" @click="pruneOpen = true">
          <UiIcon name="trash" :size="14" />
          <span class="hidden sm:inline">{{ t('logs.prune') }}</span>
        </button>
      </div>

      <!-- Counts and active filters. Every number here says what it counts:
           the old bar showed "N / M entries", where M was only what happened to
           be loaded, read as though it were the size of the table. -->
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-tick text-ink-faint">
        <span v-if="store.loading && !store.loaded" class="flex items-center gap-1.5">
          <UiIcon name="spinner" :size="12" class="animate-spin" />
          {{ t('common.loading') }}
        </span>
        <template v-else>
          <span class="num">{{ t('logs.showing', { n: n(filtered.length) }) }}</span>
          <!-- Only when the two actually differ: "0 shown of 0 loaded" reads as
               a broken counter rather than a filtered view. -->
          <span v-if="store.entries.length !== filtered.length" class="num">
            {{ t('logs.ofLoaded', { n: n(store.entries.length) }) }}
          </span>
          <span v-if="store.hasMore" class="text-ink-muted">{{ t('logs.moreAvailable') }}</span>
          <span v-if="store.liveCount" class="num text-ok">{{ t('logs.sinceLoad', { n: n(store.liveCount) }) }}</span>
          <span v-if="store.trimmed" class="num" :title="t('logs.trimmedHint')">
            {{ t('logs.trimmed', { n: n(store.trimmed) }) }}
          </span>
        </template>

        <span v-for="lv in levels" :key="lv">
          <button
            v-if="tally[lv]"
            class="chip"
            :class="[
              LEVEL_TONE[lv]?.badge === 'short'
                ? 'border-short/40 text-short bg-short-dim'
                : LEVEL_TONE[lv]?.badge === 'signal'
                  ? 'border-signal/50 text-signal bg-signal-dim'
                  : 'border-line text-ink-muted bg-raised',
              level === lv ? 'ring-1 ring-current' : '',
            ]"
            :aria-pressed="level === lv"
            @click="level = level === lv ? '' : lv"
          >
            {{ lv }} <span class="num">{{ n(tally[lv]) }}</span>
          </button>
        </span>

        <div v-if="hasFilters" class="flex items-center gap-1.5 ms-auto">
          <UiBadge v-if="requestId" tone="brand" class="!normal-case">
            {{ t('logs.request') }} <span class="num">{{ requestId }}</span>
          </UiBadge>
          <UiBadge v-if="accountId" tone="brand">
            {{ t('logs.account') }} <span class="num">{{ accountId }}</span>
          </UiBadge>
          <button class="btn-sm btn-quiet" @click="clearFilters">{{ t('logs.clear') }}</button>
        </div>
      </div>
    </section>

    <!-- Table -->
    <section class="panel overflow-hidden">
      <div v-if="store.loading && !store.loaded" class="p-4 space-y-2">
        <div v-for="i in 10" :key="i" class="skeleton h-7" />
      </div>
      <div v-else-if="store.error" class="p-8 flex flex-col items-center gap-3">
        <div class="alert inline-flex items-center gap-2 px-4 py-2 text-sm">
          <UiIcon name="alert" :size="16" class="shrink-0" />
          {{ store.error }}
        </div>
        <button class="btn-sm btn-ghost" @click="store.load(buildParams())">{{ t('common.retry') }}</button>
      </div>
      <div v-else-if="filtered.length === 0" class="py-6">
        <UiEmpty
          icon="logs"
          :title="hasFilters ? t('logs.noMatch') : t('logs.noEntries')"
          :body="hasFilters ? t('logs.noMatchBody') : t('logs.noEntriesBody')"
        >
          <button v-if="hasFilters" class="btn-sm btn-ghost" @click="clearFilters">{{ t('logs.clear') }}</button>
        </UiEmpty>
      </div>
      <div
        v-else
        ref="scrollContainer"
        class="overflow-auto max-h-[calc(100vh-19rem)]"
        @scroll.passive="onScroll"
      >
        <table class="w-full text-xs border-collapse">
          <!-- `bg-panel` on the header cells, not the row: a translucent
               sticky row lets the scrolled rows show through it. -->
          <thead class="sticky top-0 z-10">
            <tr>
              <th class="label bg-panel border-b border-line text-start font-normal px-3 py-2 w-[7.5rem]">
                {{ t('logs.time') }}
              </th>
              <th class="label bg-panel border-b border-line text-start font-normal py-2 w-20">
                {{ t('logs.level') }}
              </th>
              <th
                class="label bg-panel border-b border-line text-start font-normal py-2 w-28
                       hidden sm:table-cell"
              >
                {{ t('logs.category') }}
              </th>
              <th class="label bg-panel border-b border-line text-start font-normal py-2 w-44 hidden md:table-cell">
                {{ t('logs.source') }}
              </th>
              <th class="label bg-panel border-b border-line text-start font-normal py-2">
                {{ t('logs.message') }}
              </th>
              <th class="bg-panel border-b border-line w-8">
                <span class="sr-only">{{ t('logs.details') }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="entry in filtered" :key="entry.id">
              <tr
                class="border-b border-line/60 hover:bg-raised/60 cursor-pointer transition-colors align-top"
                :class="LEVEL_TONE[entry.level]?.row"
                :aria-expanded="expanded.has(entry.id)"
                @click="toggle(entry.id)"
              >
                <td class="num text-ink-faint whitespace-nowrap px-3 py-1.5" :title="entry.timestamp">
                  {{ stamp(entry.timestamp) }}
                </td>
                <td class="py-1.5">
                  <UiBadge :tone="LEVEL_TONE[entry.level]?.badge ?? 'neutral'" class="!px-1.5 !py-0">
                    {{ entry.level }}
                  </UiBadge>
                </td>
                <td class="num py-1.5 hidden sm:table-cell">
                  <button
                    class="text-ink-muted hover:text-ink transition-colors"
                    :class="category === entry.category ? 'text-brand' : ''"
                    :title="t('logs.filterCategory')"
                    @click.stop="category = category === entry.category ? '' : entry.category"
                  >
                    {{ entry.category }}
                  </button>
                </td>
                <td class="num text-ink-faint py-1.5 hidden md:table-cell">
                  <span class="block truncate max-w-[11rem]" :title="entry.source">{{ entry.source }}</span>
                </td>
                <td class="text-ink py-1.5 pe-2 w-full max-w-0">
                  <span class="[overflow-wrap:anywhere]">{{ entry.message }}</span>
                  <!-- The identifiers a row carries, inline: they are the
                       reason to open a row, so hiding all of them behind
                       opening it made every ERROR a two-click read. -->
                  <span class="inline-flex flex-wrap items-center gap-1.5 ms-2 align-middle">
                    <span v-if="entry.error_code" class="chip border-short/40 text-short bg-short-dim !normal-case">
                      {{ entry.error_code }}
                    </span>
                    <!-- On a phone these wrap one per line and triple the row
                         height, so below `sm` the identifiers live in the
                         expanded panel only. The error code stays: it is the
                         one that decides whether the row needs opening. -->
                    <span v-if="entry.account_id != null" class="chip border-line text-ink-muted bg-raised hidden sm:inline-flex">
                      {{ t('logs.account') }} <span class="num">{{ entry.account_id }}</span>
                    </span>
                    <span v-if="entry.trade_id != null" class="chip border-line text-ink-muted bg-raised hidden sm:inline-flex">
                      {{ t('logs.trade') }} <span class="num">{{ entry.trade_id }}</span>
                    </span>
                    <span v-if="entry.exchange" class="chip border-line text-ink-muted bg-raised hidden sm:inline-flex">
                      {{ exchangeLabel(entry.exchange) }}
                    </span>
                  </span>
                </td>
                <td class="text-ink-faint/60 py-1.5 pe-2">
                  <UiIcon
                    name="chevronRight"
                    :size="12"
                    class="transition-transform duration-150 rtl:rotate-180"
                    :class="expanded.has(entry.id) ? 'rotate-90 rtl:rotate-90' : ''"
                  />
                </td>
              </tr>
              <tr v-if="expanded.has(entry.id)" class="border-b border-line/60">
                <td colspan="6" class="bg-sunken/60 !py-0">
                  <div class="px-3 py-3 space-y-3">
                    <dl class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div class="sm:hidden">
                        <dt class="label">{{ t('logs.category') }}</dt>
                        <dd class="mt-0.5 num text-ink">{{ entry.category }}</dd>
                      </div>
                      <div class="md:hidden">
                        <dt class="label">{{ t('logs.source') }}</dt>
                        <dd class="mt-0.5 num text-ink break-all">{{ entry.source }}</dd>
                      </div>
                      <div v-if="entry.account_id != null">
                        <dt class="label">{{ t('logs.account') }}</dt>
                        <dd class="mt-0.5 num text-ink">
                          <button class="hover:text-brand" @click.stop="accountId = String(entry.account_id)">
                            #{{ entry.account_id }}
                          </button>
                        </dd>
                      </div>
                      <div v-if="entry.exchange">
                        <dt class="label">{{ t('logs.exchange') }}</dt>
                        <dd class="mt-0.5 num text-ink">{{ exchangeLabel(entry.exchange) }}</dd>
                      </div>
                      <div v-if="entry.trade_id != null">
                        <dt class="label">{{ t('logs.trade') }}</dt>
                        <dd class="mt-0.5 num text-ink">#{{ entry.trade_id }}</dd>
                      </div>
                      <div v-if="entry.error_code">
                        <dt class="label">{{ t('logs.code') }}</dt>
                        <dd class="mt-0.5 num text-short">{{ entry.error_code }}</dd>
                      </div>
                      <div v-if="entry.request_id">
                        <dt class="label">{{ t('logs.request') }}</dt>
                        <dd class="mt-0.5 flex items-center gap-1.5">
                          <button
                            class="num text-ink hover:text-brand"
                            :title="t('logs.traceHint')"
                            @click.stop="traceRequest(entry.request_id!)"
                          >
                            {{ entry.request_id }}
                          </button>
                        </dd>
                      </div>
                      <div>
                        <dt class="label">{{ t('logs.time') }}</dt>
                        <dd class="mt-0.5 num text-ink-muted">{{ entry.timestamp }}</dd>
                      </div>
                    </dl>

                    <div v-if="entry.context">
                      <dt class="label">{{ t('logs.context') }}</dt>
                      <pre
                        class="mt-1 text-[11px] num text-ink-muted whitespace-pre-wrap break-all
                               bg-panel rounded-lg p-2 border border-line max-h-64 overflow-auto"
                      >{{ JSON.stringify(entry.context, null, 2) }}</pre>
                    </div>

                    <button class="btn-sm btn-ghost" @click.stop="copy(JSON.stringify(entry, null, 2))">
                      <UiIcon name="check" v-if="copied === JSON.stringify(entry, null, 2)" :size="13" />
                      {{ copied === JSON.stringify(entry, null, 2) ? t('logs.copied') : t('logs.copyRow') }}
                    </button>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>

        <div v-if="store.hasMore" class="p-3 text-center border-t border-line">
          <button class="btn-sm btn-ghost" :disabled="store.loadingMore" @click="store.loadMore(buildParams())">
            <UiIcon v-if="store.loadingMore" name="spinner" :size="13" class="animate-spin" />
            {{ store.loadingMore ? t('logs.loadingMore') : t('logs.loadMore') }}
          </button>
        </div>
      </div>
    </section>

    <!-- A suspended tail has to say so, or a quiet table reads as a quiet
         system. Placed outside the scroller so scrolling cannot hide it. -->
    <button
      v-if="store.loaded && !follow && store.liveCount > 0"
      class="btn-sm btn-ghost mx-auto flex"
      @click="((follow = true), followTail())"
    >
      <UiIcon name="chevronRight" :size="13" class="-rotate-90" />
      {{ t('logs.resumeFollow') }}
    </button>

    <!-- Deletion is permanent, so this asks in a dialog rather than firing on
         a single click. -->
    <UiModal v-model="pruneOpen" :title="t('logs.pruneTitle')" size="sm">
      <div class="space-y-3">
        <p class="text-sm leading-relaxed text-ink-muted">
          {{ t('logs.pruneBody', { n: pruneDays }) }}
        </p>
        <label class="block">
          <span class="label">{{ t('logs.pruneDays') }}</span>
          <input v-model.number="pruneDays" type="number" min="1" step="1" class="field mt-1 w-28" />
        </label>
        <p v-if="!(pruneDays >= 1)" class="text-xs text-signal">{{ t('logs.pruneInvalid') }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <button class="btn-ghost" :disabled="pruning" @click="pruneOpen = false">
            {{ t('common.cancel') }}
          </button>
          <button class="btn-danger" :disabled="pruning || !(pruneDays >= 1)" @click="confirmPrune">
            <UiIcon v-if="pruning" name="spinner" :size="13" class="animate-spin" />
            {{ t('logs.prune') }}
          </button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
