import { defineStore } from 'pinia'

/**
 * Can this browser reach the panel at all?
 *
 * Separate from `stores/live.ts`, which is about the WebSocket, and from
 * `stores/market.ts`'s `feedDown`, which is about an *exchange* not answering.
 * This is the layer under both: the request never left the machine.
 *
 * It exists because of what a dropped connection looked like before it. Every
 * poller on the page — candles, ticker, positions, notifications, the bot
 * chart — failed independently, each one printed its own "Failed to fetch",
 * and the reader got a scroll of browser-internal strings rather than the one
 * fact that matters: the internet is down. So the failure is recorded once,
 * centrally, in `useApi`, and the panel says it once.
 *
 * **Two sources, and they disagree usefully.** `navigator.onLine` knows the
 * machine has no link at all, instantly and without a request. A run of failed
 * requests knows the harder case: the Wi-Fi is up, the router is not, or the
 * VPN dropped — where `onLine` stays true. Either one raises the banner.
 *
 * Recovery is live: one successful request clears it, and every poller on the
 * page is already retrying, so the banner goes away by itself.
 */

/**
 * Consecutive network-level failures before the banner appears.
 *
 * Not one: a single request can be cancelled by a navigation, and a banner that
 * flickers on every route change is noise. Two in a row is a connection.
 */
const FAILURES_BEFORE_DOWN = 2

export const useConnectionStore = defineStore('connection', {
  state: () => ({
    /** What the browser itself says. False is proof; true proves nothing. */
    online: true,
    /** Network-level failures since the last success. */
    failures: 0,
    /** When the connection was first believed lost, for "down for 2m". */
    lostAt: null as number | null,
    bound: false,
  }),

  getters: {
    /** Show the banner. Either the machine has no link, or requests stopped arriving. */
    down: (state) => !state.online || state.failures >= FAILURES_BEFORE_DOWN,
  },

  actions: {
    /** A request failed before reaching the server. */
    noteFailure() {
      this.failures += 1
      if (this.lostAt === null && this.down) this.lostAt = Date.now()
    },

    /** Anything came back — including a 500. The server answered, so the link is up. */
    noteSuccess() {
      if (this.failures || this.lostAt !== null) {
        this.failures = 0
        this.lostAt = null
      }
    },

    /**
     * Listen to the browser's own events. Called once from the app shell.
     *
     * `offline` raises the banner with no request needed; `online` does **not**
     * clear it by itself — the adapter coming back says nothing about whether
     * the server is reachable, and the next successful poll is what proves it.
     * It resets the counter so recovery takes one request rather than three.
     */
    bind() {
      if (this.bound || import.meta.server) return
      this.bound = true
      this.online = navigator.onLine
      window.addEventListener('offline', () => {
        this.online = false
        if (this.lostAt === null) this.lostAt = Date.now()
      })
      window.addEventListener('online', () => {
        this.online = true
        this.failures = 0
      })
    },
  },
})
