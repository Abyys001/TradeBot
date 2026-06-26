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
      <label class="text-xs text-zinc-500">{{ label }}</label>
      <span v-if="unit" class="text-xs text-zinc-400">{{ model }}{{ unit }}</span>
    </div>
    <div class="flex items-center gap-2">
      <input
        v-model.number="model"
        type="range"
        :min="min"
        :max="max"
        :step="step ?? 1"
        class="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-zinc-800 accent-violet-500"
      />
      <input
        v-model.number="model"
        type="number"
        :min="min"
        :max="max"
        :step="step ?? 1"
        class="w-16 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
      />
    </div>
  </div>
</template>
