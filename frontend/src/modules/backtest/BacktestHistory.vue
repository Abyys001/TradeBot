<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Backtest } from '../../api/client'

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
  if (status === 'done') return 'text-emerald-400'
  if (status === 'failed') return 'text-red-400'
  if (status === 'running') return 'text-amber-400'
  return 'text-zinc-500'
}
</script>

<template>
  <div class="rounded-lg border border-zinc-800 overflow-hidden">
    <div class="px-3 py-2 border-b border-zinc-800 bg-zinc-900/50 text-xs font-medium text-zinc-400">
      {{ t('backtest.history') }}
    </div>
    <div v-if="!sorted.length" class="px-3 py-4 text-xs text-zinc-500 text-center">
      {{ t('backtest.noRuns') }}
    </div>
    <button
      v-for="bt in sorted"
      :key="bt.id"
      type="button"
      class="w-full px-3 py-2 text-start text-xs border-b border-zinc-800/50 hover:bg-zinc-800/50 transition-colors"
      :class="activeId === bt.id ? 'bg-zinc-800' : ''"
      @click="emit('select', bt.id)"
    >
      <div class="flex justify-between items-center">
        <span class="text-zinc-300">{{ bt.symbol }} / {{ bt.timeframe }}</span>
        <span :class="statusClass(bt.status)">{{ bt.status }}</span>
      </div>
      <div v-if="bt.status === 'done'" class="text-zinc-500 mt-0.5">
        PnL: {{ bt.metrics?.net_pnl?.toFixed(2) ?? '—' }} · {{ bt.metrics?.num_trades ?? 0 }} trades
      </div>
    </button>
  </div>
</template>
