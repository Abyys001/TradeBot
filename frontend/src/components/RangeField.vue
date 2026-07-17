<script setup lang="ts">
const model = defineModel<number>({ required: true })

defineProps<{
  label: string
  min: number
  max: number
  step?: number
  unit?: string
}>()
</script>

<template>
  <div>
    <div class="mb-1 flex items-center justify-between">
      <label class="text-xs text-fg-muted">{{ label }}</label>
      <span v-if="unit" class="text-xs text-fg-muted">{{ model }}{{ unit }}</span>
    </div>
    <div class="flex items-center gap-2">
      <input
        v-model.number="model"
        type="range"
        :min="min"
        :max="max"
        :step="step ?? 1"
        class="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-surface-muted accent-violet-500"
      />
      <input
        v-model.number="model"
        type="number"
        :min="min"
        :max="max"
        :step="step ?? 1"
        class="w-16 rounded border border-border bg-surface px-2 py-1 text-xs text-fg"
      />
    </div>
  </div>
</template>
