<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAnalyticsStore, type AnalyticsRun } from '../stores/analytics'
import { useBacktestStore } from '../stores/backtest'
import { useOptimizerStore } from '../stores/optimizer'
import { useStrategyStore } from '../stores/strategy'
import EquityCurve from '../modules/backtest/EquityCurve.vue'

type SortKey = 'net_pnl' | 'sharpe_ratio' | 'created_at'

const { t } = useI18n()
const router = useRouter()
const analytics = useAnalyticsStore()
const backtestStore = useBacktestStore()
const optimizer = useOptimizerStore()
const strategies = useStrategyStore()

const sortKey = ref<SortKey>('created_at')
const sortAsc = ref(false)

const best = computed(() => analytics.data?.best ?? null)
const worst = computed(() => analytics.data?.worst ?? null)
const monthly = computed(() => analytics.data?.monthly ?? [])
const byAsset = computed(() => analytics.data?.by_asset ?? [])
const summary = computed(() => analytics.summary)

const sortedRuns = computed(() => {
  const list = [...analytics.runs]
  const key = sortKey.value
  list.sort((a, b) => {
    const av = a[key] ?? 0
    const bv = b[key] ?? 0
    if (key === 'created_at') {
      return sortAsc.value
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av))
    }
    return sortAsc.value ? Number(av) - Number(bv) : Number(bv) - Number(av)
  })
  return list
})

const emptyHint = computed(() => {
  if (analytics.runs.length) return null
  const all = backtestStore.backtests
  if (all.some((b) => b.status === 'pending' || b.status === 'running')) {
    return 'pending'
  }
  if (all.some((b) => b.status === 'failed')) {
    return 'failed'
  }
  return 'none'
})

const monthlyMax = computed(() => {
  const vals = monthly.value.map((m) => Math.abs(m.net_pnl))
  return vals.length ? Math.max(...vals) : 1
})

onMounted(async () => {
  await strategies.fetchAll()
  await backtestStore.fetchAll()
  await analytics.fetch()
  if (backtestStore.activeBacktests.length || emptyHint.value === 'pending') {
    analytics.startPollingWhileActive()
  }
})

onUnmounted(() => {
  analytics.stopPolling()
})

function goToBacktest(run: AnalyticsRun) {
  router.push({
    name: 'strategy-detail',
    params: { id: run.strategy_id },
    query: { backtestId: String(run.backtest_id) },
  })
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = key === 'created_at' ? false : true
  }
}

async function runPortfolio() {
  const items = strategies.strategies.slice(0, 3).map((s) => ({
    strategy_id: s.id,
    symbol: (s.live_config?.symbols?.[0] || s.symbol).replace(/-.*$/, ''),
  }))
  if (!items.length) return
  await optimizer.runPortfolio({ strategies: items, network: 'mainnet', interval: '1h' })
}

function fmtDate(iso: string) {
  return iso.slice(0, 10)
}
</script>

<template>
  <div class="p-4 space-y-6 max-w-6xl">
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

    <div v-if="analytics.loading && !analytics.data" class="text-sm text-zinc-500">{{ t('overview.loading') }}</div>
    <div v-else-if="analytics.error" class="text-sm text-red-400">{{ t('analytics.loadFailed') }}</div>

    <template v-else-if="!analytics.runs.length">
      <div class="rounded-xl border border-zinc-800 p-6 text-sm text-zinc-500 space-y-3">
        <p v-if="emptyHint === 'pending'">{{ t('analytics.emptyPending') }}</p>
        <p v-else-if="emptyHint === 'failed'">{{ t('analytics.emptyFailed') }}</p>
        <p v-else>{{ t('analytics.empty') }}</p>
        <div class="flex gap-3 text-xs">
          <RouterLink to="/strategies" class="text-violet-400 hover:underline">{{ t('nav.strategies') }}</RouterLink>
          <RouterLink to="/data" class="text-violet-400 hover:underline">{{ t('nav.data') }}</RouterLink>
        </div>
      </div>
    </template>

    <template v-else>
      <div v-if="summary" class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div class="rounded-xl border border-zinc-800 p-3">
          <div class="text-xs text-zinc-500">{{ t('analytics.totalRuns') }}</div>
          <div class="text-lg font-semibold text-zinc-100">{{ summary.count }}</div>
        </div>
        <div class="rounded-xl border border-zinc-800 p-3">
          <div class="text-xs text-zinc-500">{{ t('analytics.totalPnl') }}</div>
          <div
            class="text-lg font-semibold"
            :class="summary.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'"
          >
            {{ summary.totalPnl.toFixed(2) }}
          </div>
        </div>
        <div class="rounded-xl border border-zinc-800 p-3">
          <div class="text-xs text-zinc-500">{{ t('analytics.avgSharpe') }}</div>
          <div class="text-lg font-semibold text-zinc-100">
            {{ summary.avgSharpe?.toFixed(2) ?? '—' }}
          </div>
        </div>
        <div class="rounded-xl border border-zinc-800 p-3">
          <div class="text-xs text-zinc-500">{{ t('analytics.worstDrawdown') }}</div>
          <div class="text-lg font-semibold text-red-400">
            {{ summary.worstDrawdown != null ? summary.worstDrawdown.toFixed(2) : '—' }}
          </div>
        </div>
        <div class="rounded-xl border border-zinc-800 p-3">
          <div class="text-xs text-zinc-500">{{ t('analytics.totalFunding') }}</div>
          <div class="text-lg font-semibold text-zinc-100">{{ summary.totalFunding.toFixed(2) }}</div>
        </div>
      </div>

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

      <div v-if="monthly.length" class="rounded-xl border border-zinc-800 p-4">
        <h2 class="text-sm font-medium text-zinc-300 mb-3">{{ t('analytics.monthly') }}</h2>
        <div class="flex items-end gap-2 h-24">
          <div
            v-for="m in monthly"
            :key="m.month"
            class="flex-1 flex flex-col items-center gap-1 min-w-0"
          >
            <div
              class="w-full rounded-t bg-violet-600/80 min-h-[4px]"
              :style="{ height: `${Math.max(4, (Math.abs(m.net_pnl) / monthlyMax) * 72)}px` }"
              :class="m.net_pnl >= 0 ? 'bg-emerald-600/80' : 'bg-red-600/80'"
            />
            <span class="text-[10px] text-zinc-500 truncate w-full text-center">{{ m.month }}</span>
          </div>
        </div>
      </div>

      <div v-if="byAsset.length" class="rounded-xl border border-zinc-800 overflow-hidden">
        <div class="px-3 py-2 border-b border-zinc-800 bg-zinc-900/50 text-xs font-medium text-zinc-400">
          {{ t('analytics.byAsset') }}
        </div>
        <table class="w-full text-sm">
          <thead class="text-xs text-zinc-500 uppercase bg-zinc-900/30">
            <tr>
              <th class="px-3 py-2 text-start">{{ t('data.coin') }}</th>
              <th class="px-3 py-2 text-end">PnL</th>
              <th class="px-3 py-2 text-end">{{ t('backtest.winRate') }}</th>
              <th class="px-3 py-2 text-end">{{ t('backtest.numTrades') }}</th>
              <th class="px-3 py-2 text-end">{{ t('analytics.funding') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="a in byAsset"
              :key="a.symbol"
              class="border-t border-zinc-800/50"
            >
              <td class="px-3 py-2 text-zinc-300">{{ a.symbol }}</td>
              <td
                class="px-3 py-2 text-end"
                :class="a.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'"
              >
                {{ a.net_pnl.toFixed(2) }}
              </td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ (a.win_rate * 100).toFixed(1) }}%</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ a.num_trades }}</td>
              <td class="px-3 py-2 text-end text-zinc-500">{{ a.funding_paid.toFixed(2) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="rounded-xl border border-zinc-800 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="text-xs text-zinc-500 uppercase bg-zinc-900/50">
            <tr>
              <th class="px-3 py-2 text-start">{{ t('strategies.name') }}</th>
              <th class="px-3 py-2 text-start">{{ t('data.coin') }}</th>
              <th class="px-3 py-2 text-start">TF</th>
              <th
                class="px-3 py-2 text-end cursor-pointer hover:text-zinc-300"
                @click="toggleSort('net_pnl')"
              >
                PnL
              </th>
              <th
                class="px-3 py-2 text-end cursor-pointer hover:text-zinc-300"
                @click="toggleSort('sharpe_ratio')"
              >
                Sharpe
              </th>
              <th class="px-3 py-2 text-end">PF</th>
              <th class="px-3 py-2 text-end">{{ t('backtest.maxDrawdown') }}</th>
              <th class="px-3 py-2 text-end">{{ t('backtest.numTrades') }}</th>
              <th
                class="px-3 py-2 text-end cursor-pointer hover:text-zinc-300"
                @click="toggleSort('created_at')"
              >
                {{ t('analytics.date') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in sortedRuns"
              :key="r.backtest_id"
              class="border-t border-zinc-800/50 cursor-pointer hover:bg-zinc-900/50"
              @click="goToBacktest(r)"
            >
              <td class="px-3 py-2 text-zinc-300">{{ r.strategy_name }}</td>
              <td class="px-3 py-2 text-zinc-500">{{ r.symbol }}</td>
              <td class="px-3 py-2 text-zinc-500">{{ r.timeframe }}</td>
              <td class="px-3 py-2 text-end" :class="(r.net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ r.net_pnl?.toFixed(2) ?? '—' }}
              </td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ r.sharpe_ratio?.toFixed(2) ?? '—' }}</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ r.profit_factor?.toFixed(2) ?? '—' }}</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ r.max_drawdown?.toFixed(2) ?? '—' }}</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ r.num_trades ?? '—' }}</td>
              <td class="px-3 py-2 text-end text-zinc-500">{{ fmtDate(r.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
