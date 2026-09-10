<script setup lang="ts">
/**
 * The bot's chart: what it saw, what it computed, and where it acted.
 *
 * Three layers, and each one answers a different question:
 *
 *   **Candles** — the bars the bot evaluated. At the bot's own timeframe these
 *   are the rows it stored (`BotBar`), not a fresh download, so the chart
 *   cannot disagree with the journal beside it.
 *
 *   **Indicator lines** — every series the script plots, drawn from the values
 *   the runtime actually emitted per bar. A line breaks where the script had no
 *   value rather than being drawn through zero.
 *
 *   **Markers** — two kinds, kept apart on purpose. A *signal* is what the
 *   strategy wanted; an *action* is what was routed. A bot that "did nothing"
 *   usually has signals with no actions beside them, and that gap is the whole
 *   diagnosis.
 *
 * Changing the timeframe **never touches the bot**. At any interval but its own
 * the strategy is replayed purely to draw it, and the header says so — a chart
 * control that restarted a live bot would be the worst kind of surprise.
 */
import {
  CandlestickSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { tokenColor } from '~/composables/useTheme'
import { INTERVALS } from '~/stores/market'

const props = defineProps<{ botId: number; interval: string }>()

const { t } = useI18n()
const api = useApi()
const { dateTime } = useFormat()

const shown = ref(props.interval)
const data = ref<BotChart | null>(null)
const loading = ref(true)
const error = ref('')
const el = ref<HTMLElement | null>(null)

let chart: IChartApi | null = null
let candles: ISeriesApi<'Candlestick'> | null = null
let lines: ISeriesApi<'Line'>[] = []
let markerLayer: ReturnType<typeof createSeriesMarkers> | null = null

/**
 * Colours for the indicator lines, in order. Deliberately a short cycle: a
 * script plotting nine series is unreadable however it is coloured, and the
 * legend under the chart is what disambiguates the repeats.
 */
const SERIES_COLORS = ['#5B8DEF', '#F0A020', '#3BC9D8', '#B78CF2', '#7DD87D', '#FF6B81']

const legend = computed(() =>
  (data.value?.series ?? []).map((row, index) => ({
    name: row.name,
    color: SERIES_COLORS[index % SERIES_COLORS.length],
    points: row.points.length,
  })),
)

/** Only the signal markers, listed under the chart where they can carry words. */
const events = computed(() =>
  (data.value?.markers ?? [])
    .filter((marker) => marker.kind === 'signal')
    .slice(-25)
    .reverse(),
)

function mount() {
  if (!el.value || chart) return
  chart = createChart(el.value, {
    layout: { background: { color: 'transparent' }, textColor: tokenColor('--c-ink-muted'), fontSize: 11 },
    grid: {
      vertLines: { color: tokenColor('--c-chart-grid', '#1E232B') },
      horzLines: { color: tokenColor('--c-chart-grid', '#1E232B') },
    },
    rightPriceScale: { borderColor: tokenColor('--c-chart-grid', '#1E232B') },
    timeScale: { borderColor: tokenColor('--c-chart-grid', '#1E232B'), timeVisible: true },
    autoSize: true,
    handleScroll: { vertTouchDrag: false },
  })
  candles = chart.addSeries(CandlestickSeries, {
    upColor: tokenColor('--c-long', '#3BC9D8'),
    downColor: tokenColor('--c-short', '#FF6B81'),
    wickUpColor: tokenColor('--c-long', '#3BC9D8'),
    wickDownColor: tokenColor('--c-short', '#FF6B81'),
    borderVisible: false,
    priceLineVisible: false,
  })
  markerLayer = createSeriesMarkers(candles)
}

function draw() {
  if (!chart || !candles || !data.value) return

  candles.setData(
    data.value.candles.map((bar) => ({
      time: bar.time as Time,
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
    })),
  )

  for (const line of lines) chart.removeSeries(line)
  lines = []
  data.value.series.forEach((row, index) => {
    const series = chart!.addSeries(LineSeries, {
      color: SERIES_COLORS[index % SERIES_COLORS.length],
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
    })
    series.setData(row.points.map((point) => ({ time: point.time as Time, value: point.value })))
    lines.push(series)
  })

  // A signal and an action on the same bar are two marks, above and below.
  // Collapsing them would hide the case that matters most: the strategy asked
  // and nothing went out.
  const marks = data.value.markers
    .map((marker) => {
      const isSignal = marker.kind === 'signal'
      const long = marker.side === 'long'
      return {
        time: marker.time as Time,
        position: (isSignal ? 'aboveBar' : 'belowBar') as 'aboveBar' | 'belowBar',
        shape: (long ? 'arrowUp' : marker.side ? 'arrowDown' : 'circle') as
          | 'arrowUp'
          | 'arrowDown'
          | 'circle',
        color: isSignal
          ? long
            ? tokenColor('--c-long', '#3BC9D8')
            : marker.side
              ? tokenColor('--c-short', '#FF6B81')
              : tokenColor('--c-ink-muted', '#8B94A3')
          : marker.ok === false
            ? tokenColor('--c-short', '#FF6B81')
            : tokenColor('--c-signal', '#F0A020'),
        text: isSignal
          ? marker.side
            ? t(`side.${marker.side}`)
            : t('bots.flat')
          : t(`bots.action.${marker.kind}`),
        size: 1 as const,
      }
    })
    .sort((a, b) => Number(a.time) - Number(b.time))
  markerLayer?.setMarkers(marks)
  chart.timeScale().fitContent()
}

/** True once there is something to draw. Drives the overlay, never the container. */
const empty = computed(() => !data.value || data.value.note === 'no_history' || !data.value.candles.length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.botChart(props.botId, shown.value)
    // The container is rendered unconditionally (see the template), so it is
    // in the DOM with a real height by the time this runs. It used to sit
    // behind `v-else` on `loading`, which meant `mount()` ran against a null
    // ref every single time and the chart was never created — a black panel
    // whatever the timeframe.
    await nextTick()
    if (!empty.value) {
      mount()
      draw()
    }
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(shown, load)
watch(() => props.interval, (value) => { shown.value = value })

onBeforeUnmount(() => {
  chart?.remove()
  chart = null
  candles = null
  lines = []
  markerLayer = null
})
</script>

<template>
  <div class="space-y-4">
    <UiCard flush>
      <div class="px-3 py-2.5 border-b border-line flex flex-wrap items-center gap-x-3 gap-y-2">
        <span class="label">{{ t('bots.timeframe') }}</span>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="value in INTERVALS"
            :key="value"
            class="btn-quiet btn-sm num"
            :class="value === shown ? 'text-brand bg-raised' : ''"
            @click="shown = value"
          >
            {{ value }}
          </button>
        </div>
        <UiBadge v-if="data?.replayed" tone="signal" class="ms-auto">
          {{ t('bots.chartReplayed') }}
        </UiBadge>
        <UiBadge v-else tone="ok" class="ms-auto">{{ t('bots.chartRecorded') }}</UiBadge>
      </div>

      <p class="px-3 py-2 text-tick text-ink-faint leading-relaxed border-b border-line">
        {{ data?.replayed ? t('bots.chartReplayedHint') : t('bots.chartRecordedHint') }}
      </p>

      <p v-if="error" class="px-3 py-3 text-xs text-short">{{ error }}</p>
      <!-- The canvas host is always mounted. Lightweight Charts measures the
           element it is given, so it cannot be created behind a `v-if` that is
           still false — the loading and empty states are drawn *over* it. -->
      <div v-else class="relative p-1">
        <div ref="el" class="h-[22rem] sm:h-[26rem] w-full" />
        <div
          v-if="loading"
          class="absolute inset-1 rounded-lg bg-sunken/80 backdrop-blur-[1px] flex flex-col items-center justify-center gap-3"
        >
          <span
            class="w-7 h-7 rounded-full border-2 border-line border-t-brand animate-spin"
            role="status"
            :aria-label="t('bots.chartLoading')"
          />
          <span class="text-xs text-ink-muted">{{ t('bots.chartLoading') }}</span>
        </div>
        <UiEmpty
          v-else-if="empty"
          class="absolute inset-1 bg-sunken rounded-lg"
          icon="chart"
          :title="t('bots.chartNoHistory')"
          :body="t('bots.chartNoHistoryBody')"
        />
      </div>

      <div
        v-if="legend.length"
        class="px-3 py-2.5 border-t border-line flex flex-wrap items-center gap-x-4 gap-y-1.5"
      >
        <span
          v-for="row in legend"
          :key="row.name"
          class="inline-flex items-center gap-1.5 text-xs num"
        >
          <span class="w-3 h-0.5 rounded-full" :style="{ background: row.color }" />
          {{ row.name }}
        </span>
      </div>
    </UiCard>

    <!-- The signals as words. The chart shows where; this shows why, in the
         script's own `reason` string. -->
    <UiCard v-if="events.length" :title="t('bots.signals')" flush>
      <ul class="divide-y divide-line max-h-64 overflow-y-auto">
        <li v-for="(row, index) in events" :key="index" class="px-3 py-2 flex items-center gap-2 text-xs">
          <UiBadge :tone="row.side === 'long' ? 'long' : row.side ? 'short' : 'neutral'">
            {{ row.side ? t(`side.${row.side}`) : t('bots.flat') }}
          </UiBadge>
          <span class="num text-ink-muted">
            {{ dateTime(new Date(row.time * 1000).toISOString()) }}
          </span>
          <span class="text-ink-faint truncate">{{ row.reason }}</span>
        </li>
      </ul>
    </UiCard>
  </div>
</template>
