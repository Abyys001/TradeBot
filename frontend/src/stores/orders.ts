import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type OrderRecord } from '../api/client'

export const useOrdersStore = defineStore('orders', () => {
  const orders = ref<OrderRecord[]>([])
  const loading = ref(false)

  async function fetchOrders(strategyId?: number) {
    loading.value = true
    try {
      const params = strategyId ? { strategy: strategyId } : undefined
      const { data } = await api.get<OrderRecord[]>('/orders/', { params })
      orders.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  return { orders, loading, fetchOrders }
})
