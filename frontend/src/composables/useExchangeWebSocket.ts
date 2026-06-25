import { onUnmounted, ref, watch } from 'vue'
import { useWebSocket } from '@vueuse/core'

export type ExchangeWsHandler = (payload: Record<string, unknown>) => void

export function useExchangeWebSocket(credentialId: () => number | null | undefined) {
  const connected = ref(false)
  const handlers = new Set<ExchangeWsHandler>()

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'

  const url = ref('')
  const { status, data, close, open } = useWebSocket(url, {
    immediate: false,
    autoReconnect: { retries: 5, delay: 3000 },
  })

  watch(status, (s) => {
    connected.value = s === 'OPEN'
  })

  watch(data, (raw) => {
    if (!raw) return
    try {
      const payload = JSON.parse(raw) as Record<string, unknown>
      handlers.forEach((h) => h(payload))
    } catch {
      /* ignore */
    }
  })

  watch(
    credentialId,
    (id) => {
      close()
      if (!id) {
        url.value = ''
        return
      }
      url.value = `${protocol}://${window.location.host}/ws/exchange/${id}/`
      open()
    },
    { immediate: true },
  )

  function onEvent(handler: ExchangeWsHandler) {
    handlers.add(handler)
    return () => handlers.delete(handler)
  }

  onUnmounted(() => {
    handlers.clear()
    close()
  })

  return { connected, onEvent }
}
