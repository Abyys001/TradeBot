import { defineStore } from 'pinia'

/** Module-level so the loop survives component churn but never runs twice. */
let balanceTimer: ReturnType<typeof setInterval> | null = null

/**
 * Connected accounts, loaded once and shared.
 *
 * The dashboard, the accounts page, the order ticket and the history filter all
 * need the same list. Fetching it per page meant four requests and four
 * slightly different views of the same truth; this is the one copy.
 */
export const useAccountsStore = defineStore('accounts', {
  state: () => ({
    items: [] as Account[],
    nonUsdt: [] as { id: number; label: string; asset: string }[],
    loading: false,
    /** True only for the very first load, so refreshes don't blank the page. */
    initial: true,
    refreshing: false,
    error: '',
    loadedAt: null as number | null,
  }),

  getters: {
    byId: (s) => (id: number | null) => s.items.find((a) => a.id === id) ?? null,
    labelFor: (s) => (id: number | null) =>
      s.items.find((a) => a.id === id)?.label ?? (id === null ? '' : `#${id}`),

    active: (s) => s.items.filter((a) => a.status === 'active'),
    paused: (s) => s.items.filter((a) => a.status === 'paused'),
    failing: (s) => s.items.filter((a) => a.status === 'error'),

    /** Spec §7: an account whose key was never proven trade-only is flagged. */
    unverified: (s) => s.items.filter((a) => !a.withdrawal_check_passed),

    /**
     * Only USDT balances are summed. Q4: an account denominated in something
     * else is reported as unusable, and folding it into a dollar total would
     * be the exact silent conversion that rule exists to prevent.
     */
    totalUsdt(): number {
      return this.items
        .filter((a) => a.balance_is_usdt)
        .reduce((sum, a) => sum + Number(a.last_balance ?? 0), 0)
    },

    /** What would actually be traded right now: active, USDT, verified. */
    tradeable(): Account[] {
      return this.items.filter((a) => a.status === 'active' && a.balance_is_usdt)
    },

    tradeableUsdt(): number {
      return this.tradeable.reduce((sum, a) => sum + Number(a.last_balance ?? 0), 0)
    },

    /** Descending capital, for the dashboard's allocation bars. */
    byCapital(): Account[] {
      return [...this.items].sort(
        (a, b) => Number(b.last_balance ?? 0) - Number(a.last_balance ?? 0),
      )
    },

    exchangeCount(): number {
      return new Set(this.items.map((a) => a.exchange)).size
    },
  },

  actions: {
    async load() {
      this.loading = true
      try {
        const data = await useApi().balances()
        this.items = data.accounts
        this.nonUsdt = data.non_usdt
        this.error = ''
        this.loadedAt = Date.now()
      } catch (e: any) {
        this.error = errorMessage(e)
      } finally {
        this.loading = false
        this.initial = false
      }
    },

    /** Only fetch if we have nothing — page navigation should feel instant. */
    async ensure() {
      if (this.items.length || this.loading) return
      await this.load()
    },

    /** Ask every exchange for a fresh balance, then re-read (spec §6). */
    async refresh(force = true) {
      this.refreshing = true
      try {
        await useApi().refreshBalances(force)
        await this.load()
      } catch (e: any) {
        this.error = errorMessage(e)
      } finally {
        this.refreshing = false
      }
    },

    /**
     * Spec §6: "the admin must be able to see the current balance of every
     * connected account at all times."
     *
     * A number that only updates when someone remembers to press a button is
     * not current, so the panel keeps them fresh by itself. The request is
     * rate-limited on the server, so several open tabs still produce one
     * fan-out, and the result is pushed to all of them over the WebSocket.
     */
    startAutoRefresh(intervalMs = 45000) {
      if (balanceTimer || import.meta.server) return
      balanceTimer = setInterval(() => {
        // Nothing to refresh on a hidden tab, and a phone in a pocket should
        // not be waking the exchanges every 45 seconds.
        if (document.visibilityState !== 'visible') return
        this.refresh(false)
      }, intervalMs)
    },

    stopAutoRefresh() {
      if (balanceTimer) clearInterval(balanceTimer)
      balanceTimer = null
    },

    applyLiveBalances(map: Record<number, { balance: string; asset: string; at?: number }>) {
      for (const account of this.items) {
        const live = map[account.id]
        if (!live) continue
        account.last_balance = live.balance
        account.last_balance_asset = live.asset
        // Timestamp too, or the row shows a fresh figure under a stale "4h ago".
        account.last_balance_at = new Date(live.at ?? Date.now()).toISOString()
      }
      this.loadedAt = Date.now()
    },

    async setPaused(account: Account, paused: boolean) {
      const api = useApi()
      const updated = paused ? await api.pause(account.id) : await api.resume(account.id)
      this.replace(updated)
      return updated
    },

    async verify(account: Account) {
      const updated = await useApi().verifyAccount(account.id)
      this.replace(updated)
      return updated
    },

    async remove(id: number) {
      await useApi().remove(id)
      this.items = this.items.filter((a) => a.id !== id)
    },

    replace(updated: Account) {
      const index = this.items.findIndex((a) => a.id === updated.id)
      if (index === -1) this.items.push(updated)
      else this.items[index] = updated
    },
  },
})
