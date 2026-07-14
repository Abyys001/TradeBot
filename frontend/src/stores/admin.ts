import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type Investor, type InvestorCreatePayload } from '../api/client'

export const useAdminStore = defineStore('admin', () => {
  const investors = ref<Investor[]>([])
  const loading = ref(false)

  async function fetchAll() {
    loading.value = true
    try {
      const { data } = await api.get<Investor[]>('/admin/investors/')
      investors.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(payload: InvestorCreatePayload) {
    const { data } = await api.post<Investor>('/admin/investors/', payload)
    investors.value.unshift(data)
    return data
  }

  async function resetPassword(id: number, password: string) {
    const { data } = await api.post<Investor>(`/admin/investors/${id}/reset-password/`, { password })
    replace(data)
    return data
  }

  async function setTrading(id: number, enabled: boolean) {
    const { data } = await api.post<Investor>(`/admin/investors/${id}/set-trading/`, { enabled })
    replace(data)
    return data
  }

  async function setActive(id: number, active: boolean) {
    const { data } = await api.post<Investor>(`/admin/investors/${id}/set-active/`, { active })
    replace(data)
    return data
  }

  function replace(inv: Investor) {
    const idx = investors.value.findIndex((i) => i.id === inv.id)
    if (idx >= 0) investors.value[idx] = inv
  }

  return { investors, loading, fetchAll, create, resetPassword, setTrading, setActive }
})
