<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ result: Record<string, number> | null }>()
const { t } = useI18n()
</script>

<template>
  <div v-if="result" class="grid grid-cols-3 gap-2 text-xs">
    <div class="rounded border border-border p-2">
      <div class="text-fg-muted">{{ t('optimizer.median') }}</div>
      <div class="text-fg">{{ result.median_final?.toFixed(2) }}</div>
    </div>
    <div class="rounded border border-border p-2">
      <div class="text-fg-muted">P5</div>
      <div class="text-negative">{{ result.p5_final?.toFixed(2) }}</div>
    </div>
    <div class="rounded border border-border p-2">
      <div class="text-fg-muted">P95</div>
      <div class="text-positive">{{ result.p95_final?.toFixed(2) }}</div>
    </div>
  </div>
</template>
