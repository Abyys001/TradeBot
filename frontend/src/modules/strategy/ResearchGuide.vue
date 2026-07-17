<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useHistoryStore } from '../../stores/history'
import { useStrategyStore } from '../../stores/strategy'

const emit = defineEmits<{ upload: []; create: [] }>()

const { t } = useI18n()
const history = useHistoryStore()
const strategies = useStrategyStore()

onMounted(() => {
  void history.fetchDatasets()
})

const hasData = computed(() => history.datasets.length > 0)
const hasStrategy = computed(() => strategies.strategies.length > 0)
</script>

<template>
  <div class="rounded-xl border border-border bg-surface-muted/30 p-6 space-y-4">
    <div>
      <h2 class="text-base font-semibold text-fg">{{ t('strategies.researchTitle') }}</h2>
      <p class="text-sm text-fg-muted mt-1">{{ t('strategies.researchSubtitle') }}</p>
    </div>

    <div class="grid gap-3 md:grid-cols-3">
      <div class="rounded-lg border border-border p-4 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-fg-muted">1</span>
          <span
            class="text-xs rounded px-1.5 py-0.5"
            :class="hasData ? 'bg-success-bg text-positive' : 'bg-surface-raised text-fg-muted'"
          >
            {{ hasData ? '✓' : '—' }}
          </span>
        </div>
        <h3 class="text-sm font-medium text-fg">{{ t('strategies.researchStep1') }}</h3>
        <p class="text-xs text-fg-muted">{{ t('strategies.researchStep1Hint') }}</p>
        <RouterLink
          to="/data"
          class="inline-block text-xs text-accent hover:text-accent underline"
        >
          {{ t('nav.data') }} →
        </RouterLink>
      </div>

      <div class="rounded-lg border border-border p-4 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-fg-muted">2</span>
          <span
            class="text-xs rounded px-1.5 py-0.5"
            :class="hasStrategy ? 'bg-success-bg text-positive' : 'bg-surface-raised text-fg-muted'"
          >
            {{ hasStrategy ? '✓' : '—' }}
          </span>
        </div>
        <h3 class="text-sm font-medium text-fg">{{ t('strategies.researchStep2') }}</h3>
        <p class="text-xs text-fg-muted">{{ t('strategies.researchStep2Hint') }}</p>
        <div class="flex gap-2">
          <button
            type="button"
            class="text-xs text-accent hover:text-accent underline"
            @click="emit('upload')"
          >
            {{ t('strategies.uploadPine') }}
          </button>
          <button
            type="button"
            class="text-xs text-accent hover:text-accent underline"
            @click="emit('create')"
          >
            {{ t('strategies.new') }}
          </button>
        </div>
      </div>

      <div class="rounded-lg border border-border p-4 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-fg-muted">3</span>
          <span class="text-xs rounded px-1.5 py-0.5 bg-surface-raised text-fg-muted">—</span>
        </div>
        <h3 class="text-sm font-medium text-fg">{{ t('strategies.researchStep3') }}</h3>
        <p class="text-xs text-fg-muted">{{ t('strategies.researchStep3Hint') }}</p>
      </div>
    </div>
  </div>
</template>
