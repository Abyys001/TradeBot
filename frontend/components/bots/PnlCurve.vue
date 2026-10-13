<script setup lang="ts">
/**
 * A bot's cumulative realised result, drawn from `performance.curve`.
 *
 * `total` is already the running sum, computed in Decimal on the server; this
 * only parses it for plotting.
 */
const props = withDefaults(
  defineProps<{ perf: BotPerformance | null; height?: number }>(),
  { height: 110 },
)

const { t } = useI18n()
const { money, signed, dateTime } = useFormat()

const points = computed(() =>
  (props.perf?.curve ?? []).map((point) => ({
    label: dateTime(point.at),
    value: Number(point.total),
    meta: signed(point.pnl),
  })),
)
</script>

<template>
  <UiTrendChart
    v-if="points.length"
    :points="points"
    :height="height"
    :format="(n: number) => `${n >= 0 ? '+' : ''}$${money(n)}`"
  />
  <p
    v-else
    class="grid place-items-center text-xs text-ink-faint text-center px-4 rounded-lg border border-dashed border-line"
    :style="{ minHeight: `${height}px` }"
  >
    {{ t('bots.perf.noCurve') }}
  </p>
</template>
