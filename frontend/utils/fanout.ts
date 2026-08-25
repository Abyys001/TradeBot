/** A single account's leg of a fan-out: who, how long the dispatch took, whether it filled. */
export interface FanLeg {
  label: string
  ms: number
  ok: boolean
}

/**
 * The demo replay the landing runs when no real trade exists yet — the same
 * legs the hero network and the live diagram draw, so the two tell one story.
 * The figures are plausible dispatch times, not measurements.
 */
export const DEMO_LEGS: FanLeg[] = [
  { label: 'Hyperliquid', ms: 180, ok: true },
  { label: 'Bybit', ms: 240, ok: true },
  { label: 'Binance', ms: 310, ok: true },
  { label: 'OKX', ms: 420, ok: true },
  { label: 'Gate.io', ms: 260, ok: true },
  { label: 'KuCoin', ms: 900, ok: false },
  { label: 'Toobit', ms: 380, ok: true },
]

/** The eight exchanges behind one interface. */
export const EXCHANGES = [
  'Hyperliquid',
  'Bybit',
  'Binance',
  'OKX',
  'Gate.io',
  'KuCoin',
  'Toobit',
  'LBank',
]
