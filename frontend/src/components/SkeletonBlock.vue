<script setup lang="ts">
defineProps<{
  class?: string
}>()
</script>

<template>
  <div
    class="animate-pulse rounded-lg bg-zinc-800/80"
    :class="$props.class"
  />
</template>
