<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ series: number[]; height?: number }>()

const height = computed(() => props.height ?? 120)
const pathD = computed(() => {
  const s = props.series
  if (!s.length) return ''
  const w = 400
  const h = height.value - 8
  const min = Math.min(...s)
  const max = Math.max(...s)
  const range = max - min || 1
  return s
    .map((v, i) => {
      const x = (i / Math.max(s.length - 1, 1)) * w
      const y = h - ((v - min) / range) * h + 4
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})
</script>

<template>
  <div class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-2">
    <svg v-if="series.length" :viewBox="`0 0 400 ${height}`" class="w-full" :height="height">
      <path :d="pathD" fill="none" stroke="#8b5cf6" stroke-width="1.5" />
    </svg>
    <div v-else class="text-xs text-zinc-500 text-center py-6">—</div>
  </div>
</template>
