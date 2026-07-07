<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    value?: number
    indeterminate?: boolean
    size?: 'sm' | 'md'
    color?: 'amber' | 'violet' | 'emerald'
  }>(),
  { value: 0, indeterminate: false, size: 'sm', color: 'amber' },
)

const pct = computed(() => Math.min(100, Math.max(0, props.value)))

const barColor = computed(() => {
  if (props.color === 'violet') return 'bg-violet-500'
  if (props.color === 'emerald') return 'bg-emerald-500'
  return 'bg-amber-500'
})

const trackHeight = computed(() => (props.size === 'md' ? 'h-1.5' : 'h-1'))
</script>

<template>
  <div class="w-full rounded-full bg-zinc-800 overflow-hidden" :class="trackHeight">
    <div
      v-if="indeterminate"
      class="h-full w-1/3 rounded-full animate-pulse"
      :class="barColor"
    />
    <div
      v-else
      class="h-full rounded-full transition-all duration-300"
      :class="barColor"
      :style="{ width: `${pct}%` }"
    />
  </div>
</template>
