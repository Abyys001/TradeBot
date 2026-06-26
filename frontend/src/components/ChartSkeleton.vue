<script setup lang="ts">
import Skeleton from './Skeleton.vue'
</script>

<template>
  <div class="flex h-full w-full flex-col gap-3 p-6">
    <div class="flex gap-2">
      <Skeleton class="h-4 w-24" />
      <Skeleton class="h-4 w-16" />
      <Skeleton class="h-4 w-20" />
    </div>
    <Skeleton class="min-h-0 flex-1" />
    <div class="flex gap-2">
      <Skeleton class="h-3 w-full max-w-[60%]" />
      <Skeleton class="h-3 w-16" />
    </div>
  </div>
</template>
