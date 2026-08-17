<script setup lang="ts">
/**
 * Time left in the current candle.
 *
 * Entries and SL/TP moves are timed against the bar, not against the wall
 * clock: "am I early enough in this candle" is a question the admin was
 * previously answering by watching the last bar twitch. This says it exactly.
 *
 * Derived from the clock, not from the feed. Exchange intervals are aligned to
 * the UNIX epoch — the same arithmetic `market.applyTick` uses to decide when a
 * new bar starts — so the countdown agrees with the chart even between polls,
 * and keeps running while a poll is in flight.
 */
const { t } = useI18n()
const market = useMarketStore()

const mounted = ref(false)
onMounted(() => (mounted.value = true))

/** Its own clock: the store's poll cadence is far too coarse to count seconds. */
const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  // 250ms rather than 1s: on a one-second boundary the readout would visibly
  // skip a number whenever the interval drifted against the clock.
  ticker = setInterval(() => (now.value = Date.now()), 250)
})

onBeforeUnmount(() => {
  if (ticker) clearInterval(ticker)
  ticker = null
})

const remaining = computed(() => {
  const seconds = market.intervalSeconds
  const elapsed = Math.floor(now.value / 1000) % seconds
  return seconds - elapsed
})

/** mm:ss, or h:mm:ss once a bar is long enough for hours to matter. */
const label = computed(() => {
  const total = remaining.value
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return hours ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`
})

/** The last few seconds of a bar are the ones worth reacting to. */
const closing = computed(() => remaining.value <= 10)
</script>

<template>
  <div
    class="pointer-events-none select-none flex items-center gap-1.5 rounded-md border
           border-line bg-sunken/90 backdrop-blur px-2 py-1"
    :title="t('terminal.candleTimerHint', { interval: market.interval })"
  >
    <span class="label leading-none">{{ market.interval }}</span>
    <span
      class="num text-xs tabular-nums leading-none transition-colors"
      :class="mounted && closing ? 'text-signal' : 'text-ink'"
    >
      {{ mounted ? label : '--:--' }}
    </span>
  </div>
</template>
