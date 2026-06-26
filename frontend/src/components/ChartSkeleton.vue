<script setup lang="ts">
<<<<<<< HEAD
import SkeletonBlock from './SkeletonBlock.vue'
</script>

<template>
  <div class="absolute inset-0 z-10 flex flex-col gap-3 bg-zinc-950/80 p-4 backdrop-blur-[1px]">
    <SkeletonBlock class="h-8 w-32" />
    <SkeletonBlock class="flex-1 w-full" />
    <div class="flex gap-2">
      <SkeletonBlock class="h-6 w-20" />
      <SkeletonBlock class="h-6 w-20" />
      <SkeletonBlock class="h-6 w-20" />
=======
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
>>>>>>> 1af07065fe5a87dc8ca34e162c3bf176e3907b0c
    </div>
  </div>
</template>
