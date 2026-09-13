import { defineStore } from 'pinia'

export type Basis = 'price' | 'margin'
export type EditSource = 'ticket' | 'chart' | 'position'

/**
 * The single source of truth for the working order.
 *
 * Spec §3 requires SL/TP to be editable from three places — the order ticket,
 * the chart, and the position row. All three call `setSL`/`setTP` here, and all
 * three render from this state. That is the whole reason this store exists: one
 * write path means the three surfaces cannot disagree, and one fan-out command
 * is emitted regardless of which surface the admin touched.
 *
 * `basis` lives here too. It used to be a ref passed down by prop and v-model,
 * which meant the chart could be interpreting a percentage one way while the
 * ticket displayed it the other.
 */
export const useOrderStore = defineStore('order', {
  state: () => ({
    symbol: 'BTCUSDC',
    side: 'long' as 'long' | 'short',
    market: 'futures' as 'futures' | 'spot',
    orderType: 'market' as 'market' | 'limit',
    limitPrice: null as number | null,
    leverage: 10,
    slPct: null as number | null,
    tpPct: null as number | null,
    basis: 'price' as Basis,
    exitPolicy: 'protected' as ExitPolicy,
    /**
     * The disaster stop, for `strategy_managed` only. Deliberately far out —
     * the strategy's own exit should always reach the position first. It is
     * what rests at the venue when this platform is not running to act.
     */
    safetyNetPct: null as number | null,
    entryPrice: null as number | null,
    liquidationPrice: null as number | null,
    lastEditedFrom: null as EditSource | null,
    lastEditedAt: null as number | null,
    /** The open trade these numbers describe — see `adoptTrade`. */
    hydratedTradeId: null as number | null,
  }),

  getters: {
    // Liquidation distance depends on leverage alone: 1/leverage.
    liquidationDistancePct: (s) => 100 / s.leverage,

    strategyManaged: (s) => s.exitPolicy === 'strategy_managed',

    /**
     * This order may be sent as it stands.
     *
     * Under `protected` that means both halves are set: the server requires
     * them on every open and every amend — they become real trigger prices sent
     * to the exchange — so this is what the send and amend buttons gate on
     * rather than letting the request come back a 400. Under
     * `strategy_managed` (Q37) there is nothing to require: the exit is a
     * decision the strategy has yet to make, and a blank box is that decision
     * being deferred rather than a form half filled in.
     */
    hasProtection(): boolean {
      if (this.strategyManaged) return true
      return this.slPct !== null && this.tpPct !== null
    },

    /**
     * Nothing at all will rest at the exchange for this order.
     *
     * Not a blocker — it is a legal, deliberate state — but the one fact the
     * ticket has to put in front of the admin before they press send, because
     * the position is then protected by a *running process* rather than by the
     * venue.
     */
    unprotected(): boolean {
      if (!this.strategyManaged) return false
      return this.slPct === null && this.tpPct === null && this.safetyNetPct === null
    },

    /** The stop that would actually rest at the venue: the net only fills a blank. */
    restingSlPct(): number | null {
      return this.slPct !== null ? this.slPct : this.safetyNetPct
    },

    /**
     * A net past liquidation can never fire, so it is protection that is not
     * there. The server refuses it with the same arithmetic; saying so here
     * turns a 400 at send time into a number the admin can see is wrong.
     */
    safetyNetBeyondLiquidation(): boolean {
      if (this.safetyNetPct === null || this.slPct !== null) return false
      const move =
        this.basis === 'margin' ? this.safetyNetPct / this.leverage : this.safetyNetPct
      return move >= this.liquidationDistancePct
    },
    isOpen: (s) => s.entryPrice !== null,

    /** The price move the typed percentage actually implies (Q5a). */
    slPriceMovePct(): number | null {
      if (this.slPct === null) return null
      return this.basis === 'margin' ? this.slPct / this.leverage : this.slPct
    },

    /**
     * What the stop costs as a share of the account. Under the price basis at
     * 10x a "2%" stop is a 20% account loss — the number the admin most needs
     * in front of them before pressing send.
     */
    slAccountLossPct(): number | null {
      const move = this.slPriceMovePct
      return move === null ? null : move * this.leverage
    },

    tpAccountGainPct(): number | null {
      if (this.tpPct === null) return null
      const move = this.basis === 'margin' ? this.tpPct / this.leverage : this.tpPct
      return move * this.leverage
    },

    /** A stop past liquidation can never trigger — the position dies first. */
    slBeyondLiquidation(): boolean {
      const move = this.slPriceMovePct
      return move !== null && move >= this.liquidationDistancePct
    },

    slPrice(): number | null {
      return targetPrice(this, 'sl')
    },
    tpPrice(): number | null {
      return targetPrice(this, 'tp')
    },
  },

  actions: {
    /**
     * Every SL/TP write lands here, so the sanity check lives here too.
     *
     * A percentage at or below zero is not a stop — it sits at entry or on the
     * *profit* side of it, where it fires the moment the trade goes right. The
     * ticket cannot produce one by typing (`Number(x) || null` swallows a zero)
     * but a chart drag can: pull the stop line across entry and the computed
     * move goes negative. Clearing it is the honest outcome; silently flipping
     * the sign would place a stop the admin did not ask for. The server refuses
     * the same values, so an unclamped drag would otherwise be a 400 at the
     * moment of sending rather than a line that visibly refuses to be dragged
     * there.
     *
     * The stop is also capped at 100%: past it the stop price is below zero.
     * The target is not — a 250% take profit is a real thing to ask for.
     */
    setSL(pct: number | null, from: EditSource) {
      this.slPct = pct === null || !(pct > 0) ? null : Math.min(pct, 100)
      this.touch(from)
    },
    setTP(pct: number | null, from: EditSource) {
      this.tpPct = pct === null || !(pct > 0) ? null : pct
      this.touch(from)
    },
    touch(from: EditSource) {
      this.lastEditedFrom = from
      this.lastEditedAt = Date.now()
    },

    /**
     * Q5c: a chart drag — and now a typed price box — gives an absolute price.
     * Convert it to a percentage off the admin's own entry so it can be
     * re-applied to each account's own fill. `from` names the surface, because
     * the price boxes on the ticket and the position row write through here too
     * and "last edited from the chart" would be a lie.
     */
    setSLFromPrice(price: number, from: EditSource = 'chart') {
      const entry = this.entryPrice
      if (!entry) return
      const move = this.side === 'long' ? (entry - price) / entry : (price - entry) / entry
      const pct = move * 100
      // A drag is a *move*, never a clear. Pulled across entry it computes a
      // negative stop, which `setSL` turns into null — and a null level is a
      // line that disappears off the chart with no way to get it back, on a
      // position that is still live and still protected on the exchange. The
      // level stays where it was and the line simply refuses to go there; the
      // way to remove a stop is to empty the box on the ticket.
      if (!(pct > 0)) return
      this.setSL(round4(this.basis === 'margin' ? pct * this.leverage : pct), from)
    },
    setTPFromPrice(price: number, from: EditSource = 'chart') {
      const entry = this.entryPrice
      if (!entry) return
      const move = this.side === 'long' ? (price - entry) / entry : (entry - price) / entry
      const pct = move * 100
      if (!(pct > 0)) return
      this.setTP(round4(this.basis === 'margin' ? pct * this.leverage : pct), from)
    },

    priceFor(kind: 'sl' | 'tp'): number | null {
      return targetPrice(this, kind)
    },

    /**
     * Switching basis keeps the *position on the chart* fixed rather than the
     * number in the box. Reinterpreting "2" from a price move into a margin
     * move would silently move every stop by the leverage multiple.
     */
    setBasis(next: Basis) {
      if (next === this.basis) return
      const factor = next === 'margin' ? this.leverage : 1 / this.leverage
      if (this.slPct !== null) this.slPct = round4(this.slPct * factor)
      if (this.tpPct !== null) this.tpPct = round4(this.tpPct * factor)
      this.basis = next
    },

    /**
     * Take on a trade the panel was not already editing.
     *
     * Called from the positions poll, so it runs on every page and covers the
     * case a reload does not: a trade opened in another browser, or one
     * `possync` restored, arriving while this ticket holds numbers from a
     * previous trade. Those numbers matter — an amend sends *both* sides, so
     * dragging the stop on an adopted trade would otherwise push a take profit
     * this panel invented.
     *
     * A recent edit is never overwritten. The poll is three seconds behind and
     * an amend takes a moment to persist; adopting on top of a level the admin
     * has just set would put the old one back in front of them while the
     * exchanges rest on the new one.
     */
    adoptTrade(trade: HydratableTrade) {
      const editing =
        this.lastEditedAt !== null && Date.now() - this.lastEditedAt < ADOPT_GRACE_MS

      if (this.hydratedTradeId !== trade.id) {
        if (editing) {
          // The grace protects the admin's levels, not the trade's direction. A
          // stale side draws a short's stop below entry, and dragging it back
          // above — where a short's stop belongs — reads as a negative stop,
          // which `setSL` clears: the line vanishes and the amend is refused.
          this.side = sideOf(trade)
          this.hydratedTradeId = trade.id
          return
        }
        this.hydrateFromTrade(trade)
        return
      }

      // Already this trade — but "already adopted" is not "still agrees". The
      // server is the authority on an open position's levels, and the panel
      // has to fall back in step with it on every poll rather than only on the
      // first one. Adopting once per trade id is what let the two drift: a
      // level cleared in the browser (a stop dragged across entry used to do
      // exactly that), an amend made from another tab, or a trade `possync`
      // restored left the chart drawing levels the exchanges had never agreed
      // to — or, when the level had been cleared, drawing **nothing at all**
      // for the rest of the position while the stop sat resting on every
      // account. Only the levels are re-read; the symbol, market and leverage
      // are not, so the admin can still look at another pair mid-position.
      if (editing || this.matchesTrade(trade)) return
      this.adoptLevels(trade)
    },

    /** Does the panel already show this trade's protection, exactly? */
    matchesTrade(trade: HydratableTrade): boolean {
      const same = (mine: number | null, theirs: string | null) =>
        mine === (theirs === null || theirs === '' ? null : Number(theirs))
      return (
        this.side === sideOf(trade) &&
        this.basis === basisOf(trade) &&
        same(this.slPct, trade.sl_pct) &&
        same(this.tpPct, trade.tp_pct) &&
        this.exitPolicy === policyOf(trade)
      )
    },

    /** The protection as the server holds it — side, basis and both levels. */
    adoptLevels(trade: HydratableTrade) {
      this.side = sideOf(trade)
      this.basis = basisOf(trade)
      this.slPct = trade.sl_pct === null ? null : Number(trade.sl_pct)
      this.tpPct = trade.tp_pct === null ? null : Number(trade.tp_pct)
      // Q37: the policy is part of the protection, and the server is the
      // authority on it. Without this a strategy-managed position would be
      // re-read into a ticket still set to `protected`, where two blank boxes
      // read as an unfinished form and the amend button would refuse.
      this.exitPolicy = policyOf(trade)
      this.safetyNetPct =
        trade.safety_net_pct === null || trade.safety_net_pct === undefined
          ? null
          : Number(trade.safety_net_pct)
      this.lastEditedFrom = null
    },

    /** Adopt an open trade after a page reload so the terminal is not blank. */
    hydrateFromTrade(trade: HydratableTrade) {
      this.symbol = trade.symbol
      this.market = trade.market === 'spot' ? 'spot' : 'futures'
      this.leverage = trade.leverage || this.leverage
      this.adoptLevels(trade)
      if (trade.admin_entry_price) this.entryPrice = Number(trade.admin_entry_price)
      this.hydratedTradeId = trade.id
    },

    /**
     * Switching policy clears what the other one cannot express, rather than
     * leaving it set and ignored. A safety net left behind on a protected
     * order reads on the panel as protection that exists and would be dropped
     * by the server anyway.
     */
    setExitPolicy(policy: ExitPolicy) {
      this.exitPolicy = policy
      if (policy === 'protected') this.safetyNetPct = null
      this.touch('ticket')
    },

    setSafetyNet(pct: number | null) {
      this.safetyNetPct = pct === null || !(pct > 0) ? null : Math.min(pct, 100)
      this.touch('ticket')
    },

    reset() {
      this.slPct = null
      this.tpPct = null
      this.safetyNetPct = null
      this.liquidationPrice = null
      this.lastEditedFrom = null
      this.lastEditedAt = null
      this.hydratedTradeId = null
    },
  },
})

/**
 * Everything hydration reads. Both `Trade` and the leaner trade the positions
 * snapshot carries satisfy it, which is the point — the poll is the panel's
 * most current news of an open trade and should not need the full shape.
 */
type HydratableTrade = Pick<
  Trade,
  | 'id'
  | 'symbol'
  | 'side'
  | 'market'
  | 'leverage'
  | 'sl_pct'
  | 'tp_pct'
  | 'sltp_basis'
  | 'exit_policy'
  | 'safety_net_pct'
  | 'admin_entry_price'
>

/** How long a fresh edit is protected from the poll's older view of the trade. */
const ADOPT_GRACE_MS = 15_000

function sideOf(trade: Pick<Trade, 'side'>): 'long' | 'short' {
  return trade.side === 'short' ? 'short' : 'long'
}

function basisOf(trade: Pick<Trade, 'sltp_basis'>): Basis {
  return trade.sltp_basis === 'margin' ? 'margin' : 'price'
}

/** Anything the server has not stamped is a trade from before Q37: protected. */
function policyOf(trade: Pick<Trade, 'exit_policy'>): ExitPolicy {
  return trade.exit_policy === 'strategy_managed' ? 'strategy_managed' : 'protected'
}

/** Chart drags produce long floats; four decimals is past any exchange's tick. */
function round4(n: number): number {
  return Math.round(n * 10000) / 10000
}

/**
 * Percentage → absolute price, in one place.
 *
 * A free function rather than a store method because both a getter and an
 * action need it, and a getter cannot call an action. Two copies of this
 * arithmetic is exactly how the chart line and the ticket end up disagreeing
 * about where the stop is.
 */
function targetPrice(
  state: {
    entryPrice: number | null
    slPct: number | null
    tpPct: number | null
    basis: Basis
    leverage: number
    side: 'long' | 'short'
  },
  kind: 'sl' | 'tp',
): number | null {
  const entry = state.entryPrice
  const pct = kind === 'sl' ? state.slPct : state.tpPct
  if (!entry || pct === null) return null
  const move = (state.basis === 'margin' ? pct / state.leverage : pct) / 100
  const adverse = kind === 'sl'
  const sign = (state.side === 'long') === adverse ? -1 : 1
  return entry * (1 + sign * move)
}
