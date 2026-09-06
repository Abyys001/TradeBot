<script setup lang="ts">
/**
 * A determinate progress bar, for waits long enough that a spinner lies.
 *
 * Determinate on purpose: the two places this is used — a backtest downloading
 * history, a replay walking bars — both know how far along they are, and a
 * spinner over a ninety-second download is indistinguishable from a hang.
 *
 * `value` is `[0, 1]`. An indeterminate phase (queued, waiting on a thread to
 * pick the job up) passes `null` and gets a sweeping bar instead of a fake
 * number, because inventing "37%" is the thing this component exists to avoid.
 */
const props = withDefaults(
  defineProps<{
    value: number | null
    label?: string
    detail?: string
    tone?: 'brand' | 'ok' | 'signal'
  }>(),
  { tone: 'brand', label: '', detail: '' },
)

const pct = computed(() =>
  props.value === null ? null : Math.round(Math.min(1, Math.max(0, props.value)) * 100),
)

const FILL = {
  brand: 'bg-brand',
  ok: 'bg-ok',
  signal: 'bg-signal',
}
</script>

<template>
  <div class="space-y-1.5">
    <div v-if="label || detail || pct !== null" class="flex items-baseline gap-2 text-xs">
      <span v-if="label" class="text-ink-muted truncate">{{ label }}</span>
      <span v-if="detail" class="text-ink-faint num truncate">{{ detail }}</span>
      <span v-if="pct !== null" class="num text-ink-muted ms-auto shrink-0">{{ pct }}%</span>
    </div>
    <div
      class="h-1.5 rounded-full bg-sunken border border-line overflow-hidden"
      role="progressbar"
      :aria-valuenow="pct ?? undefined"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="label || undefined"
    >
      <div
        v-if="pct !== null"
        class="h-full rounded-full transition-[width] duration-300 ease-out"
        :class="FILL[tone]"
        :style="{ width: `${pct}%` }"
      />
      <div v-else class="h-full w-1/3 rounded-full animate-sweep" :class="FILL[tone]" />
    </div>
  </div>
</template>

<style scoped>
/* The indeterminate case. Deliberately slow — a fast sweep reads as an error
   animation, and this is a normal wait. */
@keyframes sweep {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(300%);
  }
}
.animate-sweep {
  animation: sweep 1.4s ease-in-out infinite;
}
</style>
