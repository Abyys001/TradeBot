<script setup lang="ts">
/**
 * Pick a pair by typing at it.
 *
 * The backtest form used to be a bare text input, which means the operator has
 * to already know how the venue spells the pair — `BTCUSDT` or `BTCUSDC`,
 * `1000PEPE` or `PEPE` — and a typo comes back as "no bars for this window"
 * two minutes into a download.
 *
 * Three sources, in this order, and the order is the point:
 *
 *   **The pinned pairs** (`PINNED_SYMBOLS`) are code, always present, and head
 *   the list whether or not the catalogue has answered. Same rule as the
 *   terminal's picker: a slow `/symbols/` cannot make one of them vanish.
 *
 *   **The catalogue** is what the connected exchanges actually list. It arrives
 *   with a connected account and can legitimately be empty on a fresh install.
 *
 *   **Whatever was typed** is still accepted. Exchanges list far more pairs
 *   than any catalogue sync curates, and refusing a pair because this panel has
 *   not heard of it would be the picker deciding what can be traded.
 */
import { PINNED_SYMBOLS } from '~/stores/market'

const model = defineModel<string>({ required: true })
withDefaults(defineProps<{ disabled?: boolean; placeholder?: string }>(), { disabled: false })

const { t } = useI18n()
const api = useApi()

const open = ref(false)
const query = ref('')
const catalogue = ref<SymbolInfo[]>([])
const loading = ref(false)
const box = ref<HTMLElement | null>(null)

/** Split `BTCUSDT` for a row that has no catalogue entry to read base/quote off. */
const QUOTES = ['USDT', 'USDC', 'USD', 'BTC', 'ETH', 'EUR', 'TRY', 'DAI', 'FDUSD']
function split(symbol: string): { base: string; quote: string } {
  const upper = symbol.toUpperCase()
  const quote = QUOTES.find((q) => upper.endsWith(q) && upper.length > q.length)
  return quote ? { base: upper.slice(0, -quote.length), quote } : { base: upper, quote: '' }
}

const options = computed(() => {
  const needle = query.value.trim().toUpperCase()
  const known = new Map(catalogue.value.map((row) => [row.symbol, row]))
  const hit = (row: { symbol: string; base: string }) =>
    !needle || row.symbol.includes(needle) || row.base.includes(needle)

  const pinned = PINNED_SYMBOLS.map(
    (symbol) => known.get(symbol) ?? { symbol, ...split(symbol) },
  ).filter(hit)
  const rest = catalogue.value
    .filter((row) => !PINNED_SYMBOLS.includes(row.symbol) && hit(row))
    .slice(0, 120)
  return { pinned, rest }
})

/** True when what was typed matches nothing listed — offered as itself. */
const freeText = computed(() => {
  const typed = query.value.trim().toUpperCase()
  if (!typed) return ''
  const listed = [...options.value.pinned, ...options.value.rest]
  return listed.some((row) => row.symbol === typed) ? '' : typed
})

async function load() {
  if (catalogue.value.length || loading.value) return
  loading.value = true
  try {
    catalogue.value = (await api.symbols()).symbols
  } catch {
    // A 409 here means nothing has been downloaded yet, which is a normal
    // state on a fresh install — the pinned list and free text still work.
    catalogue.value = []
  } finally {
    loading.value = false
  }
}

function choose(symbol: string) {
  model.value = symbol.toUpperCase()
  open.value = false
  query.value = ''
}

async function toggle() {
  open.value = !open.value
  if (open.value) await load()
}

/** Escape closes; the click-away layer below handles the pointer case. */
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}
</script>

<template>
  <div ref="box" class="relative" @keydown="onKeydown">
    <button
      type="button"
      class="field flex items-center gap-2 text-start"
      :disabled="disabled"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="toggle"
    >
      <span class="num truncate flex-1">{{ model || placeholder || '—' }}</span>
      <UiIcon name="chevronDown" :size="14" class="text-ink-faint shrink-0" />
    </button>

    <div v-if="open" class="fixed inset-0 z-30" @click="open = false" />

    <div
      v-if="open"
      class="absolute z-40 mt-1 w-[min(20rem,calc(100vw-2rem))] panel shadow-lift p-2
             max-h-80 overflow-y-auto"
      role="listbox"
    >
      <input
        v-model="query"
        class="field text-xs py-1.5"
        :placeholder="t('terminal.searchSymbol')"
        spellcheck="false"
        autofocus
        @keyup.enter="freeText && choose(freeText)"
      />

      <p v-if="loading" class="text-tick text-ink-faint px-2 py-2">{{ t('common.loading') }}</p>

      <ul class="mt-1.5">
        <li v-if="freeText">
          <button
            type="button"
            class="w-full text-start px-2 py-1.5 rounded-md text-xs hover:bg-raised
                   flex items-center gap-2 text-brand"
            @click="choose(freeText)"
          >
            <UiIcon name="plus" :size="12" />
            <span class="num font-medium">{{ freeText }}</span>
            <span class="text-ink-faint ms-auto">{{ t('bots.useTyped') }}</span>
          </button>
        </li>
        <li v-if="freeText && (options.pinned.length || options.rest.length)"
            class="my-1 border-t border-line" />

        <li v-for="option in options.pinned" :key="`p-${option.symbol}`">
          <button
            type="button"
            class="w-full text-start px-2 py-1.5 rounded-md text-xs hover:bg-raised
                   flex items-center gap-2"
            :class="option.symbol === model ? 'text-brand' : ''"
            @click="choose(option.symbol)"
          >
            <span class="num font-medium">{{ option.base }}</span>
            <span class="text-ink-faint">{{ option.quote }}</span>
          </button>
        </li>
        <li v-if="options.pinned.length && options.rest.length" class="my-1 border-t border-line" />

        <li v-for="option in options.rest" :key="option.symbol">
          <button
            type="button"
            class="w-full text-start px-2 py-1.5 rounded-md text-xs hover:bg-raised
                   flex items-center gap-2"
            :class="option.symbol === model ? 'text-brand' : ''"
            @click="choose(option.symbol)"
          >
            <span class="num font-medium">{{ option.base }}</span>
            <span class="text-ink-faint">{{ option.quote }}</span>
          </button>
        </li>

        <li
          v-if="!loading && !options.pinned.length && !options.rest.length && !freeText"
          class="px-2 py-2 text-tick text-ink-faint"
        >
          {{ t('bots.noSymbolsYet') }}
        </li>
      </ul>
    </div>
  </div>
</template>
