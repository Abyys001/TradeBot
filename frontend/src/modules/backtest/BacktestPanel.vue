<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../stores/strategy'
import { useBacktestStore } from '../../stores/backtest'
import { useHistoryStore } from '../../stores/history'
import { useToast } from '../../composables/useToast'
import BacktestHistory from './BacktestHistory.vue'
import BacktestResults from './BacktestResults.vue'
import OptimizerPanel from '../optimizer/OptimizerPanel.vue'

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
const newCoin = ref('')

const strategy = computed(() => strategyStore.strategies.find((s) => s.id === props.strategyId) ?? null)

const selectedCoins = ref<string[]>([])
const selectedIntervals = ref<string[]>([])
const selectedNetwork = ref('mainnet')
const startDate = ref('')
const endDate = ref('')

const availableIntervals = computed(() => {
  const fromApi = historyStore.markets?.intervals
  return fromApi?.length ? fromApi : FALLBACK_TIMEFRAMES
})

const strategyBacktests = computed(() => backtestStore.forStrategy(props.strategyId))

const hasCoverageWarnings = computed(() => coverageWarnings().length > 0)

function applyRouteQuery() {
  const coin = route.query.dataCoin as string | undefined
  const interval = route.query.dataInterval as string | undefined
  const network = route.query.dataNetwork as string | undefined
  if (coin) selectedCoins.value = [coin.toUpperCase().replace(/-.*$/, '')]
  if (interval) selectedIntervals.value = [interval.toLowerCase()]
  if (network === 'mainnet' || network === 'testnet') selectedNetwork.value = network
}

watch(
  strategy,
  (s) => {
    if (!s) return
    if (route.query.dataCoin || route.query.dataInterval) {
      applyRouteQuery()
      return
    }
    const symbols = s.live_config?.symbols?.length ? s.live_config.symbols : [s.symbol]
    selectedCoins.value = symbols.map((x) => x.toUpperCase().replace(/-.*$/, ''))
    selectedIntervals.value = s.live_config?.timeframes?.length
      ? [...s.live_config.timeframes]
      : [s.timeframe || '1h']
  },
  { immediate: true },
)

watch(
  () => [route.query.dataCoin, route.query.dataInterval, route.query.dataNetwork],
  () => applyRouteQuery(),
)

watch(selectedNetwork, (net) => {
  void historyStore.fetchMarkets(net)
})

watch(
  () => historyStore.activeDownloads.length,
  (count, prev) => {
    if (prev > 0 && count === 0) void historyStore.fetchDatasets()
  },
)

onMounted(async () => {
  applyRouteQuery()
  await Promise.all([
    backtestStore.fetchAll(props.strategyId),
    historyStore.fetchDatasets(),
    historyStore.fetchMarkets(selectedNetwork.value),
  ])
})

function addCoin() {
  const v = newCoin.value.trim().toUpperCase().replace(/-.*$/, '')
  if (v && !selectedCoins.value.includes(v)) {
    selectedCoins.value = [...selectedCoins.value, v]
  }
  newCoin.value = ''
}

function toggleCoin(coin: string) {
  if (selectedCoins.value.includes(coin)) {
    selectedCoins.value = selectedCoins.value.filter((c) => c !== coin)
  } else {
    selectedCoins.value = [...selectedCoins.value, coin]
  }
}

function toggleInterval(iv: string) {
  if (selectedIntervals.value.includes(iv)) {
    selectedIntervals.value = selectedIntervals.value.filter((x) => x !== iv)
  } else {
    selectedIntervals.value = [...selectedIntervals.value, iv]
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
  const s = strategy.value
  if (!s) return
  const coin = selectedCoins.value[0]
  const interval = selectedIntervals.value[0]
  if (!coin || !interval) return
  running.value = true
  try {
    const id = await backtestStore.runInline(s.id, coin, interval)
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
  const s = strategy.value
  if (!s) return

  if (s.validation_status !== 'ok') {
    const result = await strategyStore.validate(s.id)
    if (!result.ok) {
      toast.show(t('backtest.validateFirst'), 'error')
      return
    }
  }

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
        })
        ids.push(id)
      }
    }
    toast.show(t('backtest.queued', { count: ids.length }), 'success')
    if (ids.length) {
      backtestStore.select(ids[0])
      emit('selectBacktest', ids[0])
    }
    void Promise.all(ids.map((id) => backtestStore.pollUntilDone(id)))
  } catch {
    toast.show(t('backtest.runFailed'), 'error')
  } finally {
    running.value = false
  }
}

function onSelect(id: number) {
  backtestStore.select(id)
  emit('selectBacktest', id)
  void backtestStore.fetchOne(id)
}
</script>

<template>
  <div class="flex flex-col h-full min-h-0 gap-3 p-3 overflow-y-auto">
    <div class="space-y-3">
      <h3 class="text-sm font-medium text-zinc-200">{{ t('backtest.runTitle') }}</h3>

      <div v-if="missingDatasets().length" class="rounded-lg border border-amber-800 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
        {{ t('backtest.needDownload') }}
        <RouterLink to="/data" class="underline ms-1">{{ t('nav.data') }}</RouterLink>
      </div>

      <div
        v-for="(warn, i) in coverageWarnings()"
        :key="i"
        class="rounded-lg border border-amber-800/60 bg-amber-950/20 px-3 py-2 text-xs text-amber-300"
      >
        {{ warn }}
      </div>

      <p v-if="hasCoverageWarnings" class="text-xs text-amber-400/80">
        {{ t('backtest.coverageClamped') }}
      </p>

      <label class="text-xs text-zinc-500 block">
        {{ t('backtest.network') }}
        <select
          v-model="selectedNetwork"
          class="mt-1 block w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
        >
          <option value="mainnet">mainnet</option>
          <option value="testnet">testnet</option>
        </select>
      </label>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.symbols') }}</label>
        <div class="mt-1 flex flex-wrap gap-1">
          <button
            v-for="coin in selectedCoins"
            :key="coin"
            type="button"
            class="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300"
            @click="toggleCoin(coin)"
          >
            {{ coin }} ×
          </button>
          <input
            v-model="newCoin"
            type="text"
            :placeholder="t('strategy.addSymbol')"
            class="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-200 w-24"
            @keydown.enter.prevent="addCoin"
          />
        </div>
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.timeframes') }}</label>
        <div class="mt-1 flex flex-wrap gap-1">
          <button
            v-for="tf in availableIntervals"
            :key="tf"
            type="button"
            class="rounded px-2 py-0.5 text-xs transition-colors"
            :class="selectedIntervals.includes(tf) ? 'bg-emerald-900 text-emerald-300' : 'bg-zinc-800 text-zinc-400'"
            @click="toggleInterval(tf)"
          >
            {{ tf }}
          </button>
        </div>
      </div>

      <div class="flex gap-2">
        <label class="text-xs text-zinc-500 flex-1">
          {{ t('backtest.startDate') }}
          <input v-model="startDate" type="date" class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200" />
        </label>
        <label class="text-xs text-zinc-500 flex-1">
          {{ t('backtest.endDate') }}
          <input v-model="endDate" type="date" class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200" />
        </label>
      </div>

      <button
        type="button"
        class="w-full rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
        :disabled="running || !selectedCoins.length || !selectedIntervals.length"
        @click="runQuickBacktest"
      >
        {{ t('backtest.quickRun') }}
      </button>

      <button
        type="button"
        class="w-full rounded-lg bg-violet-700 px-3 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
        :disabled="running || !selectedCoins.length || !selectedIntervals.length"
        @click="runBacktests"
      >
        {{ running ? t('backtest.running') : t('backtest.run') }}
      </button>
    </div>

    <BacktestHistory
      :backtests="strategyBacktests"
      :active-id="backtestStore.activeId"
      @select="onSelect"
    />

    <BacktestResults :backtest="backtestStore.active" />

    <OptimizerPanel :strategy-id="strategyId" />
  </div>
</template>
