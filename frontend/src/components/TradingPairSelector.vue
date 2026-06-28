<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHistoryStore } from '../stores/history'
import {
  POPULAR_COINS,
  buildPairOptions,
  coinToPair,
  fallbackPairs,
  filterPairs,
  normalizePair,
  pairToCoin,
} from '../utils/tradingPairs'

const props = withDefaults(
  defineProps<{
    multiple?: boolean
    network?: string
    placeholder?: string
    disabled?: boolean
    /** Coins with downloaded OHLCV for the active timeframe (shows green dot in list). */
    markedCoins?: Set<string>
  }>(),
  {
    multiple: false,
    network: 'mainnet',
    disabled: false,
  },
)

const model = defineModel<string | string[]>({ required: true })

const { t } = useI18n()
const history = useHistoryStore()

const rootEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLInputElement | null>(null)
const search = ref('')
const open = ref(false)
const highlightIndex = ref(0)
const loadingMarkets = ref(false)
const dropdownStyle = ref<{ top: string; left: string; width: string }>({
  top: '0px',
  left: '0px',
  width: '0px',
})

const selectedPairs = computed<string[]>(() => {
  if (props.multiple) {
    return Array.isArray(model.value) ? model.value.map((p) => normalizePair(p)) : []
  }
  return typeof model.value === 'string' && model.value ? [normalizePair(model.value)] : []
})

const allPairs = computed(() => {
  const coins = history.markets?.coins?.length ? history.markets.coins : []
  if (coins.length) return buildPairOptions(coins)
  return fallbackPairs()
})

const filteredPairs = computed(() => filterPairs(allPairs.value, search.value))

const displayValue = computed(() => {
  if (props.multiple || open.value) return search.value
  return typeof model.value === 'string' ? model.value : ''
})

const inputPlaceholder = computed(() => {
  if (props.placeholder) return props.placeholder
  if (props.multiple && selectedPairs.value.length) return t('strategy.searchPairs')
  return t('strategy.searchPairs')
})

const marketsHint = computed(() => {
  if (loadingMarkets.value) return t('strategy.pairsLoading')
  if (history.marketsError) return t('strategy.pairsFallback')
  return ''
})

function hasStoredData(pair: string): boolean {
  if (!props.markedCoins?.size) return false
  return props.markedCoins.has(pairToCoin(pair))
}

async function loadMarkets() {
  if (history.markets?.network === props.network && history.markets.coins?.length) return
  loadingMarkets.value = true
  try {
    await history.fetchMarkets(props.network)
  } catch {
    /* fallback list used */
  } finally {
    loadingMarkets.value = false
  }
}

async function positionDropdown() {
  await nextTick()
  const el = rootEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  dropdownStyle.value = {
    top: `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
  }
}

async function openDropdown() {
  if (props.disabled) return
  open.value = true
  highlightIndex.value = 0
  if (!props.multiple && typeof model.value === 'string' && model.value) {
    search.value = pairToCoin(model.value)
  }
  await positionDropdown()
}

function closeDropdown() {
  open.value = false
  search.value = ''
  highlightIndex.value = 0
}

function selectPair(pair: string) {
  const normalized = normalizePair(pair)
  if (props.multiple) {
    const current = Array.isArray(model.value) ? [...model.value.map((p) => normalizePair(p))] : []
    if (!current.includes(normalized)) {
      model.value = [...current, normalized]
    }
    search.value = ''
    highlightIndex.value = 0
    void positionDropdown()
    inputEl.value?.focus()
    return
  }
  model.value = normalized
  closeDropdown()
}

function removePair(pair: string) {
  if (!props.multiple || !Array.isArray(model.value)) return
  model.value = model.value.filter((p) => normalizePair(p) !== normalizePair(pair))
}

function addFromSearch() {
  const raw = search.value.trim()
  if (!raw) return
  selectPair(normalizePair(raw))
}

function onInput(e: Event) {
  search.value = (e.target as HTMLInputElement).value
  if (!open.value) open.value = true
  highlightIndex.value = 0
  void positionDropdown()
}

function onKeydown(e: KeyboardEvent) {
  if (props.disabled) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (!open.value) void openDropdown()
    highlightIndex.value = Math.min(highlightIndex.value + 1, Math.max(filteredPairs.value.length - 1, 0))
    return
  }

  if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlightIndex.value = Math.max(highlightIndex.value - 1, 0)
    return
  }

  if (e.key === 'Enter') {
    e.preventDefault()
    const highlighted = filteredPairs.value[highlightIndex.value]
    if (highlighted) {
      selectPair(highlighted)
      return
    }
    addFromSearch()
    return
  }

  if (e.key === 'Escape') {
    e.preventDefault()
    closeDropdown()
    return
  }

  if (e.key === 'Backspace' && props.multiple && !search.value && Array.isArray(model.value) && model.value.length) {
    model.value = model.value.slice(0, -1)
  }
}

function onDocumentClick(e: MouseEvent) {
  const target = e.target as Node
  if (rootEl.value?.contains(target)) return
  const panel = document.getElementById('trading-pair-dropdown-panel')
  if (panel?.contains(target)) return
  closeDropdown()
}

function onScrollOrResize() {
  if (open.value) void positionDropdown()
}

watch(
  () => props.network,
  () => {
    void loadMarkets()
  },
)

watch(open, (isOpen) => {
  if (isOpen) void positionDropdown()
})

onMounted(() => {
  void loadMarkets()
  document.addEventListener('click', onDocumentClick, true)
  window.addEventListener('resize', onScrollOrResize)
  window.addEventListener('scroll', onScrollOrResize, true)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick, true)
  window.removeEventListener('resize', onScrollOrResize)
  window.removeEventListener('scroll', onScrollOrResize, true)
})
</script>

<template>
  <div ref="rootEl" class="relative">
    <div
      v-if="multiple && selectedPairs.length"
      class="mb-2 flex flex-wrap gap-1.5"
    >
      <button
        v-for="pair in selectedPairs"
        :key="pair"
        type="button"
        class="inline-flex items-center gap-1 rounded-md border border-emerald-700/50 bg-emerald-950/60 px-2 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-900/70"
        :disabled="disabled"
        @click="removePair(pair)"
      >
        <span dir="ltr">{{ pair }}</span>
        <span class="leading-none text-emerald-400/90" aria-hidden="true">×</span>
      </button>
    </div>

    <div
      class="flex items-stretch overflow-hidden rounded-lg border transition-colors"
      :class="open ? 'border-emerald-600 ring-1 ring-emerald-600/40' : 'border-zinc-600'"
    >
      <input
        ref="inputEl"
        :value="displayValue"
        type="text"
        dir="ltr"
        autocomplete="off"
        spellcheck="false"
        class="min-w-0 flex-1 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 disabled:opacity-50"
        :placeholder="inputPlaceholder"
        :disabled="disabled"
        @focus="openDropdown"
        @input="onInput"
        @keydown="onKeydown"
      />
      <button
        type="button"
        class="flex shrink-0 items-center gap-1 border-s border-zinc-700 bg-zinc-900 px-3 text-xs text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        :disabled="disabled"
        @click="open ? closeDropdown() : openDropdown()"
      >
        <span v-if="multiple && selectedPairs.length" class="rounded bg-emerald-900/80 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
          {{ selectedPairs.length }}
        </span>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 transition-transform" :class="{ 'rotate-180': open }" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z" clip-rule="evenodd" />
        </svg>
      </button>
    </div>

    <p v-if="marketsHint" class="mt-1 text-[10px] text-zinc-500">{{ marketsHint }}</p>

    <Teleport to="body">
      <div
        v-if="open"
        id="trading-pair-dropdown-panel"
        class="fixed z-[9999] overflow-hidden rounded-lg border border-zinc-600 bg-zinc-950 shadow-2xl shadow-black/50"
        :style="dropdownStyle"
      >
        <div class="border-b border-zinc-800 bg-zinc-900/80 px-3 py-2">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{{ t('strategy.popularPairs') }}</p>
          <div class="mt-1.5 flex flex-wrap gap-1">
            <button
              v-for="coin in POPULAR_COINS"
              :key="coin"
              type="button"
              class="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors"
              :class="selectedPairs.includes(coinToPair(coin)) ? 'bg-emerald-900 text-emerald-300' : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'"
              @mousedown.prevent="selectPair(coinToPair(coin))"
            >
              <span v-if="hasStoredData(coinToPair(coin))" class="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              {{ coinToPair(coin) }}
            </button>
          </div>
        </div>

        <ul class="max-h-56 overflow-y-auto py-1">
          <li v-if="!filteredPairs.length" class="px-3 py-3 text-xs text-zinc-500">
            {{ t('strategy.noPairsFound') }}
          </li>
          <li v-for="(pair, idx) in filteredPairs" :key="pair">
            <button
              type="button"
              class="flex w-full items-center justify-between px-3 py-2 text-start text-sm transition-colors"
              :class="idx === highlightIndex ? 'bg-emerald-950/50 text-emerald-100' : 'text-zinc-300 hover:bg-zinc-900'"
              @mousedown.prevent="selectPair(pair)"
            >
              <span class="flex items-center gap-2">
                <span
                  v-if="markedCoins?.size"
                  class="h-1.5 w-1.5 shrink-0 rounded-full"
                  :class="hasStoredData(pair) ? 'bg-emerald-400' : 'bg-zinc-600'"
                  :title="hasStoredData(pair) ? t('backtest.dataReady') : t('backtest.dataMissing')"
                />
                <span dir="ltr" class="font-medium">{{ pair }}</span>
              </span>
              <span v-if="selectedPairs.includes(pair)" class="text-[10px] uppercase text-emerald-400">
                {{ t('strategy.pairSelected') }}
              </span>
              <span v-else-if="hasStoredData(pair)" class="text-[10px] text-emerald-500/80">
                {{ t('backtest.dataReady') }}
              </span>
            </button>
          </li>
        </ul>
      </div>
    </Teleport>
  </div>
</template>
