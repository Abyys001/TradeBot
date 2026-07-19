<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  type: 'button',
})
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    class="ui-button inline-flex items-center justify-center gap-2 font-medium transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50"
    :class="[
      {
        'bg-accent text-accent-fg shadow-md shadow-accent/20 hover:bg-accent-hover hover:shadow-glow hover:-translate-y-0.5 active:translate-y-0 active:shadow-md': variant === 'primary',
        'border border-border bg-surface-raised text-fg hover:bg-surface-muted hover:border-border-hover hover:shadow-sm hover:-translate-y-0.5 active:translate-y-0': variant === 'secondary',
        'text-fg-muted hover:bg-surface-muted hover:text-fg': variant === 'ghost',
        'bg-negative/10 text-negative border border-negative/20 hover:bg-negative/20 hover:-translate-y-0.5 active:translate-y-0': variant === 'danger',
      },
      {
        'rounded-md px-2.5 py-1 text-xs': size === 'sm',
        'rounded-lg px-4 py-2 text-sm': size === 'md',
        'rounded-lg px-6 py-2.5 text-sm': size === 'lg',
      },
    ]"
  >
    <svg v-if="loading" class="animate-spin -ms-0.5 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
    <slot />
  </button>
</template>
