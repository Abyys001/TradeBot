<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useTheme } from '../composables/useTheme'

withDefaults(defineProps<{ variant?: 'inline' | 'menu-item' }>(), { variant: 'inline' })

const { t } = useI18n()
const { theme, toggle } = useTheme()
</script>

<template>
  <button
    v-if="variant === 'inline'"
    type="button"
    class="hidden h-7 w-7 items-center justify-center rounded border border-border text-fg-muted hover:text-fg sm:flex"
    :aria-label="t('theme.toggle')"
    :title="theme === 'dark' ? t('theme.switchToLight') : t('theme.switchToDark')"
    @click="toggle"
  >
    <svg v-if="theme === 'dark'" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="4" />
      <path stroke-linecap="round" d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
    <svg v-else class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  </button>

  <button
    v-else
    type="button"
    class="block w-full px-3 py-2 text-start text-xs text-fg-muted hover:bg-surface-muted"
    @click="toggle"
  >
    {{ theme === 'dark' ? t('theme.switchToLight') : t('theme.switchToDark') }}
  </button>
</template>
