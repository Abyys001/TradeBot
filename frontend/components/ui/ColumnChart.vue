<script setup lang="ts">
/**
 * Fan-out time per trade, with the spec §4 fan-out deadline drawn across it.
 *
 * The reference line is the whole reason this is a chart and not a number: the
 * question is never "how many milliseconds" but "how close are we to the
 * promise, and is it drifting". Columns under the line are one quiet ink;
 * columns over it turn amber, which in this panel always and only means
 * something failed.
 *
 * One series, so no legend — the card title names it. Hover gives the exact
 * figure; the axis carries only the reference value and the extremes, because
 * a label on every column would out-ink the data.
 */
const props = withDefaults(
  defineProps<{
    points: ColumnPoint[]
    /** The budget line, in the same unit as the values. */
    reference?: number
    referenceLabel?: string
    height?: number
    unit?: string
  }>(),
  { height: 132, unit: 'ms' },
)

const hovered = ref<number | null>(null)

const ceiling = computed(() => {
  const peak = Math.max(...props.points.map((p) => p.value), props.reference ?? 0)
  // Headroom so the tallest column does not touch the frame, and so the
  // reference line stays visible even when nothing has come close to it.
  return peak * 1.15 || 1
})

function heightPct(value: number): string {
  return `${Math.max(1.5, (value / ceiling.value) * 100)}%`
}

const referenceTop = computed(() =>
  props.reference === undefined ? null : `${100 - (props.reference / ceiling.value) * 100}%`,
)
</script>

<template>
  <figure class="min-w-0">
    <div
      class="relative"
      :style="{ height: `clamp(${Math.round(height * 0.7)}px, 20vh, ${Math.round(height * 1.35)}px)` }"
      @pointerleave="hovered = null"
    >
      <!-- The budget. Dashed so it reads as a threshold, not as data. -->
      <div
        v-if="referenceTop !== null"
        class="absolute inset-x-0 border-t border-dashed border-signal/50 pointer-events-none"
        :style="{ top: referenceTop }"
      >
        <span class="absolute -top-2 end-0 text-[0.65rem] num text-signal bg-panel px-1">
          {{ referenceLabel }}
        </span>
      </div>

      <div class="h-full flex items-end gap-[2px]">
        <button
          v-for="(point, i) in points"
          :key="point.key"
          type="button"
          class="flex-1 min-w-[3px] h-full flex items-end group focus:outline-none"
          :aria-label="`${point.label} — ${point.value}${unit}`"
          @pointerenter="hovered = i"
          @focus="hovered = i"
        >
          <span
            class="w-full rounded-t transition-colors"
            :class="[
              point.over ? 'bg-signal/80' : 'bg-brand/60',
              hovered === i ? 'brightness-125' : 'group-hover:brightness-125',
            ]"
            :style="{ height: heightPct(point.value) }"
          />
        </button>
      </div>

      <!-- Tooltip. Anchored to the top so it never covers the column it describes. -->
      <div
        v-if="hovered !== null && points[hovered]"
        class="absolute top-0 start-0 pointer-events-none bg-raised border border-line-strong
               rounded-lg px-2.5 py-1.5 shadow-lift text-xs whitespace-nowrap z-10"
      >
        <p class="num font-medium" :class="points[hovered].over ? 'text-signal' : 'text-ink'">
          {{ points[hovered].value }}{{ unit }}
        </p>
        <p class="text-ink-muted">{{ points[hovered].label }}</p>
        <p v-if="points[hovered].meta" class="text-ink-faint">{{ points[hovered].meta }}</p>
      </div>
    </div>

    <figcaption v-if="$slots.caption" class="label mt-2">
      <slot name="caption" />
    </figcaption>
  </figure>
</template>
