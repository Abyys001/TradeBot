/**
 * Exchange slugs → the name shown to the admin.
 *
 * The wire carries slugs everywhere — the feed badge, the pong's `exchange`,
 * the accounts list — and a bare "hyperliquid" next to a price is a different
 * promise from "Hyperliquid". Keep the pretty name here so every surface reads
 * the same, and fall back to the slug rather than a guess when the backend
 * adds an exchange this map has not caught up with.
 */
const EXCHANGE_LABELS: Record<string, string> = {
  hyperliquid: 'Hyperliquid',
  bybit: 'Bybit',
  binance: 'Binance',
  okx: 'OKX',
  gateio: 'Gate.io',
  kucoin: 'KuCoin',
  toobit: 'Toobit',
  lbank: 'LBank',
  paper: 'Paper (demo)',
}

export function exchangeLabel(slug: string): string {
  if (!slug) return ''
  return EXCHANGE_LABELS[slug] ?? slug
}

/**
 * Split a canonical pair into base and quote for display.
 *
 * The venues this panel quotes settle in USDC (Hyperliquid perps) or USDT, so
 * the quote is read off the symbol rather than assumed — hardcoding "/USDT"
 * once rendered `BTCUSDC/USDT` in the watchlist.
 */
export function splitSymbol(symbol: string): { base: string; quote: string } {
  const quote = ['USDC', 'USDT', 'USD'].find((q) => symbol.endsWith(q)) ?? ''
  return { base: symbol.slice(0, symbol.length - quote.length), quote }
}
