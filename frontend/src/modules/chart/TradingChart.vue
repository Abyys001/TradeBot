<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type SeriesMarker,
  type Time,
  ColorType,
} from 'lightweight-charts'
import { useStrategyStore } from '../../stores/strategy'
import { useChartStore } from '../../stores/chart'
import { useBacktestStore } from '../../stores/backtest'
import ChartSkeleton from '../../components/ChartSkeleton.vue'

const props = defineProps<{ strategyId: number }>()

const { t } = useI18n()
const strategyStore = useStrategyStore()
const chartStore = useChartStore()
const backtestStore = useBacktestStore()

const container = ref<HTMLElement | null>(null)
let chart: IChartApi | null = null
let series: ISeriesApi<'Candlestick'> | null = null
let markersApi: ReturnType<typeof createSeriesMarkers<Time>> | null = null
let resizeObserver: ResizeObserver | null = null

const selected = computed(() =>
  strategyStore.strategies.find((s) => s.id === props.strategyId) ?? null,
)

const showSkeleton = computed(
  () => chartStore.loading || backtestStore.running || strategyStore.loading,
)

function ensureChart() {
  if (!container.value || chart) return
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
  resizeObserver = new ResizeObserver(() => {
    if (el && chart) {
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight })
    }
  })
  resizeObserver.observe(el)
}

async function loadChartData(backtestId?: number) {
  const s = selected.value
  if (!s) return
  await nextTick()
  ensureChart()
  if (!series) return

  const symbol = s.live_config?.symbols?.[0] || s.symbol
  const bar = s.live_config?.timeframes?.[0] || s.timeframe
  await chartStore.fetchCandles(symbol, bar)
  if (backtestId != null) {
    await chartStore.fetchMarkers(s.id, 'backtest', backtestId)
  } else {
    await chartStore.fetchMarkers(s.id, 'live')
  }
  updateSeries()
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
}

watch(
  () => chartStore.candles,
  () => {
    if (!series || !chartStore.candles.length) return
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

watch(selected, () => {
  if (selected.value) loadChartData()
})

watch(() => props.strategyId, () => {
  if (selected.value) loadChartData()
})

watch(
  () => backtestStore.lastResult,
  (bt) => {
    if (bt?.status === 'done' && bt.id) loadChartData(bt.id)
  },
)

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.remove()
  chart = null
  series = null
  markersApi = null
})
</script>

<template>
  <div class="relative h-full w-full">
    <div
      v-if="!selected && !strategyStore.loading"
      class="flex h-full items-center justify-center text-zinc-500 text-sm"
    >
      {{ t('chart.noStrategy') }}
    </div>
    <div v-show="selected || strategyStore.loading" ref="container" class="h-full w-full" />
    <ChartSkeleton v-if="showSkeleton && (selected || strategyStore.loading)" />
  </div>
</template>
