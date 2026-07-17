<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { BacktestMetrics } from '../../api/client'

defineProps<{ metrics: BacktestMetrics }>()
const { t } = useI18n()
</script>

<template>
  <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.netPnl') }}</div>
      <div class="text-lg font-semibold" :class="(metrics.net_pnl ?? 0) >= 0 ? 'text-positive' : 'text-negative'">
        {{ metrics.net_pnl?.toFixed(2) ?? '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.grossPnl') }}</div>
      <div class="text-lg font-semibold" :class="(metrics.gross_pnl ?? 0) >= 0 ? 'text-positive' : 'text-negative'">
        {{ metrics.gross_pnl?.toFixed(2) ?? '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.totalCommission') }}</div>
      <div class="text-lg font-semibold text-fg">
        {{ metrics.total_commission?.toFixed(4) ?? '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.winRate') }}</div>
      <div class="text-lg font-semibold text-fg">
        {{ metrics.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.maxDrawdown') }}</div>
      <div class="text-lg font-semibold text-negative">{{ metrics.max_drawdown != null ? metrics.max_drawdown.toFixed(2) + '%' : '—' }}</div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.numTrades') }}</div>
      <div class="text-lg font-semibold text-fg">{{ metrics.num_trades ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.initialCapital') }}</div>
      <div class="text-lg font-semibold text-fg">{{ metrics.initial_balance?.toFixed(2) ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.sharpe') }}</div>
      <div class="text-lg font-semibold text-fg">{{ metrics.sharpe_ratio?.toFixed(2) ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.profitFactor') }}</div>
      <div class="text-lg font-semibold text-fg">{{ metrics.profit_factor?.toFixed(2) ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-border bg-surface-muted/50 px-3 py-2">
      <div class="text-xs text-fg-muted">{{ t('backtest.riskReward') }}</div>
      <div class="text-lg font-semibold text-fg">{{ metrics.risk_reward?.toFixed(2) ?? '—' }}</div>
    </div>
  </div>
</template>
