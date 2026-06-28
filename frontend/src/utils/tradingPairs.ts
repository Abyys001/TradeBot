export const DEFAULT_QUOTE = 'USDT'

const FALLBACK_COINS = [
  'BTC',
  'ETH',
  'SOL',
  'DOGE',
  'XRP',
  'AVAX',
  'LINK',
  'ARB',
  'OP',
  'SUI',
  'BNB',
  'ADA',
  'MATIC',
  'DOT',
  'LTC',
]

export const POPULAR_COINS = ['BTC', 'ETH', 'SOL']

export function pairToCoin(pair: string): string {
  const s = pair.trim().toUpperCase()
  if (s.includes('-')) return s.split('-')[0]
  if (s.includes('/')) return s.split('/')[0]
  return s
}

export function coinToPair(coin: string, quote = DEFAULT_QUOTE): string {
  const base = pairToCoin(coin)
  return `${base}-${quote}`
}

export function normalizePair(input: string, quote = DEFAULT_QUOTE): string {
  return coinToPair(input, quote)
}

export function buildPairOptions(coins: string[], quote = DEFAULT_QUOTE): string[] {
  const seen = new Set<string>()
  const pairs: string[] = []
  for (const raw of coins) {
    const pair = coinToPair(raw, quote)
    if (!seen.has(pair)) {
      seen.add(pair)
      pairs.push(pair)
    }
  }
  return pairs.sort((a, b) => a.localeCompare(b))
}

export function fallbackPairs(quote = DEFAULT_QUOTE): string[] {
  return buildPairOptions(FALLBACK_COINS, quote)
}

export function filterPairs(pairs: string[], query: string, limit = 80): string[] {
  const q = query.trim().toUpperCase()
  if (!q) return pairs.slice(0, limit)
  return pairs
    .filter((pair) => {
      const coin = pairToCoin(pair)
      return pair.includes(q) || coin.includes(q) || coin.startsWith(q)
    })
    .slice(0, limit)
}
