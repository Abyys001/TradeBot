import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, type ExecutionLog } from '../api/client'

export interface TerminalLine {
  id: string
  level: string
  message: string
  created_at: string
}

export const useTerminalStore = defineStore('terminal', () => {
  const lines = ref<TerminalLine[]>([])
  const levelFilter = ref<string>('all')
  const paused = ref(false)

  async function fetchLogs(limit = 100) {
    const { data } = await api.get<ExecutionLog[]>('/logs/', { params: { limit } })
    lines.value = data.reverse().map((log) => ({
      id: String(log.id),
      level: log.level,
      message: formatLogMessage(log),
      created_at: log.created_at,
    }))
  }

  function formatLogMessage(log: ExecutionLog): string {
    const p = log.payload || {}
    if (log.event === 'bar.received') {
      return `Received ${p.timeframe} candle for ${p.symbol}`
    }
    if (log.event === 'strategy.evaluated') {
      return `Strategy '${p.name}' evaluated: ${p.action}`
    }
    if (log.event === 'order.placed') {
      return `Signal Triggered: ${String(p.side).toUpperCase()} ${p.symbol} at ${p.price}. Pushing to Celery...`
    }
    if (log.event === 'order.filled') {
      return `Hyperliquid Response: Order #${p.exchange_order_id} Filled.`
    }
    if (log.event === 'kill_switch.triggered') {
      return 'Kill switch triggered — all strategies stopped.'
    }
    return log.event
  }

  function pushLine(payload: Record<string, unknown>) {
    if (payload.source !== 'log') return
    const line: TerminalLine = {
      id: `${Date.now()}-${Math.random()}`,
      level: String(payload.level || 'info'),
      message: String(payload.message || payload.event),
      created_at: String(payload.created_at || new Date().toISOString()),
    }
    lines.value.push(line)
    if (lines.value.length > 500) lines.value.shift()
  }

  const filteredLines = computed(() => {
    if (levelFilter.value === 'all') return lines.value
    return lines.value.filter((l) => l.level === levelFilter.value)
  })

  return { lines, levelFilter, paused, fetchLogs, pushLine, filteredLines, formatLogMessage }
})
