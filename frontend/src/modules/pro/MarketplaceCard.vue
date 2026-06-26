<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MarketplacePackage } from '../../stores/pro'

defineProps<{ pkg: MarketplacePackage }>()
const emit = defineEmits<{ import: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="rounded-xl border border-zinc-800 p-4 space-y-2">
    <h3 class="text-sm font-medium text-zinc-200">{{ pkg.name }}</h3>
    <p class="text-xs text-zinc-500">{{ pkg.description || t('marketplace.noDescription') }}</p>
    <button
      type="button"
      class="text-xs text-violet-400 hover:underline"
      @click="emit('import')"
    >
      {{ t('marketplace.import') }}
    </button>
  </div>
</template>
