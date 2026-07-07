import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useStorage } from '@vueuse/core'

export const useLayoutStore = defineStore('layout', () => {
  const navCollapsed = useStorage('tb-nav-collapsed', false)
  const backtestPanelOpen = useStorage('tb-backtest-panel-open', true)
  const strategyDrawerOpen = useStorage('tb-strategy-drawer-open', true)
  const optimizerPanelOpen = useStorage('tb-optimizer-panel-open', false)

  const navWidth = computed(() => (navCollapsed.value ? '64px' : '240px'))

  function toggleNav() {
    navCollapsed.value = !navCollapsed.value
  }

  function setBacktestPanelOpen(open: boolean) {
    backtestPanelOpen.value = open
  }

  function toggleBacktestPanel() {
    backtestPanelOpen.value = !backtestPanelOpen.value
  }

  function setStrategyDrawerOpen(open: boolean) {
    strategyDrawerOpen.value = open
  }

  function toggleStrategyDrawer() {
    strategyDrawerOpen.value = !strategyDrawerOpen.value
  }

  function setOptimizerPanelOpen(open: boolean) {
    optimizerPanelOpen.value = open
  }

  function toggleOptimizerPanel() {
    optimizerPanelOpen.value = !optimizerPanelOpen.value
  }

  function applyBacktestModeDefaults() {
    strategyDrawerOpen.value = false
    backtestPanelOpen.value = true
  }

  function applyLiveModeDefaults() {
    strategyDrawerOpen.value = true
  }

  return {
    isNavCollapsed: navCollapsed,
    navCollapsed,
    backtestPanelOpen,
    strategyDrawerOpen,
    optimizerPanelOpen,
    navWidth,
    toggleNav,
    setBacktestPanelOpen,
    toggleBacktestPanel,
    setStrategyDrawerOpen,
    toggleStrategyDrawer,
    setOptimizerPanelOpen,
    toggleOptimizerPanel,
    applyBacktestModeDefaults,
    applyLiveModeDefaults,
  }
})
