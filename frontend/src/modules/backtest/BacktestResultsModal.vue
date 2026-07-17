<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Backtest } from '../../api/client'
import AppModal from '../../components/AppModal.vue'
import MetricsCards from './MetricsCards.vue'
import EquityCurve from './EquityCurve.vue'
import BacktestResultsSkeleton from '../../components/BacktestResultsSkeleton.vue'
import ResponsiveTable from '../../components/ResponsiveTable.vue'

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
      <div class="flex items-center gap-2 text-sm text-fg-muted">
        <span>{{ backtest.symbol }} / {{ backtest.timeframe }}</span>
        <span
          class="rounded px-1.5 py-0.5 text-xs font-medium"
          :class="{
            'bg-success-bg text-positive': backtest.status === 'done',
            'bg-danger-bg text-negative': backtest.status === 'failed',
            'bg-warning-bg text-warning': backtest.status === 'running',
            'bg-surface-raised text-fg-muted': backtest.status === 'pending',
          }"
        >
          {{ backtest.status }}
        </span>
      </div>

      <template v-if="isLoading">
        <p class="text-xs text-fg-muted">{{ t('backtest.progress') }}</p>
        <BacktestResultsSkeleton />
      </template>

      <template v-else>
        <div v-if="metrics" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div class="rounded-xl border border-border bg-surface-muted/60 px-4 py-3">
            <div class="text-xs text-fg-muted">{{ t('backtest.netPnl') }}</div>
            <div
              class="text-2xl font-bold"
              :class="(metrics.net_pnl ?? 0) >= 0 ? 'text-positive' : 'text-negative'"
            >
              {{ metrics.net_pnl?.toFixed(2) ?? '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-border bg-surface-muted/60 px-4 py-3">
            <div class="text-xs text-fg-muted">{{ t('backtest.winRate') }}</div>
            <div class="text-2xl font-bold text-fg">
              {{ metrics.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-border bg-surface-muted/60 px-4 py-3">
            <div class="text-xs text-fg-muted">{{ t('backtest.maxDrawdown') }}</div>
            <div class="text-2xl font-bold text-negative">
              {{ metrics.max_drawdown != null ? metrics.max_drawdown.toFixed(2) + '%' : '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-border bg-surface-muted/60 px-4 py-3">
            <div class="text-xs text-fg-muted">{{ t('backtest.numTrades') }}</div>
            <div class="text-2xl font-bold text-fg">{{ metrics.num_trades ?? '—' }}</div>
          </div>
        </div>

        <div v-if="metrics?.equity_series?.length">
          <h3 class="mb-2 text-xs font-medium text-fg-muted">{{ t('backtest.equityCurve') }}</h3>
          <EquityCurve :series="metrics.equity_series" :height="200" />
        </div>

        <div v-if="trades.length" class="overflow-hidden rounded-lg border border-border">
          <div class="border-b border-border bg-surface-muted/50 px-3 py-2 text-xs font-medium text-fg-muted">
            {{ t('backtest.tradesTitle', { count: trades.length }) }}
          </div>
          <div class="scrollbar-styled max-h-48 overflow-y-auto">
            <ResponsiveTable sticky-head>
              <template #head>
                <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
                <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
                <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
                <th class="px-3 py-2 text-end">{{ t('backtest.pnl') }}</th>
                <th class="px-3 py-2 text-end">{{ t('backtest.exitReason') }}</th>
              </template>
              <template #row>
                <tr v-for="(tr, i) in trades" :key="i" class="border-t border-border/50 text-xs">
                  <td class="px-3 py-1.5 text-fg">{{ tr.side }}</td>
                  <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.entry_price }}</td>
                  <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.exit_price ?? '—' }}</td>
                  <td
                    class="px-3 py-1.5 text-end"
                    :class="Number(tr.pnl) >= 0 ? 'text-positive' : 'text-negative'"
                  >
                    {{ tr.pnl }}
                  </td>
                  <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.exit_reason || '—' }}</td>
                </tr>
              </template>
              <template #card>
                <div v-for="(tr, i) in trades" :key="i" class="rounded-lg border border-border bg-surface-muted/40 p-3 text-xs">
                  <div class="flex items-center justify-between">
                    <span class="font-medium text-fg">{{ tr.side }}</span>
                    <span :class="Number(tr.pnl) >= 0 ? 'text-positive' : 'text-negative'">{{ tr.pnl }}</span>
                  </div>
                  <div class="mt-1.5 grid grid-cols-3 gap-y-1">
                    <div>
                      <div class="text-[10px] text-fg-muted">{{ t('backtest.entry') }}</div>
                      <div class="text-fg-muted">{{ tr.entry_price }}</div>
                    </div>
                    <div>
                      <div class="text-[10px] text-fg-muted">{{ t('backtest.exit') }}</div>
                      <div class="text-fg-muted">{{ tr.exit_price ?? '—' }}</div>
                    </div>
                    <div>
                      <div class="text-[10px] text-fg-muted">{{ t('backtest.exitReason') }}</div>
                      <div class="text-fg-muted">{{ tr.exit_reason || '—' }}</div>
                    </div>
                  </div>
                </div>
              </template>
            </ResponsiveTable>
          </div>
        </div>

        <div v-if="metrics">
          <h3 class="mb-2 text-xs font-medium text-fg-muted">{{ t('backtest.moreMetrics') }}</h3>
          <MetricsCards :metrics="metrics" />
        </div>

        <p v-if="backtest.error" class="text-sm text-negative">{{ backtest.error }}</p>
      </template>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-lg bg-surface-raised px-4 py-2 text-sm text-fg hover:bg-border"
          @click="emit('close')"
        >
          {{ t('modal.close') }}
        </button>
        <button
          v-if="!isLoading && backtest.status === 'done'"
          type="button"
          class="rounded-lg bg-accent px-4 py-2 text-sm text-white hover:opacity-90"
          @click="emit('viewChart'); emit('close')"
        >
          {{ t('backtest.viewOnChart') }}
        </button>
      </div>
    </template>
  </AppModal>
</template>
