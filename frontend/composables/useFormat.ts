/**
 * Number and time formatting, in one place.
 *
 * Two rules the whole panel depends on:
 *
 *  - Money and quantities keep the locale's *digits* but never its decimal
 *    conventions guessed twice in two components. One helper, one behaviour.
 *  - Persian numerals are deliberately NOT used for prices. The admin reads
 *    the same figures on the exchange's own screen in Latin digits, and a
 *    mismatch between the two is exactly how a wrong size gets sent.
 */
const LATIN = 'en-US'

export function useFormat() {
  const { t } = useI18n()

  /** A price/balance. Nullish and unparseable both render as an em dash. */
  function money(value: string | number | null | undefined, digits = 2): string {
    const n = Number(value)
    if (value === null || value === undefined || value === '' || Number.isNaN(n)) return '—'
    return n.toLocaleString(LATIN, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  }

  /** Compact form for KPI tiles, where 1,284,000 costs more room than it earns. */
  function compact(value: string | number | null | undefined): string {
    const n = Number(value)
    if (value === null || value === undefined || value === '' || Number.isNaN(n)) return '—'
    if (Math.abs(n) < 10000) return money(n, 2)
    return n.toLocaleString(LATIN, { notation: 'compact', maximumFractionDigits: 1 })
  }

  /** A quantity — more decimals, trailing zeros trimmed. */
  function qty(value: string | number | null | undefined, digits = 6): string {
    const n = Number(value)
    if (value === null || value === undefined || value === '' || Number.isNaN(n)) return '—'
    return String(Number(n.toFixed(digits)))
  }

  function pct(value: string | number | null | undefined, digits = 2): string {
    const n = Number(value)
    if (value === null || value === undefined || value === '' || Number.isNaN(n)) return '—'
    return `${n.toFixed(digits)}%`
  }

  function signed(value: string | number | null | undefined, digits = 2): string {
    const n = Number(value)
    if (value === null || value === undefined || value === '' || Number.isNaN(n)) return '—'
    return `${n > 0 ? '+' : ''}${money(n, digits)}`
  }

  /** Milliseconds, at the precision the fan-out deadline is argued in. */
  function ms(value: number | null | undefined): string {
    if (value === null || value === undefined || Number.isNaN(value)) return '—'
    return value < 10 ? `${value.toFixed(1)}ms` : `${Math.round(value)}ms`
  }

  function dateTime(value: string | null | undefined): string {
    if (!value) return '—'
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleString(LATIN, {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }

  /** "4m ago" — the only place the active locale's words are used. */
  function since(value: string | null | undefined): string {
    if (!value) return '—'
    const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000)
    if (Number.isNaN(seconds)) return '—'
    if (seconds < 45) return t('time.justNow')
    const units: [number, string][] = [
      [60, 'time.minutes'],
      [3600, 'time.hours'],
      [86400, 'time.days'],
    ]
    for (let i = units.length - 1; i >= 0; i--) {
      const [size, key] = units[i]
      if (seconds >= size) return t(key, { n: Math.floor(seconds / size) })
    }
    return t('time.justNow')
  }

  return { money, compact, qty, pct, signed, ms, dateTime, since }
}
