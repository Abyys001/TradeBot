<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import { useCredentialsStore } from '../stores/credentials'
import StrategyConfigurator from '../modules/strategy/StrategyConfigurator.vue'
import TradingChart from '../modules/chart/TradingChart.vue'
import AuditTerminal from '../modules/terminal/AuditTerminal.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const store = useStrategyStore()
const credentials = useCredentialsStore()

const strategyId = computed(() => Number(route.params.id))

onMounted(async () => {
  await Promise.all([store.fetchAll(), credentials.fetchAll()])
  store.select(strategyId.value)
})

watch(strategyId, (id) => {
  if (!Number.isNaN(id)) store.select(id)
})

watch(
  () => store.strategies,
  () => {
    if (!store.strategies.find((s) => s.id === strategyId.value)) {
      router.replace({ name: 'strategies' })
    }
  },
)
</script>

<template>
  <div class="flex flex-1 min-h-0 flex-col">
    <div v-if="!store.selected" class="flex-1 flex items-center justify-center text-zinc-500">
      {{ t('overview.loading') }}
    </div>
    <template v-else>
      <div class="flex flex-1 min-h-0">
        <aside class="w-80 shrink-0 border-e border-zinc-800 overflow-y-auto">
          <StrategyConfigurator :strategy-id="strategyId" />
        </aside>
        <main class="flex flex-1 flex-col min-w-0">
          <div class="flex-1 min-h-0 relative">
            <TradingChart :strategy-id="strategyId" />
          </div>
          <AuditTerminal />
        </main>
      </div>
    </template>
  </div>
</template>
