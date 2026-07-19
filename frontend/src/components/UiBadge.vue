<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info'
  size?: 'sm' | 'md'
}>(), {
  variant: 'default',
  size: 'sm',
})
</script>

<template>
  <span
    class="ui-badge inline-flex items-center gap-1 font-medium"
    :class="[
      {
        'bg-surface-muted text-fg-muted': variant === 'default',
        'bg-success-bg text-positive': variant === 'success',
        'bg-warning-bg text-warning': variant === 'warning',
        'bg-danger-bg text-negative': variant === 'danger',
        'bg-info-bg text-info': variant === 'info',
      },
      {
        'rounded-md px-1.5 py-0.5 text-[10px]': size === 'sm',
        'rounded-lg px-2.5 py-1 text-xs': size === 'md',
      },
    ]"
  >
    <slot />
  </span>
</template>
