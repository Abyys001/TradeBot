<script setup lang="ts">
/**
 * Closed trades, under the chart, beside the open position (spec §8).
 *
 * The full log lives on /history — per-account filters, per-leg expansion,
 * summary figures. This is deliberately not that: it is the last handful of
 * trades in the place the admin is already looking, because "what did the
 * previous entry on this pair do" is a question asked *while* sizing the next
 * one, and sending someone to another page to answer it loses the chart.
 *
 * PnL is summed from the legs rather than read off the trade: spec §5 makes
 * every account's dollar size differ, so the trade's own number would be a
 * blend that matches no account's statement.
 */
const { t } = useI18n()
const api = useApi()
const localePath = useLocalePath()
const trading = useTradingStore()
const { money, dateTime } = useFormat()

/** Enough to see a pattern, few enough to fit without its own scrollbar. */
const LIMIT = 8

const trades = ref<Trade[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  try {
    trades.value = (await api.trades()).slice(0, LIMIT)
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

// A trade that just closed belongs in the list without a refresh — this pane is
// most often read straight after closing one.
watch(() => trading.lastResult, load)

function pnlOf(trade: Trade) {
  return trade.legs.reduce((sum, leg) => sum + Number(leg.pnl ?? 0), 0)
}

/** Only a settled trade has a PnL worth showing; an open one is still moving. */
function isSettled(trade: Trade) {
  return trade.legs.some((leg) => leg.pnl !== null)
}

function tone(value: number) {
  return value === 0 ? 'text-ink-faint' : value > 0 ? 'text-long' : 'text-short'
}
</script>

<template>
  <div>
    <div v-if="loading" class="p-4 text-xs text-ink-faint">{{ t('common.loading') }}</div>

    <p v-else-if="error" class="p-4 text-xs text-signal">{{ error }}</p>

    <UiEmpty
      v-else-if="!trades.length"
      icon="history"
      :title="t('dashboard.noTradesTitle')"
      :body="t('dashboard.noTradesBody')"
    />

    <template v-else>
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-line">
            <th class="label text-start font-normal px-4 py-2">{{ t('ticket.symbol') }}</th>
            <th class="label text-start font-normal py-2">{{ t('terminal.recent.side') }}</th>
            <th class="label text-end font-normal py-2">{{ t('terminal.recent.opened') }}</th>
            <th class="label text-end font-normal py-2">{{ t('terminal.recent.accounts') }}</th>
            <th class="label text-end font-normal px-4 py-2">{{ t('history.pnl') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="trade in trades" :key="trade.id" class="border-b border-line/50">
            <td class="px-4 py-2 font-medium">{{ trade.symbol }}</td>
            <td class="py-2">
              <span :class="trade.side === 'long' ? 'text-long' : 'text-short'">
                {{ t(`side.${trade.side}`) }}
              </span>
              <span class="text-ink-faint num ms-1.5">{{ trade.leverage }}x</span>
            </td>
            <td class="py-2 text-end text-ink-muted whitespace-nowrap">
              {{ dateTime(trade.opened_at) }}
            </td>
            <td class="py-2 text-end num text-ink-muted">{{ trade.legs.length }}</td>
            <td class="px-4 py-2 text-end num" :class="tone(pnlOf(trade))">
              <template v-if="isSettled(trade)">
                {{ pnlOf(trade) >= 0 ? '+' : '' }}{{ money(pnlOf(trade)) }}
              </template>
              <span v-else class="text-ink-faint">{{ t('terminal.recent.stillOpen') }}</span>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="px-4 py-2">
        <NuxtLink :to="localePath('/history')" class="text-xs text-brand hover:underline">
          {{ t('dashboard.viewAll') }}
        </NuxtLink>
      </div>
    </template>
  </div>
</template>
