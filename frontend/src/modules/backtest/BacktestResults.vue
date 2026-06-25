<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Backtest } from '../../api/client'
import MetricsCards from './MetricsCards.vue'
import EquityCurve from './EquityCurve.vue'

const props = defineProps<{ backtest: Backtest | null }>()
const { t } = useI18n()

const trades = computed(() => props.backtest?.trades ?? [])
</script>

<template>
  <div v-if="!backtest" class="text-sm text-zinc-500 py-4 text-center">
    {{ t('backtest.selectRun') }}
  </div>
  <div v-else class="space-y-4">
    <div class="flex items-center gap-2 text-sm">
      <span class="text-zinc-400">{{ backtest.symbol }} / {{ backtest.timeframe }}</span>
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

    <p v-if="backtest.error" class="text-sm text-red-400">{{ backtest.error }}</p>

    <MetricsCards v-if="backtest.status === 'done'" :metrics="backtest.metrics" />
    <EquityCurve
      v-if="backtest.status === 'done' && backtest.metrics?.equity_series?.length"
      :series="backtest.metrics.equity_series"
    />

    <div v-if="trades.length" class="rounded-lg border border-zinc-800 overflow-hidden">
      <table class="w-full text-xs">
        <thead class="text-zinc-500 uppercase bg-zinc-900/50">
          <tr>
            <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
            <th class="px-3 py-2 text-end">{{ t('backtest.pnl') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(tr, i) in trades" :key="i" class="border-t border-zinc-800/50">
            <td class="px-3 py-1.5 text-zinc-300">{{ tr.side }}</td>
            <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.entry_price }}</td>
            <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.exit_price ?? '—' }}</td>
            <td class="px-3 py-1.5 text-end" :class="Number(tr.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ tr.pnl }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
