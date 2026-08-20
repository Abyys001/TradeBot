<script setup lang="ts">
/**
 * The instrument header: what is being traded, at what price, from where.
 *
 * The provenance badge is not decoration: it names the exchange the price on
 * this line came from. Every price shown here came from one — there is no
 * synthetic series behind the panel any more. When no exchange is reachable
 * the badge says so and the number greys out, in the same line as the price
 * rather than in a tooltip somewhere.
 */
import { PINNED_SYMBOLS } from '~/stores/market'
const { t } = useI18n()
const market = useMarketStore()
const order = useOrderStore()
const trading = useTradingStore()
const { money, pct, since } = useFormat()

const picking = ref(false)
const query = ref('')

const intervals: Interval[] = ['1m', '5m', '15m', '1h', '4h', '1d']

const matches = computed(() => {
  const needle = query.value.trim().toUpperCase()
  const known = new Map(market.symbols.map((s) => [s.symbol, s]))
  const hit = (s: SymbolInfo) => !needle || s.symbol.includes(needle) || s.base.includes(needle)
  // The pins are the platform's list, not the venue's: they head the picker in
  // their canonical order whether or not the catalogue has answered yet, so a
  // slow or partial `/symbols/` cannot make one of them vanish.
  const pinned = PINNED_SYMBOLS.map(
    (symbol) => known.get(symbol) ?? { symbol, ...splitSymbol(symbol) },
  ).filter(hit)
  const rest = market.symbols.filter((s) => !PINNED_SYMBOLS.includes(s.symbol) && hit(s))
  return { pinned, rest }
})

/** Direction of the last price move, for the flash on the number. */
const direction = ref<'up' | 'down' | null>(null)
watch(
  () => market.price,
  (next, previous) => {
    if (next === null || previous === null || next === previous) return
    direction.value = next > previous ? 'up' : 'down'
  },
)

/**
 * The venue this line is quoting, in the admin's words.
 *
 * When the feed is pinned, the pin is the answer — the whole point of a pin is
 * that the chart cannot change venue, so the badge names the pin rather than
 * whoever happened to answer. Unpinned, it names the live source (stream) or
 * the last polled one.
 */
const feedName = computed(() => {
  if (!market.live) return ''
  const slug = market.pinnedSource || (market.streaming ? market.streamSource : market.source)
  return exchangeLabel(slug)
})

const feedHint = computed(() => {
  if (!market.live) return t('terminal.feedDownHint')
  const name = exchangeLabel(market.pinnedSource || market.source || market.streamSource)
  const ms = Math.round(market.providerMs ?? 0)
  if (market.pinnedSource) {
    return t('terminal.pinnedFeedHint', {
      name,
      mode: market.streaming ? t('terminal.streaming') : t('terminal.polling'),
      ms,
    })
  }
  return market.streaming
    ? t('terminal.streamHint', { source: name })
    : t('terminal.sourceHint', { source: name, ms })
})

/**
 * How far behind the chart is, in the admin's terms.
 *
 * Stored bars are named as such — that is a different failure from a live feed
 * that has simply gone quiet, and the fix is different too.
 */
const chartStaleHint = computed(() => {
  const last = market.lastCandle
  const age = last ? since(new Date(last.time * 1000).toISOString()) : '—'
  return market.stored
    ? t('terminal.chartStoredHint', { age })
    : t('terminal.chartDelayedHint', { age })
})

async function choose(symbol: string) {
  picking.value = false
  query.value = ''
  await market.setSymbol(symbol)
  // The ticket follows the chart: routing an order for a symbol other than the
  // one on screen is the single worst thing this page could do.
  order.symbol = market.symbol
}

/** Typed free-text: exchanges list far more pairs than the picker curates. */
async function submitQuery() {
  if (!query.value.trim()) return
  await choose(query.value)
}
</script>

<template>
  <div class="flex items-center gap-1.5 xs:gap-2 sm:gap-3 px-2 xs:px-3 sm:px-4 h-14
              border-b border-line shrink-0 min-w-0">
    <!-- Symbol -->
    <div class="relative min-w-0">
      <button
        class="flex items-center gap-1.5 rounded-lg px-1.5 xs:px-2 py-1 max-w-full
               hover:bg-raised transition-colors"
        :aria-expanded="picking"
        @click="picking = !picking"
      >
        <span class="num text-sm font-semibold truncate">{{ market.symbol }}</span>
        <UiIcon name="chevronDown" :size="14" class="text-ink-faint shrink-0" />
      </button>

      <!-- Click-away layer: a dropdown that only closes by re-clicking the
           trigger is a dropdown left open over the chart. -->
      <div v-if="picking" class="fixed inset-0 z-30" @click="picking = false" />

      <div
        v-if="picking"
        class="absolute z-40 mt-1 w-[min(15rem,calc(100vw-2rem))] panel shadow-lift p-2
               max-h-80 overflow-y-auto"
      >
        <input
          v-model="query"
          class="field text-xs py-1.5"
          :placeholder="t('terminal.searchSymbol')"
          spellcheck="false"
          @keyup.enter="submitQuery"
        />
        <ul class="mt-1.5">
          <template v-for="option in matches.pinned" :key="option.symbol">
            <li>
              <button
                class="w-full text-start px-2 py-1.5 rounded-md text-xs hover:bg-raised
                       flex items-center gap-2"
                :class="option.symbol === market.symbol ? 'text-brand' : ''"
                @click="choose(option.symbol)"
              >
                <span class="num font-medium">{{ option.base }}</span>
                <span class="text-ink-faint">{{ option.quote }}</span>
              </button>
            </li>
          </template>
          <li v-if="matches.pinned.length && matches.rest.length" class="my-1 border-t border-line" />
          <template v-for="option in matches.rest" :key="option.symbol">
            <li>
              <button
                class="w-full text-start px-2 py-1.5 rounded-md text-xs hover:bg-raised
                       flex items-center gap-2"
                :class="option.symbol === market.symbol ? 'text-brand' : ''"
                @click="choose(option.symbol)"
              >
                <span class="num font-medium">{{ option.base }}</span>
                <span class="text-ink-faint">{{ option.quote }}</span>
              </button>
            </li>
          </template>
          <li v-if="!matches.pinned.length && !matches.rest.length" class="px-2 py-2 text-xs text-ink-muted">
            {{ t('terminal.pressEnterToUse', { symbol: query.toUpperCase() }) }}
          </li>
        </ul>
      </div>
    </div>

    <!-- Price -->
    <div class="shrink-0">
      <p
        class="num text-sm font-semibold transition-colors"
        :class="[
          market.stale ? 'text-ink-faint' : direction === 'up' ? 'text-long' : direction === 'down' ? 'text-short' : '',
        ]"
      >
        {{ market.mark === null ? '—' : money(market.mark, 2) }}
      </p>
      <p
        v-if="market.changePct !== null"
        class="num text-[0.65rem]"
        :class="market.changePct >= 0 ? 'text-long' : 'text-short'"
      >
        {{ market.changePct >= 0 ? '+' : '' }}{{ pct(market.changePct) }} {{ t('terminal.change24h') }}
      </p>
    </div>

    <UiBadge :tone="order.side === 'long' ? 'long' : 'short'" class="hidden sm:inline-flex">
      {{ t(`side.${order.side}`) }} {{ order.leverage }}x
    </UiBadge>

    <!-- Timeframe -->
    <div class="ms-auto shrink-0 flex items-center gap-1 sm:gap-2">
      <div class="hidden sm:flex items-center gap-0.5 rounded-lg bg-sunken border border-line p-0.5">
        <button
          v-for="option in intervals"
          :key="option"
          class="num text-[0.7rem] px-1.5 py-0.5 rounded-md transition-colors"
          :class="
            market.interval === option
              ? 'bg-raised text-ink'
              : 'text-ink-muted hover:text-ink'
          "
          @click="market.setTimeframe(option)"
        >
          {{ option }}
        </button>
      </div>

      <select
        class="field sm:hidden w-auto text-xs py-1"
        :value="market.interval"
        :aria-label="t('terminal.interval')"
        @change="market.setTimeframe(($event.target as HTMLSelectElement).value as Interval)"
      >
        <option v-for="option in intervals" :key="option" :value="option">{{ option }}</option>
      </select>

      <!-- Provenance, and how fresh it is. A streaming feed and a polled one
           are both real exchange data but they are not the same promise: the
           first is the venue's own tick, the second is up to 15s old. The dot
           pulses only while bars are actually being pushed. When the feed is
           pinned the badge names the pin — that venue is the only one allowed
           to answer — and marks it as pinned. -->
      <UiBadge
        :tone="market.live ? (market.streaming ? 'ok' : 'neutral') : 'signal'"
        :title="feedHint"
      >
        <span
          v-if="market.streaming"
          class="w-1.5 h-1.5 rounded-full bg-current animate-pulse me-1.5 shrink-0"
          aria-hidden="true"
        />
        <span class="hidden md:inline">
          {{ market.live ? feedName : t('terminal.feedDown') }}
          <span v-if="market.live && market.pinnedSource" class="opacity-70">· {{ t('terminal.pinned') }}</span>
        </span>
        <span class="md:hidden">{{ market.live ? '●' : '○' }}</span>
      </UiBadge>

      <!-- The bars stopped arriving while the price kept coming. Both are real
           and they are no longer the same moment, so the panel says so rather
           than letting the ticker's freshness vouch for the chart. -->
      <UiBadge v-if="market.chartStale && market.candles.length" tone="signal" :title="chartStaleHint">
        <span class="hidden md:inline">{{ t('terminal.chartDelayed') }}</span>
        <span class="md:hidden">⌛</span>
      </UiBadge>

      <UiBadge v-if="trading.halted" tone="signal" dot class="hidden lg:inline-flex">
        {{ t('policy.stopAllActive') }}
      </UiBadge>

      <span v-if="market.lastTickAt" class="label hidden xl:inline whitespace-nowrap">
        {{ since(new Date(market.lastTickAt).toISOString()) }}
      </span>
    </div>
  </div>
</template>
