import { onUnmounted, ref, watch } from 'vue'
import { useWebSocket } from '@vueuse/core'
import { useAuthStore } from '../stores/auth'
import { useBacktestStore } from '../stores/backtest'
import { useChartStore } from '../stores/chart'
import { useHealthStore } from '../stores/health'
import { useHistoryStore } from '../stores/history'
import { usePaperStore } from '../stores/paper'
import { useTerminalStore } from '../stores/terminal'

export function useDashboardWebSocket() {
  const connected = ref(false)
  const auth = useAuthStore()
  const health = useHealthStore()
  const terminal = useTerminalStore()
  const chart = useChartStore()
  const backtest = useBacktestStore()
<<<<<<< HEAD
=======
  const history = useHistoryStore()
  const paper = usePaperStore()
>>>>>>> 1af07065fe5a87dc8ca34e162c3bf176e3907b0c

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${protocol}://${window.location.host}/ws/dashboard/`

  const { status, data, close, open } = useWebSocket(url, {
    immediate: false,
    autoReconnect: { retries: 10, delay: 2000 },
  })

  watch(status, (s) => {
    connected.value = s === 'OPEN'
  })

  watch(data, (raw) => {
    if (!raw) return
    try {
      const payload = JSON.parse(raw) as Record<string, unknown>
      if (payload.source === 'health') health.applyWsPayload(payload)
      if (payload.source === 'log') terminal.pushLine(payload)
      if (payload.source === 'candle_tick') chart.applyCandleTick(payload)
      if (payload.source === 'pnl') chart.applyPnl(payload)
<<<<<<< HEAD
      if (payload.source === 'backtest') backtest.applyWsPayload(payload)
=======
      if (payload.source === 'backtest') backtest.applyWs(payload)
      if (payload.source === 'history_download') history.applyWs(payload)
      if (payload.source === 'paper') paper.applyWs(payload)
>>>>>>> 1af07065fe5a87dc8ca34e162c3bf176e3907b0c
      if (payload.source === 'kill_switch' && auth.user) {
        auth.user.is_trading_enabled = false
      }
    } catch {
      /* ignore malformed */
    }
  })

  function connect() {
    if (auth.user) open()
  }

  function disconnect() {
    close()
  }

  onUnmounted(disconnect)

  return { connected, connect, disconnect, status }
}
