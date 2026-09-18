/**
 * One clock for the whole panel: **UK time**, the way TradingView shows it.
 *
 * The admin reads this platform beside a TradingView chart set to Europe/London
 * and compares timestamps across the two. A browser in Tehran rendering the
 * same bar four and a half hours later is not a cosmetic difference — it is two
 * screens disagreeing about when a trade happened, which is the one thing a
 * trade log exists to settle. So the timezone is a property of the platform,
 * not of the machine it is opened on.
 *
 * Nothing here moves a timestamp. Lightweight Charts has no timezone of its own
 * and the usual workaround is to shift every value by the offset, which leaves
 * the chart holding numbers that are not the instants they claim to be — and
 * every marker, price line and paging bound then has to remember to lie the
 * same way. Instead the *formatters* are replaced: the axis and the crosshair
 * render a real epoch second in London, and every value in the chart stays the
 * instant the server sent.
 *
 * BST is not a fixed offset and not the same offset all year, so everything
 * goes through `Intl` with the IANA zone rather than a `+1` constant. The last
 * Sunday in March takes care of itself.
 */

/** The zone every timestamp in the panel is rendered in. */
export const DISPLAY_TZ = 'Europe/London'

/** `GMT` or `BST` — which of the two is in force at that instant. */
export function zoneLabel(at: Date = new Date()): string {
  const part = new Intl.DateTimeFormat('en-GB', {
    timeZone: DISPLAY_TZ,
    timeZoneName: 'short',
  })
    .formatToParts(at)
    .find((p) => p.type === 'timeZoneName')
  return part?.value ?? 'GMT'
}

function parts(at: Date, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone: DISPLAY_TZ, ...options }).format(at)
}

/** `14:35` in London. */
export function ukTime(epochSeconds: number): string {
  return parts(new Date(epochSeconds * 1000), {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/** `18 Sep 14:35` in London — enough to check a row against TradingView. */
export function ukDateTime(epochSeconds: number): string {
  return parts(new Date(epochSeconds * 1000), {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/**
 * The two Lightweight Charts options that put the axis and the crosshair on
 * London's clock. Spread into `createChart`, and into both charts — an axis in
 * one timezone beside a trade log in another is the bug this exists to close.
 *
 * `tickMarkType` is the library's own classification of the label it is about
 * to draw (year / month / day / time / second). Honouring it is what keeps a
 * daily chart reading `18 Sep` rather than `00:00` fourteen times in a row.
 */
export function ukChartLocalization() {
  return {
    localization: {
      locale: 'en-GB',
      timeFormatter: (time: unknown) => ukDateTime(Number(time)),
    },
    timeScale: {
      timeVisible: true,
      tickMarkFormatter: (time: unknown, tickMarkType: number) => {
        const at = new Date(Number(time) * 1000)
        // 0 Year · 1 Month · 2 DayOfMonth · 3 Time · 4 TimeWithSeconds
        if (tickMarkType === 0) return parts(at, { year: 'numeric' })
        if (tickMarkType === 1) return parts(at, { month: 'short' })
        if (tickMarkType === 2) return parts(at, { day: 'numeric', month: 'short' })
        if (tickMarkType === 4) {
          return parts(at, {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
          })
        }
        return ukTime(Number(time))
      },
    },
  }
}
