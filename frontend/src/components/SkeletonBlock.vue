<script setup lang="ts">
defineProps<{
  class?: string
}>()
</script>

<template>
  <div
    class="animate-pulse rounded-lg bg-surface-raised/80"
    :class="$props.class"
  />
</template>
