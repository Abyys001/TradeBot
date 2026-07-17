<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChartStore } from '../../stores/chart'
import { useStrategyStore } from '../../stores/strategy'

const props = defineProps<{ strategyId: number }>()

const { t } = useI18n()
const chart = useChartStore()
const strategy = useStrategyStore()

const strategyData = computed(() =>
  strategy.strategies.find((s) => s.id === props.strategyId),
)

const pnlValue = computed(() => {
  const fromState = strategyData.value?.state?.pnl
  return parseFloat(chart.pnl || String(fromState ?? 0))
})

const pnlClass = computed(() =>
  pnlValue.value >= 0 ? 'text-positive border-positive/50' : 'text-negative border-negative/50',
)
</script>

<template>
  <div
    class="absolute top-4 end-4 z-10 rounded-lg border bg-surface-muted/90 px-4 py-3 backdrop-blur shadow-lg"
    :class="pnlClass"
  >
    <div class="text-xs text-fg-muted mb-0.5">{{ t('chart.pnl') }}</div>
    <div class="text-lg font-mono font-semibold">
      {{ pnlValue >= 0 ? '+' : '' }}{{ pnlValue.toFixed(4) }}
    </div>
  </div>
</template>
