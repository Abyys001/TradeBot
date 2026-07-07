import { onMounted, onUnmounted } from 'vue'

export function useHotkeys(bindings: Record<string, () => void>) {
  function onKeydown(e: KeyboardEvent) {
    const mod = e.ctrlKey || e.metaKey
    if (mod && e.key === 'Enter') {
      const handler = bindings['mod+enter']
      if (handler) {
        e.preventDefault()
        handler()
      }
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))
}
