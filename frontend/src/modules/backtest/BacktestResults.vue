<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Backtest } from '../../api/client'
import MetricsCards from './MetricsCards.vue'
import EquityCurve from './EquityCurve.vue'
import ProgressBar from '../../components/ProgressBar.vue'
import ResponsiveTable from '../../components/ResponsiveTable.vue'

const props = defineProps<{ backtest: Backtest | null }>()
const { t } = useI18n()

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'medium', hour12: false })
}

const trades = computed(() => props.backtest?.trades ?? [])
const isActive = computed(
  () => props.backtest?.status === 'pending' || props.backtest?.status === 'running',
)
</script>

<template>
  <div v-if="!backtest" class="text-sm text-fg-muted py-4 text-center">
    {{ t('backtest.selectRun') }}
  </div>
  <div v-else class="space-y-4">
    <div class="flex items-center gap-2 text-sm">
      <span class="text-fg-muted">{{ backtest.symbol }} / {{ backtest.timeframe }}</span>
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

    <div v-if="isActive" class="space-y-1">
      <p class="text-xs text-fg-muted">{{ t('backtest.progress') }}</p>
      <ProgressBar indeterminate color="amber" />
    </div>

    <p v-if="backtest.error" class="text-sm text-negative">{{ backtest.error }}</p>

    <MetricsCards v-if="backtest.status === 'done'" :metrics="backtest.metrics" />
    <EquityCurve
      v-if="backtest.status === 'done' && backtest.metrics?.equity_series?.length"
      :series="backtest.metrics.equity_series"
    />

    <div v-if="trades.length" class="rounded-lg border border-border overflow-hidden">
      <ResponsiveTable>
        <template #head>
          <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
          <th class="px-3 py-2 text-start">{{ t('backtest.time') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.pnl') }}</th>
          <th class="px-3 py-2 text-end">{{ t('backtest.exitReason') }}</th>
        </template>
        <template #row>
          <tr v-for="(tr, i) in trades" :key="i" class="border-t border-border/50 text-xs">
            <td class="px-3 py-1.5 text-fg">{{ tr.side }}</td>
            <td class="px-3 py-1.5 text-fg-muted">
              <div>{{ fmtTime(tr.entry_time) }}</div>
              <div v-if="tr.exit_time" class="text-fg-muted">→ {{ fmtTime(tr.exit_time) }}</div>
            </td>
            <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.entry_price }}</td>
            <td class="px-3 py-1.5 text-end text-fg-muted">{{ tr.exit_price ?? '—' }}</td>
            <td class="px-3 py-1.5 text-end" :class="Number(tr.pnl) >= 0 ? 'text-positive' : 'text-negative'">
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
            <div class="mt-1 text-fg-muted">
              {{ fmtTime(tr.entry_time) }}<span v-if="tr.exit_time"> → {{ fmtTime(tr.exit_time) }}</span>
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
</template>
