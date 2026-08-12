import { defineStore } from 'pinia'

export interface FailureNotice {
  id: number | string
  account: number | null
  accountLabel: string
  message: string
  code: string
  created_at: string
}

/**
 * Spec §4: a failed order raises a notice that stays on screen until the admin
 * dismisses it by hand.
 *
 * Nothing in here may auto-expire — no timeout, no max-count eviction. If that
 * ever gets "cleaned up", a partner's failed order goes unnoticed.
 *
 * Two sources feed it and both matter: the WebSocket for immediacy, and the
 * REST endpoint on every load so a notice survives a page reload. The old
 * version only listened to the socket, which meant refreshing the page silently
 * cleared every outstanding failure — the one thing the spec forbids.
 */
/**
 * A transient confirmation. Spec §10 left success notifications open; this is
 * the answer: successes *do* auto-expire, and failures never do. The asymmetry
 * is the whole point — a confirmation you missed costs nothing, a failure you
 * missed is a partner's order that never went out.
 */
export interface Toast {
  id: string
  message: string
  tone: 'ok' | 'signal'
  detail?: string
}

export const useNotificationStore = defineStore('notifications', {
  state: () => ({
    items: [] as FailureNotice[],
    hydrated: false,
    /** Collapsed to a counter chip rather than the full stack of cards. */
    collapsed: false,
    toasts: [] as Toast[],
  }),

  getters: {
    count: (s) => s.items.length,
    hasFailures: (s) => s.items.length > 0,
    newest: (s) => s.items[0] ?? null,
  },

  actions: {
    /** Reconcile from the server. Safe to call repeatedly. */
    async hydrate() {
      try {
        const rows = await useApi().notifications()
        const accounts = useAccountsStore()
        this.items = rows.map((row) => ({
          id: row.id,
          account: row.account,
          accountLabel: accounts.labelFor(row.account),
          message: row.message,
          code: row.code,
          created_at: row.created_at,
        }))
      } catch {
        // Offline: keep whatever the socket already delivered rather than
        // wiping the list. A stale notice is far better than a missing one.
      } finally {
        this.hydrated = true
      }
    },

    receive(notice: FailureNotice) {
      if (this.items.some((i) => String(i.id) === String(notice.id))) return
      if (!notice.accountLabel) {
        notice.accountLabel = useAccountsStore().labelFor(notice.account)
      }
      this.items.unshift(notice)
      this.collapsed = false
    },

    /**
     * Dismissal is a server-side fact, not a local one: it must survive a
     * reload, and the same admin on a second screen should see it clear.
     * The card is removed optimistically because the alternative — a card that
     * lingers until a round trip lands — reads as a broken button.
     */
    async dismiss(id: number | string) {
      const removed = this.items.find((i) => i.id === id)
      this.items = this.items.filter((i) => i.id !== id)
      if (typeof id !== 'number') return
      try {
        await useApi().dismiss(id)
      } catch {
        if (removed) this.items.unshift(removed)
      }
    },

    async dismissAll() {
      const ids = this.items.map((i) => i.id)
      for (const id of ids) await this.dismiss(id)
    },

    /**
     * A confirmation that clears itself after a few seconds.
     *
     * Deliberately not the same channel as a failure notice: this one is
     * allowed to disappear, so it must never be used to report something that
     * needs acting on. Failures go through `receive`.
     */
    toast(message: string, options: { tone?: 'ok' | 'signal'; detail?: string } = {}) {
      const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
      this.toasts = [...this.toasts, { id, message, tone: options.tone ?? 'ok', detail: options.detail }]
      if (import.meta.client) setTimeout(() => this.dropToast(id), 4500)
    },

    dropToast(id: string) {
      this.toasts = this.toasts.filter((toast) => toast.id !== id)
    },
  },
})
