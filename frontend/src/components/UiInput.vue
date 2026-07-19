<script setup lang="ts">
const modelValue = defineModel<string | number>({ default: '' })

withDefaults(defineProps<{
  label?: string
  placeholder?: string
  type?: string
  error?: string
  hint?: string
  disabled?: boolean
  required?: boolean
}>(), {
  type: 'text',
})
</script>

<template>
  <div class="ui-input-group">
    <label v-if="label" class="mb-1.5 block text-sm font-medium text-fg">
      {{ label }}
      <span v-if="required" class="text-negative">*</span>
    </label>
    <div class="relative">
      <span v-if="$slots.icon" class="pointer-events-none absolute inset-y-0 start-0 flex items-center ps-3 text-fg-muted">
        <slot name="icon" />
      </span>
      <input
        v-model="modelValue"
        :type="type"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        class="w-full rounded-lg border bg-surface px-3 py-2 text-sm text-fg transition-all duration-200 placeholder:text-fg-muted/50 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
        :class="[
          error ? 'border-negative focus:border-negative focus:ring-negative/20' : 'border-border hover:border-border-hover',
          $slots.icon ? 'ps-10' : '',
        ]"
      />
    </div>
    <p v-if="error" class="mt-1.5 text-xs text-negative">{{ error }}</p>
    <p v-else-if="hint" class="mt-1.5 text-xs text-fg-muted">{{ hint }}</p>
  </div>
</template>
