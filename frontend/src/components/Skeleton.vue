<script setup lang="ts">
defineProps<{ class?: string }>()
</script>

<template>
  <div class="animate-shimmer rounded-lg bg-zinc-800/80" :class="$props.class" />
</template>
