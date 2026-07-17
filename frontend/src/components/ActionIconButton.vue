<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    variant?: 'default' | 'danger' | 'success' | 'warning'
  }>(),
  { variant: 'default' },
)

const buttonClass = computed(() => {
  const map = {
    default: 'text-fg-muted hover:text-fg hover:bg-surface-raised',
    danger: 'text-fg-muted hover:text-negative hover:bg-danger-bg',
    success: 'text-fg-muted hover:text-positive hover:bg-success-bg',
    warning: 'text-fg-muted hover:text-warning hover:bg-warning-bg',
  }
  return map[props.variant]
})
</script>

<template>
  <button
    type="button"
    :title="title"
    class="inline-flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
    :class="buttonClass"
  >
    <slot />
  </button>
</template>
