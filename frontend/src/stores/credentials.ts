import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type Credential, type CredentialCreatePayload } from '../api/client'

export const useCredentialsStore = defineStore('credentials', () => {
  const credentials = ref<Credential[]>([])
  const loading = ref(false)

  async function fetchAll() {
    loading.value = true
    try {
      const { data } = await api.get<Credential[]>('/credentials/')
      credentials.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(payload: CredentialCreatePayload) {
    const { data } = await api.post<Credential>('/credentials/', payload)
    credentials.value.unshift(data)
    return data
  }

  async function update(id: number, patch: Partial<CredentialCreatePayload & { label: string; network: string; wallet_address: string }>) {
    const { data } = await api.patch<Credential>(`/credentials/${id}/`, patch)
    const idx = credentials.value.findIndex((c) => c.id === id)
    if (idx >= 0) credentials.value[idx] = data
    return data
  }

  async function remove(id: number) {
    await api.delete(`/credentials/${id}/`)
    credentials.value = credentials.value.filter((c) => c.id !== id)
  }

  async function verify(id: number) {
    const { data } = await api.post<{ ok: boolean; detail?: string }>(`/credentials/${id}/verify/`)
    await fetchAll()
    return data
  }

  return { credentials, loading, fetchAll, create, update, remove, verify }
})
