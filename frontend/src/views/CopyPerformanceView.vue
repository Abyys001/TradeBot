<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCopyTradingStore } from '../stores/copytrading'
import StatCard from '../modules/overview/StatCard.vue'
import EquityCurve from '../modules/backtest/EquityCurve.vue'

const { t } = useI18n()
const copy = useCopyTradingStore()

const equitySeries = computed(() => copy.equity.map((p) => Number(p.equity)))
const netAccent = computed(() => {
  const v = Number(copy.summary?.net_pnl ?? 0)
  return v > 0 ? 'green' : v < 0 ? 'red' : 'neutral'
})

function fmt(v: string | number | undefined, dp = 2) {
  return Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: dp })
}

onMounted(() => copy.fetchMy())
</script>

<template>
  <div class="mx-auto max-w-5xl p-6">
    <h1 class="mb-1 text-xl font-semibold text-fg">{{ t('copy.title') }}</h1>
    <p class="mb-6 text-sm text-fg-muted">{{ t('copy.subtitle') }}</p>

    <div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard :label="t('copy.netPnl')" :value="'$' + fmt(copy.summary?.net_pnl)" :accent="netAccent" :sub="t('copy.afterFees')" />
      <StatCard :label="t('copy.realizedPnl')" :value="'$' + fmt(copy.summary?.realized_pnl)" />
      <StatCard :label="t('copy.feesOwed')" :value="'$' + fmt(copy.summary?.fees_owed)" accent="amber" :sub="t('copy.platformShare')" />
      <StatCard :label="t('copy.openTrades')" :value="copy.summary?.open_trades ?? 0" :sub="t('copy.closedN', { n: copy.summary?.closed_trades ?? 0 })" />
    </div>

    <div class="mb-6">
      <div class="mb-2 text-sm font-medium text-fg">{{ t('copy.equityCurve') }}</div>
      <EquityCurve :series="equitySeries" :height="160" />
    </div>

    <div class="overflow-x-auto rounded-xl border border-border">
      <table class="w-full text-left text-sm">
        <thead class="bg-surface-raised text-xs uppercase text-fg-muted">
          <tr>
            <th class="px-4 py-3">{{ t('copy.pair') }}</th>
            <th class="px-4 py-3">{{ t('copy.side') }}</th>
            <th class="px-4 py-3">{{ t('copy.entry') }}</th>
            <th class="px-4 py-3">{{ t('copy.exit') }}</th>
            <th class="px-4 py-3">{{ t('copy.pnl') }}</th>
            <th class="px-4 py-3">{{ t('copy.fee') }}</th>
            <th class="px-4 py-3">{{ t('copy.status') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          <tr v-for="tr in copy.trades" :key="tr.id" class="text-fg">
            <td class="px-4 py-2 font-medium text-fg">{{ tr.pair }}</td>
            <td class="px-4 py-2">
              <span :class="tr.side === 'buy' ? 'text-positive' : 'text-negative'">{{ tr.side?.toUpperCase() }}</span>
            </td>
            <td class="px-4 py-2 tabular-nums">{{ fmt(tr.entry_price ?? undefined, 4) }}</td>
            <td class="px-4 py-2 tabular-nums">{{ tr.exit_price ? fmt(tr.exit_price, 4) : '—' }}</td>
            <td class="px-4 py-2 tabular-nums" :class="Number(tr.gross_pnl) >= 0 ? 'text-positive' : 'text-negative'">
              {{ fmt(tr.gross_pnl) }}
            </td>
            <td class="px-4 py-2 tabular-nums text-warning">{{ fmt(tr.platform_share_amount) }}</td>
            <td class="px-4 py-2">
              <span :class="tr.status === 'open' ? 'text-info' : 'text-fg-muted'">{{ tr.status }}</span>
            </td>
          </tr>
          <tr v-if="!copy.loading && copy.trades.length === 0">
            <td colspan="7" class="px-4 py-8 text-center text-fg-muted">{{ t('copy.noTrades') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
