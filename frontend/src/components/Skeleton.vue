<script setup lang="ts">
defineProps<{ class?: string }>()
</script>

<template>
  <div class="animate-shimmer rounded-lg bg-surface-raised/80" :class="$props.class" />
</template>
