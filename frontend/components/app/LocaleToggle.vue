<script setup lang="ts">
/**
 * Two locales, so a toggle rather than a menu. Switching also flips the
 * document direction — see app.vue, which is what makes Persian a translation
 * pass rather than a rebuild.
 */
const { locale, locales, setLocale } = useI18n()

const other = computed(() =>
  (locales.value as { code: string; name: string }[]).find((l) => l.code !== locale.value),
)
</script>

<template>
  <button
    v-if="other"
    class="btn-quiet btn-sm text-xs font-medium"
    :title="other.name"
    @click="setLocale(other.code as any)"
  >
    {{ other.code === 'fa' ? 'فا' : 'EN' }}
  </button>
</template>
