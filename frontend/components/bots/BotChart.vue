<script setup lang="ts">
/**
 * The bot's chart: a **visual backtest of real history**, with the live run
 * drawn on top of it.
 *
 * The old version of this tab could only draw the bars the bot had recorded
 * since it was started, which meant a bot started this morning had a chart that
 * began this morning — and the question an operator actually has ("would this
 * have traded last night, and did it?") could not be asked of it at all.
 *
 * Four layers, each answering a different question:
 *
 *   **Candles** — the venue's own bars, from the exchange the feed is pinned to
 *   (Hyperliquid by default). Dragging back asks for the page before this one,
 *   so the scrollback is the venue's history rather than the bot's uptime.
 *
 *   **Indicator lines** — every series the script plots, from the same replay
 *   that produced the marks below, so the two cannot disagree.
 *
 *   **Entries and exits** — where the strategy *would* have traded, at the fill
 *   model's own price. This is the visual backtest.
 *
 *   **Actions** — what the running bot really routed. An entry with no action
 *   beside it is the discrepancy, and the header counts them rather than
 *   leaving it to be spotted by eye across a hundred marks.
 *
 * The last bar ticks: the component takes the engine's pushed frames straight
 * off the socket (`live.onBar`) rather than through the market store, which
 * belongs to the admin's own trading chart and must not be moved to a bot's
 * pair to get them.
 *
 * Every label is UK time — `utils/clock.ts`, the same clock as the trade log
 * and as TradingView.
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
import { ukChartLocalization, ukDateTime, zoneLabel } from '~/utils/clock'

const props = defineProps<{ botId: number; interval: string; market?: string; symbol?: string }>()

const { t } = useI18n()
const api = useApi()
const { money } = useFormat()
const live = useLiveStore()

const shown = ref(props.interval)
const data = ref<BotChart | null>(null)
const loading = ref(true)
/** A page of older bars is in flight. Separate from `loading`: the chart stays. */
const paging = ref(false)
/** The venue has no more history before what is on screen. Stops asking. */
const exhausted = ref(false)
const error = ref('')
const el = ref<HTMLElement | null>(null)

/** Everything on screen, oldest first. Pages are prepended, ticks fold in. */
const candles = ref<BotChart['candles']>([])
const series = ref<ChartSeries[]>([])
const markers = ref<ChartMarker[]>([])
const trades = ref<ChartTrade[]>([])

let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let lines: ISeriesApi<'Line'>[] = []
let markerLayer: ReturnType<typeof createSeriesMarkers> | null = null
let stopBars: (() => void) | null = null

const PAGE = 400

/**
 * Colours for the indicator lines, in order. Deliberately a short cycle: a
 * script plotting nine series is unreadable however it is coloured, and the
 * legend under the chart is what disambiguates the repeats.
 */
const SERIES_COLORS = ['#5B8DEF', '#F0A020', '#3BC9D8', '#B78CF2', '#7DD87D', '#FF6B81']

const legend = computed(() =>
  series.value.map((row, index) => ({
    name: row.name,
    color: SERIES_COLORS[index % SERIES_COLORS.length],
  })),
)

const summary = computed(() => data.value?.summary ?? {})
const empty = computed(() => !candles.value.length)

/** The bot's own timeframe is the one it trades; anything else is for looking. */
const ownInterval = computed(() => shown.value === props.interval)

function mount() {
  if (!el.value || chart) return
  const uk = ukChartLocalization()
  chart = createChart(el.value, {
    layout: {
      background: { color: 'transparent' },
      textColor: tokenColor('--c-ink-muted'),
      fontSize: 11,
    },
    grid: {
      vertLines: { color: tokenColor('--c-chart-grid', '#1E232B') },
      horzLines: { color: tokenColor('--c-chart-grid', '#1E232B') },
    },
    rightPriceScale: { borderColor: tokenColor('--c-chart-grid', '#1E232B') },
    localization: uk.localization,
    timeScale: { borderColor: tokenColor('--c-chart-grid', '#1E232B'), ...uk.timeScale },
    autoSize: true,
    handleScroll: { vertTouchDrag: false },
  })
  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: tokenColor('--c-long', '#3BC9D8'),
    downColor: tokenColor('--c-short', '#FF6B81'),
    wickUpColor: tokenColor('--c-long', '#3BC9D8'),
    wickDownColor: tokenColor('--c-short', '#FF6B81'),
    borderVisible: false,
    priceLineVisible: true,
  })
  markerLayer = createSeriesMarkers(candleSeries)

  // Dragging past the left edge asks for the page before this one. The guard is
  // a bar count rather than a pixel: at 1m a screen is minutes wide and at 1d it
  // is years, and the point at which more history is worth fetching is the same
  // number of bars from the edge either way.
  chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (!range || paging.value || loading.value || exhausted.value) return
    if (range.from < 20) void pageBack()
  })
}

function drawCandles() {
  candleSeries?.setData(
    candles.value.map((bar) => ({
      time: bar.time as Time,
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
    })),
  )
}

function drawSeries() {
  if (!chart) return
  for (const line of lines) chart.removeSeries(line)
  lines = []
  series.value.forEach((row, index) => {
    const line = chart!.addSeries(LineSeries, {
      color: SERIES_COLORS[index % SERIES_COLORS.length],
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
    })
    line.setData(row.points.map((point) => ({ time: point.time as Time, value: point.value })))
    lines.push(line)
  })
}

/** Pine's shape vocabulary → the four Lightweight Charts offers. */
function shapeFor(style: string | undefined, above: boolean) {
  if (style?.startsWith('shape.arrow') || style?.startsWith('shape.triangle')) {
    return (above ? 'arrowDown' : 'arrowUp') as 'arrowUp' | 'arrowDown'
  }
  if (style?.startsWith('shape.label')) return 'square' as const
  return 'circle' as const
}

/**
 * One marker row → one mark. Five kinds, and they are deliberately not
 * collapsed: a signal, the fill it produced, the shape the script drew and the
 * order that was really sent are four different facts about the same bar, and
 * the interesting case is the one where the last is missing.
 */
function markFor(marker: ChartMarker) {
  const long = marker.side === 'long'
  const longColor = tokenColor('--c-long', '#3BC9D8')
  const shortColor = tokenColor('--c-short', '#FF6B81')
  if (marker.kind === 'entry') {
    return {
      position: (long ? 'belowBar' : 'aboveBar') as 'belowBar' | 'aboveBar',
      shape: (long ? 'arrowUp' : 'arrowDown') as 'arrowUp' | 'arrowDown',
      color: long ? longColor : shortColor,
      text:
        `${marker.trade ?? ''} ${marker.label || t(`bots.chartMark.entry.${marker.side ?? 'flat'}`)}`.trim(),
    }
  }
  if (marker.kind === 'exit') {
    const win = Number(marker.pnl ?? 0) >= 0
    return {
      position: (long ? 'aboveBar' : 'belowBar') as 'belowBar' | 'aboveBar',
      shape: 'square' as const,
      color: win ? tokenColor('--c-ok', '#7DD87D') : shortColor,
      text: `${marker.trade ?? ''} ${marker.label || t('bots.chartMark.exit')}`.trim(),
    }
  }
  if (marker.kind === 'shape') {
    // The script's own furniture, where the script put it: a `plotshape` is a
    // condition, so `location=` is the whole of where it belongs and its
    // series carries no price to place it at. Dimmed on purpose — this is what
    // the author drew, not what the replay traded, and the two must stay
    // distinguishable at a glance.
    const above = marker.location !== 'location.belowbar'
    return {
      position: (above ? 'aboveBar' : 'belowBar') as 'belowBar' | 'aboveBar',
      shape: shapeFor(marker.style, above),
      color: tokenColor('--c-ink-muted', '#8B94A3'),
      text: marker.label || '',
    }
  }
  if (marker.kind === 'action') {
    return {
      position: 'belowBar' as const,
      shape: 'circle' as const,
      color: marker.ok === false ? shortColor : tokenColor('--c-signal', '#F0A020'),
      text: t(`bots.action.${marker.action_type}`),
    }
  }
  return {
    position: 'aboveBar' as const,
    shape: (long ? 'arrowUp' : marker.side ? 'arrowDown' : 'circle') as
      | 'arrowUp'
      | 'arrowDown'
      | 'circle',
    color: long ? longColor : marker.side ? shortColor : tokenColor('--c-ink-muted', '#8B94A3'),
    text: marker.side ? t(`side.${marker.side}`) : t('bots.flat'),
  }
}

function drawMarkers() {
  markerLayer?.setMarkers(
    markers.value
      .map((marker) => ({ time: marker.time as Time, size: 1 as const, ...markFor(marker) }))
      .sort((a, b) => Number(a.time) - Number(b.time)),
  )
}

function draw() {
  if (!chart) return
  drawCandles()
  drawSeries()
  drawMarkers()
}

/** One replayed trade's identity: its two ends and its side. */
function tradeKey(row: ChartTrade) {
  return `${row.side}:${row.entry_time}:${row.exit_time}`
}

/** Merge a page of older bars in front of what is on screen, without duplicates. */
function prepend(page: BotChart) {
  const oldest = candles.value[0]?.time ?? Infinity
  const fresh = page.candles.filter((bar) => bar.time < oldest)
  if (!fresh.length) {
    exhausted.value = true
    return
  }
  candles.value = fresh.concat(candles.value)
  markers.value = page.markers.filter((m) => m.time < oldest).concat(markers.value)
  // A campaign that opened on this page and closed on the one already held is
  // on both, because a page carries every trade with *either* end inside it —
  // the exit mark is the reason the operator is looking, and it cannot be
  // dropped because the entry is off the left edge. So the merge is by
  // identity, not by position.
  const held = new Set(trades.value.map(tradeKey))
  trades.value = page.trades.filter((row) => !held.has(tradeKey(row))).concat(trades.value)

  const byName = new Map(series.value.map((row) => [row.name, row]))
  for (const row of page.series) {
    const points = row.points.filter((p) => p.time < oldest)
    const existing = byName.get(row.name)
    if (existing) existing.points = points.concat(existing.points)
    else byName.set(row.name, { name: row.name, points })
  }
  series.value = [...byName.values()]
}

async function pageBack() {
  const oldest = candles.value[0]?.time
  if (!oldest) return
  paging.value = true
  try {
    const page = await api.botChart(props.botId, shown.value, PAGE, oldest)
    if (page.note === 'no_history' || !page.candles.length) {
      exhausted.value = true
      return
    }
    // Keep the view where the admin left it: `setData` on a prepended series
    // would otherwise jump the scroll to the new left edge every page.
    const range = chart?.timeScale().getVisibleLogicalRange()
    const before = candles.value.length
    prepend(page)
    draw()
    if (range) {
      const shift = candles.value.length - before
      chart?.timeScale().setVisibleLogicalRange({
        from: range.from + shift,
        to: range.to + shift,
      })
    }
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    paging.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  exhausted.value = false
  try {
    const page = await api.botChart(props.botId, shown.value, PAGE)
    data.value = page
    candles.value = page.candles
    series.value = page.series
    markers.value = page.markers
    trades.value = page.trades
    // The container is rendered unconditionally (see the template), so it is in
    // the DOM with a real height by the time this runs. It used to sit behind
    // `v-else` on `loading`, which meant `mount()` ran against a null ref every
    // time and the chart was never created — a black panel whatever the
    // timeframe.
    await nextTick()
    if (!empty.value) {
      mount()
      draw()
      chart?.timeScale().fitContent()
    }
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

/**
 * Fold one pushed bar into the series and repaint the last candle only.
 *
 * Replace-or-append on the bar's own timestamp: the exchange re-sends the same
 * forming bar on every tick, and appending blindly is how a live chart grows a
 * duplicate candle per second.
 */
function applyBar(payload: any) {
  if (
    payload.symbol !== data.value?.symbol ||
    payload.interval !== shown.value ||
    payload.market !== data.value?.market
  ) {
    return
  }
  const bar = {
    time: payload.bar.t as number,
    open: String(payload.bar.o),
    high: String(payload.bar.h),
    low: String(payload.bar.l),
    close: String(payload.bar.c),
    volume: String(payload.bar.v ?? '0'),
  }
  const last = candles.value[candles.value.length - 1]
  if (last && bar.time === last.time) candles.value[candles.value.length - 1] = bar
  else if (!last || bar.time > last.time) candles.value.push(bar)
  else return
  candleSeries?.update({
    time: bar.time as Time,
    open: Number(bar.open),
    high: Number(bar.high),
    low: Number(bar.low),
    close: Number(bar.close),
  })
}

/**
 * Follow this bot's pair rather than the admin's own chart symbol.
 *
 * The engine keeps one subscription per consumer, so this takes the socket over
 * while the tab is open and hands it back on the way out — otherwise leaving a
 * bot page would leave the trading chart permanently subscribed to the bot's
 * instrument.
 */
function follow() {
  if (!data.value) return
  live.subscribeMarket({
    symbol: data.value.symbol,
    interval: shown.value,
    market: data.value.market,
  })
}

const zone = computed(() => zoneLabel())
const lastClose = computed(() => candles.value[candles.value.length - 1]?.close ?? null)
const lastAt = computed(() => {
  const bar = candles.value[candles.value.length - 1]
  return bar ? ukDateTime(bar.time) : ''
})

onMounted(() => {
  stopBars = live.onBar(applyBar)
  void load().then(follow)
})
watch(shown, () => {
  exhausted.value = false
  void load().then(follow)
})
watch(
  () => props.interval,
  (value) => {
    shown.value = value
  },
)
watch(() => live.connected, follow)

onBeforeUnmount(() => {
  stopBars?.()
  // Give the socket back to the admin's own chart.
  useMarketStore().resubscribe()
  chart?.remove()
  chart = null
  candleSeries = null
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
        <span v-if="data?.source" class="num text-tick text-ink-faint ms-auto">
          {{ t('bots.chartFeed', { venue: data.source }) }} · {{ zone }}
        </span>
        <UiBadge v-if="!ownInterval" tone="signal">{{ t('bots.chartReplayed') }}</UiBadge>
      </div>

      <!-- What this chart is, said once. Every mark on it is a replay of the
           venue's real bars; the routed orders are the separate ring marks. -->
      <p class="px-3 py-2 text-tick text-ink-faint leading-relaxed border-b border-line">
        {{ ownInterval ? t('bots.chartHistoryHint') : t('bots.chartReplayedHint') }}
      </p>

      <div
        v-if="!empty"
        class="px-3 py-2 border-b border-line flex flex-wrap items-center gap-x-4 gap-y-1 text-xs num"
      >
        <span v-if="lastClose">
          <span class="text-ink-faint">{{ data?.symbol }}</span>
          {{ money(lastClose) }}
          <span class="text-ink-faint">· {{ lastAt }}</span>
        </span>
        <span class="text-ink-muted">
          {{ t('bots.chartTrades', { n: summary.trades ?? 0, bars: summary.bars ?? 0 }) }}
        </span>
        <span v-if="summary.net_profit" :class="Number(summary.net_profit) >= 0 ? 'text-ok' : 'text-short'">
          {{ money(summary.net_profit) }}
        </span>
        <!-- The discrepancy, counted rather than left to the eye: replayed
             entries with no routed order beside them. -->
        <span v-if="summary.unrouted" class="text-signal">
          {{ t('bots.chartUnrouted', { n: summary.unrouted }) }}
        </span>
        <span v-if="paging" class="text-ink-faint">{{ t('bots.chartPaging') }}</span>
        <span v-else-if="exhausted" class="text-ink-faint">{{ t('bots.chartOldest') }}</span>
      </div>

      <p v-if="error" class="px-3 py-3 text-xs text-short">{{ error }}</p>
      <!-- The canvas host is always mounted. Lightweight Charts measures the
           element it is given, so it cannot be created behind a `v-if` that is
           still false — the loading and empty states are drawn *over* it. -->
      <div v-else class="relative p-1">
        <div ref="el" class="h-[22rem] sm:h-[30rem] w-full" />
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
          :title="data?.note === 'invalid_strategy' ? t('bots.chartInvalid') : t('bots.chartNoHistory')"
          :body="data?.note === 'invalid_strategy' ? t('bots.chartInvalidBody') : t('bots.chartNoHistoryBody')"
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

    <!-- TradingView's List of Trades, for the window on screen. The chart shows
         where; this shows what each one returned. -->
    <UiCard v-if="trades.length" :title="t('bots.chartTradeList')" flush>
      <ul class="divide-y divide-line max-h-72 overflow-y-auto">
        <li
          v-for="(row, index) in trades.slice().reverse()"
          :key="`${row.entry_time}-${index}`"
          class="px-3 py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
        >
          <UiBadge :tone="row.side === 'long' ? 'long' : 'short'">
            {{ t(`side.${row.side}`) }}
          </UiBadge>
          <span class="num text-ink-muted">{{ ukDateTime(row.entry_time) }}</span>
          <span class="num">{{ money(row.entry_price) }}</span>
          <span class="text-ink-faint">→</span>
          <span class="num text-ink-muted">{{ row.exit_time ? ukDateTime(row.exit_time) : '—' }}</span>
          <span class="num">{{ row.exit_time ? money(row.exit_price) : '—' }}</span>
          <span class="num ms-auto" :class="Number(row.pnl) >= 0 ? 'text-ok' : 'text-short'">
            {{ money(row.pnl) }}
          </span>
          <span v-if="row.exit_reason" class="text-ink-faint truncate w-full sm:w-auto">
            {{ row.exit_reason }}
          </span>
        </li>
      </ul>
    </UiCard>
  </div>
</template>
