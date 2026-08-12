<script setup lang="ts">
/**
 * Sets lang, dir and the colour theme on <html>.
 *
 * @nuxtjs/i18n knows each locale's direction but does not write it to the
 * document on its own, so without this the Persian build renders RTL text in
 * an LTR document: punctuation lands on the wrong side and the layout never
 * mirrors. Doing it here means Persian is a translation pass, not a rebuild.
 *
 * The theme is applied the same way, from a cookie, so it is already correct in
 * the server-rendered HTML — set after hydration it would flash a white page.
 */
const { locale, locales, t } = useI18n()
const { theme } = useTheme()

const direction = computed<'ltr' | 'rtl'>(() =>
  (locales.value as { code: string; dir?: string }[]).find((l) => l.code === locale.value)?.dir ===
  'rtl'
    ? 'rtl'
    : 'ltr',
)

useHead({
  htmlAttrs: {
    lang: () => locale.value,
    dir: () => direction.value,
    'data-theme': () => theme.value,
  },
  titleTemplate: (page) => (page ? `${page} · WalletManager` : 'WalletManager CopyTrader'),
  meta: [
    // Colours the browser chrome on mobile; a light bar over a black panel is
    // the most visible seam there is.
    { name: 'theme-color', content: () => (theme.value === 'light' ? '#f6f7fa' : '#07090c') },
    { name: 'description', content: () => t('landing.lede') },
  ],
})
</script>

<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>
