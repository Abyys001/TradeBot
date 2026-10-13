/**
 * One bot's performance, kept fresh while it runs.
 *
 * Polled rather than pushed: the endpoint prices the open position, which the
 * socket does not carry, and a hidden tab or a stopped bot has no reason to
 * wake the server. A bar or a routed action on the socket refreshes it
 * immediately instead of at the next tick.
 *
 * The figures are Decimal strings from the server and are only drawn here.
 */
export function useBotPerformance(
  botId: Ref<number> | ComputedRef<number>,
  active: Ref<boolean> | ComputedRef<boolean>,
  intervalMs = 10_000,
) {
  const api = useApi()
  const live = useLiveStore()

  const perf = ref<BotPerformance | null>(null)
  const loading = ref(true)
  const error = ref('')
  let timer: ReturnType<typeof setInterval> | null = null
  let inflight = false

  async function load() {
    if (inflight) return
    inflight = true
    try {
      perf.value = await api.botPerformance(botId.value)
      error.value = ''
    } catch (e: any) {
      error.value = errorMessage(e)
    } finally {
      loading.value = false
      inflight = false
    }
  }

  function stopTimer() {
    if (timer) clearInterval(timer)
    timer = null
  }

  function sync() {
    stopTimer()
    if (!active.value || import.meta.server) return
    timer = setInterval(() => {
      if (document.visibilityState === 'visible') void load()
    }, intervalMs)
  }

  onMounted(() => {
    void load()
    sync()
  })
  onBeforeUnmount(stopTimer)

  watch(botId, () => {
    perf.value = null
    loading.value = true
    void load()
  })
  // Starting or stopping changes both what to poll and what the figures are.
  watch(active, () => {
    sync()
    void load()
  })
  watch(
    () => [live.botBars[botId.value]?.at, live.botActions[botId.value]?.at],
    () => {
      if (active.value) void load()
    },
  )

  return { perf, loading, error, reload: load }
}
