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
    <h1 class="mb-1 text-xl font-semibold text-zinc-100">{{ t('copy.title') }}</h1>
    <p class="mb-6 text-sm text-zinc-500">{{ t('copy.subtitle') }}</p>

    <div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard :label="t('copy.netPnl')" :value="'$' + fmt(copy.summary?.net_pnl)" :accent="netAccent" :sub="t('copy.afterFees')" />
      <StatCard :label="t('copy.realizedPnl')" :value="'$' + fmt(copy.summary?.realized_pnl)" />
      <StatCard :label="t('copy.feesOwed')" :value="'$' + fmt(copy.summary?.fees_owed)" accent="amber" :sub="t('copy.platformShare')" />
      <StatCard :label="t('copy.openTrades')" :value="copy.summary?.open_trades ?? 0" :sub="t('copy.closedN', { n: copy.summary?.closed_trades ?? 0 })" />
    </div>

    <div class="mb-6">
      <div class="mb-2 text-sm font-medium text-zinc-300">{{ t('copy.equityCurve') }}</div>
      <EquityCurve :series="equitySeries" :height="160" />
    </div>

    <div class="overflow-x-auto rounded-xl border border-zinc-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-zinc-900/70 text-xs uppercase text-zinc-500">
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
        <tbody class="divide-y divide-zinc-800">
          <tr v-for="tr in copy.trades" :key="tr.id" class="text-zinc-300">
            <td class="px-4 py-2 font-medium text-zinc-100">{{ tr.pair }}</td>
            <td class="px-4 py-2">
              <span :class="tr.side === 'buy' ? 'text-emerald-400' : 'text-red-400'">{{ tr.side?.toUpperCase() }}</span>
            </td>
            <td class="px-4 py-2 tabular-nums">{{ fmt(tr.entry_price ?? undefined, 4) }}</td>
            <td class="px-4 py-2 tabular-nums">{{ tr.exit_price ? fmt(tr.exit_price, 4) : '—' }}</td>
            <td class="px-4 py-2 tabular-nums" :class="Number(tr.gross_pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ fmt(tr.gross_pnl) }}
            </td>
            <td class="px-4 py-2 tabular-nums text-amber-400">{{ fmt(tr.platform_share_amount) }}</td>
            <td class="px-4 py-2">
              <span :class="tr.status === 'open' ? 'text-sky-400' : 'text-zinc-500'">{{ tr.status }}</span>
            </td>
          </tr>
          <tr v-if="!copy.loading && copy.trades.length === 0">
            <td colspan="7" class="px-4 py-8 text-center text-zinc-600">{{ t('copy.noTrades') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
