import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'

export interface PaperTrade {
  id: number
  side: string
  entry_price: string
  exit_price: string | null
  size: string
  pnl: string
  entry_bar: number
  exit_bar: number | null
  created_at: string
}

export const usePaperStore = defineStore('paper', () => {
  const balance = ref('—')
  const equity = ref('—')
  const active = ref(false)
  const trades = ref<PaperTrade[]>([])

  function applyWs(payload: Record<string, unknown>) {
    if (payload.source !== 'paper') return
    if (payload.equity != null) equity.value = String(payload.equity)
    if (payload.balance != null) balance.value = String(payload.balance)
  }

  async function fetchAccount(strategyId: number) {
    const { data } = await api.get<{ balance: string; equity: string; is_active: boolean }>(
      `/paper/${strategyId}/`,
    )
    balance.value = data.balance
    equity.value = data.equity
    active.value = data.is_active
    return data
  }

  async function fetchTrades(strategyId: number) {
    const { data } = await api.get<{ trades: PaperTrade[] }>(`/paper/${strategyId}/trades/`)
    trades.value = data.trades
    return data.trades
  }

  async function start(strategyId: number) {
    await api.post(`/paper/${strategyId}/`)
    await fetchAccount(strategyId)
  }

  async function stop(strategyId: number) {
    await api.delete(`/paper/${strategyId}/`)
    await fetchAccount(strategyId)
  }

  return { balance, equity, active, trades, applyWs, fetchAccount, fetchTrades, start, stop }
})
