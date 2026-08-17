import { defineStore } from 'pinia'
import type { LogEntry } from '../composables/useApi'

/** One backend page. Matches the API's own default/max (`apps/logging/views.py`). */
const PAGE_LIMIT = 200
/**
 * Hard safety ceiling on the live-tail buffer only (`receive()`). Deliberate
 * history loaded via `loadMore()` is never trimmed against this — an admin
 * paging back into an incident shouldn't have the tail end of their own
 * lookup evicted by an unrelated live event arriving in the background.
 */
const LIVE_TAIL_CEILING = 2000

export const useSystemLogStore = defineStore('systemLog', {
  state: () => ({
    entries: [] as LogEntry[], // newest-first, matching the API's ordering
    loaded: false,
    loading: false,
    loadingMore: false,
    hasMore: false,
    error: '' as string,
  }),

  getters: {
    newestFirst: (state) => state.entries,
  },

  actions: {
    /** Replaces the current set with the newest page matching `params`. */
    async load(params?: Record<string, string>) {
      this.loading = true
      this.error = ''
      try {
        const { logs } = useApi()
        const rows = await logs({ limit: String(PAGE_LIMIT), ...params })
        this.entries = rows
        this.hasMore = rows.length >= PAGE_LIMIT
        this.loaded = true
      } catch (e: any) {
        this.error = e?.message ?? 'Failed to load logs'
      } finally {
        this.loading = false
      }
    },

    /** Appends the page older than the oldest currently-loaded entry. */
    async loadMore(params?: Record<string, string>) {
      if (this.loadingMore || !this.hasMore || !this.entries.length) return
      this.loadingMore = true
      try {
        const { logs } = useApi()
        const oldest = this.entries[this.entries.length - 1]
        const rows = await logs({
          limit: String(PAGE_LIMIT),
          before_id: String(oldest.id),
          ...params,
        })
        this.entries = [...this.entries, ...rows]
        this.hasMore = rows.length >= PAGE_LIMIT
      } catch (e: any) {
        this.error = e?.message ?? 'Failed to load more logs'
      } finally {
        this.loadingMore = false
      }
    },

    receive(entry: LogEntry) {
      this.entries = [entry, ...this.entries].slice(0, LIVE_TAIL_CEILING)
    },

    async prune(days = 30) {
      const { pruneLogs } = useApi()
      const result = await pruneLogs(days)
      return result.pruned
    },

    clear() {
      this.entries = []
      this.loaded = false
      this.hasMore = false
    },
  },
})
