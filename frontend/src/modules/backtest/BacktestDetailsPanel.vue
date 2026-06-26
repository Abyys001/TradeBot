<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { BacktestMetrics } from '../../api/client'
import MetricsCards from './MetricsCards.vue'
import EquityCurve from './EquityCurve.vue'

defineProps<{ metrics: BacktestMetrics | null | undefined }>()

const { t } = useI18n()
const open = ref(false)
</script>

<template>
  <div v-if="metrics" class="shrink-0 border-b border-zinc-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-900/50"
      @click="open = !open"
    >
      <span>{{ t('backtest.moreMetrics') }}</span>
      <span>{{ open ? '▼' : '▶' }}</span>
    </button>
    <div v-show="open" class="space-y-3 border-t border-zinc-800/50 p-3">
      <MetricsCards :metrics="metrics" />
      <EquityCurve
        v-if="metrics.equity_series?.length"
        :series="metrics.equity_series"
        :height="100"
      />
    </div>
  </div>
</template>
