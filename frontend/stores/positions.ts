import { defineStore } from 'pinia'

/**
 * The open position, per account, marked to market (spec §3 positions panel).
 *
 * Everything here comes from `/trading/positions/` rather than being computed
 * in the browser. PnL is money, money is Decimal, and Decimal only exists on
 * the backend — a second implementation of the same formula in JavaScript
 * floats is how the panel and the exchange end up disagreeing about what the
 * position is worth.
 *
 * Polled rather than pushed: the WebSocket carries *events* (a leg failed, a
 * balance changed), and a mark-to-market number that moves continuously is not
 * an event. The poll is cheap — one query plus a cached ticker.
 */
const POLL_MS = 3000

let timer: ReturnType<typeof setInterval> | null = null

export const usePositionsStore = defineStore('positions', {
  state: () => ({
    snapshot: null as PositionSnapshot | null,
    loading: false,
    loaded: false,
    error: '',
  }),

  getters: {
    trade: (s) => s.snapshot?.trade ?? null,
    hasPosition: (s) => s.snapshot?.trade != null,
    legs: (s) => s.snapshot?.legs ?? [],
    totals: (s) => s.snapshot?.totals ?? null,

    /** Only the legs that actually hold a position; failed legs are listed apart. */
    filled(): PositionLeg[] {
      return this.legs.filter((leg) => leg.ok)
    },
    failed(): PositionLeg[] {
      return this.legs.filter((leg) => !leg.ok)
    },

    /** Legs holding a position with no stop attached — spec §4's quiet failure. */
    unprotected(): PositionLeg[] {
      return this.legs.filter((leg) => leg.ok && !leg.sltp_attached)
    },

    pnl: (s) => (s.snapshot?.totals?.pnl == null ? null : Number(s.snapshot.totals.pnl)),
    roePct: (s) =>
      s.snapshot?.totals?.roe_pct == null ? null : Number(s.snapshot.totals.roe_pct),
    markPrice: (s) => (s.snapshot?.mark ? Number(s.snapshot.mark.price) : null),

    byAccount: (s) => (id: number) => s.snapshot?.legs.find((leg) => leg.account === id) ?? null,
  },

  actions: {
    async load() {
      this.loading = true
      try {
        this.snapshot = await useApi().positions()
        this.error = ''
      } catch (e: any) {
        this.error = errorMessage(e)
      } finally {
        this.loading = false
        this.loaded = true
      }
    },

    start() {
      this.load()
      if (timer || import.meta.server) return
      timer = setInterval(() => this.load(), POLL_MS)
    },

    stop() {
      if (timer) clearInterval(timer)
      timer = null
    },

    clear() {
      this.snapshot = null
    },
  },
})
