import { defineStore } from 'pinia'
import type { LogEntry } from '../composables/useApi'

const MAX_ENTRIES = 500

export const useSystemLogStore = defineStore('systemLog', {
  state: () => ({
    entries: [] as LogEntry[],
    loaded: false,
    loading: false,
    error: '' as string,
  }),

  getters: {
    newestFirst: (state) => [...state.entries].reverse(),
  },

  actions: {
    async load(params?: Record<string, string>) {
      this.loading = true
      this.error = ''
      try {
        const { logs } = useApi()
        this.entries = await logs(params)
        this.loaded = true
      } catch (e: any) {
        this.error = e?.message ?? 'Failed to load logs'
      } finally {
        this.loading = false
      }
    },

    receive(entry: LogEntry) {
      this.entries.push(entry)
      if (this.entries.length > MAX_ENTRIES) {
        this.entries = this.entries.slice(-MAX_ENTRIES)
      }
    },

    async prune(days = 30) {
      const { pruneLogs } = useApi()
      const result = await pruneLogs(days)
      return result.pruned
    },

    clear() {
      this.entries = []
      this.loaded = false
    },
  },
})
