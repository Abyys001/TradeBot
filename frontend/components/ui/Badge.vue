<script setup lang="ts">
/**
 * A state chip.
 *
 * Every tone ships with its own text, never colour alone — the whole point of
 * a status badge is that it still reads for someone who cannot separate amber
 * from green, or on a printed screenshot.
 */
withDefaults(
  defineProps<{ tone?: 'neutral' | 'ok' | 'signal' | 'short' | 'long' | 'brand'; dot?: boolean }>(),
  { tone: 'neutral', dot: false },
)

const TONE = {
  neutral: 'border-line text-ink-muted bg-raised',
  ok: 'border-ok/40 text-ok bg-ok-dim',
  signal: 'border-signal/50 text-signal bg-signal-dim',
  short: 'border-short/40 text-short bg-short-dim',
  long: 'border-long/40 text-long bg-long-dim',
  brand: 'border-brand/40 text-brand bg-brand-dim',
}
</script>

<template>
  <span class="chip" :class="TONE[tone]">
    <span v-if="dot" class="w-1.5 h-1.5 rounded-full bg-current" />
    <slot />
  </span>
</template>
