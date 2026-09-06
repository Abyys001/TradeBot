/**
 * A clock that ticks in the page rather than at the next reload.
 *
 * The promotion gate's soak row is the reason this exists. "14 days required,
 * 0.5 days measured" is a number an operator cannot plan around, and rounded to
 * a decimal it looks frozen for two and a half hours at a time. The server
 * sends seconds and the instant the run started; this counts from there, so the
 * minutes visibly move and the answer to "when can I promote this" is on screen
 * instead of in arithmetic.
 *
 * Stops itself when the run is not running: a stopped bot's soak is a fixed
 * number, and a counter that kept climbing would be claiming runtime that is
 * not happening.
 */
export function useCountdown(
  since: Ref<string | null | undefined>,
  baseSeconds: Ref<number>,
  running: Ref<boolean>,
) {
  const now = ref(Date.now())
  let timer: ReturnType<typeof setInterval> | null = null

  function start() {
    stop()
    if (!running.value) return
    // Once a second. The display resolves to minutes, but a 60s tick makes the
    // first change take up to a minute to appear, which reads as broken.
    timer = setInterval(() => (now.value = Date.now()), 1000)
  }

  function stop() {
    if (timer) clearInterval(timer)
    timer = null
  }

  const seconds = computed(() => {
    if (!running.value || !since.value) return baseSeconds.value
    const started = new Date(since.value).getTime()
    if (Number.isNaN(started)) return baseSeconds.value
    return Math.max(0, Math.floor((now.value - started) / 1000))
  })

  onMounted(start)
  watch(running, start)
  onBeforeUnmount(stop)

  return { seconds }
}

/**
 * `3d 04h 17m` — days, hours and minutes, and never a bare decimal of days.
 *
 * Seconds are dropped above an hour on purpose: at that scale they are noise
 * that makes the whole string change every tick and nothing readable move.
 */
export function formatDuration(total: number): string {
  const seconds = Math.max(0, Math.floor(total))
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  if (days) return `${days}d ${pad(hours)}h ${pad(minutes)}m`
  if (hours) return `${hours}h ${pad(minutes)}m`
  if (minutes) return `${minutes}m ${pad(secs)}s`
  return `${secs}s`
}
