<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { BacktestMetrics } from '../../api/client'

defineProps<{ metrics: BacktestMetrics }>()
const { t } = useI18n()
</script>

<template>
  <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.netPnl') }}</div>
      <div class="text-lg font-semibold" :class="(metrics.net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
        {{ metrics.net_pnl?.toFixed(2) ?? '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.grossPnl') }}</div>
      <div class="text-lg font-semibold" :class="(metrics.gross_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
        {{ metrics.gross_pnl?.toFixed(2) ?? '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.totalCommission') }}</div>
      <div class="text-lg font-semibold text-zinc-200">
        {{ metrics.total_commission?.toFixed(4) ?? '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.winRate') }}</div>
      <div class="text-lg font-semibold text-zinc-200">
        {{ metrics.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—' }}
      </div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.maxDrawdown') }}</div>
      <div class="text-lg font-semibold text-red-400">{{ metrics.max_drawdown?.toFixed(2) ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.numTrades') }}</div>
      <div class="text-lg font-semibold text-zinc-200">{{ metrics.num_trades ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.sharpe') }}</div>
      <div class="text-lg font-semibold text-zinc-200">{{ metrics.sharpe_ratio?.toFixed(2) ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.profitFactor') }}</div>
      <div class="text-lg font-semibold text-zinc-200">{{ metrics.profit_factor?.toFixed(2) ?? '—' }}</div>
    </div>
    <div class="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
      <div class="text-xs text-zinc-500">{{ t('backtest.riskReward') }}</div>
      <div class="text-lg font-semibold text-zinc-200">{{ metrics.risk_reward?.toFixed(2) ?? '—' }}</div>
    </div>
  </div>
</template>
