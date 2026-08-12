import { defineStore } from 'pinia'

/**
 * The admin's own list of pairs to keep an eye on.
 *
 * Kept in a cookie rather than on the server: it is a personal preference, not
 * platform state, and storing it server-side would mean a migration, an
 * endpoint and a sync path for something that is a list of ten strings. The
 * cookie is also readable during SSR, so the list renders in the first HTML
 * instead of popping in after hydration.
 *
 * Prices come from one batched request for the whole list (`market/tickers/`).
 * One request per row would be ten round trips every few seconds from every
 * open panel, and each quote is already cached server-side.
 */
const POLL_MS = 5000
const MAX = 20
const DEFAULT_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']

export interface WatchRow {
  symbol: string
  price: number | null
  changePct: number | null
  live: boolean
  /** Direction of the last change, for the flash on the number. */
  direction: 'up' | 'down' | null
}

let timer: ReturnType<typeof setInterval> | null = null
/** Reference counting: the chart and the dashboard can both be mounted. */
let subscribers = 0

export const useWatchlistStore = defineStore('watchlist', () => {
  const stored = useCookie<string[]>('watchlist', {
    default: () => [...DEFAULT_SYMBOLS],
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  const quotes = ref<Record<string, WatchRow>>({})
  const loading = ref(false)
  const error = ref('')

  const symbols = computed(() => stored.value ?? [])
  const rows = computed<WatchRow[]>(() =>
    symbols.value.map(
      (symbol) =>
        quotes.value[symbol] ?? {
          symbol,
          price: null,
          changePct: null,
          live: false,
          direction: null,
        },
    ),
  )
  const has = (symbol: string) => symbols.value.includes(symbol.toUpperCase())
  const isFull = computed(() => symbols.value.length >= MAX)

  async function load() {
    if (!symbols.value.length) {
      quotes.value = {}
      return
    }
    loading.value = !Object.keys(quotes.value).length
    try {
      const data = await useApi().tickers(symbols.value, 'futures')
      const next: Record<string, WatchRow> = {}
      for (const quote of data.tickers) {
        const price = Number(quote.price)
        const previous = quotes.value[quote.symbol]?.price ?? null
        next[quote.symbol] = {
          symbol: quote.symbol,
          price,
          changePct: quote.change_pct === null ? null : Number(quote.change_pct),
          live: quote.live,
          direction:
            previous === null || previous === price ? null : price > previous ? 'up' : 'down',
        }
      }
      quotes.value = next
      error.value = ''
    } catch (e: any) {
      error.value = errorMessage(e)
    } finally {
      loading.value = false
    }
  }

  function add(symbol: string) {
    const next = symbol.trim().toUpperCase()
    // Anything the exchanges quote is allowed, not only the curated picker
    // list — but a stray "btc " or "btc/usdt" would just render as a dead row.
    if (!/^[A-Z0-9]{4,20}$/.test(next)) return false
    if (has(next) || isFull.value) return false
    stored.value = [...symbols.value, next]
    load()
    return true
  }

  function remove(symbol: string) {
    stored.value = symbols.value.filter((s) => s !== symbol.toUpperCase())
    const { [symbol.toUpperCase()]: _dropped, ...rest } = quotes.value
    quotes.value = rest
  }

  function toggle(symbol: string) {
    return has(symbol) ? (remove(symbol), false) : add(symbol)
  }

  /** Reordering by drag on a phone is a fight; two buttons are not. */
  function move(symbol: string, delta: number) {
    const list = [...symbols.value]
    const from = list.indexOf(symbol.toUpperCase())
    const to = from + delta
    if (from === -1 || to < 0 || to >= list.length) return
    list.splice(to, 0, ...list.splice(from, 1))
    stored.value = list
  }

  function reset() {
    stored.value = [...DEFAULT_SYMBOLS]
    load()
  }

  /** Each mounted watchlist subscribes; the poll stops when the last unmounts. */
  function start() {
    subscribers++
    load()
    if (timer || import.meta.server) return
    timer = setInterval(load, POLL_MS)
  }

  function stop() {
    subscribers = Math.max(0, subscribers - 1)
    if (subscribers > 0 || !timer) return
    clearInterval(timer)
    timer = null
  }

  return {
    symbols,
    rows,
    quotes,
    loading,
    error,
    isFull,
    max: MAX,
    has,
    load,
    add,
    remove,
    toggle,
    move,
    reset,
    start,
    stop,
  }
})
