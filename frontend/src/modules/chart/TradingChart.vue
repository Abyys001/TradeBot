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

const QUALITY_COLORS: Record<string, string> = {
  CLEAN: '#22c55e',
  FLAT: '#eab308',
  SUSPECT: '#f97316',
  MISSING: '#ef4444',
}
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
let qualitySeries: ISeriesApi<'Histogram'> | null = null
let markersApi: ReturnType<typeof createSeriesMarkers<Time>> | null = null
let priceLines: IPriceLine[] = []
let plotLineSeries: ISeriesApi<'Line'>[] = []
let plotMarkersApi: ReturnType<typeof createSeriesMarkers<Time>> | null = null

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

function clearPlotOverlays() {
  if (!chart) return
  for (const ls of plotLineSeries) {
    try { chart.removeSeries(ls) } catch { /* already removed */ }
  }
  plotLineSeries = []
  plotMarkersApi = null
}

function updatePlotOverlays() {
  if (!chart || !series) return
  clearPlotOverlays()

  const bt = activeBacktest.value
  const pd = bt?.metrics?.plot_data
  if (!pd) return

  const candles = chartStore.candles
  if (!candles.length) return

  // --- plot() lines ---
  for (const line of pd.lines ?? []) {
    if (!line.values?.length) continue
    const ls = chart.addSeries(LineSeries, {
      color: line.color || '#2196f3',
      lineWidth: (line.linewidth ?? 1) as 1 | 2 | 3 | 4,
      lineStyle: line.style === 'dashed' ? 1 : line.style === 'dotted' ? 2 : 0,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    const lineData: LineData[] = line.values
      .map((v, i) => {
        if (v == null || i >= candles.length) return null
        return { time: candles[i].time as Time, value: v }
      })
      .filter((d): d is LineData => d != null)
    ls.setData(lineData)
    plotLineSeries.push(ls)
  }

  // --- hline() price lines ---
  for (const h of pd.hlines ?? []) {
    priceLines.push(
      series.createPriceLine({
        price: h.price,
        color: h.color || '#9598a1',
        lineWidth: (h.linewidth ?? 1) as 1 | 2 | 3 | 4,
        lineStyle: h.linestyle === 'dashed' ? 1 : h.linestyle === 'dotted' ? 2 : 0,
        axisLabelVisible: true,
        title: h.title || '',
      }),
    )
  }

  // --- plotshape() + plotchar() markers ---
  const plotMarkers: SeriesMarker<Time>[] = []
  const shapeMap: Record<string, string> = {
    circle: 'circle', cross: 'cross', triangleup: 'arrowUp', triangledown: 'arrowDown',
    flag: 'circle', arrowup: 'arrowUp', arrowdown: 'arrowDown',
  }
  for (const shape of pd.shapes ?? []) {
    for (const idx of shape.bar_indices ?? []) {
      if (idx >= candles.length) continue
      plotMarkers.push({
        time: candles[idx].time as Time,
        position: shape.location === 'below' ? 'belowBar' : 'aboveBar',
        color: shape.color || '#2196f3',
        shape: (shapeMap[shape.style] ?? 'circle') as 'arrowUp' | 'arrowDown' | 'circle' | 'cross',
        text: shape.text || '',
      })
    }
  }
  for (const ch of pd.chars ?? []) {
    for (const idx of ch.bar_indices ?? []) {
      if (idx >= candles.length) continue
      plotMarkers.push({
        time: candles[idx].time as Time,
        position: ch.location === 'below' ? 'belowBar' : 'aboveBar',
        color: ch.color || '#2196f3',
        shape: 'circle',
        text: ch.text || ch.char || '',
      })
    }
  }
  if (plotMarkers.length) {
    plotMarkersApi = createSeriesMarkers(series, plotMarkers)
  }
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
  if (!series) return
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

  const pos = chartStore.openPosition
  if (pos) {
    if (pos.liq != null && pos.liq > 0) {
      priceLines.push(
        series.createPriceLine({
          price: pos.liq,
          color: '#f97316',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'LIQ',
        }),
      )
    }
    if (pos.entry?.price != null && pos.entry.price > 0) {
      const isProfit = pos.pnl >= 0
      priceLines.push(
        series.createPriceLine({
          price: pos.entry.price,
          color: isProfit ? '#22c55e' : '#ef4444',
          lineWidth: 2,
          lineStyle: 0,
          axisLabelVisible: true,
          title: 'ENTRY',
        }),
      )
    }
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

  if (qualitySeries) {
    const qualityData: HistogramData[] = chartStore.quality.map((q) => ({
      time: q.time as Time,
      value: 1,
      color: QUALITY_COLORS[q.q] ?? '#71717a',
    }))
    qualitySeries.setData(qualityData)
  }

  updatePriceLines()
  updatePlotOverlays()
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

  qualitySeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: 'quality',
  })
  chart.priceScale('quality').applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
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
    clearPlotOverlays()
    chart?.remove()
    chart = null
    series = null
    qualitySeries = null
    markersApi = null
  })
})
</script>

<template>
  <div class="relative h-full w-full flex flex-col">
    <div
      v-if="selected && (mode === 'live' || mode === 'paper')"
      class="absolute top-2 start-2 z-10 flex max-w-[calc(100%-4rem)] flex-wrap gap-2"
    >
      <select
        v-model="selectedSymbol"
        class="rounded border border-border bg-surface-muted/90 px-2 py-1 text-xs text-fg"
      >
        <option v-for="sym in symbols" :key="sym" :value="sym">{{ sym }}</option>
      </select>
      <select
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
