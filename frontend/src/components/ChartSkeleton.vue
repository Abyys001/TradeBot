<script setup lang="ts">
import SkeletonBlock from './SkeletonBlock.vue'
</script>

<template>
  <div class="absolute inset-0 z-10 flex flex-col gap-3 bg-surface/80 p-4 backdrop-blur-[1px]">
    <SkeletonBlock class="h-8 w-32" />
    <SkeletonBlock class="flex-1 w-full" />
    <div class="flex gap-2">
      <SkeletonBlock class="h-6 w-20" />
      <SkeletonBlock class="h-6 w-20" />
      <SkeletonBlock class="h-6 w-20" />
    </div>
  </div>
</template>
