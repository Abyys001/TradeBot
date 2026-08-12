<script setup lang="ts">
/**
 * Cumulative realised PnL across the trade log — change over time, so a line.
 *
 * One series, so no legend and no palette: the line takes its colour from the
 * sign of the final value, which is the only categorical fact present (up or
 * down), and that fact is also written next to it in words. Zero gets a
 * baseline because "did this make money" is read against zero, not against the
 * lowest point.
 *
 * A crosshair with a tooltip is standard for a line chart and costs nothing —
 * without it, the only readable value is the last one.
 */
const props = withDefaults(
  defineProps<{
    points: { label: string; value: number; meta?: string }[]
    height?: number
    format?: (n: number) => string
  }>(),
  { height: 120, format: (n: number) => n.toFixed(2) },
)

const W = 300
const hovered = ref<number | null>(null)

const bounds = computed(() => {
  const values = props.points.map((p) => p.value).concat(0)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const pad = (max - min) * 0.12 || 1
  return { min: min - pad, max: max + pad }
})

const H = computed(() => props.height)

function x(i: number): number {
  if (props.points.length <= 1) return W / 2
  return (i / (props.points.length - 1)) * W
}

function y(value: number): number {
  const { min, max } = bounds.value
  const span = max - min || 1
  return H.value - ((value - min) / span) * H.value
}

const line = computed(() =>
  props.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(2)} ${y(p.value).toFixed(2)}`).join(' '),
)

const area = computed(() => {
  if (props.points.length < 2) return ''
  const zero = y(0)
  return `${line.value} L ${W} ${zero} L 0 ${zero} Z`
})

const last = computed(() => props.points[props.points.length - 1]?.value ?? 0)
const positive = computed(() => last.value >= 0)
const zeroY = computed(() => y(0))

/** Nearest point to the pointer, in chart units rather than pixels. */
function onMove(event: PointerEvent) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  if (!rect.width || props.points.length === 0) return
  const ratio = (event.clientX - rect.left) / rect.width
  hovered.value = Math.min(
    props.points.length - 1,
    Math.max(0, Math.round(ratio * (props.points.length - 1))),
  )
}
</script>

<template>
  <figure class="relative min-w-0" @pointermove="onMove" @pointerleave="hovered = null">
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      preserveAspectRatio="none"
      class="w-full block"
      :style="{ height: `${H}px` }"
      role="img"
      :aria-label="`Cumulative result, ${format(last)}`"
    >
      <!-- Zero baseline: the reference the whole series is judged against. -->
      <line
        x1="0"
        :y1="zeroY"
        :x2="W"
        :y2="zeroY"
        stroke="currentColor"
        class="text-line-strong"
        stroke-width="1"
        stroke-dasharray="3 3"
        vector-effect="non-scaling-stroke"
      />

      <path
        v-if="area"
        :d="area"
        :class="positive ? 'fill-long/10' : 'fill-short/10'"
        stroke="none"
      />
      <path
        :d="line"
        fill="none"
        :class="positive ? 'stroke-long' : 'stroke-short'"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
      />

      <g v-if="hovered !== null && points[hovered]">
        <line
          :x1="x(hovered)"
          y1="0"
          :x2="x(hovered)"
          :y2="H"
          stroke="currentColor"
          class="text-line-strong"
          stroke-width="1"
          vector-effect="non-scaling-stroke"
        />
        <circle
          :cx="x(hovered)"
          :cy="y(points[hovered].value)"
          r="4"
          :class="positive ? 'fill-long' : 'fill-short'"
          stroke="rgb(var(--c-panel))"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
        />
      </g>
    </svg>

    <div
      v-if="hovered !== null && points[hovered]"
      class="absolute top-0 pointer-events-none bg-raised border border-line-strong rounded-lg
             px-2.5 py-1.5 shadow-lift text-xs whitespace-nowrap z-10"
      :style="{
        left: `${(hovered / Math.max(1, points.length - 1)) * 100}%`,
        transform: 'translateX(-50%)',
      }"
    >
      <p class="num font-medium" :class="points[hovered].value >= 0 ? 'text-long' : 'text-short'">
        {{ format(points[hovered].value) }}
      </p>
      <p class="text-ink-muted">{{ points[hovered].label }}</p>
      <p v-if="points[hovered].meta" class="text-ink-faint">{{ points[hovered].meta }}</p>
    </div>
  </figure>
</template>
