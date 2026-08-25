import { defineStore } from 'pinia'

/**
 * Strategies, bots and their runs.
 *
 * One store rather than three, because the panel never shows a bot without the
 * strategy behind it — a bot's identity is "this version of that script", and
 * splitting them means two loading states for one question.
 *
 * Nothing here recomputes a number. Metrics, PnL, gate rows and leg outcomes
 * all arrive computed in Decimal from the server; the browser's job is to draw
 * them. Same rule as `stores/positions.ts`.
 */
export const useBotsStore = defineStore('bots', () => {
  const api = useApi()

  const strategies = ref<Strategy[]>([])
  const bots = ref<BotSummary[]>([])
  const policy = ref<BotPolicy | null>(null)
  const loading = ref(false)
  const error = ref('')

  /** Bot id → its most recent run, refreshed by the socket as bars arrive. */
  const runs = ref<Record<number, BotRun>>({})

  const running = computed(() => bots.value.filter((bot) => bot.state === 'paper' || bot.state === 'live'))
  const live = computed(() => bots.value.filter((bot) => bot.state === 'live'))

  function byId(id: number): BotSummary | undefined {
    return bots.value.find((bot) => bot.id === id)
  }

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const [strategyRows, botRows] = await Promise.all([api.strategies(), api.bots()])
      strategies.value = strategyRows
      bots.value = botRows
      for (const bot of botRows) if (bot.latest_run) runs.value[bot.id] = bot.latest_run
    } catch (e: any) {
      error.value = errorMessage(e)
    } finally {
      loading.value = false
    }
  }

  async function loadPolicy() {
    if (policy.value) return policy.value
    policy.value = await api.botPolicy()
    return policy.value
  }

  function upsert(bot: BotSummary) {
    const index = bots.value.findIndex((row) => row.id === bot.id)
    if (index >= 0) bots.value[index] = bot
    else bots.value.push(bot)
  }

  /**
   * The socket says a bot changed state. Applied optimistically to the row the
   * panel is already drawing rather than triggering a reload — a bot that
   * stopped at 03:00 should turn red in the list immediately, not at the next
   * poll tick.
   */
  function applyState(botId: number, state: BotState) {
    const bot = byId(botId)
    if (bot) {
      bot.state = state
      bot.dry_run = state !== 'live'
    }
  }

  function applyRun(botId: number, run: BotRun) {
    runs.value[botId] = run
  }

  async function start(id: number, state: 'paper' | 'live') {
    const result = await api.startBot(id, state)
    applyState(id, result.state as BotState)
    return result
  }

  async function stop(id: number, reason = '') {
    const result = await api.stopBot(id, reason)
    applyState(id, 'stopped')
    return result
  }

  return {
    strategies,
    bots,
    runs,
    policy,
    loading,
    error,
    running,
    live,
    byId,
    load,
    loadPolicy,
    upsert,
    applyState,
    applyRun,
    start,
    stop,
  }
})
