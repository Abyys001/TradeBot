<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import BacktestSidebar from '../modules/backtest/BacktestSidebar.vue'
import TradingChart from '../modules/chart/TradingChart.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const store = useStrategyStore()

const strategyId = computed(() => Number(route.params.id))

onMounted(async () => {
  store.select(strategyId.value)
  await store.fetchAll({ preserveSelection: true })
})

watch(strategyId, (id) => {
  if (!Number.isNaN(id)) store.select(id)
})

watch(
  () => store.strategies,
  () => {
    if (store.strategies.length && !store.strategies.find((s) => s.id === strategyId.value)) {
      router.replace({ name: 'strategies' })
    }
  },
)
</script>

<template>
  <div class="flex flex-1 min-h-0">
    <main class="relative flex min-w-0 flex-1 flex-col">
      <div class="border-b border-zinc-800 px-4 py-2">
        <h1 class="text-sm font-medium text-zinc-300">{{ t('strategy.title') }}</h1>
      </div>
      <div class="relative flex-1 min-h-0">
        <TradingChart :strategy-id="strategyId" />
      </div>
    </main>
    <BacktestSidebar :strategy-id="strategyId" />
  </div>
</template>
