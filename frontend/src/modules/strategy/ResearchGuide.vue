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
  <div class="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6 space-y-4">
    <div>
      <h2 class="text-base font-semibold text-zinc-200">{{ t('strategies.researchTitle') }}</h2>
      <p class="text-sm text-zinc-500 mt-1">{{ t('strategies.researchSubtitle') }}</p>
    </div>

    <div class="grid gap-3 md:grid-cols-3">
      <div class="rounded-lg border border-zinc-800 p-4 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-zinc-400">1</span>
          <span
            class="text-xs rounded px-1.5 py-0.5"
            :class="hasData ? 'bg-emerald-900/50 text-emerald-400' : 'bg-zinc-800 text-zinc-500'"
          >
            {{ hasData ? '✓' : '—' }}
          </span>
        </div>
        <h3 class="text-sm font-medium text-zinc-200">{{ t('strategies.researchStep1') }}</h3>
        <p class="text-xs text-zinc-500">{{ t('strategies.researchStep1Hint') }}</p>
        <RouterLink
          to="/data"
          class="inline-block text-xs text-violet-400 hover:text-violet-300 underline"
        >
          {{ t('nav.data') }} →
        </RouterLink>
      </div>

      <div class="rounded-lg border border-zinc-800 p-4 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-zinc-400">2</span>
          <span
            class="text-xs rounded px-1.5 py-0.5"
            :class="hasStrategy ? 'bg-emerald-900/50 text-emerald-400' : 'bg-zinc-800 text-zinc-500'"
          >
            {{ hasStrategy ? '✓' : '—' }}
          </span>
        </div>
        <h3 class="text-sm font-medium text-zinc-200">{{ t('strategies.researchStep2') }}</h3>
        <p class="text-xs text-zinc-500">{{ t('strategies.researchStep2Hint') }}</p>
        <div class="flex gap-2">
          <button
            type="button"
            class="text-xs text-violet-400 hover:text-violet-300 underline"
            @click="emit('upload')"
          >
            {{ t('strategies.uploadPine') }}
          </button>
          <button
            type="button"
            class="text-xs text-violet-400 hover:text-violet-300 underline"
            @click="emit('create')"
          >
            {{ t('strategies.new') }}
          </button>
        </div>
      </div>

      <div class="rounded-lg border border-zinc-800 p-4 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-zinc-400">3</span>
          <span class="text-xs rounded px-1.5 py-0.5 bg-zinc-800 text-zinc-500">—</span>
        </div>
        <h3 class="text-sm font-medium text-zinc-200">{{ t('strategies.researchStep3') }}</h3>
        <p class="text-xs text-zinc-500">{{ t('strategies.researchStep3Hint') }}</p>
      </div>
    </div>
  </div>
</template>
