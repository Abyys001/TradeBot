import { defineStore } from 'pinia'

/**
 * Chrome state: the navigation rail, and which pane a small screen is showing.
 *
 * Kept in a store rather than in the layout so a page can steer it — the chart
 * page, for example, collapses the rail on arrival because it wants every pixel
 * of width, and gives it back on the way out.
 *
 * A setup-style store because the collapse preference lives in a cookie: it is
 * readable during SSR, so the rail renders at its final width in the first HTML
 * the browser parses. Held in memory only, every reload flashed the rail open
 * and then snapped it shut.
 */
export const useUiStore = defineStore('ui', () => {
  const collapsed = useCookie<boolean>('sidebar-collapsed', {
    default: () => false,
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  /**
   * What the admin actually chose, as opposed to what a page imposed. The chart
   * page collapses the rail on arrival; without remembering the preference, one
   * visit to the chart would silently become the setting forever.
   */
  const preference = ref(collapsed.value)
  const autoCollapsed = ref(false)

  const drawerOpen = ref(false)
  const chartPane = ref<'chart' | 'ticket' | 'accounts'>('chart')

  function toggleSidebar() {
    collapsed.value = !collapsed.value
    // A manual toggle *is* the new preference, even on the chart page.
    preference.value = collapsed.value
    autoCollapsed.value = false
  }

  /**
   * Called on every route change. Pages that want the rail out of the way say
   * so here rather than reaching into the sidebar component.
   */
  function syncToRoute(name: string) {
    if (name === 'chart') {
      if (!collapsed.value) {
        preference.value = collapsed.value
        collapsed.value = true
        autoCollapsed.value = true
      }
      return
    }
    if (autoCollapsed.value) {
      collapsed.value = preference.value
      autoCollapsed.value = false
    }
  }

  const openDrawer = () => {
    drawerOpen.value = true
  }
  const closeDrawer = () => {
    drawerOpen.value = false
  }
  const showPane = (pane: 'chart' | 'ticket' | 'accounts') => {
    chartPane.value = pane
  }

  return {
    // `sidebarCollapsed` keeps its old name: it is read in three components.
    sidebarCollapsed: collapsed,
    drawerOpen,
    chartPane,
    toggleSidebar,
    syncToRoute,
    openDrawer,
    closeDrawer,
    showPane,
  }
})
