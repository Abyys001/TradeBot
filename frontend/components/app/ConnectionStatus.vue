<script setup lang="ts">
/**
 * Link health in the top bar: connected or not, and how far away things are.
 *
 * **Two measured numbers, never one.** The first is the browser's own round
 * trip to the engine, timed on the keepalive. On a local network that is a
 * millisecond — a true number that says nothing about whether an order reaches
 * an exchange inside the spec §4 budget. The second is what does: the engine's
 * last measured round trip to the exchange, timed on real market-data calls and
 * reported in the pong.
 *
 * Neither is ever a placeholder. A number that has not been measured within the
 * last minute is not shown at all.
 *
 * Colour follows the thresholds the store documents, and never carries the
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
  const lines: string[] = []
  if (live.pingQuality) {
    lines.push(
      t('connection.pingHint', {
        ms: live.pingMedian ?? 0,
        quality: t(`connection.${live.pingQuality}`),
      }),
    )
  }
  if (live.exchangeQuality) {
    lines.push(
      t('connection.exchangeHint', {
        ms: live.exchangeMs ?? 0,
        exchange: live.exchangeName,
        quality: t(`connection.${live.exchangeQuality}`),
      }),
    )
  } else {
    lines.push(t('connection.exchangeUnmeasured'))
  }
  return lines.join('\n')
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
         connection rather than part of its name. Two hops, labelled, because an
         unlabelled "1ms" invites the reader to think it is the whole path. -->
    <template v-if="live.pingMedian !== null">
      <span class="w-px h-3 bg-line-strong hidden sm:block" />
      <span class="num text-xs" :class="PING_TONE[live.pingQuality ?? 'good']">
        <span class="text-ink-faint text-tick uppercase me-0.5">{{ t('connection.link') }}</span>
        {{ live.pingMedian }}<span class="text-ink-faint">ms</span>
      </span>
    </template>

    <!-- The hop that actually carries an order. Absent, not zeroed, when the
         engine has measured nothing recently. -->
    <template v-if="live.exchangeMs !== null">
      <span class="w-px h-3 bg-line-strong hidden sm:block" />
      <span
        class="num text-xs hidden sm:inline"
        :class="PING_TONE[live.exchangeQuality ?? 'good']"
      >
        <span class="text-ink-faint text-tick uppercase me-0.5">
          {{ live.exchangeName || t('connection.exchange') }}
        </span>
        {{ Math.round(live.exchangeMs) }}<span class="text-ink-faint">ms</span>
      </span>
    </template>
  </div>
</template>
