<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const emit = defineEmits<{ create: []; upload: [] }>()

const { t } = useI18n()
</script>

<template>
  <div class="flex flex-col items-center text-center">
    <div
      class="mb-6 flex h-32 w-32 items-center justify-center rounded-2xl border border-border bg-surface-muted/50"
    >
      <svg class="h-20 w-20 text-violet-500/70" viewBox="0 0 80 80" fill="none">
        <rect x="8" y="44" width="8" height="20" rx="1" fill="currentColor" opacity="0.5" />
        <rect x="22" y="32" width="8" height="32" rx="1" fill="currentColor" opacity="0.7" />
        <rect x="36" y="24" width="8" height="40" rx="1" fill="currentColor" />
        <rect x="50" y="36" width="8" height="28" rx="1" fill="currentColor" opacity="0.6" />
        <rect x="64" y="28" width="8" height="36" rx="1" fill="currentColor" opacity="0.8" />
        <path
          d="M12 18 L28 18 L28 14 L36 22 L28 30 L28 26 L12 26 Z"
          fill="currentColor"
          opacity="0.4"
        />
      </svg>
    </div>

    <h2 class="text-lg font-semibold text-fg">{{ t('strategies.emptyTitle') }}</h2>
    <p class="mt-2 max-w-md text-sm text-fg-muted">{{ t('strategies.empty') }}</p>

    <button
      type="button"
      class="mt-6 rounded-xl bg-accent px-8 py-3 text-sm font-medium text-accent-fg shadow-lg shadow-violet-900/30 transition-colors hover:opacity-90"
      @click="emit('create')"
    >
      {{ t('strategies.createFirst') }}
    </button>

    <button
      type="button"
      class="mt-3 text-sm text-violet-400 transition-colors hover:text-violet-300"
      @click="emit('upload')"
    >
      {{ t('strategies.uploadPine') }}
    </button>
  </div>
</template>
