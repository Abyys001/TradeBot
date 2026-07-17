<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type IPriceLine,
  type CandlestickData,
  type SeriesMarker,
  type Time,
  ColorType,
} from 'lightweight-charts'
import { useStrategyStore } from '../../stores/strategy'
import { useChartStore } from '../../stores/chart'
import { useBacktestStore } from '../../stores/backtest'
import ChartSkeleton from '../../components/ChartSkeleton.vue'
import PnlCard from './PnlCard.vue'

const props = withDefaults(
  defineProps<{
    strategyId: number
    mode?: 'live' | 'backtest' | 'paper'
    backtestId?: number | null
  }>(),
  { mode: 'live', backtestId: null },
)

const { t } = useI18n()
const strategyStore = useStrategyStore()
const chartStore = useChartStore()
const backtestStore = useBacktestStore()

const container = ref<HTMLElement | null>(null)
let chart: IChartApi | null = null
let series: ISeriesApi<'Candlestick'> | null = null
let markersApi: ReturnType<typeof createSeriesMarkers<Time>> | null = null
let priceLines: IPriceLine[] = []

const selectedSymbol = ref('')
const selectedTimeframe = ref('')

const selected = computed(() =>
  strategyStore.strategies.find((s) => s.id === props.strategyId) ?? null,
)

const showSkeleton = computed(
  () => chartStore.loading || backtestStore.running || strategyStore.loading,
)

const symbols = computed(() => {
  const s = selected.value
  if (!s) return []
  return s.live_config?.symbols?.length ? s.live_config.symbols : [s.symbol]
})

const timeframes = computed(() => {
  const s = selected.value
  if (!s) return []
  return s.live_config?.timeframes?.length ? s.live_config.timeframes : [s.timeframe]
})

const activeBacktest = computed(() => {
  if (!props.backtestId) return null
  return backtestStore.backtests.find((b) => b.id === props.backtestId) ?? null
})

watch(selected, (s) => {
  if (!s) return
  selectedSymbol.value = symbols.value[0] || s.symbol
  selectedTimeframe.value = timeframes.value[0] || s.timeframe
}, { immediate: true })

function clearPriceLines() {
  if (!series) return
  for (const pl of priceLines) {
    series.removePriceLine(pl)
  }
  priceLines = []
}

async function loadChartData() {
  const s = selected.value
  if (!s || !container.value) return

  if (props.mode === 'backtest' && props.backtestId) {
    const bt = activeBacktest.value ?? (await backtestStore.fetchOne(props.backtestId))
    const network = bt.network ?? 'mainnet'
    const startMs = bt.range_start ? new Date(bt.range_start).getTime() : undefined
    const endMs = bt.range_end ? new Date(bt.range_end).getTime() : undefined
    await chartStore.fetchStoredCandles(bt.symbol, bt.timeframe, {
      start: startMs,
      end: endMs,
      network,
    })
    await chartStore.fetchMarkers(s.id, 'backtest', bt.id, network)
  } else if (props.mode === 'paper') {
    await chartStore.fetchCandles(selectedSymbol.value, selectedTimeframe.value)
    await chartStore.fetchMarkers(s.id, 'paper')
  } else {
    await chartStore.fetchCandles(selectedSymbol.value, selectedTimeframe.value)
    await chartStore.fetchMarkers(s.id, 'live')
  }
  updateSeries()
}

function updatePriceLines() {
  clearPriceLines()
  if (!series || props.mode !== 'backtest') return
  for (const level of chartStore.levels) {
    const isStop = level.type === 'stop'
    priceLines.push(
      series.createPriceLine({
        price: level.price,
        color: isStop ? '#ef4444' : '#3b82f6',
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: isStop ? 'SL' : 'TP',
      }),
    )
  }
}

function updateSeries() {
  if (!series) return
  const data: CandlestickData[] = chartStore.candles.map((c) => ({
    time: c.time as CandlestickData['time'],
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }))
  series.setData(data)

  const markers: SeriesMarker<CandlestickData['time']>[] = chartStore.markers.map((m) => ({
    time: m.time as CandlestickData['time'],
    position: m.position as 'belowBar' | 'aboveBar',
    color: m.color,
    shape: m.shape as 'arrowUp' | 'arrowDown',
    text: m.text,
  }))
  if (markersApi) {
    markersApi.setMarkers(markers)
  } else if (series) {
    markersApi = createSeriesMarkers(series, markers)
  }
  updatePriceLines()
}

watch(
  () => chartStore.candles,
  () => {
    if (!series || !chartStore.candles.length || props.mode === 'backtest') return
    const last = chartStore.candles[chartStore.candles.length - 1]
    series.update({
      time: last.time as CandlestickData['time'],
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
    })
  },
  { deep: true },
)

watch([selected, () => props.strategyId, () => props.mode, () => props.backtestId], loadChartData)
watch(
  () => [activeBacktest.value?.status, activeBacktest.value?.trades?.length] as const,
  ([status]) => {
    if (props.mode === 'backtest' && props.backtestId && status === 'done') {
      void loadChartData()
    }
  },
)
watch([selectedSymbol, selectedTimeframe], () => {
  if (props.mode === 'live' || props.mode === 'paper') loadChartData()
})

watch(
  () => backtestStore.lastResult,
  (bt) => {
    if (bt?.status === 'done' && bt.id) void loadChartData()
  },
)

onMounted(() => {
  if (!container.value) return
  chart = createChart(container.value, {
    layout: {
      background: { type: ColorType.Solid, color: '#09090b' },
      textColor: '#a1a1aa',
    },
    grid: {
      vertLines: { color: '#27272a' },
      horzLines: { color: '#27272a' },
    },
    crosshair: { mode: 1 },
    rightPriceScale: { borderColor: '#3f3f46' },
    timeScale: { borderColor: '#3f3f46' },
  })
  series = chart.addSeries(CandlestickSeries, {
    upColor: '#22c55e',
    downColor: '#ef4444',
    borderVisible: false,
    wickUpColor: '#22c55e',
    wickDownColor: '#ef4444',
  })

  const el = container.value
  const ro = new ResizeObserver(() => {
    if (el && chart) {
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight })
    }
  })
  ro.observe(el)
  loadChartData()

  onUnmounted(() => {
    ro.disconnect()
    clearPriceLines()
    chart?.remove()
    chart = null
    series = null
    markersApi = null
  })
})
</script>

<template>
  <div class="relative h-full w-full flex flex-col">
    <div
      v-if="selected && (mode === 'live' || mode === 'paper') && (symbols.length > 1 || timeframes.length > 1)"
      class="absolute top-2 start-2 z-10 flex max-w-[calc(100%-4rem)] flex-wrap gap-2"
    >
      <select
        v-if="symbols.length > 1"
        v-model="selectedSymbol"
        class="rounded border border-border bg-surface-muted/90 px-2 py-1 text-xs text-fg"
      >
        <option v-for="sym in symbols" :key="sym" :value="sym">{{ sym }}</option>
      </select>
      <select
        v-if="timeframes.length > 1"
        v-model="selectedTimeframe"
        class="rounded border border-border bg-surface-muted/90 px-2 py-1 text-xs text-fg"
      >
        <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
      </select>
    </div>

    <div
      v-if="selected && mode === 'backtest' && activeBacktest"
      class="absolute top-2 start-2 z-10 max-w-[calc(100%-4rem)] rounded border border-border bg-surface-muted/90 px-2 py-1 text-xs text-fg"
    >
      {{ activeBacktest.symbol }} / {{ activeBacktest.timeframe }}
      <span
        v-if="activeBacktest.status === 'running' || activeBacktest.status === 'pending'"
        class="ms-2 text-warning"
      >
        {{ activeBacktest.status }}…
      </span>
      <span
        v-else-if="activeBacktest.metrics?.net_pnl != null"
        class="ms-2"
        :class="activeBacktest.metrics.net_pnl >= 0 ? 'text-positive' : 'text-negative'"
      >
        PnL: {{ activeBacktest.metrics.net_pnl.toFixed(2) }}
      </span>
    </div>

    <div v-if="!selected && !strategyStore.loading" class="flex h-full items-center justify-center text-fg-muted text-sm">
      {{ t('chart.noStrategy') }}
    </div>
    <div v-show="selected || strategyStore.loading" ref="container" class="flex-1 w-full min-h-0" />
    <ChartSkeleton v-if="showSkeleton && (selected || strategyStore.loading)" />
    <PnlCard v-if="selected && mode === 'live'" :strategy-id="strategyId" />
  </div>
</template>
