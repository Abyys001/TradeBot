import { watch } from 'vue'
import { useStorage } from '@vueuse/core'

export type Theme = 'dark' | 'light'

// Persisted theme. The viewer's toggle stamps `data-theme` on <html>; Tailwind
// `dark:` variants key off the `dark` class. Defaults to dark (the app's
// original hardcoded look) so existing users see no change.
const theme = useStorage<Theme>('tb-theme', 'dark')

function apply(value: Theme) {
  const root = document.documentElement
  root.setAttribute('data-theme', value)
  root.classList.toggle('dark', value === 'dark')
}

export function useTheme() {
  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }
  return { theme, toggle }
}

// Call once at app startup to sync the DOM with the stored value.
export function initTheme() {
  apply(theme.value)
  watch(theme, apply)
}
