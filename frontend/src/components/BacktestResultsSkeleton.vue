<script setup lang="ts">
import Skeleton from './Skeleton.vue'

withDefaults(
  defineProps<{
    compact?: boolean
    showChart?: boolean
    showTable?: boolean
  }>(),
  {
    compact: false,
    showChart: true,
    showTable: true,
  },
)
</script>

<template>
  <div class="space-y-3" :class="compact ? 'scale-95 origin-top' : 'space-y-4'">
    <div class="grid grid-cols-2 gap-2" :class="compact ? '' : 'gap-3 sm:grid-cols-4'">
      <div
        v-for="i in 4"
        :key="i"
        class="rounded-xl border border-border bg-surface-muted/40 p-3"
        :class="compact ? 'px-2 py-2' : 'px-4 py-3'"
      >
        <Skeleton class="mb-2 h-3 w-16" />
        <Skeleton :class="compact ? 'h-5 w-12' : 'h-7 w-16'" />
      </div>
    </div>

    <div v-if="showChart">
      <Skeleton v-if="!compact" class="mb-2 h-3 w-24" />
      <Skeleton :class="compact ? 'h-16' : 'h-[200px]'" />
    </div>

    <div v-if="showTable && !compact" class="overflow-hidden rounded-lg border border-border">
      <Skeleton class="h-8 rounded-none" />
      <div class="space-y-2 p-3">
        <Skeleton v-for="i in 4" :key="i" class="h-4 w-full" />
      </div>
    </div>
  </div>
</template>
