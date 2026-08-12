<script setup lang="ts">
/**
 * The empty state.
 *
 * An empty panel that just says "no data" teaches nothing. Each of these says
 * what would fill it and offers the action that starts it, because on a fresh
 * install every single panel is empty at once and that is the moment the admin
 * decides whether the thing works.
 */
defineProps<{ icon?: IconName; title: string; body?: string }>()
</script>

<template>
  <div class="flex flex-col items-center text-center gap-3 py-10 px-4">
    <div
      v-if="icon"
      class="w-10 h-10 rounded-full grid place-items-center bg-raised border border-line text-ink-faint"
    >
      <UiIcon :name="icon" :size="18" />
    </div>
    <div>
      <p class="text-sm font-medium">{{ title }}</p>
      <p v-if="body" class="text-xs text-ink-muted mt-1 max-w-sm leading-relaxed">{{ body }}</p>
    </div>
    <slot />
  </div>
</template>
