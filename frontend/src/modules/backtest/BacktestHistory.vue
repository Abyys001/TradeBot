<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Backtest } from '../../api/client'
import ProgressBar from '../../components/ProgressBar.vue'

const props = defineProps<{
  backtests: Backtest[]
  activeId: number | null
}>()

const emit = defineEmits<{ select: [id: number] }>()

const { t } = useI18n()

const sorted = computed(() =>
  [...props.backtests].sort((a, b) => b.created_at.localeCompare(a.created_at)),
)

function statusClass(status: string) {
  if (status === 'done') return 'text-positive'
  if (status === 'failed') return 'text-negative'
  if (status === 'running') return 'text-warning'
  return 'text-fg-muted'
}

function isActive(status: string) {
  return status === 'pending' || status === 'running'
}
</script>

<template>
  <div class="rounded-lg border border-border overflow-hidden">
    <div class="px-3 py-2 border-b border-border bg-surface-muted/50 text-xs font-medium text-fg-muted">
      {{ t('backtest.history') }}
    </div>
    <div v-if="!sorted.length" class="px-3 py-4 text-xs text-fg-muted text-center">
      {{ t('backtest.noRuns') }}
    </div>
    <button
      v-for="bt in sorted"
      :key="bt.id"
      type="button"
      class="w-full px-3 py-2 text-start text-xs border-b border-border/50 hover:bg-surface-raised/50 transition-colors"
      :class="activeId === bt.id ? 'bg-surface-raised' : ''"
      @click="emit('select', bt.id)"
    >
      <div class="flex justify-between items-center">
        <span class="text-fg">{{ bt.symbol }} / {{ bt.timeframe }}</span>
        <span :class="[statusClass(bt.status), { 'animate-pulse': bt.status === 'running' }]">
          {{ bt.status }}
        </span>
      </div>
      <ProgressBar v-if="isActive(bt.status)" indeterminate color="amber" class="mt-1.5" />
      <div v-if="bt.status === 'done'" class="text-fg-muted mt-0.5">
        PnL: {{ bt.metrics?.net_pnl?.toFixed(2) ?? '—' }} · {{ bt.metrics?.num_trades ?? 0 }} trades
      </div>
      <div v-else-if="bt.status === 'failed' && bt.error" class="text-negative/80 mt-0.5 truncate">
        {{ bt.error }}
      </div>
    </button>
  </div>
</template>
