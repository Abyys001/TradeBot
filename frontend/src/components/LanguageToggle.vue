<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { setLocale } from '../i18n'

withDefaults(defineProps<{ variant?: 'inline' | 'menu-item' }>(), { variant: 'inline' })
const emit = defineEmits<{ (e: 'change'): void }>()

const { locale } = useI18n()

function toggleLocale() {
  setLocale(locale.value === 'en' ? 'fa' : 'en')
  emit('change')
}
</script>

<template>
  <button
    v-if="variant === 'inline'"
    type="button"
    class="hidden rounded px-2 py-1 text-xs text-fg-muted hover:text-fg border border-border sm:block"
    @click="toggleLocale"
  >
    {{ locale === 'en' ? 'FA' : 'EN' }}
  </button>

  <button
    v-else
    type="button"
    class="block w-full px-3 py-2 text-start text-xs text-fg-muted hover:bg-surface-muted"
    @click="toggleLocale"
  >
    {{ locale === 'en' ? 'فارسی' : 'English' }}
  </button>
</template>
