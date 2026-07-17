<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  sub?: string
  accent?: 'green' | 'red' | 'neutral' | 'amber'
}>()
</script>

<template>
  <div class="rounded-xl border border-border bg-surface-raised/60 p-4">
    <div class="text-xs text-fg-muted mb-1">{{ label }}</div>
    <div
      class="text-2xl font-semibold tabular-nums"
      :class="{
        'text-positive': accent === 'green',
        'text-negative': accent === 'red',
        'text-warning': accent === 'amber',
        'text-fg': !accent || accent === 'neutral',
      }"
    >
      {{ value }}
    </div>
    <div v-if="sub" class="text-xs text-fg-muted mt-1">{{ sub }}</div>
  </div>
</template>
