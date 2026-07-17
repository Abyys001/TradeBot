<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBacktestStore } from '../../stores/backtest'
import BacktestRunForm from './BacktestRunForm.vue'
import BacktestHistory from './BacktestHistory.vue'
import ProgressBar from '../../components/ProgressBar.vue'

const props = defineProps<{ strategyId: number }>()

const emit = defineEmits<{ selectBacktest: [id: number | null]; viewResults: [id: number] }>()

const { t } = useI18n()
const backtestStore = useBacktestStore()
const formRef = ref<InstanceType<typeof BacktestRunForm> | null>(null)

const strategyBacktests = computed(() => backtestStore.forStrategy(props.strategyId))

const activeBacktest = computed(() => backtestStore.active)

const isActive = computed(
  () => activeBacktest.value?.status === 'pending' || activeBacktest.value?.status === 'running',
)

const canRun = computed(() => formRef.value?.canRun ?? false)

function onSelect(id: number) {
  backtestStore.select(id)
  emit('selectBacktest', id)
  void backtestStore.fetchOne(id)
  const bt = backtestStore.backtests.find((b) => b.id === id)
  if (bt?.status === 'done') {
    emit('viewResults', id)
  }
}

function runBacktests() {
  void formRef.value?.runBacktests()
}

defineExpose({ runBacktests, canRun })
</script>

<template>
  <div class="flex flex-col gap-2.5 p-4">
    <BacktestRunForm
      ref="formRef"
      :strategy-id="strategyId"
      @select-backtest="emit('selectBacktest', $event)"
    />

    <BacktestHistory
      :backtests="strategyBacktests"
      :active-id="backtestStore.activeId"
      @select="onSelect"
    />

    <div v-if="activeBacktest" class="space-y-1.5 border-t border-border pt-2.5">
      <div class="flex items-center gap-2 text-xs">
        <span class="text-fg-muted">{{ activeBacktest.symbol }} / {{ activeBacktest.timeframe }}</span>
        <span
          class="rounded px-1.5 py-0.5 text-[10px] font-medium"
          :class="{
            'bg-success-bg text-positive': activeBacktest.status === 'done',
            'bg-danger-bg text-negative': activeBacktest.status === 'failed',
            'bg-warning-bg text-warning': activeBacktest.status === 'running',
            'bg-surface-raised text-fg-muted': activeBacktest.status === 'pending',
          }"
        >
          {{ activeBacktest.status }}
        </span>
      </div>
      <div v-if="isActive" class="space-y-1.5">
        <p class="text-xs text-fg-muted">{{ t('backtest.progress') }}</p>
        <ProgressBar indeterminate color="amber" />
      </div>
      <p v-if="activeBacktest.error" class="text-xs text-negative">{{ activeBacktest.error }}</p>
    </div>
    <p v-else class="border-t border-border pt-3 text-center text-xs text-fg-muted">
      {{ t('backtest.selectRun') }}
    </p>
  </div>
</template>
