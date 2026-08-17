import { defineStore } from 'pinia'
import type { LogEntry } from '../composables/useApi'

/** One backend page. Matches the API's own default/max (`apps/logging/views.py`). */
const PAGE_LIMIT = 200
/**
 * Hard safety ceiling on the live-tail buffer. Deliberate history loaded via
 * `loadMore()` is exempt: the ceiling is raised by exactly as many rows as the
 * admin has paged in, so an unrelated live event arriving in the background
 * cannot evict the incident they are reading. The previous version trimmed the
 * whole array in `receive()`, which quietly did the thing this comment promised
 * it would not.
 */
const LIVE_TAIL_CEILING = 2000

export const useSystemLogStore = defineStore('systemLog', {
  state: () => ({
    entries: [] as LogEntry[], // newest-first, matching the API's ordering
    loaded: false,
    loading: false,
    loadingMore: false,
    hasMore: false,
    /** Rows pulled in by explicit paging, exempt from the live-tail ceiling. */
    pagedIn: 0,
    /** Live rows dropped by the ceiling — shown rather than silently lost. */
    trimmed: 0,
    /** Rows that arrived over the socket since the last full load. */
    liveCount: 0,
    levels: [] as string[],
    categories: [] as string[],
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
        this.pagedIn = 0
        this.trimmed = 0
        this.liveCount = 0
        this.loaded = true
      } catch (e: any) {
        this.error = errorMessage(e)
      } finally {
        this.loading = false
      }
    },

    /** The level/category values the backend actually writes, so the filter
     * dropdowns cannot drift out of sync with the model's choices. */
    async loadFacets() {
      if (this.levels.length) return
      try {
        const { logFacets } = useApi()
        const facets = await logFacets()
        this.levels = facets.levels
        this.categories = facets.categories
      } catch {
        // A missing facet list is not worth an error banner over the log itself;
        // the filters simply stay on whatever is already loaded.
      }
    },

    /** Appends the page older than the oldest currently-loaded entry. */
    async loadMore(params?: Record<string, string>) {
      if (this.loadingMore || !this.hasMore || !this.entries.length) return
      this.loadingMore = true
      this.error = ''
      try {
        const { logs } = useApi()
        const oldest = this.entries[this.entries.length - 1]
        const rows = await logs({
          limit: String(PAGE_LIMIT),
          before_id: String(oldest.id),
          ...params,
        })
        const known = new Set(this.entries.map((e) => e.id))
        const fresh = rows.filter((row) => !known.has(row.id))
        this.entries = [...this.entries, ...fresh]
        this.pagedIn += fresh.length
        this.hasMore = rows.length >= PAGE_LIMIT
      } catch (e: any) {
        this.error = errorMessage(e)
      } finally {
        this.loadingMore = false
      }
    },

    receive(entry: LogEntry) {
      // A push can race the REST page that already contains it (the row is
      // written, broadcast, and only then does an in-flight query return it).
      // Two rows with one id is a duplicate `:key`, which Vue renders wrong.
      if (this.entries.some((e) => e.id === entry.id)) return
      const next = [entry, ...this.entries]
      const ceiling = LIVE_TAIL_CEILING + this.pagedIn
      if (next.length > ceiling) {
        this.trimmed += next.length - ceiling
        next.length = ceiling
        // The oldest loaded row is gone, so the cursor no longer describes a
        // continuous window — there is more to fetch by definition.
        this.hasMore = true
      }
      this.entries = next
      this.liveCount += 1
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
      this.pagedIn = 0
      this.trimmed = 0
      this.liveCount = 0
    },
  },
})
