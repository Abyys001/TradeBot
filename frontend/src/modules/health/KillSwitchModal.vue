<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const emit = defineEmits<{ close: []; confirm: [] }>()
const { t } = useI18n()
const confirmText = ref('')

function submit() {
  if (confirmText.value === 'CONFIRM') emit('confirm')
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
    <div class="w-full max-w-md rounded-xl border border-negative/40 bg-surface-muted p-6 shadow-2xl">
      <h2 class="text-lg font-bold text-negative mb-2">{{ t('health.killConfirmTitle') }}</h2>
      <p class="text-sm text-fg-muted mb-4">{{ t('health.killConfirmBody') }}</p>
      <label class="block text-xs text-fg-muted mb-1">{{ t('health.killConfirmType') }}</label>
      <input
        v-model="confirmText"
        type="text"
        class="w-full mb-4 rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm focus:border-negative focus:outline-none"
      />
      <div class="flex gap-3 justify-end">
        <button
          type="button"
          class="rounded-lg px-4 py-2 text-sm text-fg-muted hover:text-fg"
          @click="emit('close')"
        >
          {{ t('health.cancel') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-40"
          :disabled="confirmText !== 'CONFIRM'"
          @click="submit"
        >
          {{ t('health.confirm') }}
        </button>
      </div>
    </div>
  </div>
</template>
