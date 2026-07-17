import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, fetchCsrf, type User } from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isAdmin = computed(() => !!user.value && (user.value.role === 'admin' || user.value.is_admin === true))
  const isInvestor = computed(() => !!user.value && user.value.role === 'investor')

  async function init() {
    await fetchCsrf()
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      await fetchCsrf()
      const { data } = await api.post<User>('/auth/login/', { username, password })
      user.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    await api.post('/auth/logout/')
    user.value = null
  }

  async function fetchMe() {
    const { data } = await api.get<User>('/me/')
    user.value = data
    return data
  }

  return { user, loading, isAdmin, isInvestor, init, login, logout, fetchMe }
})
