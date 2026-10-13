<script setup lang="ts">
/**
 * A section that folds. Its body is not mounted until the first time it opens,
 * so a stacked page of heavy panels (each one fetching its own data) costs
 * only the ones the reader actually looks at.
 */
const open = defineModel<boolean>({ default: false })
defineProps<{ title: string; hint?: string }>()

const bodyId = useId()
const seen = ref(open.value)
watch(open, (value) => {
  if (value) seen.value = true
})
</script>

<template>
  <section class="min-w-0">
    <button
      type="button"
      class="w-full flex items-center gap-3 rounded-lg px-3 py-3 min-h-11 text-start
             bg-panel border border-line hover:bg-raised transition-colors
             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/70"
      :aria-expanded="open"
      :aria-controls="bodyId"
      @click="open = !open"
    >
      <span class="min-w-0 flex-1">
        <span class="text-sm font-medium block truncate">{{ title }}</span>
        <span v-if="hint" class="text-xs text-ink-muted block truncate mt-0.5">{{ hint }}</span>
      </span>
      <slot name="badge" />
      <UiIcon
        name="chevronDown"
        :size="16"
        class="text-ink-faint shrink-0 transition-transform"
        :class="open ? 'rotate-180' : ''"
      />
    </button>
    <div v-if="seen" v-show="open" :id="bodyId" class="pt-3">
      <slot />
    </div>
  </section>
</template>
