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

    /**
     * Legs whose protection is reported attached but never confirmed by a
     * read-back from the exchange (adapter has no get_sltp endpoint, or the
     * read failed). Not a failure — the SL/TP may well be resting — but the
     * admin should read "unconfirmed", not "verified", for these.
     */
    unconfirmed(): PositionLeg[] {
      return this.legs.filter((leg) => leg.ok && leg.sltp_attached && !leg.sltp_verified)
    },

    /**
     * Legs still resting on the *previous* SL/TP — an amend that failed on this
     * account alone. The whole point of moving a stop mid-trade is that every
     * exchange moves with it, so the one that did not has to be named rather
     * than left looking like the rest.
     */
    stale(): PositionLeg[] {
      return this.legs.filter((leg) => leg.ok && leg.sltp_stale)
    },

    pnl: (s) => (s.snapshot?.totals?.pnl == null ? null : Number(s.snapshot.totals.pnl)),
    roePct: (s) =>
      s.snapshot?.totals?.roe_pct == null ? null : Number(s.snapshot.totals.roe_pct),
    markPrice: (s) => (s.snapshot?.mark ? Number(s.snapshot.mark.price) : null),

    /**
     * Set when the server held the position but could not price it. The legs,
     * sizes and entries are still real; every PnL field is null. An unknown PnL
     * has to read as unknown — showing zero would look like a flat trade.
     */
    feedError: (s) => s.snapshot?.feed_error ?? '',

    /**
     * Open trades running that this panel does not draw. Not a normal state:
     * it means an entry went out while an earlier trade was still open, so the
     * platform holds two. The close button flattens both — this is what stops
     * the second one from being invisible until then.
     */
    otherOpenTrades: (s) => s.snapshot?.other_open_trades ?? 0,

    byAccount: (s) => (id: number) => s.snapshot?.legs.find((leg) => leg.account === id) ?? null,
  },

  actions: {
    async load() {
      this.loading = true
      try {
        this.snapshot = await useApi().positions()
        this.error = ''
        // The poll is the panel's most reliable news of an open trade, so it is
        // also what keeps the editing surfaces pointed at a real one: the id
        // every amend is sent against (`trading.adopt`), and the percentages
        // that amend carries (`order.adoptTrade`). Without this a position
        // opened in another browser is drawn, marked to market and completely
        // un-amendable.
        const open = this.snapshot?.trade ?? null
        useTradingStore().adopt(open?.id ?? null)
        if (open) useOrderStore().adoptTrade(open)
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
