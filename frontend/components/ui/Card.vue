<script setup lang="ts">
/**
 * A titled surface. Every dashboard block is one of these, so the header
 * rhythm — label, optional hint, right-aligned actions — is defined once
 * instead of hand-rolled per panel and drifting by two pixels each time.
 */
withDefaults(
  defineProps<{
    title?: string
    hint?: string
    /** Removes the body padding for tables and charts that bleed to the edge. */
    flush?: boolean
    tone?: 'default' | 'signal' | 'ok'
  }>(),
  { tone: 'default' },
)

const slots = useSlots()
</script>

<template>
  <section
    class="panel flex flex-col min-w-0"
    :class="{
      'border-signal/40': tone === 'signal',
      'border-ok/40': tone === 'ok',
    }"
  >
    <header
      v-if="title || slots.header || slots.actions"
      class="flex items-center gap-3 px-4 py-3 border-b border-line min-w-0"
    >
      <div class="min-w-0">
        <h2 v-if="title" class="text-sm font-medium truncate">{{ title }}</h2>
        <p v-if="hint" class="text-xs text-ink-muted mt-0.5 truncate">{{ hint }}</p>
        <slot name="header" />
      </div>
      <div v-if="slots.actions" class="ms-auto flex items-center gap-2 shrink-0">
        <slot name="actions" />
      </div>
    </header>

    <div class="min-w-0 flex-1" :class="flush ? '' : 'p-4'">
      <slot />
    </div>

    <footer v-if="slots.footer" class="px-4 py-3 border-t border-line">
      <slot name="footer" />
    </footer>
  </section>
</template>
