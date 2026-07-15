import { useBreakpoints as useVueUseBreakpoints } from '@vueuse/core'

/**
 * Tailwind v4 default breakpoints (no tailwind.config.js in this project —
 * config lives in src/style.css). Kept in sync with the `sm:`/`md:`/`lg:` etc.
 * classes used throughout the app so JS-side checks agree with CSS-side ones.
 */
export const TAILWIND_BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
}

export function useBreakpoints() {
  const breakpoints = useVueUseBreakpoints(TAILWIND_BREAKPOINTS)

  // `lg` is the cutoff already used by the in-repo drawer pattern
  // (StrategyDetailView's backtest panel: `lg:relative ... lg:hidden`).
  const isMobile = breakpoints.smaller('lg')
  const isTablet = breakpoints.between('sm', 'lg')
  const isPhone = breakpoints.smaller('sm')

  return { breakpoints, isMobile, isTablet, isPhone }
}
