<script setup lang="ts">
/** A section's opener: eyebrow, title, optional body. Centered or start-aligned. */
withDefaults(
  defineProps<{
    eyebrow?: string
    title: string
    body?: string
    align?: 'start' | 'center'
  }>(),
  { align: 'start' },
)
</script>

<template>
  <div
    v-reveal
    class="max-w-2xl"
    :class="align === 'center' ? 'mx-auto text-center' : ''"
  >
    <p
      v-if="eyebrow"
      class="label mb-3 flex items-center gap-2"
      :class="align === 'center' ? 'justify-center' : ''"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-brand/70" />
      {{ eyebrow }}
    </p>
    <h2 class="display text-2xl sm:text-3xl tracking-tight">{{ title }}</h2>
    <p v-if="body" class="mt-3 text-sm sm:text-base text-ink-muted leading-relaxed">
      {{ body }}
    </p>
  </div>
</template>
