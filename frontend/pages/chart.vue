<script setup lang="ts">
/**
 * The trading screen (spec §3) — chart, order ticket, positions.
 *
 * SL/TP is editable from three surfaces — ticket, chart, position bar — and all
 * three write to the same order store, so one edit produces one fan-out no
 * matter where it came from. A limit order's entry line is draggable too, which
 * makes the chart a fourth *input* rather than only a picture.
 *
 * Everything on this page marks against one price (stores/market.ts), which is
 * what makes a live PnL possible. When no exchange is reachable the feed falls
 * back to labelled synthetic data and the header says so — see SymbolBar.
 *
 * Layout is genuinely different per size rather than a shrunk desktop:
 *
 *   lg+      chart + position bar + per-account detail, ticket in a side rail
 *   md       chart on top, ticket beneath it full width
 *   phone    one pane at a time, switched by a tab strip — three columns on a
 *            390px screen leaves the chart 90px wide, which is not a chart
 */
const { t } = useI18n()
const order = useOrderStore()
const trading = useTradingStore()
const positions = usePositionsStore()
const market = useMarketStore()
const ui = useUiStore()
const { isDark } = useTheme()

// `/terminal` was this page's old address; keep it working rather than 404 on
// a link someone bookmarked.
definePageMeta({ alias: ['/terminal'] })

useHead({ title: t('nav.chart') })

const chartEl = ref<HTMLElement | null>(null)
let chart: ChartAdapter | null = null

/** Which detail panel sits under the chart on a wide screen. */
const detail = ref<'positions' | 'fanout'>('positions')

const paneOptions = computed(() => [
  { value: 'chart', label: t('terminal.pane.chart') },
  { value: 'ticket', label: t('terminal.pane.ticket') },
  { value: 'accounts', label: t('terminal.pane.accounts') },
])

const detailOptions = computed(() => [
  { value: 'positions', label: t('terminal.detail.positions') },
  { value: 'fanout', label: t('terminal.detail.fanout') },
])

/**
 * The price every line on the chart hangs off.
 *
 *   open position → the fill it actually got
 *   limit order   → the limit price, which is the thing being dragged
 *   market order  → the live mark
 */
const anchor = computed(() => {
  const open = positions.trade?.admin_entry_price
  if (open) return Number(open)
  if (order.orderType === 'limit' && order.limitPrice) return Number(order.limitPrice)
  return market.mark
})

/** A limit order's entry is an input; a filled position's entry is a record. */
const entryDraggable = computed(
  () => !positions.hasPosition && order.orderType === 'limit',
)

async function mountChart() {
  if (!chartEl.value || chart) return
  chart = useChartAdapter()
  await chart.mount(chartEl.value)
  chart.setEntryDraggable(entryDraggable.value)
  paintSeries()

  // Surface 2 of 3: dragging the lines on the chart.
  chart.onSLTPDrag(async (kind, price) => {
    if (kind === 'entry') {
      // Dragging the limit line *is* how the limit price is set. Round to the
      // same two decimals the ticket shows so the two never disagree by 1e-9.
      order.limitPrice = Math.round(price * 100) / 100
      syncPosition()
      syncChartLines()
      return
    }
    if (kind === 'sl') order.setSLFromPrice(price)
    else order.setTPFromPrice(price)
    // A drag on an open trade is a mid-trade amendment (spec §4).
    if (trading.hasOpenTrade) {
      await trading.amend(order.slPct, order.tpPct)
      await positions.load()
    }
  })

  syncChartLines()
}

function paintSeries() {
  if (!chart || !market.candles.length) return
  chart.setCandles(market.candles.map((c) => ({ ...c, time: c.time as never })))
}

onMounted(async () => {
  await Promise.all([trading.ensureTrades(), trading.loadPolicy(), market.start()])
  positions.start()
  // A reload mid-position must not land on an empty ticket.
  if (trading.openTrade) order.hydrateFromTrade(trading.openTrade)
  // The ticket and the chart must never disagree about the instrument.
  if (order.symbol !== market.symbol) await market.setSymbol(order.symbol)
  await mountChart()
})

onBeforeUnmount(() => {
  market.stop()
  positions.stop()
  chart?.destroy()
  chart = null
})

// On a phone the chart element only exists while its pane is showing, so it is
// mounted when that pane appears rather than once at page load.
watch(
  () => ui.chartPane,
  async (pane) => {
    if (pane !== 'chart') return
    await nextTick()
    await mountChart()
  },
)

watch(isDark, () => chart?.applyTheme())

watch(entryDraggable, (value) => {
  chart?.setEntryDraggable(value)
  syncPosition()
})

// The order always names the instrument on screen. The picker writes both, but
// a trade hydrated from the server can arrive with a different symbol.
watch(
  () => market.symbol,
  (symbol) => {
    order.symbol = symbol
  },
)

// A whole new series (symbol or timeframe changed) replaces the data outright;
// a tick only updates the last bar, which is why these are two watchers.
watch(
  () => market.revision,
  () => {
    paintSeries()
    // Snap to the newest candle. Switching BTC → AVAX otherwise leaves the
    // price scale where BTC was and the new candles $80k off-screen.
    chart?.resetView()
    syncPosition()
    syncChartLines()
  },
)

watch(
  () => market.lastCandle,
  (bar) => {
    if (bar) chart?.appendCandle({ ...bar, time: bar.time as never })
  },
  { deep: true },
)

watch(
  () => market.mark,
  (price) => {
    chart?.showMark(price)
    syncPosition()
    // While flat the SL/TP lines hang off the live price, so they move with it.
    if (!positions.hasPosition) syncChartLines()
  },
)

watch(
  () => [order.slPct, order.tpPct, order.leverage, order.side, order.basis, order.limitPrice],
  () => {
    syncPosition()
    syncChartLines()
  },
)

/** The open trade's real fill is the anchor; when flat, the live mark is. */
watch(
  () => positions.trade,
  () => {
    syncPosition()
    syncChartLines()
  },
)

function syncPosition() {
  const price = anchor.value
  if (price === null || chart?.isDragging) return
  order.entryPrice = price
  order.liquidationPrice =
    order.side === 'long' ? price * (1 - 1 / order.leverage) : price * (1 + 1 / order.leverage)
  chart?.showPosition({
    entry: price,
    liquidation: positions.hasPosition ? order.liquidationPrice : null,
    side: order.side,
  })
}

function syncChartLines() {
  // Repainting mid-drag would snap the held line back to the stored value.
  if (chart?.isDragging) return
  chart?.showSLTP(order.priceFor('sl'), order.priceFor('tp'))
}
</script>

<template>
  <div class="lg:h-[calc(100dvh-3.5rem)] lg:grid lg:grid-cols-[1fr_22rem] xl:grid-cols-[1fr_24rem]">
    <!-- Pane switcher: phones only. -->
    <div class="lg:hidden sticky top-14 z-20 bg-base/90 backdrop-blur border-b border-line p-2">
      <UiSegmented
        :model-value="ui.chartPane"
        :options="paneOptions"
        size="sm"
        @update:model-value="ui.showPane($event as any)"
      />
    </div>

    <!-- Chart column -->
    <section
      class="flex flex-col min-w-0 lg:h-full"
      :class="ui.chartPane === 'chart' ? '' : 'hidden lg:flex'"
    >
      <TerminalSymbolBar />

      <div
        ref="chartEl"
        class="chart-surface flex-1 min-h-[320px] lg:min-h-0 touch-pan-y relative"
      >
        <div
          v-if="market.loading && !market.candles.length"
          class="absolute inset-0 grid place-items-center text-xs text-ink-muted"
        >
          {{ t('common.loading') }}
        </div>

        <!-- Says what can be grabbed. The lines carry a ⇕ for the same reason:
             a draggable control nobody knows is draggable is a static one. -->
        <p
          class="absolute bottom-2 start-3 text-[0.65rem] text-ink-faint pointer-events-none
                 hidden sm:block"
        >
          {{ entryDraggable ? t('terminal.dragHintLimit') : t('terminal.dragHint') }}
        </p>
      </div>

      <TerminalPositionBar />

      <!-- Detail under the chart. On a wide screen there is room for the
           per-account breakdown without hiding it behind a navigation. -->
      <div class="hidden lg:flex flex-col border-t border-line max-h-[15rem] min-h-0">
        <div class="px-3 py-2 shrink-0">
          <UiSegmented v-model="detail" :options="detailOptions" size="sm" :block="false" />
        </div>
        <div class="overflow-y-auto min-h-0">
          <TerminalPositionsTable v-if="detail === 'positions'" />
          <div v-else class="p-4">
            <TerminalFanOutSummary v-if="trading.lastResult" :result="trading.lastResult" />
            <UiEmpty v-else icon="bolt" :title="t('fanout.noneTitle')" :body="t('fanout.noneBody')" />
          </div>
        </div>
      </div>

      <!-- Phones get the per-account table under the bar, scrolled with the
           page — but only when there is a position; an empty-state card between
           the chart and the ticket on a 390px screen is pure noise. -->
      <div v-if="positions.hasPosition" class="lg:hidden border-t border-line">
        <TerminalPositionsTable />
      </div>
    </section>

    <!-- Side rail on desktop; a pane on a phone. -->
    <aside
      class="border-s border-line lg:h-full lg:overflow-y-auto min-w-0"
      :class="ui.chartPane === 'ticket' ? '' : 'hidden lg:block'"
    >
      <TerminalTicket />
      <div class="hidden lg:block border-t border-line">
        <MarketWatchlist variant="compact" />
      </div>
      <div class="hidden lg:block border-t border-line">
        <TerminalAccountsPane />
      </div>
    </aside>

    <!-- Routing list and watchlist share the phone's third pane; both are
         "what else is going on" rather than part of the order itself. -->
    <section class="lg:hidden" :class="ui.chartPane === 'accounts' ? '' : 'hidden'">
      <TerminalAccountsPane />
      <div class="border-t border-line">
        <MarketWatchlist variant="compact" />
      </div>
    </section>
  </div>
</template>
