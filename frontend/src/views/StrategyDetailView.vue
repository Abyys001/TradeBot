<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import { useBacktestStore } from '../stores/backtest'
import { useHistoryStore } from '../stores/history'
import { useLayoutStore } from '../stores/layout'
import { useStrategyForm } from '../composables/useStrategyForm'
import { useBacktestHotkeys } from '../composables/useBacktestHotkeys'
import { useToast } from '../composables/useToast'
import TradingChart from '../modules/chart/TradingChart.vue'
import BacktestPanel from '../modules/backtest/BacktestPanel.vue'
import BacktestResultsModal from '../modules/backtest/BacktestResultsModal.vue'
import PineScriptModal from '../modules/strategy/PineScriptModal.vue'
import AdvancedSettingsModal from '../modules/strategy/AdvancedSettingsModal.vue'
import OptimizerPanel from '../modules/optimizer/OptimizerPanel.vue'
import LiveDeploymentPanel from '../modules/live/LiveDeploymentPanel.vue'
import ChartSkeleton from '../components/ChartSkeleton.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const store = useStrategyStore()
const backtestStore = useBacktestStore()
const historyStore = useHistoryStore()
const layout = useLayoutStore()
const toast = useToast()

const activeBacktestId = ref<number | null>(null)
const showPineModal = ref(false)
const showAdvancedModal = ref(false)
const resultsModalBacktestId = ref<number | null>(null)
const lastAutoShownId = ref<number | null>(null)
const backtestPanelRef = ref<InstanceType<typeof BacktestPanel> | null>(null)
const sidebarTab = ref<'backtest' | 'live'>('backtest')

const strategyId = computed(() => Number(route.params.id))
const strategyForm = useStrategyForm(strategyId)

const activeBacktest = computed(() => backtestStore.active)
const resultsBacktest = computed(() => {
  if (!resultsModalBacktestId.value) return null
  return backtestStore.backtests.find((b) => b.id === resultsModalBacktestId.value) ?? null
})

const showViewResultsBtn = computed(
  () => activeBacktest.value?.status === 'done' && activeBacktest.value?.metrics,
)

const isBacktestRunning = computed(() => {
  const bt = activeBacktest.value
  if (!bt || activeBacktestId.value !== bt.id) return false
  return bt.status === 'pending' || bt.status === 'running'
})

const hotkeysBlocked = computed(
  () =>
    showPineModal.value ||
    showAdvancedModal.value ||
    !!resultsModalBacktestId.value ||
    layout.optimizerPanelOpen,
)

useBacktestHotkeys({
  run: () => backtestPanelRef.value?.runBacktests(),
  canRun: () => backtestPanelRef.value?.canRun ?? false,
  blocked: hotkeysBlocked,
})

function syncBacktestFromRoute() {
  const btId = route.query.backtestId
  if (btId) {
    const id = Number(btId)
    activeBacktestId.value = id
    backtestStore.select(id)
  }
}

function openResults(id: number) {
  resultsModalBacktestId.value = id
}

function closeResults() {
  resultsModalBacktestId.value = null
}

async function initBacktestData(id: number) {
  await Promise.all([
    backtestStore.fetchAll(id),
    historyStore.fetchDatasets(),
    historyStore.fetchMarkets('mainnet'),
  ])
  if (backtestStore.activeBacktests.length) {
    backtestStore.startPollingActive()
  }
}

onMounted(async () => {
  layout.applyBacktestModeDefaults()
  layout.setBacktestPanelOpen(true)

  await store.fetchAll({ preserveSelection: true })
  store.select(strategyId.value)
  syncBacktestFromRoute()
  await initBacktestData(strategyId.value)
  if (activeBacktestId.value) {
    await backtestStore.fetchOne(activeBacktestId.value)
  }
})

onUnmounted(() => {
  if (!backtestStore.activeBacktests.length) {
    backtestStore.stopPollingActive()
  }
})

watch(
  () => route.query.backtestId,
  async (btId) => {
    if (!btId) return
    const id = Number(btId)
    activeBacktestId.value = id
    backtestStore.select(id)
    await backtestStore.fetchOne(id)
  },
)

watch(strategyId, async (id) => {
  if (!Number.isNaN(id)) {
    store.select(id)
    await initBacktestData(id)
  }
})

watch(
  () => store.strategies,
  () => {
    if (!store.strategies.find((s) => s.id === strategyId.value)) {
      router.replace({ name: 'strategies' })
    }
  },
)

watch(
  () => backtestStore.active?.status,
  (status, prev) => {
    const id = backtestStore.activeId
    const bt = backtestStore.active
    if (status === 'done' && prev !== 'done' && id && id !== lastAutoShownId.value) {
      lastAutoShownId.value = id
      toast.show(t('backtest.completed'), 'success')
      openResults(id)
    }
    if (status === 'failed' && prev !== 'failed' && bt) {
      toast.show(bt.error || t('backtest.runFailed'), 'error')
    }
  },
)

function onSelectBacktest(id: number | null) {
  activeBacktestId.value = id
  if (id) {
    void router.replace({
      query: { ...route.query, backtestId: String(id) },
    })
  } else {
    const { backtestId: _removed, ...rest } = route.query
    void router.replace({ query: rest })
  }
}

function onViewResults(id: number) {
  openResults(id)
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col">
    <div v-if="!store.selected" class="flex flex-1 items-center justify-center text-zinc-500">
      {{ t('overview.loading') }}
    </div>
    <template v-else>
      <div class="relative flex min-h-0 flex-1 overflow-hidden">
        <main class="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <div class="flex shrink-0 flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-900/30 px-3 py-2">
            <button
              type="button"
              class="rounded-lg border border-zinc-700 px-2 py-1 text-xs text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
              @click="router.push({ name: 'strategies' })"
            >
              ΓåÉ {{ t('backtest.backToStrategies') }}
            </button>
            <div class="min-w-0">
              <h1 class="text-sm font-semibold text-violet-200">{{ t('backtest.engineTitle') }}</h1>
              <p class="truncate text-xs text-zinc-500">{{ store.selected.name }}</p>
            </div>
            <div class="ms-auto flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-300 transition-colors hover:bg-zinc-800"
                @click="showPineModal = true"
              >
                {{ t('backtest.editPineScript') }}
              </button>
              <button
                type="button"
                class="rounded-lg border border-zinc-700 px-3 py-1 text-xs text-zinc-300 transition-colors hover:bg-zinc-800"
                @click="showAdvancedModal = true"
              >
                ΓÜÖ {{ t('backtest.advancedSettings') }}
              </button>
              <button
                type="button"
                class="rounded-lg border px-3 py-1 text-xs transition-colors"
                :class="layout.optimizerPanelOpen ? 'border-amber-700 bg-amber-950 text-amber-200' : 'border-zinc-700 text-zinc-500 hover:text-zinc-300'"
                @click="layout.toggleOptimizerPanel()"
              >
                {{ t('backtest.optimize') }}
              </button>
            </div>
          </div>

          <div class="relative min-h-0 flex-1 overflow-hidden">
            <TradingChart
              class="h-full w-full"
              :strategy-id="strategyId"
              mode="backtest"
              :backtest-id="activeBacktestId"
            />
            <div
              v-if="isBacktestRunning"
              class="absolute inset-0 z-10 bg-zinc-950/60 backdrop-blur-[1px]"
            >
              <ChartSkeleton />
            </div>
            <button
              v-if="showViewResultsBtn && activeBacktestId"
              type="button"
              class="absolute end-4 top-4 z-20 rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white shadow-lg hover:bg-violet-600"
              @click="openResults(activeBacktestId!)"
            >
              {{ t('backtest.viewResults') }}
            </button>
          </div>
        </main>

        <aside
          v-show="layout.backtestPanelOpen"
          class="scrollbar-styled flex min-h-0 flex-col overflow-x-hidden overflow-y-auto border-s border-zinc-800 bg-zinc-950 fixed inset-y-0 end-0 z-40 w-80 max-w-[85vw] shadow-2xl lg:relative lg:inset-auto lg:z-auto lg:w-[400px] lg:max-w-none lg:shadow-none"
        >
          <div class="sticky top-0 z-10 shrink-0 border-b border-zinc-800 bg-zinc-950/95 px-4 py-2 backdrop-blur-sm">
            <div class="flex items-center justify-between mb-2">
              <div class="flex gap-1">
                <button
                  type="button"
                  class="rounded px-2 py-0.5 text-xs font-medium transition-colors"
                  :class="sidebarTab === 'backtest' ? 'bg-violet-700 text-white' : 'text-zinc-400 hover:text-zinc-200'"
                  @click="sidebarTab = 'backtest'"
                >
                  {{ t('live.tabBacktest') }}
                </button>
                <button
                  type="button"
                  class="rounded px-2 py-0.5 text-xs font-medium transition-colors"
                  :class="sidebarTab === 'live' ? 'bg-violet-700 text-white' : 'text-zinc-400 hover:text-zinc-200'"
                  @click="sidebarTab = 'live'"
                >
                  {{ t('live.tabLive') }}
                </button>
              </div>
              <button type="button" class="rounded px-1.5 py-0.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 lg:hidden" @click="layout.setBacktestPanelOpen(false)">✘</button>
            </div>
          </div>
          <BacktestPanel
            v-show="sidebarTab === 'backtest'"
            ref="backtestPanelRef"
            class="min-h-0 flex-1"
            :strategy-id="strategyId"
            @select-backtest="onSelectBacktest"
            @view-results="onViewResults"
          />
          <LiveDeploymentPanel
            v-show="sidebarTab === 'live'"
            class="min-h-0 flex-1"
            :strategy-id="strategyId"
          />
        </aside>
      </div>

      <div
        v-if="layout.backtestPanelOpen"
        class="fixed inset-0 z-30 bg-black/50 lg:hidden"
        @click="layout.setBacktestPanelOpen(false)"
      />

      <button
        v-if="!layout.backtestPanelOpen"
        type="button"
        class="fixed bottom-4 end-4 z-20 flex h-12 w-12 items-center justify-center rounded-full bg-violet-700 text-white shadow-lg hover:bg-violet-600 lg:hidden"
        @click="layout.setBacktestPanelOpen(true)"
      >
        ⚙
      </button>

      <div
        v-show="layout.optimizerPanelOpen"
        class="absolute inset-y-0 end-0 z-40 flex w-80 max-w-[90vw] flex-col border-s border-zinc-700 bg-zinc-950 shadow-2xl"
      >
        <div class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-3 py-2">
          <span class="text-sm font-medium text-amber-200">{{ t('backtest.optimize') }}</span>
          <button
            type="button"
            class="rounded px-2 py-0.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            @click="layout.setOptimizerPanelOpen(false)"
          >
            Γ£ò
          </button>
        </div>
        <div class="scrollbar-styled min-h-0 flex-1 overflow-y-auto p-3">
          <OptimizerPanel :strategy-id="strategyId" />
        </div>
      </div>

      <PineScriptModal
        v-if="showPineModal"
        :strategy-form="strategyForm"
        @close="showPineModal = false"
      />
      <AdvancedSettingsModal
        v-if="showAdvancedModal"
        :strategy-form="strategyForm"
        @close="showAdvancedModal = false"
      />
      <BacktestResultsModal
        v-if="resultsBacktest"
        :backtest="resultsBacktest"
        @close="closeResults"
      />
    </template>
  </div>
</template>
