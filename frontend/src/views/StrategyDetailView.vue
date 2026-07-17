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
import { useBreakpoints } from '../composables/useBreakpoints'
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
const showToolbarMenu = ref(false)
const { isMobile } = useBreakpoints()

function toggleOptimizerPanel() {
  // On a phone, the backtest/live panel and the optimizer panel are both
  // full-width overlays — never let both be open at once.
  if (isMobile.value && !layout.optimizerPanelOpen) {
    layout.setBacktestPanelOpen(false)
  }
  layout.toggleOptimizerPanel()
}

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
    <div v-if="!store.selected" class="flex flex-1 items-center justify-center text-fg-muted">
      {{ t('overview.loading') }}
    </div>
    <template v-else>
      <div class="relative flex min-h-0 flex-1 overflow-hidden">
        <main class="flex flex-1 min-h-0 min-w-0 flex-col overflow-hidden">
          <div class="flex shrink-0 flex-wrap items-center gap-2 border-b border-border bg-surface-raised px-3 py-2">
            <button
              type="button"
              class="rounded-lg border border-border px-2 py-1 text-xs text-fg-muted transition-colors hover:bg-surface-raised hover:text-fg"
              @click="router.push({ name: 'strategies' })"
            >
              ΓåÉ {{ t('backtest.backToStrategies') }}
            </button>
            <div class="min-w-0">
              <h1 class="text-sm font-semibold text-accent">{{ t('backtest.engineTitle') }}</h1>
              <p class="truncate text-xs text-fg-muted">{{ store.selected.name }}</p>
            </div>
            <div class="ms-auto flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="hidden rounded-lg border border-border px-3 py-1 text-xs text-fg transition-colors hover:bg-surface-raised sm:inline-block"
                @click="showPineModal = true"
              >
                {{ t('backtest.editPineScript') }}
              </button>
              <button
                type="button"
                class="hidden rounded-lg border border-border px-3 py-1 text-xs text-fg transition-colors hover:bg-surface-raised sm:inline-block"
                @click="showAdvancedModal = true"
              >
                {{ t('backtest.advancedSettings') }}
              </button>
              <button
                type="button"
                class="rounded-lg border px-3 py-1 text-xs transition-colors"
                :class="layout.optimizerPanelOpen ? 'border-warning bg-warning-bg text-warning' : 'border-border text-fg-muted hover:text-fg'"
                @click="toggleOptimizerPanel()"
              >
                {{ t('backtest.optimize') }}
              </button>
              <div class="relative sm:hidden">
                <button
                  type="button"
                  class="flex h-7 w-7 items-center justify-center rounded-lg border border-border text-fg-muted hover:bg-surface-raised hover:text-fg"
                  :aria-label="t('nav.moreActions')"
                  @click="showToolbarMenu = !showToolbarMenu"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                    <circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" />
                  </svg>
                </button>
                <div v-if="showToolbarMenu" class="fixed inset-0 z-10" @click="showToolbarMenu = false" />
                <div
                  v-if="showToolbarMenu"
                  class="absolute end-0 top-full z-20 mt-1 w-44 overflow-hidden rounded-lg border border-border bg-surface shadow-xl"
                >
                  <button
                    type="button"
                    class="block w-full px-3 py-2 text-start text-xs text-fg hover:bg-surface-raised"
                    @click="showPineModal = true; showToolbarMenu = false"
                  >
                    {{ t('backtest.editPineScript') }}
                  </button>
                  <button
                    type="button"
                    class="block w-full px-3 py-2 text-start text-xs text-fg hover:bg-surface-raised"
                    @click="showAdvancedModal = true; showToolbarMenu = false"
                  >
                    {{ t('backtest.advancedSettings') }}
                  </button>
                </div>
              </div>
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
              class="absolute inset-0 z-10 bg-surface/60 backdrop-blur-[1px]"
            >
              <ChartSkeleton />
            </div>
            <button
              v-if="showViewResultsBtn && activeBacktestId"
              type="button"
              class="absolute end-2 top-2 z-20 rounded-lg bg-accent px-2.5 py-1.5 text-xs font-medium text-accent-fg shadow-lg hover:opacity-90 sm:end-4 sm:top-4 sm:px-4 sm:py-2 sm:text-sm"
              @click="openResults(activeBacktestId!)"
            >
              {{ t('backtest.viewResults') }}
            </button>
          </div>
        </main>

        <aside
          v-show="layout.backtestPanelOpen"
          class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex min-h-0 flex-col overflow-x-hidden overflow-y-auto border-s border-border bg-surface fixed inset-y-0 end-0 z-40 w-80 max-w-[85vw] shadow-2xl lg:relative lg:inset-auto lg:z-auto lg:w-[400px] lg:max-w-none lg:shadow-none"
        >
          <div class="sticky top-0 z-10 shrink-0 border-b border-border bg-surface/95 px-4 py-2 backdrop-blur-sm">
            <div class="flex items-center justify-between mb-2">
              <div class="flex gap-1">
                <button
                  type="button"
                  class="rounded px-2 py-0.5 text-xs font-medium transition-colors"
                  :class="sidebarTab === 'backtest' ? 'bg-accent text-accent-fg' : 'text-fg-muted hover:text-fg'"
                  @click="sidebarTab = 'backtest'"
                >
                  {{ t('live.tabBacktest') }}
                </button>
                <button
                  type="button"
                  class="rounded px-2 py-0.5 text-xs font-medium transition-colors"
                  :class="sidebarTab === 'live' ? 'bg-accent text-accent-fg' : 'text-fg-muted hover:text-fg'"
                  @click="sidebarTab = 'live'"
                >
                  {{ t('live.tabLive') }}
                </button>
              </div>
              <button type="button" class="rounded px-1.5 py-0.5 text-fg-muted hover:bg-surface-raised hover:text-fg lg:hidden" @click="layout.setBacktestPanelOpen(false)">✘</button>
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
        class="fixed bottom-4 end-4 z-20 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-fg shadow-lg hover:opacity-90 lg:hidden"
        @click="layout.setBacktestPanelOpen(true)"
      >
        ⚙
      </button>

      <div
        v-if="layout.optimizerPanelOpen"
        class="fixed inset-0 z-30 bg-black/50 lg:hidden"
        @click="layout.setOptimizerPanelOpen(false)"
      />

      <div
        v-show="layout.optimizerPanelOpen"
        class="fixed inset-y-0 end-0 z-40 flex w-80 max-w-[90vw] flex-col border-s border-border bg-surface shadow-2xl lg:absolute"
      >
        <div class="flex shrink-0 items-center justify-between border-b border-border px-3 py-2">
          <span class="text-sm font-medium text-warning">{{ t('backtest.optimize') }}</span>
          <button
            type="button"
            class="rounded px-2 py-0.5 text-fg-muted hover:bg-surface-raised hover:text-fg"
            @click="layout.setOptimizerPanelOpen(false)"
          >
            Γ£ò
          </button>
        </div>
        <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade min-h-0 flex-1 overflow-y-auto p-3">
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
