<script setup lang="ts">
/** Renders one glyph from `utils/icons.ts`. See that file for why it is inline. */
const props = withDefaults(defineProps<{ name: IconName; size?: number | string }>(), {
  size: 18,
})
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="shrink-0"
  >
    <path :d="ICON_PATHS[props.name]" />
  </svg>
</template>
