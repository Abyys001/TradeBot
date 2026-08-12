<script setup lang="ts">
/**
 * The last few trades, one line each: what was sent, how many accounts took it,
 * how long the fan-out ran, and what it made.
 *
 * The fan-out column is the one to watch — it is the spec §4 promise measured
 * on every single action, and it turns amber the moment a trade goes over
 * budget rather than waiting for someone to audit the log.
 */
const { t } = useI18n()
const localePath = useLocalePath()
const trading = useTradingStore()
const { money, ms, dateTime } = useFormat()

const rows = computed(() =>
  trading.trades.slice(0, 6).map((trade) => {
    const filled = trade.legs.filter((l) => l.ok).length
    const pnl = trade.legs.reduce((sum, l) => sum + Number(l.pnl ?? 0), 0)
    return {
      trade,
      filled,
      failed: trade.legs.length - filled,
      pnl,
      over: (trade.fanout_ms ?? 0) > 1000,
    }
  }),
)
</script>

<template>
  <UiCard :title="t('dashboard.recentTrades')" flush>
    <template #actions>
      <NuxtLink :to="localePath('/history')" class="btn-ghost btn-sm">
        {{ t('dashboard.viewAll') }}
      </NuxtLink>
    </template>

    <ul v-if="rows.length" class="divide-y divide-line">
      <li
        v-for="row in rows"
        :key="row.trade.id"
        class="px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-1.5"
      >
        <span
          class="w-1.5 h-1.5 rounded-full shrink-0"
          :class="row.trade.side === 'long' ? 'bg-long' : 'bg-short'"
          :aria-label="t(`side.${row.trade.side}`)"
        />
        <span class="num text-sm font-medium">{{ row.trade.symbol }}</span>
        <span class="text-xs" :class="row.trade.side === 'long' ? 'text-long' : 'text-short'">
          {{ t(`side.${row.trade.side}`) }} {{ row.trade.leverage }}x
        </span>

        <span class="text-xs text-ink-muted">
          {{ t('dashboard.legsFilled', { filled: row.filled, total: row.trade.legs.length }) }}
        </span>

        <span
          class="num text-xs ms-auto"
          :class="row.over ? 'text-signal' : 'text-ink-muted'"
          :title="t('dashboard.fanoutTitle')"
        >
          {{ ms(row.trade.fanout_ms) }}
        </span>

        <span
          class="num text-sm w-20 text-end"
          :class="row.pnl === 0 ? 'text-ink-faint' : row.pnl > 0 ? 'text-long' : 'text-short'"
        >
          {{ row.pnl === 0 ? '—' : `${row.pnl > 0 ? '+' : ''}${money(row.pnl)}` }}
        </span>

        <span class="num text-[0.65rem] text-ink-faint w-full sm:w-auto sm:ms-0">
          {{ dateTime(row.trade.opened_at) }}
        </span>
      </li>
    </ul>

    <UiEmpty
      v-else
      icon="history"
      :title="t('dashboard.noTradesTitle')"
      :body="t('dashboard.noTradesBody')"
    />
  </UiCard>
</template>
