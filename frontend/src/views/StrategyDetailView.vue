<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import { useBacktestStore } from '../stores/backtest'
import { useExchangeWebSocket } from '../composables/useExchangeWebSocket'
import { useToast } from '../composables/useToast'
import StrategyConfigurator from '../modules/strategy/StrategyConfigurator.vue'
import TradingChart from '../modules/chart/TradingChart.vue'
import AuditTerminal from '../modules/terminal/AuditTerminal.vue'
import BacktestPanel from '../modules/backtest/BacktestPanel.vue'
import PaperPanel from '../modules/paper/PaperPanel.vue'
import PositionsPanel from '../modules/live/PositionsPanel.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const store = useStrategyStore()
const backtestStore = useBacktestStore()
const toast = useToast()

const positionsPanelRef = ref<{ refresh: () => void } | null>(null)

const mode = ref<'live' | 'backtest' | 'paper'>('live')
const activeBacktestId = ref<number | null>(null)

const strategyId = computed(() => Number(route.params.id))
const hasCredential = computed(() => !!store.selected?.credential)
const isLiveActive = computed(() => store.selected?.status === 'active')
const credentialId = computed(() => (mode.value === 'live' ? store.selected?.credential ?? null : null))

const exchangeWs = useExchangeWebSocket(() => credentialId.value)

onMounted(() => {
  exchangeWs.onEvent((payload) => {
    if (payload.type === 'order.fill' || payload.type === 'order.update') {
      positionsPanelRef.value?.refresh()
      if (payload.status) toast.show(String(payload.status), 'info')
    }
  })
})

function syncModeFromRoute() {
  const qMode = route.query.mode
  if (qMode === 'backtest' || qMode === 'paper' || qMode === 'live') {
    mode.value = qMode
  }
  const btId = route.query.backtestId
  if (btId) activeBacktestId.value = Number(btId)
}

function syncModeFromStrategy() {
  const s = store.selected
  if (!s) return
  if (!route.query.mode) {
    if (!s.credential) mode.value = 'backtest'
    else mode.value = 'live'
  }
}

onMounted(async () => {
  await store.fetchAll()
  store.select(strategyId.value)
  syncModeFromRoute()
  syncModeFromStrategy()
  if (activeBacktestId.value) {
    await backtestStore.fetchAll(strategyId.value)
  }
})

watch(strategyId, async (id) => {
  if (!Number.isNaN(id)) {
    store.select(id)
    syncModeFromStrategy()
    await backtestStore.fetchAll(id)
  }
})

watch(() => store.selected, syncModeFromStrategy)

watch(
  () => store.strategies,
  () => {
    if (!store.strategies.find((s) => s.id === strategyId.value)) {
      router.replace({ name: 'strategies' })
    }
  },
)

function onSelectBacktest(id: number | null) {
  activeBacktestId.value = id
}
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
          <div class="flex items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-900/30">
            <button
              v-if="hasCredential"
              type="button"
              class="rounded-lg px-3 py-1 text-xs font-medium transition-colors"
              :class="mode === 'live' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'"
              @click="mode = 'live'"
            >
              {{ t('backtest.modeLive') }}
            </button>
            <button
              type="button"
              class="rounded-lg px-3 py-1 text-xs font-medium transition-colors"
              :class="mode === 'backtest' ? 'bg-violet-900 text-violet-200' : 'text-zinc-500 hover:text-zinc-300'"
              @click="mode = 'backtest'"
            >
              {{ t('backtest.modeBacktest') }}
            </button>
            <button
              type="button"
              class="rounded-lg px-3 py-1 text-xs font-medium transition-colors"
              :class="mode === 'paper' ? 'bg-cyan-900 text-cyan-200' : 'text-zinc-500 hover:text-zinc-300'"
              @click="mode = 'paper'"
            >
              {{ t('paper.mode') }}
            </button>
            <span v-if="!hasCredential" class="text-xs text-zinc-500 ms-2">{{ t('strategy.liveRequiresCredential') }}</span>
          </div>

          <div class="flex flex-1 min-h-0">
            <div class="flex-1 min-h-0 relative">
              <TradingChart
                :strategy-id="strategyId"
                :mode="mode"
                :backtest-id="activeBacktestId"
              />
            </div>
            <aside
              v-if="mode === 'backtest'"
              class="w-72 shrink-0 border-s border-zinc-800 overflow-hidden flex flex-col"
            >
              <BacktestPanel :strategy-id="strategyId" @select-backtest="onSelectBacktest" />
            </aside>
          </div>

          <AuditTerminal v-if="(mode === 'live' && hasCredential) || mode === 'paper'" :strategy-id="strategyId" />
          <div v-if="mode === 'live' && hasCredential" class="border-t border-zinc-800 p-3">
            <PositionsPanel ref="positionsPanelRef" :strategy-id="strategyId" :active="isLiveActive" />
          </div>
          <div v-if="mode === 'paper'" class="border-t border-zinc-800 p-3">
            <PaperPanel :strategy-id="strategyId" />
          </div>
        </main>
      </div>
    </template>
  </div>
</template>
