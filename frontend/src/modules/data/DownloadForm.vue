<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHistoryStore } from '../../stores/history'
import { useHealthStore } from '../../stores/health'
import { useToast } from '../../composables/useToast'

const emit = defineEmits<{ submitted: [] }>()

const { t } = useI18n()
const history = useHistoryStore()
const healthStore = useHealthStore()
const toast = useToast()

const FALLBACK_TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w']

const DATA_TYPES = ['ohlcv', 'funding', 'open_interest'] as const

const network = ref('mainnet')
const startDate = ref('2023-01-01')
const endDate = ref('')
const coinSearch = ref('')
const selectedCoins = ref<string[]>(['BTC'])
const selectedIntervals = ref<string[]>(['1h'])
const selectedDataTypes = ref<string[]>(['ohlcv'])
const submitting = ref(false)

const ohlcvSelected = computed(() => selectedDataTypes.value.includes('ohlcv'))

function dataTypeLabel(dt: string) {
  if (dt === 'ohlcv') return 'OHLCV'
  if (dt === 'funding') return t('data.dataTypeFunding')
  return t('data.dataTypeOpenInterest')
}

const availableIntervals = computed(() => {
  const fromApi = history.markets?.intervals
  return fromApi?.length ? fromApi : FALLBACK_TIMEFRAMES
})

const availableCoins = computed(() => {
  const coins = history.markets?.coins ?? []
  const q = coinSearch.value.trim().toUpperCase()
  if (!q) return coins.slice(0, 50)
  return coins.filter((c) => c.includes(q)).slice(0, 50)
})

const marketsError = computed(() => history.marketsError ?? history.markets?.error ?? null)

const celeryOffline = computed(() => healthStore.health?.celery?.status !== 'ok')

onMounted(async () => {
  try {
    await history.fetchMarkets(network.value)
  } catch {
    /* marketsError surfaced in UI */
  }
  void healthStore.fetchHealth()
})

watch(network, (net) => {
  void history.fetchMarkets(net)
})

function toggleCoin(coin: string) {
  if (selectedCoins.value.includes(coin)) {
    selectedCoins.value = selectedCoins.value.filter((c) => c !== coin)
  } else {
    selectedCoins.value = [...selectedCoins.value, coin]
  }
}

function removeCoin(coin: string) {
  selectedCoins.value = selectedCoins.value.filter((c) => c !== coin)
}

function toggleInterval(iv: string) {
  if (selectedIntervals.value.includes(iv)) {
    selectedIntervals.value = selectedIntervals.value.filter((x) => x !== iv)
  } else {
    selectedIntervals.value = [...selectedIntervals.value, iv]
  }
}

function toggleDataType(dt: string) {
  if (selectedDataTypes.value.includes(dt)) {
    selectedDataTypes.value = selectedDataTypes.value.filter((x) => x !== dt)
  } else {
    selectedDataTypes.value = [...selectedDataTypes.value, dt]
  }
}

async function submit() {
  if (celeryOffline.value) {
    toast.show(t('data.celeryOffline'), 'error')
    return
  }
  if (!selectedCoins.value.length || !selectedDataTypes.value.length) {
    toast.show(t('data.selectRequired'), 'error')
    return
  }
  if (ohlcvSelected.value && !selectedIntervals.value.length) {
    toast.show(t('data.selectRequired'), 'error')
    return
  }
  submitting.value = true
  try {
    await history.startDownload({
      coins: selectedCoins.value,
      intervals: selectedIntervals.value,
      dataTypes: selectedDataTypes.value,
      start: startDate.value,
      end: endDate.value || undefined,
      network: network.value,
    })
    toast.show(t('data.downloadQueued'), 'success')
    emit('submitted')
  } catch {
    toast.show(history.error === 'Celery worker is offline' ? t('data.celeryOffline') : t('data.downloadFailed'), 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="rounded-xl border border-zinc-800 p-4 space-y-4">
    <h3 class="text-sm font-medium text-zinc-200">{{ t('data.downloadTitle') }}</h3>

    <div
      v-if="marketsError"
      class="rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-xs text-red-300"
    >
      {{ t('data.marketsError') }}: {{ marketsError }}
    </div>

    <div class="flex gap-3 flex-wrap">
      <label class="text-xs text-zinc-500">
        {{ t('data.network') }}
        <select v-model="network" class="mt-1 block rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200">
          <option value="mainnet">mainnet</option>
          <option value="testnet">testnet</option>
        </select>
      </label>
      <label class="text-xs text-zinc-500">
        {{ t('data.startDate') }}
        <input v-model="startDate" type="date" class="mt-1 block rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200" />
      </label>
      <label class="text-xs text-zinc-500">
        {{ t('data.endDate') }}
        <input v-model="endDate" type="date" class="mt-1 block rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200" />
      </label>
    </div>

    <div>
      <label class="text-xs text-zinc-500">{{ t('data.coins') }}</label>
      <input
        v-model="coinSearch"
        type="text"
        :placeholder="t('data.searchCoins')"
        class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-200"
      />
      <div class="mt-2 flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
        <button
          v-for="coin in availableCoins"
          :key="coin"
          type="button"
          class="rounded px-2 py-0.5 text-xs transition-colors"
          :class="selectedCoins.includes(coin) ? 'bg-emerald-900 text-emerald-300' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'"
          @click="toggleCoin(coin)"
        >
          {{ coin }}
        </button>
      </div>
      <div v-if="selectedCoins.length" class="mt-2">
        <p class="text-[10px] text-zinc-500 mb-1">{{ t('data.selectedCoins') }}</p>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="c in selectedCoins"
            :key="c"
            type="button"
            class="inline-flex items-center gap-1 rounded bg-emerald-900/70 px-2 py-0.5 text-xs text-emerald-300 hover:bg-emerald-800/80"
            :title="t('data.removeCoin', { coin: c })"
            @click="removeCoin(c)"
          >
            <span>{{ c }}</span>
            <span class="text-emerald-400/90 leading-none" aria-hidden="true">×</span>
          </button>
        </div>
      </div>
    </div>

    <div>
      <label class="text-xs text-zinc-500">{{ t('data.dataTypes') }}</label>
      <div class="mt-2 flex flex-wrap gap-1.5">
        <button
          v-for="dt in DATA_TYPES"
          :key="dt"
          type="button"
          class="rounded px-2 py-0.5 text-xs transition-colors"
          :class="selectedDataTypes.includes(dt) ? 'bg-emerald-900 text-emerald-300' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'"
          @click="toggleDataType(dt)"
        >
          {{ dataTypeLabel(dt) }}
        </button>
        <button
          type="button"
          disabled
          class="rounded px-2 py-0.5 text-xs bg-zinc-900 text-zinc-600 cursor-not-allowed"
          :title="t('data.tradesUnavailable')"
        >
          {{ t('data.dataTypeTrades') }}
        </button>
      </div>
    </div>

    <div :class="{ 'opacity-40 pointer-events-none': !ohlcvSelected }">
      <label class="text-xs text-zinc-500">{{ t('data.intervals') }}</label>
      <div class="mt-2 flex flex-wrap gap-1.5">
        <button
          v-for="iv in availableIntervals"
          :key="iv"
          type="button"
          :disabled="!ohlcvSelected"
          class="rounded px-2 py-0.5 text-xs transition-colors"
          :class="selectedIntervals.includes(iv) ? 'bg-emerald-900 text-emerald-300' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'"
          @click="toggleInterval(iv)"
        >
          {{ iv }}
        </button>
      </div>
    </div>

    <button
      type="button"
      class="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
      :disabled="submitting || celeryOffline"
      :title="celeryOffline ? t('data.celeryOffline') : undefined"
      @click="submit"
    >
      {{ submitting ? t('data.downloading') : t('data.startDownload') }}
    </button>
  </div>
</template>
