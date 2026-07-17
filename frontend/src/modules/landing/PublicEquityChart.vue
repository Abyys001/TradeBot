<script setup lang="ts">
import { computed } from 'vue'
import type { PublicEquityPoint } from '../../api/public'

const props = defineProps<{ points: PublicEquityPoint[]; height?: number }>()

const height = computed(() => props.height ?? 200)
const width = 800

const geometry = computed(() => {
  const s = props.points
  if (!s.length) return null
  const h = height.value - 8
  const values = s.map((p) => p.equity)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const coords = s.map((p, i) => {
    const x = (i / Math.max(s.length - 1, 1)) * width
    const y = h - ((p.equity - min) / range) * h + 4
    return [x, y] as const
  })

  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${width},${h + 4} L0,${h + 4} Z`
  return { line, area }
})
</script>

<template>
  <div class="rounded-xl border border-border bg-surface-raised p-4">
    <svg v-if="geometry" :viewBox="`0 0 ${width} ${height}`" class="w-full" :height="height" preserveAspectRatio="none">
      <defs>
        <linearGradient id="public-equity-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.35" />
          <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path :d="geometry.area" fill="url(#public-equity-fill)" stroke="none" />
      <path :d="geometry.line" fill="none" stroke="#8b5cf6" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
    </svg>
    <div v-else class="flex items-center justify-center py-10 text-sm text-fg-muted">—</div>
  </div>
</template>
