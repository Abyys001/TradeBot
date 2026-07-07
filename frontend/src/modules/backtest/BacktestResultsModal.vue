<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Backtest } from '../../api/client'
import AppModal from '../../components/AppModal.vue'
import MetricsCards from './MetricsCards.vue'
import EquityCurve from './EquityCurve.vue'
import BacktestResultsSkeleton from '../../components/BacktestResultsSkeleton.vue'

const props = defineProps<{ backtest: Backtest }>()
const emit = defineEmits<{ close: []; viewChart: [] }>()

const { t } = useI18n()

const metrics = computed(() => props.backtest.metrics)
const trades = computed(() => props.backtest.trades ?? [])
const isLoading = computed(
  () => props.backtest.status === 'pending' || props.backtest.status === 'running',
)
</script>

<template>
  <AppModal :title="t('backtest.resultsTitle')" size="lg" @close="emit('close')">
    <div class="space-y-4 p-4">
      <div class="flex items-center gap-2 text-sm text-zinc-400">
        <span>{{ backtest.symbol }} / {{ backtest.timeframe }}</span>
        <span
          class="rounded px-1.5 py-0.5 text-xs font-medium"
          :class="{
            'bg-emerald-900 text-emerald-300': backtest.status === 'done',
            'bg-red-900 text-red-300': backtest.status === 'failed',
            'bg-amber-900 text-amber-300': backtest.status === 'running',
            'bg-zinc-800 text-zinc-400': backtest.status === 'pending',
          }"
        >
          {{ backtest.status }}
        </span>
      </div>

      <template v-if="isLoading">
        <p class="text-xs text-zinc-500">{{ t('backtest.progress') }}</p>
        <BacktestResultsSkeleton />
      </template>

      <template v-else>
        <div v-if="metrics" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.netPnl') }}</div>
            <div
              class="text-2xl font-bold"
              :class="(metrics.net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'"
            >
              {{ metrics.net_pnl?.toFixed(2) ?? '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.winRate') }}</div>
            <div class="text-2xl font-bold text-zinc-100">
              {{ metrics.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.maxDrawdown') }}</div>
            <div class="text-2xl font-bold text-red-400">
              {{ metrics.max_drawdown != null ? metrics.max_drawdown.toFixed(2) + '%' : '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.numTrades') }}</div>
            <div class="text-2xl font-bold text-zinc-100">{{ metrics.num_trades ?? '—' }}</div>
          </div>
        </div>

        <div v-if="metrics?.equity_series?.length">
          <h3 class="mb-2 text-xs font-medium text-zinc-500">{{ t('backtest.equityCurve') }}</h3>
          <EquityCurve :series="metrics.equity_series" :height="200" />
        </div>

        <div v-if="trades.length" class="overflow-hidden rounded-lg border border-zinc-800">
          <div class="border-b border-zinc-800 bg-zinc-900/50 px-3 py-2 text-xs font-medium text-zinc-400">
            {{ t('backtest.tradesTitle', { count: trades.length }) }}
          </div>
          <div class="scrollbar-styled max-h-48 overflow-x-auto overflow-y-auto">
            <table class="w-full text-xs">
              <thead class="sticky top-0 bg-zinc-900/95 text-zinc-500 uppercase">
                <tr>
                  <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.pnl') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.exitReason') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(tr, i) in trades" :key="i" class="border-t border-zinc-800/50">
                  <td class="px-3 py-1.5 text-zinc-300">{{ tr.side }}</td>
                  <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.entry_price }}</td>
                  <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.exit_price ?? '—' }}</td>
                  <td
                    class="px-3 py-1.5 text-end"
                    :class="Number(tr.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'"
                  >
                    {{ tr.pnl }}
                  </td>
                  <td class="px-3 py-1.5 text-end text-zinc-500">{{ tr.exit_reason || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="metrics">
          <h3 class="mb-2 text-xs font-medium text-zinc-500">{{ t('backtest.moreMetrics') }}</h3>
          <MetricsCards :metrics="metrics" />
        </div>

        <p v-if="backtest.error" class="text-sm text-red-400">{{ backtest.error }}</p>
      </template>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
          @click="emit('close')"
        >
          {{ t('modal.close') }}
        </button>
        <button
          v-if="!isLoading && backtest.status === 'done'"
          type="button"
          class="rounded-lg bg-violet-700 px-4 py-2 text-sm text-white hover:bg-violet-600"
          @click="emit('viewChart'); emit('close')"
        >
          {{ t('backtest.viewOnChart') }}
        </button>
      </div>
    </template>
  </AppModal>
</template>
