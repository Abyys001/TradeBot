<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ result: Record<string, number> | null }>()
const { t } = useI18n()
</script>

<template>
  <div v-if="result" class="grid grid-cols-3 gap-2 text-xs">
    <div class="rounded border border-zinc-800 p-2">
      <div class="text-zinc-500">{{ t('optimizer.median') }}</div>
      <div class="text-zinc-200">{{ result.median_final?.toFixed(2) }}</div>
    </div>
    <div class="rounded border border-zinc-800 p-2">
      <div class="text-zinc-500">P5</div>
      <div class="text-red-400">{{ result.p5_final?.toFixed(2) }}</div>
    </div>
    <div class="rounded border border-zinc-800 p-2">
      <div class="text-zinc-500">P95</div>
      <div class="text-emerald-400">{{ result.p95_final?.toFixed(2) }}</div>
    </div>
  </div>
</template>
