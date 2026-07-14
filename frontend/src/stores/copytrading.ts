import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  api,
  type AdminCopyOverview,
  type CopyEquityPoint,
  type CopySummary,
  type CopyTradeRow,
  type FeeConfig,
  type FeeLedgerRow,
} from '../api/client'

export const useCopyTradingStore = defineStore('copytrading', () => {
  // Investor
  const summary = ref<CopySummary | null>(null)
  const trades = ref<CopyTradeRow[]>([])
  const equity = ref<CopyEquityPoint[]>([])
  // Admin
  const overview = ref<AdminCopyOverview | null>(null)
  const feeConfig = ref<FeeConfig | null>(null)
  const ledger = ref<FeeLedgerRow[]>([])
  const loading = ref(false)

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
      ledger.value = l.data
    } finally {
      loading.value = false
    }
  }

  async function saveFeeConfig(patch: Partial<FeeConfig>) {
    const { data } = await api.put<FeeConfig>('/copytrading/fee-config/', patch)
    feeConfig.value = data
    return data
  }

  async function settle(ids: number[]) {
    await api.post('/copytrading/admin/ledger/', { ids })
    await fetchAdmin()
  }

  return { summary, trades, equity, overview, feeConfig, ledger, loading, fetchMy, fetchAdmin, saveFeeConfig, settle }
})
