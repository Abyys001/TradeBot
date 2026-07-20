<script setup lang="ts">
interface Option {
  label: string
  value: string | number
}

const modelValue = defineModel<string | number>({ default: '' })

defineProps<{
  label?: string
  options: Option[]
  placeholder?: string
  error?: string
  disabled?: boolean
}>()
</script>

<template>
  <div class="ui-select-group">
    <label v-if="label" class="mb-1.5 block text-sm font-medium text-fg">{{ label }}</label>
    <div class="relative">
      <select
        v-model="modelValue"
        :disabled="disabled"
        class="w-full appearance-none rounded-lg border border-border bg-surface px-3 py-2 pe-8 text-sm text-fg transition-all duration-200 hover:border-border-hover focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
        :class="{ 'border-negative focus:border-negative focus:ring-negative/20': error }"
      >
        <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
        <option v-for="opt in options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <span class="pointer-events-none absolute inset-y-0 end-0 flex items-center pe-2 text-fg-muted">
        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 9l6 6 6-6" />
        </svg>
      </span>
    </div>
    <p v-if="error" class="mt-1.5 text-xs text-negative">{{ error }}</p>
  </div>
</template>
