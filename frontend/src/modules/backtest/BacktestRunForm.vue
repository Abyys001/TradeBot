<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../stores/strategy'
import { useBacktestStore } from '../../stores/backtest'
import { useHistoryStore } from '../../stores/history'
import { useToast } from '../../composables/useToast'
import ProgressBar from '../../components/ProgressBar.vue'
import TradingPairSelector from '../../components/TradingPairSelector.vue'
import { coinToPair, pairToCoin } from '../../utils/tradingPairs'

const props = defineProps<{ strategyId: number }>()

const emit = defineEmits<{ selectBacktest: [id: number | null] }>()

const route = useRoute()
const { t } = useI18n()
const strategyStore = useStrategyStore()
const backtestStore = useBacktestStore()
const historyStore = useHistoryStore()
const toast = useToast()

const FALLBACK_TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d']
const running = ref(false)
const downloading = ref(false)
const batchIds = ref<number[]>([])
const selectedPair = ref('BTC-USDT')
const selectedInterval = ref('1h')
const runAllPairs = ref(false)
const showQuickMenu = ref(false)
const strategy = computed(() => strategyStore.strategies.find((s) => s.id === props.strategyId) ?? null)

const strategySymbols = computed(() => {
  const s = strategy.value
  if (!s) return []
  const symbols = s.live_config?.symbols?.length ? s.live_config.symbols : [s.symbol]
  return symbols.map((x) => x.toUpperCase().replace(/-.*$/, ''))
})

const strategyIntervals = computed(() => {
  const s = strategy.value
  if (!s) return ['1h']
  return s.live_config?.timeframes?.length
    ? [...s.live_config.timeframes]
    : [s.timeframe || '1h']
})

const selectedCoins = ref<string[]>([])
const selectedIntervals = ref<string[]>([])
const selectedNetwork = ref('mainnet')
const startDate = ref('')
const endDate = ref('')
const initialCapital = ref<number>(10_000)

const strategyPairLabels = computed(() =>
  strategySymbols.value.map((coin) => coinToPair(coin)),
)

const storedCoinsForInterval = computed(() => {
  const iv = selectedInterval.value.toLowerCase()
  const net = selectedNetwork.value
  const coins = new Set<string>()
  for (const ds of historyStore.datasets) {
    if (
      ds.interval.toLowerCase() === iv &&
      (ds.network || 'mainnet') === net &&
      (ds.kind === 'ohlcv' || !ds.kind)
    ) {
      coins.add(ds.coin.toUpperCase())
    }
  }
  return coins
})

const selectedCoinHasData = computed(() => {
  if (runAllPairs.value) return missingList.value.length === 0
  const coin = pairToCoin(selectedPair.value)
  return historyStore.hasDataset(coin, selectedInterval.value, selectedNetwork.value)
})

const activeDownload = computed(() =>
  historyStore.activeDownloads.find((d) => d.network === selectedNetwork.value),
)

const availableIntervals = computed(() => {
  const fromApi = historyStore.markets?.intervals
  const base = fromApi?.length ? fromApi : FALLBACK_TIMEFRAMES
  const merged = new Set([...base, ...strategyIntervals.value])
  return [...merged]
})

const anyActive = computed(() =>
  backtestStore.forStrategy(props.strategyId).some((b) => b.status === 'pending' || b.status === 'running'),
)

const validationBlocked = computed(() => strategy.value?.validation_status === 'error')

const batchProgress = computed(() => {
  if (!batchIds.value.length) return null
  const runs = batchIds.value
    .map((id) => backtestStore.backtests.find((b) => b.id === id))
    .filter((b): b is NonNullable<typeof b> => Boolean(b))
  const finished = runs.filter((b) => b.status === 'done' || b.status === 'failed').length
  return { finished, total: batchIds.value.length }
})

const missingList = computed(() => missingDatasets())
const hasCoverageWarnings = computed(() => coverageWarnings().length > 0)

const runBlockedReason = computed(() => {
  if (validationBlocked.value) return t('backtest.validateFirst')
  if (!selectedCoins.value.length || !selectedIntervals.value.length) return t('backtest.selectPairs')
  const missing = missingList.value
  if (missing.length) return t('backtest.missingData', { pairs: missing.join(', ') })
  return null
})

const canRun = computed(() => !running.value && !anyActive.value && !runBlockedReason.value)

const selectClass =
  'mt-1 block w-full rounded-lg border border-border bg-surface-muted px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40'

function syncSelectionFromUi() {
  if (runAllPairs.value) {
    selectedCoins.value = [...strategySymbols.value]
    selectedIntervals.value = [...strategyIntervals.value]
  } else {
    const coin = pairToCoin(selectedPair.value)
    selectedCoins.value = coin ? [coin] : []
    selectedIntervals.value = selectedInterval.value ? [selectedInterval.value] : []
  }
}

async function ensureValidated(): Promise<boolean> {
  const s = strategy.value
  if (!s || s.validation_status === 'ok') return true
  const result = await strategyStore.validate(s.id)
  if (!result.ok) {
    toast.show(t('backtest.validateFirst'), 'error')
    return false
  }
  return true
}

function applyRouteQuery() {
  const coin = route.query.dataCoin as string | undefined
  const interval = route.query.dataInterval as string | undefined
  const network = route.query.dataNetwork as string | undefined
  if (coin) {
    selectedPair.value = coinToPair(coin)
  }
  if (interval) selectedInterval.value = interval.toLowerCase()
  if (network === 'mainnet' || network === 'testnet') selectedNetwork.value = network
  syncSelectionFromUi()
}

function syncFromStrategy(s: NonNullable<typeof strategy.value>) {
  if (route.query.dataCoin || route.query.dataInterval) {
    applyRouteQuery()
    return
  }
  const first = strategySymbols.value[0] || pairToCoin(s.symbol)
  selectedPair.value = coinToPair(first)
  selectedInterval.value = strategyIntervals.value[0] || s.timeframe || '1h'
  syncSelectionFromUi()
}

watch(strategy, (s) => { if (s) syncFromStrategy(s) }, { immediate: true })
watch([selectedPair, selectedInterval, runAllPairs], syncSelectionFromUi)

watch(
  () => [route.query.dataCoin, route.query.dataInterval, route.query.dataNetwork],
  () => applyRouteQuery(),
)

watch(selectedNetwork, (net) => {
  void historyStore.fetchMarkets(net)
  void historyStore.fetchDatasets(net)
})

onMounted(() => {
  void historyStore.fetchMarkets(selectedNetwork.value)
  void historyStore.fetchDatasets(selectedNetwork.value)
})

async function downloadMissingData() {
  syncSelectionFromUi()
  const coins = [...new Set(selectedCoins.value)]
  const intervals = [...new Set(selectedIntervals.value)]
  if (!coins.length || !intervals.length) return

  downloading.value = true
  try {
    await historyStore.startDownload({
      coins,
      intervals,
      network: selectedNetwork.value,
      start: startDate.value || '2023-01-01',
      end: endDate.value || undefined,
    })
    toast.show(t('backtest.downloadQueued'), 'success')
  } catch {
    toast.show(
      historyStore.error === 'Celery worker is offline' ? t('data.celeryOffline') : t('data.downloadFailed'),
      'error',
    )
  } finally {
    downloading.value = false
  }
}

function fmtDate(ms: number) {
  return new Date(ms).toISOString().slice(0, 10)
}

function missingDatasets() {
  return selectedCoins.value.flatMap((coin) =>
    selectedIntervals.value
      .filter((iv) => !historyStore.hasDataset(coin, iv, selectedNetwork.value))
      .map((iv) => `${coin}/${iv}`),
  )
}

function coverageWarnings() {
  const startMs = startDate.value ? new Date(startDate.value).getTime() : undefined
  const endMs = endDate.value ? new Date(endDate.value + 'T23:59:59').getTime() : undefined
  const warnings: string[] = []

  for (const coin of selectedCoins.value) {
    for (const interval of selectedIntervals.value) {
      const cov = historyStore.hasDatasetCoverage(
        coin,
        interval,
        startMs,
        endMs,
        selectedNetwork.value,
      )
      if (cov.ok || !cov.dataset) continue
      const ds = cov.dataset
      if (cov.reason === 'start') {
        warnings.push(
          t('backtest.coverageStart', {
            pair: `${coin}/${interval}`,
            have: fmtDate(ds.start_ts),
            want: startDate.value,
          }),
        )
      } else if (cov.reason === 'end') {
        warnings.push(
          t('backtest.coverageEnd', {
            pair: `${coin}/${interval}`,
            have: fmtDate(ds.end_ts),
            want: endDate.value,
          }),
        )
      }
    }
  }
  return warnings
}

function effectiveRange(coin: string, interval: string) {
  const startMs = startDate.value ? new Date(startDate.value).getTime() : undefined
  const endMs = endDate.value ? new Date(endDate.value + 'T23:59:59').getTime() : undefined
  const ds = historyStore.findDataset(coin, interval, selectedNetwork.value)
  if (!ds) return { start: startMs, end: endMs }
  let start = startMs
  let end = endMs
  if (start != null && ds.start_ts > start) start = ds.start_ts
  if (end != null && ds.end_ts < end) end = ds.end_ts
  return { start, end }
}

async function runQuickBacktest() {
  syncSelectionFromUi()
  const s = strategy.value
  if (!s) return
  if (!(await ensureValidated())) return
  const coin = selectedCoins.value[0]
  const interval = selectedIntervals.value[0]
  if (!coin || !interval) return

  const ds = historyStore.findDataset(coin, interval, selectedNetwork.value)
  if (!ds) {
    toast.show(t('backtest.missingData', { pairs: `${coin}/${interval}` }), 'error')
    return
  }

  running.value = true
  showQuickMenu.value = false
  try {
    const id = await backtestStore.runStored(s.id, {
      coin,
      interval,
      network: selectedNetwork.value,
      start: ds.start_ts,
      end: ds.end_ts,
      initial_capital: initialCapital.value,
    })
    toast.show(t('backtest.queued', { count: 1 }), 'success')
    backtestStore.select(id)
    emit('selectBacktest', id)
    void backtestStore.pollUntilDone(id)
  } catch {
    toast.show(t('backtest.runFailed'), 'error')
  } finally {
    running.value = false
  }
}

async function runBacktests() {
  syncSelectionFromUi()
  const s = strategy.value
  if (!s) return
  if (!(await ensureValidated())) return

  const missing = missingDatasets()
  if (missing.length) {
    toast.show(t('backtest.missingData', { pairs: missing.join(', ') }), 'error')
    return
  }

  running.value = true
  try {
    const ids: number[] = []
    for (const coin of selectedCoins.value) {
      for (const interval of selectedIntervals.value) {
        const range = effectiveRange(coin, interval)
        const id = await backtestStore.runStored(s.id, {
          coin,
          interval,
          network: selectedNetwork.value,
          start: range.start,
          end: range.end,
          initial_capital: initialCapital.value,
        })
        ids.push(id)
      }
    }
    toast.show(t('backtest.queued', { count: ids.length }), 'success')
    if (ids.length) {
      batchIds.value = ids
      backtestStore.select(ids[0])
      emit('selectBacktest', ids[0])
    }
    void Promise.all(ids.map((id) => backtestStore.pollUntilDone(id))).then(() => {
      batchIds.value = []
    })
  } catch {
    toast.show(t('backtest.runFailed'), 'error')
  } finally {
    running.value = false
  }
}

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

defineExpose({ runBacktests, canRun })
</script>

<template>
  <div class="space-y-2.5">
    <div>
      <label class="text-xs text-fg-muted">{{ t('strategy.symbols') }}</label>

      <div v-if="runAllPairs" class="mt-1.5 flex flex-wrap gap-1.5">
        <span
          v-for="pair in strategyPairLabels"
          :key="pair"
          class="inline-flex items-center gap-1 rounded-md border border-border bg-surface-muted px-2 py-1 text-xs text-fg"
          dir="ltr"
        >
          <span
            class="h-1.5 w-1.5 rounded-full"
            :class="storedCoinsForInterval.has(pairToCoin(pair)) ? 'bg-positive' : 'bg-border'"
          />
          {{ pair }}
        </span>
      </div>

      <TradingPairSelector
        v-else
        v-model="selectedPair"
        :network="selectedNetwork"
        :marked-coins="storedCoinsForInterval"
        class="mt-1.5"
      />

      <div
        v-if="!runAllPairs"
        class="mt-1.5 flex flex-wrap items-center justify-between gap-2 rounded-lg border px-2.5 py-2 text-xs"
        :class="selectedCoinHasData ? 'border-positive/40 bg-success-bg text-positive' : 'border-warning/40 bg-warning-bg text-warning'"
      >
        <span>{{ selectedCoinHasData ? t('backtest.dataReady') : t('backtest.dataMissing') }}</span>
        <button
          v-if="!selectedCoinHasData"
          type="button"
          class="shrink-0 rounded-md bg-accent px-2 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
          :disabled="downloading || !!activeDownload"
          @click="downloadMissingData"
        >
          {{ downloading || activeDownload ? t('backtest.downloading') : t('backtest.downloadMissing') }}
        </button>
      </div>

      <p v-if="activeDownload" class="mt-1 text-[10px] text-accent">
        {{ t('backtest.downloadInProgress') }}
      </p>
    </div>
    <label class="text-xs text-fg-muted block">
      {{ t('strategy.timeframes') }}
      <select
        v-model="selectedInterval"
        :disabled="runAllPairs"
        :class="selectClass"
      >
        <option v-for="tf in availableIntervals" :key="tf" :value="tf">{{ tf }}</option>
      </select>
    </label>

    <label class="flex items-center gap-2 text-xs text-fg-muted cursor-pointer">
      <input
        v-model="runAllPairs"
        type="checkbox"
        class="rounded border-border bg-surface-muted text-accent focus:ring-accent/40"
      />
      {{ t('backtest.runAllPairs') }}
    </label>

    <label class="text-xs text-fg-muted block">
      {{ t('backtest.network') }}
      <select v-model="selectedNetwork" :class="selectClass">
        <option value="mainnet">mainnet</option>
        <option value="testnet">testnet</option>
      </select>
    </label>

    <div class="grid grid-cols-2 gap-2.5">
      <label class="text-xs text-fg-muted min-w-0">
        {{ t('backtest.startDate') }}
        <input v-model="startDate" type="date" :class="selectClass" />
      </label>
      <label class="text-xs text-fg-muted min-w-0">
        {{ t('backtest.endDate') }}
        <input v-model="endDate" type="date" :class="selectClass" />
      </label>
    </div>

    <label class="text-xs text-fg-muted block">
      {{ t('backtest.initialCapital') }}
      <div class="relative mt-1">
        <input
          v-model.number="initialCapital"
          type="number"
          min="100"
          step="100"
          :class="selectClass"
        />
        <span class="pointer-events-none absolute inset-y-0 end-3 flex items-center text-[10px] text-fg-muted">
          USDT · fee 0.05%
        </span>
      </div>
    </label>

    <div v-if="batchProgress" class="space-y-1">
      <div class="flex justify-between text-xs text-fg-muted">
        <span>{{ t('backtest.batchProgress') }}</span>
        <span>{{ batchProgress.finished }}/{{ batchProgress.total }}</span>
      </div>
      <ProgressBar :value="(batchProgress.finished / batchProgress.total) * 100" color="violet" />
    </div>

    <div class="flex gap-2">
      <button
        type="button"
        class="relative flex-1 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="!canRun"
        :title="runBlockedReason ?? (hasCoverageWarnings ? t('backtest.coverageClamped') : undefined)"
        @click="runBacktests"
      >
        <span v-if="runBlockedReason" class="absolute -top-1 -end-1 h-2 w-2 rounded-full bg-warning" />
        {{ running || anyActive ? t('backtest.running') : t('backtest.run') }}
      </button>
      <div class="relative">
        <button
          type="button"
          class="rounded-lg border border-border px-2 py-2 text-sm text-fg hover:bg-surface-raised disabled:opacity-50"
          :disabled="!canRun"
          :title="t('backtest.quickRun')"
          @click="showQuickMenu = !showQuickMenu"
        >
          ⋯
        </button>
        <div
          v-if="showQuickMenu"
          class="absolute end-0 top-full z-10 mt-1 w-48 rounded-lg border border-border bg-surface-muted py-1 shadow-lg"
        >
          <button
            type="button"
            class="block w-full px-3 py-2 text-start text-xs text-fg hover:bg-surface-raised"
            @click="runQuickBacktest"
          >
            {{ t('backtest.quickRun') }}
          </button>
        </div>
      </div>
    </div>

    <p
      v-if="runBlockedReason && missingList.length"
      class="text-xs text-warning"
    >
      {{ runBlockedReason }}
      <button
        type="button"
        class="ms-1 underline hover:opacity-80 disabled:opacity-50"
        :disabled="downloading || !!activeDownload"
        @click="downloadMissingData"
      >
        {{ t('backtest.downloadMissing') }}
      </button>
      <span class="text-fg-muted">·</span>
      <RouterLink to="/data" class="underline ms-1">{{ t('nav.data') }}</RouterLink>
    </p>    <p v-else-if="hasCoverageWarnings" class="text-xs text-warning/80">
      {{ t('backtest.coverageClamped') }}
    </p>

    <p class="text-center text-[10px] text-fg-muted">
      {{ isMac ? t('backtest.hotkeyHintMac') : t('backtest.hotkeyHintWin') }}
    </p>
  </div>
</template>
