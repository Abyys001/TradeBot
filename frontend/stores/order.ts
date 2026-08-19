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
    entryPrice: null as number | null,
    liquidationPrice: null as number | null,
    lastEditedFrom: null as EditSource | null,
    lastEditedAt: null as number | null,
  }),

  getters: {
    // Liquidation distance depends on leverage alone: 1/leverage.
    liquidationDistancePct: (s) => 100 / s.leverage,

    /**
     * Both halves of the protection are set. The server requires them on every
     * open and every amend — they become real trigger prices sent to the
     * exchange — so this is what the send and amend buttons gate on rather than
     * letting the request come back a 400.
     */
    hasProtection: (s) => s.slPct !== null && s.tpPct !== null,
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
     * Q5c: a chart drag gives an absolute price. Convert it to a percentage off
     * the admin's own entry so it can be re-applied to each account's own fill.
     */
    setSLFromPrice(price: number) {
      const entry = this.entryPrice
      if (!entry) return
      const move = this.side === 'long' ? (entry - price) / entry : (price - entry) / entry
      const pct = move * 100
      this.setSL(round4(this.basis === 'margin' ? pct * this.leverage : pct), 'chart')
    },
    setTPFromPrice(price: number) {
      const entry = this.entryPrice
      if (!entry) return
      const move = this.side === 'long' ? (price - entry) / entry : (entry - price) / entry
      const pct = move * 100
      this.setTP(round4(this.basis === 'margin' ? pct * this.leverage : pct), 'chart')
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

    /** Adopt an open trade after a page reload so the terminal is not blank. */
    hydrateFromTrade(trade: Trade) {
      this.symbol = trade.symbol
      this.side = trade.side === 'short' ? 'short' : 'long'
      this.market = trade.market === 'spot' ? 'spot' : 'futures'
      this.leverage = trade.leverage || this.leverage
      this.basis = trade.sltp_basis === 'margin' ? 'margin' : 'price'
      this.slPct = trade.sl_pct === null ? null : Number(trade.sl_pct)
      this.tpPct = trade.tp_pct === null ? null : Number(trade.tp_pct)
      if (trade.admin_entry_price) this.entryPrice = Number(trade.admin_entry_price)
      this.lastEditedFrom = null
    },

    reset() {
      this.slPct = null
      this.tpPct = null
      this.liquidationPrice = null
      this.lastEditedFrom = null
      this.lastEditedAt = null
    },
  },
})

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
