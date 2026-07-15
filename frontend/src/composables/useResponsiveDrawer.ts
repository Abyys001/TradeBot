import { watch, type Ref } from 'vue'
import { useRoute } from 'vue-router'

export interface UseResponsiveDrawerOptions {
  isOpen: Ref<boolean>
  setOpen: (open: boolean) => void
  /** Close the drawer whenever the route changes (e.g. nav drawers). */
  closeOnRouteChange?: boolean
}

/**
 * Shared open/close lifecycle for off-canvas drawers (mobile sidebar, side
 * panels, etc). Positioning itself stays pure CSS (`fixed ... lg:relative`,
 * mirroring StrategyDetailView's backtest-panel pattern) since Tailwind's
 * `lg:` variants already make desktop ignore the open/closed state — this
 * composable only centralizes the state transitions, not the class strings,
 * because panel width/placement legitimately differs per consumer.
 */
export function useResponsiveDrawer(options: UseResponsiveDrawerOptions) {
  const { isOpen, setOpen, closeOnRouteChange = false } = options

  function open() {
    setOpen(true)
  }
  function close() {
    setOpen(false)
  }
  function toggle() {
    setOpen(!isOpen.value)
  }

  if (closeOnRouteChange) {
    const route = useRoute()
    watch(() => route.fullPath, close)
  }

  return { open, close, toggle }
}
