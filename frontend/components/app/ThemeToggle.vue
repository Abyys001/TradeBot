<script setup lang="ts">
const { isDark, toggle } = useTheme()
const { t } = useI18n()
</script>

<template>
  <button
    class="btn-quiet btn-sm"
    :title="isDark ? t('theme.toLight') : t('theme.toDark')"
    :aria-label="isDark ? t('theme.toLight') : t('theme.toDark')"
    @click="toggle"
  >
    <UiIcon :name="isDark ? 'sun' : 'moon'" :size="16" />
  </button>
</template>
