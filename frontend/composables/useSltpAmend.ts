/**
 * Pushing a mid-trade SL/TP change to every account (spec §4).
 *
 * All three editing surfaces — the ticket, the chart lines, the position row —
 * call this one function, for the same reason all three write to
 * `stores/order.ts`: an amend is N orders to N exchanges, and three components
 * each holding their own "am I sending?" flag is how two of them fire at once.
 *
 * Two rules live here rather than at the call sites:
 *
 *  - **One amend in flight, and the last edit wins.** Dragging a stop produces
 *    a drop every time the mouse is released; without serialisation an earlier
 *    fan-out can land *after* a later one and leave the exchanges resting on a
 *    price the admin already moved away from. A push while one is running does
 *    not queue up a second request — it marks the chain dirty, and the running
 *    one re-reads the store when it finishes.
 *  - **A live position is amendable even if this tab did not open it.** The
 *    gate is `trading.hasOpenTrade`, which `stores/positions.ts` now keeps
 *    honest by adopting the id the poll reports.
 */
const amending = ref(false)
let inflight: Promise<void> | null = null
let dirty = false

export function useSltpAmend() {
  const order = useOrderStore()
  const trading = useTradingStore()
  const positions = usePositionsStore()

  const canAmend = computed(() => trading.hasOpenTrade)

  async function drain() {
    while (dirty) {
      dirty = false
      try {
        await trading.amend(order.slPct, order.tpPct)
        await positions.load()
      } catch {
        // The store holds the message and per-leg failures raise persistent
        // §4 notifications. Swallowing it here keeps one bad amend from
        // breaking the chain for the next drag.
      }
    }
  }

  /** Resolves when the fan-out this edit belongs to has landed. */
  function pushAmend(): Promise<void> {
    if (!canAmend.value) return Promise.resolve()
    dirty = true
    if (inflight) return inflight
    amending.value = true
    inflight = drain().finally(() => {
      inflight = null
      amending.value = false
    })
    return inflight
  }

  return { pushAmend, amending: readonly(amending), canAmend }
}
