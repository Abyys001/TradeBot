import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useStorage } from '@vueuse/core'

export const useLayoutStore = defineStore('layout', () => {
  const navCollapsed = useStorage('tb-nav-collapsed', false)
  // Mobile off-canvas sidebar state — deliberately separate from navCollapsed:
  // collapsed/expanded is a desktop-only icon-vs-label axis, open/closed is
  // whether the drawer is on/off screen at all. Not persisted across reloads
  // (always starts closed) since it's a transient overlay, not a preference.
  const mobileNavOpen = ref(false)
  const backtestPanelOpen = useStorage('tb-backtest-panel-open', true)
  const strategyDrawerOpen = useStorage('tb-strategy-drawer-open', true)
  const optimizerPanelOpen = useStorage('tb-optimizer-panel-open', false)

  const navWidth = computed(() => (navCollapsed.value ? '64px' : '240px'))

  function toggleNav() {
    navCollapsed.value = !navCollapsed.value
  }

  function setMobileNavOpen(open: boolean) {
    mobileNavOpen.value = open
  }

  function toggleMobileNavOpen() {
    mobileNavOpen.value = !mobileNavOpen.value
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
    mobileNavOpen,
    backtestPanelOpen,
    strategyDrawerOpen,
    optimizerPanelOpen,
    navWidth,
    toggleNav,
    setMobileNavOpen,
    toggleMobileNavOpen,
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
