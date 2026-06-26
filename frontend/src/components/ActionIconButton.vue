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
    default: 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800',
    danger: 'text-zinc-500 hover:text-red-400 hover:bg-red-950/40',
    success: 'text-zinc-500 hover:text-emerald-400 hover:bg-emerald-950/40',
    warning: 'text-zinc-500 hover:text-amber-400 hover:bg-amber-950/40',
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
