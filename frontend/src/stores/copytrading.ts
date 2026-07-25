import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  api,
  type AdminCopyOverview,
  type AdminInvestor,
  type CopyEquityPoint,
  type CopySummary,
  type CopyTradeRow,
  type FeeConfig,
  type FeeLedger,
  type FeeLedgerRow,
  type InvestorPosition,
  type MasterStrategy,
  type Subscription,
} from '../api/client'

export const useCopytradingStore = defineStore('copytrading', () => {
  // Legacy investor model
  const masters = ref<MasterStrategy[]>([])
  const subscriptions = ref<Subscription[]>([])
  const positions = ref<InvestorPosition[]>([])
  const myFees = ref<FeeLedger[]>([])
  const investors = ref<AdminInvestor[]>([])
  const ledger = ref<FeeLedger[]>([])
  const feeConfig = ref<FeeConfig | null>(null)

  // New summary model
  const summary = ref<CopySummary | null>(null)
  const trades = ref<CopyTradeRow[]>([])
  const equity = ref<CopyEquityPoint[]>([])
  const overview = ref<AdminCopyOverview | null>(null)
  const newLedger = ref<FeeLedgerRow[]>([])
  const strategyPnl = ref<Record<string, string>>({})
  const loading = ref(false)

  // ---- investor (legacy) ----
  async function fetchMarketplace() {
    const { data } = await api.get<MasterStrategy[]>('/copytrading/marketplace/')
    masters.value = data
    return data
  }

  async function fetchSubscriptions() {
    const { data } = await api.get<Subscription[]>('/copytrading/subscriptions/')
    subscriptions.value = data
    return data
  }

  async function subscribe(payload: Partial<Subscription>) {
    const { data } = await api.post<Subscription>('/copytrading/subscriptions/', payload)
    subscriptions.value.unshift(data)
    return data
  }

  async function unsubscribe(id: number) {
    await api.delete(`/copytrading/subscriptions/${id}/`)
    subscriptions.value = subscriptions.value.filter((s) => s.id !== id)
  }

  async function setActive(id: number, active: boolean) {
    const { data } = await api.post<Subscription>(
      `/copytrading/subscriptions/${id}/${active ? 'resume' : 'pause'}/`,
    )
    const idx = subscriptions.value.findIndex((s) => s.id === id)
    if (idx >= 0) subscriptions.value[idx].is_active = data.is_active
    return data
  }

  async function fetchMyPositions() {
    const { data } = await api.get<InvestorPosition[]>('/copytrading/my/positions/')
    positions.value = data
    return data
  }

  async function fetchMyFees() {
    const { data } = await api.get<FeeLedger[]>('/copytrading/my/fees/')
    myFees.value = data
    return data
  }

  // ---- investor (new) ----
  async function fetchMy() {
    loading.value = true
    try {
      const [s, t, e] = await Promise.all([
        api.get<CopySummary>('/copytrading/my/summary/'),
        api.get<CopyTradeRow[]>('/copytrading/my/trades/'),
        api.get<CopyEquityPoint[]>('/copytrading/my/equity/'),
      ])
      summary.value = s.data
      trades.value = t.data
      equity.value = e.data
    } finally {
      loading.value = false
    }
  }

  // ---- admin ----
  async function fetchInvestors() {
    const { data } = await api.get<AdminInvestor[]>('/copytrading/admin/investors/')
    investors.value = data
    return data
  }

  async function fetchLedger() {
    const { data } = await api.get<FeeLedger[]>('/copytrading/admin/fee-ledger/')
    ledger.value = data
    return data
  }

  async function fetchFeeConfig() {
    const { data } = await api.get<FeeConfig>('/copytrading/admin/fee-config/')
    feeConfig.value = data
    return data
  }

  async function setFeeConfig(share_pct: string) {
    const { data } = await api.patch<FeeConfig>('/copytrading/admin/fee-config/', { share_pct })
    feeConfig.value = data
    return data
  }

  async function saveFeeConfig(patch: Partial<FeeConfig>) {
    const { data } = await api.put<FeeConfig>('/copytrading/fee-config/', patch)
    feeConfig.value = data
    return data
  }

  async function publishStrategy(id: number, is_master: boolean, published: boolean) {
    const { data } = await api.post(`/copytrading/admin/strategies/${id}/publish/`, {
      is_master,
      published,
    })
    return data
  }

  async function fetchAdmin() {
    loading.value = true
    try {
      const [o, c, l] = await Promise.all([
        api.get<AdminCopyOverview>('/copytrading/admin/overview/'),
        api.get<FeeConfig>('/copytrading/fee-config/'),
        api.get<FeeLedgerRow[]>('/copytrading/admin/ledger/'),
      ])
      overview.value = o.data
      feeConfig.value = c.data
      newLedger.value = l.data
    } finally {
      loading.value = false
    }
  }

  async function settle(ids: number[]) {
    await api.post('/copytrading/admin/ledger/', { ids })
    await fetchAdmin()
  }

  async function fetchStrategyPnl() {
    const { data } = await api.get<{ pnl: Record<string, string> }>('/copytrading/admin/strategy-pnl/')
    strategyPnl.value = data.pnl
  }

  return {
    masters,
    subscriptions,
    positions,
    myFees,
    investors,
    ledger,
    feeConfig,
    summary,
    trades,
    equity,
    overview,
    newLedger,
    strategyPnl,
    loading,
    fetchMarketplace,
    fetchSubscriptions,
    subscribe,
    unsubscribe,
    setActive,
    fetchMyPositions,
    fetchMyFees,
    fetchMy,
    fetchInvestors,
    fetchLedger,
    fetchFeeConfig,
    setFeeConfig,
    saveFeeConfig,
    publishStrategy,
    fetchAdmin,
    settle,
    fetchStrategyPnl,
  }
})
