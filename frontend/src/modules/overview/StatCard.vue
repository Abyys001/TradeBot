<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  sub?: string
  accent?: 'green' | 'red' | 'neutral' | 'amber'
}>()
</script>

<template>
  <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
    <div class="text-xs text-zinc-500 mb-1">{{ label }}</div>
    <div
      class="text-2xl font-semibold tabular-nums"
      :class="{
        'text-emerald-400': accent === 'green',
        'text-red-400': accent === 'red',
        'text-amber-400': accent === 'amber',
        'text-zinc-100': !accent || accent === 'neutral',
      }"
    >
      {{ value }}
    </div>
    <div v-if="sub" class="text-xs text-zinc-600 mt-1">{{ sub }}</div>
  </div>
</template>
