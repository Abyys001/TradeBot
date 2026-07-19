<script setup lang="ts">
const modelValue = defineModel<boolean>({ default: false })

defineProps<{
  label?: string
  disabled?: boolean
}>()
</script>

<template>
  <label
    class="ui-checkbox inline-flex cursor-pointer items-center gap-2.5 select-none"
    :class="{ 'cursor-not-allowed opacity-50': disabled }"
  >
    <span
      class="flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded border-2 transition-all duration-200"
      :class="modelValue
        ? 'border-accent bg-accent shadow-sm shadow-accent/20'
        : 'border-border hover:border-border-hover bg-surface'"
    >
      <svg
        class="h-3 w-3 text-accent-fg transition-transform duration-200"
        :class="modelValue ? 'scale-100' : 'scale-0'"
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M2 6l3 3 5-5" />
      </svg>
    </span>
    <input
      v-model="modelValue"
      type="checkbox"
      :disabled="disabled"
      class="sr-only"
    />
    <span v-if="label" class="text-sm text-fg">{{ label }}</span>
    <slot />
  </label>
</template>
