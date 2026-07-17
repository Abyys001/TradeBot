import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  api,
  type AdminInvestor,
  type FeeConfig,
  type FeeLedger,
  type InvestorPosition,
  type MasterStrategy,
  type Subscription,
} from '../api/client'

export const useCopytradingStore = defineStore('copytrading', () => {
  const masters = ref<MasterStrategy[]>([])
  const subscriptions = ref<Subscription[]>([])
  const positions = ref<InvestorPosition[]>([])
  const myFees = ref<FeeLedger[]>([])
  const investors = ref<AdminInvestor[]>([])
  const ledger = ref<FeeLedger[]>([])
  const feeConfig = ref<FeeConfig | null>(null)
  const loading = ref(false)

  // ---- investor ----
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

  async function setFeeConfig(fee_rate: string) {
    const { data } = await api.patch<FeeConfig>('/copytrading/admin/fee-config/', { fee_rate })
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

  return {
    masters,
    subscriptions,
    positions,
    myFees,
    investors,
    ledger,
    feeConfig,
    loading,
    fetchMarketplace,
    fetchSubscriptions,
    subscribe,
    unsubscribe,
    setActive,
    fetchMyPositions,
    fetchMyFees,
    fetchInvestors,
    fetchLedger,
    fetchFeeConfig,
    setFeeConfig,
    publishStrategy,
  }
})
