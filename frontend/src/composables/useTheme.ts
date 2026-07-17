import { ref } from 'vue'
import { getTheme, setTheme, type Theme } from '../theme'

const themeRef = ref<Theme>(getTheme())

export function useTheme() {
  function toggle() {
    set(themeRef.value === 'dark' ? 'light' : 'dark')
  }
  function set(theme: Theme) {
    themeRef.value = theme
    setTheme(theme)
  }
  return { theme: themeRef, toggle, setTheme: set }
}
