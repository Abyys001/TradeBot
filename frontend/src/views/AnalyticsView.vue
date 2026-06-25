<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { useOptimizerStore } from '../stores/optimizer'
import { useStrategyStore } from '../stores/strategy'
import EquityCurve from '../modules/backtest/EquityCurve.vue'

interface AnalyticsRun {
  backtest_id: number
  strategy_id: number
  strategy_name: string
  symbol: string
  net_pnl?: number
  sharpe_ratio?: number
  profit_factor?: number
  max_drawdown?: number
  equity_series?: number[]
}

const { t } = useI18n()
const router = useRouter()
const optimizer = useOptimizerStore()
const strategies = useStrategyStore()
const runs = ref<AnalyticsRun[]>([])
const best = ref<AnalyticsRun | null>(null)
const worst = ref<AnalyticsRun | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    await strategies.fetchAll()
    const { data } = await api.get<{ runs: AnalyticsRun[]; best: AnalyticsRun; worst: AnalyticsRun }>(
      '/analytics/',
    )
    runs.value = data.runs
    best.value = data.best
    worst.value = data.worst
  } catch {
    error.value = t('analytics.loadFailed')
  } finally {
    loading.value = false
  }
})

function goToBacktest(run: AnalyticsRun) {
  router.push({
    name: 'strategy-detail',
    params: { id: run.strategy_id },
    query: { mode: 'backtest', backtestId: String(run.backtest_id) },
  })
}

async function runPortfolio() {
  const items = strategies.strategies.slice(0, 3).map((s) => ({
    strategy_id: s.id,
    symbol: (s.live_config?.symbols?.[0] || s.symbol).replace(/-.*$/, ''),
  }))
  if (!items.length) return
  await optimizer.runPortfolio({ strategies: items, network: 'mainnet', interval: '1h' })
}
</script>

<template>
  <div class="p-4 space-y-6 max-w-5xl">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-zinc-100">{{ t('analytics.title') }}</h1>
      <button
        v-if="strategies.strategies.length"
        type="button"
        class="text-xs rounded border border-zinc-700 px-2 py-1 text-zinc-400 hover:text-zinc-200"
        :disabled="optimizer.loading"
        @click="runPortfolio"
      >
        {{ t('analytics.portfolio') }}
      </button>
    </div>
    <div v-if="optimizer.portfolioResult" class="rounded-xl border border-zinc-800 p-3 text-sm text-zinc-300">
      {{ t('analytics.portfolioPnl') }}: {{ (optimizer.portfolioResult as Record<string, number>).combined_net_pnl }}
    </div>
    <div v-if="loading" class="text-sm text-zinc-500">{{ t('overview.loading') }}</div>
    <div v-else-if="error" class="text-sm text-red-400">{{ error }}</div>
    <div v-else-if="!runs.length" class="text-sm text-zinc-500">{{ t('analytics.empty') }}</div>
    <template v-else>
      <div class="grid md:grid-cols-2 gap-4">
        <button
          v-if="best"
          type="button"
          class="rounded-xl border border-zinc-800 p-4 text-start hover:border-zinc-700 transition-colors"
          @click="goToBacktest(best)"
        >
          <div class="text-xs text-zinc-500 mb-1">{{ t('analytics.best') }}</div>
          <div class="text-sm text-zinc-200">{{ best.strategy_name }} · {{ best.symbol }}</div>
          <div class="text-emerald-400 font-semibold">{{ best.net_pnl?.toFixed(2) }}</div>
          <EquityCurve v-if="best.equity_series?.length" :series="best.equity_series" class="mt-3" />
        </button>
        <button
          v-if="worst"
          type="button"
          class="rounded-xl border border-zinc-800 p-4 text-start hover:border-zinc-700 transition-colors"
          @click="goToBacktest(worst)"
        >
          <div class="text-xs text-zinc-500 mb-1">{{ t('analytics.worst') }}</div>
          <div class="text-sm text-zinc-200">{{ worst.strategy_name }} · {{ worst.symbol }}</div>
          <div class="text-red-400 font-semibold">{{ worst.net_pnl?.toFixed(2) }}</div>
          <EquityCurve v-if="worst.equity_series?.length" :series="worst.equity_series" class="mt-3" />
        </button>
      </div>
      <div class="rounded-xl border border-zinc-800 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="text-xs text-zinc-500 uppercase bg-zinc-900/50">
            <tr>
              <th class="px-3 py-2 text-start">{{ t('strategies.name') }}</th>
              <th class="px-3 py-2 text-start">{{ t('data.coin') }}</th>
              <th class="px-3 py-2 text-end">PnL</th>
              <th class="px-3 py-2 text-end">Sharpe</th>
              <th class="px-3 py-2 text-end">PF</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in runs"
              :key="r.backtest_id"
              class="border-t border-zinc-800/50 cursor-pointer hover:bg-zinc-900/50"
              @click="goToBacktest(r)"
            >
              <td class="px-3 py-2 text-zinc-300">{{ r.strategy_name }}</td>
              <td class="px-3 py-2 text-zinc-500">{{ r.symbol }}</td>
              <td class="px-3 py-2 text-end" :class="(r.net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ r.net_pnl?.toFixed(2) ?? '—' }}
              </td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ r.sharpe_ratio?.toFixed(2) ?? '—' }}</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ r.profit_factor?.toFixed(2) ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
