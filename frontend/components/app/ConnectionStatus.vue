<script setup lang="ts">
/**
 * Link health in the top bar: connected or not, and how far away the engine is.
 *
 * The latency is not a vanity metric. This panel's promise is a one-second
 * fan-out (spec §4); if the admin's own round trip to the engine is 700ms, the
 * budget is mostly gone before an order is even dispatched. Better to know that
 * while flat than to work it out afterwards from the latency chart.
 *
 * Colour follows the same thresholds the store documents, and never carries the
 * meaning alone — the number and the label are always there too.
 */
const { t } = useI18n()
const live = useLiveStore()

const STATUS = {
  live: { tone: 'ok', key: 'common.live' },
  connecting: { tone: 'neutral', key: 'common.connecting' },
  offline: { tone: 'signal', key: 'common.offline' },
} as const

const PING_TONE = {
  good: 'text-ok',
  fair: 'text-signal',
  poor: 'text-short',
} as const

const tooltip = computed(() => {
  if (live.status !== 'live') return t(`common.${live.status}`)
  const quality = live.pingQuality
  return quality
    ? t('connection.pingHint', { ms: live.pingMedian ?? 0, quality: t(`connection.${quality}`) })
    : t('common.live')
})
</script>

<template>
  <div
    class="flex items-center gap-1.5 rounded-lg border border-line bg-sunken h-8 px-2"
    :title="tooltip"
  >
    <span v-if="live.status === 'live'" class="relative flex w-1.5 h-1.5 shrink-0">
      <span class="absolute inline-flex w-full h-full rounded-full bg-ok animate-pulse-ring" />
      <span class="relative inline-flex w-1.5 h-1.5 rounded-full bg-ok" />
    </span>
    <span
      v-else
      class="w-1.5 h-1.5 rounded-full shrink-0"
      :class="live.status === 'offline' ? 'bg-signal' : 'bg-ink-faint'"
    />

    <span class="text-tick uppercase tracking-wider hidden sm:inline text-ink-muted">
      {{ t(STATUS[live.status].key) }}
    </span>

    <!-- Latency sits behind a divider so it reads as a measurement of the
         connection rather than part of its name. -->
    <template v-if="live.pingMedian !== null">
      <span class="w-px h-3 bg-line-strong hidden sm:block" />
      <span class="num text-xs" :class="PING_TONE[live.pingQuality ?? 'good']">
        {{ live.pingMedian }}<span class="text-ink-faint">ms</span>
      </span>
    </template>
  </div>
</template>
