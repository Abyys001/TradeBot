<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { BacktestMetrics } from '../../api/client'

defineProps<{ metrics: BacktestMetrics | null | undefined }>()
const { t } = useI18n()
</script>

<template>
  <div v-if="metrics" class="flex shrink-0 items-stretch gap-2 border-b border-border bg-surface-muted/40 px-3 py-2 overflow-x-auto">
    <div class="min-w-[5rem] rounded-lg border border-border bg-surface-muted/50 px-3 py-1.5">
      <div class="text-[10px] text-fg-muted">{{ t('backtest.netPnl') }}</div>
      <div class="text-sm font-semibold" :class="(metrics.net_pnl ?? 0) >= 0 ? 'text-positive' : 'text-negative'">
        {{ metrics.net_pnl?.toFixed(2) ?? '—' }}
      </div>
    </div>
    <div class="min-w-[5rem] rounded-lg border border-border bg-surface-muted/50 px-3 py-1.5">
      <div class="text-[10px] text-fg-muted">{{ t('backtest.winRate') }}</div>
      <div class="text-sm font-semibold text-fg">
        {{ metrics.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—' }}
      </div>
    </div>
    <div class="min-w-[5rem] rounded-lg border border-border bg-surface-muted/50 px-3 py-1.5">
      <div class="text-[10px] text-fg-muted">{{ t('backtest.maxDrawdown') }}</div>
      <div class="text-sm font-semibold text-negative">{{ metrics.max_drawdown != null ? metrics.max_drawdown.toFixed(2) + '%' : '—' }}</div>
    </div>
    <div class="min-w-[5rem] rounded-lg border border-border bg-surface-muted/50 px-3 py-1.5">
      <div class="text-[10px] text-fg-muted">{{ t('backtest.numTrades') }}</div>
      <div class="text-sm font-semibold text-fg">{{ metrics.num_trades ?? '—' }}</div>
    </div>
  </div>
</template>
