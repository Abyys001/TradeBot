<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAnalyticsStore, type AnalyticsRun } from '../stores/analytics'
import { useBacktestStore } from '../stores/backtest'
import { useOptimizerStore } from '../stores/optimizer'
import { useStrategyStore } from '../stores/strategy'
import EquityCurve from '../modules/backtest/EquityCurve.vue'
import BacktestHistoryCards from '../modules/backtest/BacktestHistoryCards.vue'
import ResponsiveTable from '../components/ResponsiveTable.vue'

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

</script>

<template>
  <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-3 space-y-6 max-w-7xl sm:p-4">
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
      <!-- hero: bento backtest cards -->
      <div>
        <div class="mb-3 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-2 text-xs text-zinc-500">
              <span>Sort by</span>
              <button
                v-for="opt in ([['net_pnl', 'PnL'], ['sharpe_ratio', 'Sharpe'], ['created_at', 'Date']] as [SortKey, string][])"
                :key="opt[0]"
                type="button"
                class="rounded px-2 py-0.5 transition-colors"
                :class="sortKey === opt[0] ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'"
                @click="toggleSort(opt[0])"
              >
                {{ opt[1] }}
                <span v-if="sortKey === opt[0]">{{ sortAsc ? '↑' : '↓' }}</span>
              </button>
            </div>
          </div>
          <span class="text-xs text-zinc-600">{{ analytics.runs.length }} runs</span>
        </div>
        <BacktestHistoryCards :runs="sortedRuns" @select="goToBacktest" />
      </div>

      <!-- summary stat row -->
      <div v-if="summary" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
          <div class="text-[11px] text-zinc-500">{{ t('analytics.totalRuns') }}</div>
          <div class="text-xl font-bold text-zinc-100">{{ summary.count }}</div>
        </div>
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
          <div class="text-[11px] text-zinc-500">{{ t('analytics.totalPnl') }}</div>
          <div
            class="text-xl font-bold"
            :class="summary.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'"
          >
            {{ summary.totalPnl >= 0 ? '+' : '' }}{{ summary.totalPnl.toFixed(2) }}
          </div>
        </div>
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
          <div class="text-[11px] text-zinc-500">{{ t('analytics.avgSharpe') }}</div>
          <div class="text-xl font-bold text-zinc-100">{{ summary.avgSharpe?.toFixed(2) ?? '—' }}</div>
        </div>
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
          <div class="text-[11px] text-zinc-500">{{ t('analytics.worstDrawdown') }}</div>
          <div class="text-xl font-bold text-red-400">
            {{ summary.worstDrawdown != null ? summary.worstDrawdown.toFixed(2) + '%' : '—' }}
          </div>
        </div>
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-3">
          <div class="text-[11px] text-zinc-500">{{ t('analytics.totalFunding') }}</div>
          <div class="text-xl font-bold text-zinc-100">{{ summary.totalFunding.toFixed(2) }}</div>
        </div>
      </div>

      <!-- best / worst full equity curve -->
      <div class="grid md:grid-cols-2 gap-4">
        <button
          v-if="best"
          type="button"
          class="rounded-xl border border-emerald-900/50 bg-zinc-950 p-4 text-start hover:border-emerald-800 transition-colors"
          @click="goToBacktest(best)"
        >
          <div class="text-[11px] text-zinc-500 mb-1">{{ t('analytics.best') }}</div>
          <div class="text-sm font-medium text-zinc-200">{{ best.strategy_name }} · {{ best.symbol }}</div>
          <div class="text-emerald-400 font-bold text-lg">+{{ best.net_pnl?.toFixed(2) }}</div>
          <EquityCurve v-if="best.equity_series?.length" :series="best.equity_series" class="mt-3" />
        </button>
        <button
          v-if="worst"
          type="button"
          class="rounded-xl border border-red-950/50 bg-zinc-950 p-4 text-start hover:border-red-900 transition-colors"
          @click="goToBacktest(worst)"
        >
          <div class="text-[11px] text-zinc-500 mb-1">{{ t('analytics.worst') }}</div>
          <div class="text-sm font-medium text-zinc-200">{{ worst.strategy_name }} · {{ worst.symbol }}</div>
          <div class="text-red-400 font-bold text-lg">{{ worst.net_pnl?.toFixed(2) }}</div>
          <EquityCurve v-if="worst.equity_series?.length" :series="worst.equity_series" class="mt-3" />
        </button>
      </div>

      <!-- monthly bar chart -->
      <div v-if="monthly.length" class="rounded-xl border border-zinc-800 p-4">
        <h2 class="text-sm font-medium text-zinc-300 mb-3">{{ t('analytics.monthly') }}</h2>
        <div class="flex items-end gap-2 h-24">
          <div
            v-for="m in monthly"
            :key="m.month"
            class="flex-1 flex flex-col items-center gap-1 min-w-0"
          >
            <div
              class="w-full rounded-t min-h-[4px]"
              :style="{ height: `${Math.max(4, (Math.abs(m.net_pnl) / monthlyMax) * 72)}px` }"
              :class="m.net_pnl >= 0 ? 'bg-emerald-600/80' : 'bg-red-600/80'"
            />
            <span class="text-[10px] text-zinc-500 truncate w-full text-center">{{ m.month }}</span>
          </div>
        </div>
      </div>

      <!-- by-asset table -->
      <div v-if="byAsset.length" class="rounded-xl border border-zinc-800 overflow-hidden">
        <div class="px-3 py-2 border-b border-zinc-800 bg-zinc-900/50 text-xs font-medium text-zinc-400">
          {{ t('analytics.byAsset') }}
        </div>
        <ResponsiveTable>
          <template #head>
            <th class="px-3 py-2 text-start">{{ t('data.coin') }}</th>
            <th class="px-3 py-2 text-end">PnL</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.winRate') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.numTrades') }}</th>
            <th class="px-3 py-2 text-end">{{ t('analytics.funding') }}</th>
          </template>
          <template #row>
            <tr v-for="a in byAsset" :key="a.symbol" class="border-t border-zinc-800/50">
              <td class="px-3 py-2 text-zinc-300">{{ a.symbol }}</td>
              <td class="px-3 py-2 text-end" :class="a.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ a.net_pnl.toFixed(2) }}
              </td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ (a.win_rate * 100).toFixed(1) }}%</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ a.num_trades }}</td>
              <td class="px-3 py-2 text-end text-zinc-500">{{ a.funding_paid.toFixed(2) }}</td>
            </tr>
          </template>
          <template #card>
            <div v-for="a in byAsset" :key="a.symbol" class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
              <div class="flex items-center justify-between">
                <span class="font-medium text-zinc-200">{{ a.symbol }}</span>
                <span :class="a.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ a.net_pnl.toFixed(2) }}</span>
              </div>
              <div class="mt-1.5 grid grid-cols-2 gap-y-1 text-xs">
                <span class="text-zinc-500">{{ t('backtest.winRate') }}</span>
                <span class="text-end text-zinc-400">{{ (a.win_rate * 100).toFixed(1) }}%</span>
                <span class="text-zinc-500">{{ t('backtest.numTrades') }}</span>
                <span class="text-end text-zinc-400">{{ a.num_trades }}</span>
                <span class="text-zinc-500">{{ t('analytics.funding') }}</span>
                <span class="text-end text-zinc-500">{{ a.funding_paid.toFixed(2) }}</span>
              </div>
            </div>
          </template>
        </ResponsiveTable>
      </div>
    </template>
  </div>
</template>
