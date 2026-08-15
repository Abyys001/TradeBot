import { defineStore } from 'pinia'

export interface FanOutResult {
  trade_id: number | null
  total_ms: number
  within_budget: boolean
  succeeded: { account_id: number; ms: number }[]
  failed: { account_id: number; error: string; code: string; ms: number }[]
}

/**
 * Owns the live trade, the trade log, and every fan-out round trip.
 *
 * Fan-out timing is kept because spec §4 is a hard promise (a per-leg deadline,
 * `FANOUT_TIMEOUT_SECONDS`) and the admin should be able to see whether it was
 * met on every single action, not discover months later that it drifted.
 */
export const useTradingStore = defineStore('trading', {
  state: () => ({
    tradeId: null as number | null,
    lastResult: null as FanOutResult | null,
    submitting: false,
    error: '',

    trades: [] as Trade[],
    tradesLoading: false,
    tradesLoaded: false,
    tradesError: '',

    policy: null as Policy | null,
    /** Spec §7 halt. Mirrored here so every surface reads one value. */
    halted: false,
    haltLocked: false,
    haltReason: '',
    haltPending: false,
  }),

  getters: {
    hasOpenTrade: (s) => s.tradeId !== null,
    lastFanoutMs: (s) => s.lastResult?.total_ms ?? null,
    breachedBudget: (s) => s.lastResult !== null && !s.lastResult.within_budget,

    /**
     * The spec §4 per-leg deadline, in ms, as the backend actually set it
     * (`FANOUT_TIMEOUT_SECONDS` from the policy endpoint, Q19). The fallback
     * mirrors the backend's shipped default so a comparison is never made
     * against the old 1s number; once the policy loads, this reads the truth.
     */
    fanoutBudgetMs(): number {
      return Math.round((this.policy?.fanout_timeout_seconds ?? 4.0) * 1000)
    },

    openTrade: (s) => s.trades.find((t) => t.status === 'open') ?? null,
    closedTrades: (s) => s.trades.filter((t) => t.status !== 'open'),
    latest: (s) => s.trades[0] ?? null,

    /** Every leg of every trade, newest first — the raw material for the log. */
    legs(): (TradeLeg & { trade: Trade })[] {
      return this.trades.flatMap((trade) => trade.legs.map((leg) => ({ ...leg, trade })))
    },

    realisedPnl(): number {
      return this.legs.reduce((sum, leg) => sum + Number(leg.pnl ?? 0), 0)
    },

    /** Fan-out times of the most recent trades, oldest first, for the chart. */
    fanoutSeries(): { id: number; ms: number; symbol: string; at: string }[] {
      return this.trades
        .filter((t) => t.fanout_ms !== null)
        .slice(0, 24)
        .reverse()
        .map((t) => ({ id: t.id, ms: t.fanout_ms as number, symbol: t.symbol, at: t.opened_at }))
    },

    budgetBreaches(): number {
      return this.trades.filter((t) => (t.fanout_ms ?? 0) > this.fanoutBudgetMs).length
    },

    /** Legs that filled but carry no stop — spec §4's worst quiet state. */
    unprotectedLegs(): (TradeLeg & { trade: Trade })[] {
      return this.legs.filter(
        (leg) => leg.ok && !leg.sltp_attached && leg.trade.status === 'open',
      )
    },
  },

  actions: {
    async loadTrades() {
      this.tradesLoading = true
      try {
        this.trades = await useApi().trades()
        this.tradesError = ''
        // Re-adopt an open trade after a reload, so a refresh mid-position does
        // not leave the terminal thinking there is nothing to close.
        this.tradeId = this.trades.find((t) => t.status === 'open')?.id ?? null
      } catch (e: any) {
        this.tradesError = errorMessage(e)
      } finally {
        this.tradesLoading = false
        this.tradesLoaded = true
      }
    },

    async ensureTrades() {
      if (this.tradesLoaded || this.tradesLoading) return
      await this.loadTrades()
    },

    async loadPolicy() {
      try {
        this.policy = await useApi().policy()
        this.applyHalt({
          stop_all: this.policy.stop_all,
          locked: this.policy.stop_all_locked,
          reason: this.policy.stop_all_reason,
        })
      } catch {
        this.policy = null
      }
    },

    /**
     * Spec §7: halt or resume platform-wide routing.
     *
     * Turning it on is one click with no confirmation on purpose — the moment
     * this is wanted is not the moment to fill in a dialog. Turning it *off*
     * is where the panel asks, because that is the direction that starts
     * moving money again.
     */
    async setHalt(on: boolean, reason = '') {
      this.haltPending = true
      this.error = ''
      try {
        const state = await useApi().setStopAll(on, reason)
        this.applyHalt(state)
        return state
      } catch (e: any) {
        this.error = errorMessage(e)
        throw e
      } finally {
        this.haltPending = false
      }
    },

    /**
     * Announce a fan-out result as a transient toast (spec §10).
     *
     * The count and the elapsed time are the two facts worth confirming: spec
     * §4 promises every account within the deadline, and this is where the
     * admin sees that promise kept on each individual action.
     */
    confirm(key: string, result: FanOutResult) {
      const { t } = useNuxtApp().$i18n
      const failed = result.failed.length
      useNotificationStore().toast(
        t(key, { n: result.succeeded.length }),
        {
          tone: failed ? 'signal' : 'ok',
          detail: t('toast.detail', {
            ms: Math.round(result.total_ms),
            failed,
          }),
        },
      )
    },

    /** Applied from the API, from `policy`, and from the WebSocket broadcast. */
    applyHalt(state: { stop_all: boolean; locked?: boolean; reason?: string }) {
      this.halted = state.stop_all
      if (state.locked !== undefined) this.haltLocked = state.locked
      if (state.reason !== undefined) this.haltReason = state.reason
      if (this.policy) this.policy.stop_all = state.stop_all
    },

    async open(payload: Record<string, unknown>) {
      const api = useApi()
      this.submitting = true
      this.error = ''
      try {
        const result = await api.openOrder(payload)
        this.lastResult = result
        this.tradeId = result.trade_id
        // Spec §10: successes are confirmed transiently. Per-account failures
        // still raise persistent §4 notices — this only says what got through.
        this.confirm('toast.opened', result)
        // The log is now stale by exactly one trade; refresh it in the
        // background so history and the dashboard agree without a reload.
        this.loadTrades()
        return result
      } catch (e: any) {
        this.error = errorMessage(e)
        throw e
      } finally {
        this.submitting = false
      }
    },

    async amend(slPct: number | null, tpPct: number | null) {
      if (this.tradeId === null) return null
      this.error = ''
      try {
        const result = await useApi().amendOrder(this.tradeId, { sl_pct: slPct, tp_pct: tpPct })
        this.lastResult = result
        this.confirm('toast.amended', result)
        return result
      } catch (e: any) {
        this.error = errorMessage(e)
        throw e
      }
    },

    async close() {
      if (this.tradeId === null) return null
      this.submitting = true
      this.error = ''
      try {
        const result = await useApi().closeOrder(this.tradeId)
        this.lastResult = result
        this.confirm('toast.closed', result)
        this.tradeId = null
        this.loadTrades()
        return result
      } catch (e: any) {
        this.error = errorMessage(e)
        throw e
      } finally {
        this.submitting = false
      }
    },
  },
})
