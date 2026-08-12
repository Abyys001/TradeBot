<script setup lang="ts">
/** A real checkbox under a drawn track, so keyboard and forms behave normally. */
const model = defineModel<boolean>({ required: true })
defineProps<{ label: string; hint?: string; disabled?: boolean }>()
</script>

<template>
  <label
    class="flex items-start gap-3 cursor-pointer select-none"
    :class="disabled ? 'opacity-50 cursor-not-allowed' : ''"
  >
    <input v-model="model" type="checkbox" class="sr-only peer" :disabled="disabled" />
    <span
      class="mt-0.5 w-9 h-5 rounded-full bg-raised border border-line relative shrink-0
             transition-colors peer-checked:bg-brand peer-checked:border-brand
             peer-focus-visible:ring-2 peer-focus-visible:ring-brand/70 peer-focus-visible:ring-offset-2
             peer-focus-visible:ring-offset-base"
    >
      <span
        class="absolute top-0.5 start-0.5 w-3.5 h-3.5 rounded-full transition-transform"
        :class="model ? 'bg-white translate-x-4 rtl:-translate-x-4' : 'bg-ink-muted'"
      />
    </span>
    <span class="min-w-0">
      <span class="text-sm block">{{ label }}</span>
      <span v-if="hint" class="text-xs text-ink-muted block mt-0.5 leading-relaxed">{{ hint }}</span>
    </span>
  </label>
</template>
