export type Theme = 'dark' | 'light'

/**
 * Theme, held in a cookie rather than localStorage.
 *
 * The cookie is readable during SSR, so `data-theme` is already correct in the
 * first HTML the browser parses. localStorage would only be readable after
 * hydration, which means a flash of the wrong theme on every load — on a
 * near-black panel that flash is a full white screen.
 */
export function useTheme() {
  const theme = useCookie<Theme>('theme', {
    default: () => 'dark',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  const isDark = computed(() => theme.value !== 'light')

  function toggle() {
    theme.value = isDark.value ? 'light' : 'dark'
  }

  return { theme, isDark, toggle }
}

/** Reads a themed colour token as a hex/rgb string usable by canvas charts. */
export function tokenColor(name: string, fallback = '#888'): string {
  if (import.meta.server) return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!raw) return fallback
  // Tokens are stored as "R G B" triplets so Tailwind can add an alpha channel;
  // canvas APIs want a colour string.
  return /^[\d\s]+$/.test(raw) ? `rgb(${raw.split(/\s+/).join(', ')})` : raw
}
