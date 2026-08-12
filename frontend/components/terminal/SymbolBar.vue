<script setup lang="ts">
/**
 * The instrument header: what is being traded, at what price, from where.
 *
 * The provenance badge is not decoration. When no exchange is reachable the
 * backend serves a synthetic series, and this bar is where that is admitted —
 * in the same line as the price, not in a tooltip somewhere. A trading screen
 * that cannot say whether its price is real is worse than one showing none.
 */
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
  const list = market.symbols
  if (!needle) return list
  return list.filter((s) => s.symbol.includes(needle) || s.base.includes(needle))
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
  <div class="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 h-14 border-b border-line shrink-0">
    <!-- Symbol -->
    <div class="relative shrink-0">
      <button
        class="flex items-center gap-1.5 rounded-lg px-2 py-1 hover:bg-raised transition-colors"
        :aria-expanded="picking"
        @click="picking = !picking"
      >
        <span class="num text-sm font-semibold">{{ market.symbol }}</span>
        <UiIcon name="chevronDown" :size="14" class="text-ink-faint" />
      </button>

      <!-- Click-away layer: a dropdown that only closes by re-clicking the
           trigger is a dropdown left open over the chart. -->
      <div v-if="picking" class="fixed inset-0 z-30" @click="picking = false" />

      <div
        v-if="picking"
        class="absolute z-40 mt-1 w-60 panel shadow-lift p-2 max-h-80 overflow-y-auto"
      >
        <input
          v-model="query"
          class="field text-xs py-1.5"
          :placeholder="t('terminal.searchSymbol')"
          spellcheck="false"
          @keyup.enter="submitQuery"
        />
        <ul class="mt-1.5">
          <li v-for="option in matches" :key="option.symbol">
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
          <li v-if="!matches.length" class="px-2 py-2 text-xs text-ink-muted">
            {{ t('terminal.pressEnterToUse', { symbol: query.toUpperCase() }) }}
          </li>
        </ul>
      </div>
    </div>

    <!-- Price -->
    <div class="min-w-0">
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
    <div class="ms-auto flex items-center gap-1 sm:gap-2">
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

      <!-- Provenance. Amber whenever the series is not a real feed. -->
      <UiBadge
        :tone="market.live ? 'neutral' : 'signal'"
        :title="market.live ? t('terminal.sourceHint', { source: market.source }) : t('terminal.placeholderHint')"
      >
        <span class="hidden md:inline">
          {{ market.live ? market.source : t('terminal.placeholderData') }}
        </span>
        <span class="md:hidden">{{ market.live ? '●' : '○' }}</span>
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
