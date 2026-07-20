<script setup lang="ts">
withDefaults(defineProps<{
  hover?: boolean
  padding?: 'none' | 'sm' | 'md' | 'lg'
}>(), {
  hover: false,
  padding: 'md',
})
</script>

<template>
  <div
    class="ui-card rounded-xl border border-border bg-surface-raised transition-all duration-200"
    :class="[
      hover ? 'hover:-translate-y-0.5 hover:shadow-md hover:border-border-hover cursor-pointer' : '',
      {
        'p-0': padding === 'none',
        'p-3': padding === 'sm',
        'p-5': padding === 'md',
        'p-7': padding === 'lg',
      },
    ]"
  >
    <slot />
  </div>
</template>
