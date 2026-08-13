<script setup lang="ts">
/**
 * Chrome for the pages a signed-out visitor can reach: the landing page, sign
 * in, and the risk calculator (which reads no account data — it only does
 * arithmetic on numbers you type).
 *
 * Deliberately not the app shell. A rail with four destinations that all
 * bounce to a login screen is worse than no rail.
 */
const { t } = useI18n()
const localePath = useLocalePath()
const auth = useAuthStore()
const route = useRoute()

const onLogin = computed(() => route.path === localePath('/login'))
</script>

<template>
  <div class="min-h-[100dvh] flex flex-col bg-base">
    <header class="sticky top-0 z-40 border-b border-line bg-base/85 backdrop-blur">
      <div class="max-w-6xl mx-auto h-14 flex items-center gap-3 px-4">
        <NuxtLink :to="localePath('/')" class="flex items-center gap-2.5 min-w-0">
          <span
            class="w-8 h-8 rounded-lg bg-brand-dim border border-brand/30 grid place-items-center text-brand shrink-0"
          >
            <UiIcon name="bolt" :size="16" />
          </span>
          <span class="display text-sm truncate">
            WalletManager<span class="text-ink-faint">/</span>CopyTrader
          </span>
        </NuxtLink>

        <nav class="ms-auto flex items-center gap-1 sm:gap-2">
          <NuxtLink :to="localePath('/risk')" class="btn-quiet btn-sm hidden xs:inline-flex">
            {{ t('nav.risk') }}
          </NuxtLink>
          <AppThemeToggle />
          <AppLocaleToggle />
          <NuxtLink
            v-if="auth.authenticated"
            :to="localePath('/dashboard')"
            class="btn-primary btn-sm"
          >
            {{ t('nav.dashboard') }}
          </NuxtLink>
          <NuxtLink v-else-if="!onLogin" :to="localePath('/login')" class="btn-primary btn-sm">
            {{ t('nav.signIn') }}
          </NuxtLink>
        </nav>
      </div>
    </header>

    <main class="flex-1">
      <slot />
    </main>

    <footer class="border-t border-line mt-auto">
      <div
        class="max-w-6xl mx-auto px-4 py-6 flex flex-col sm:flex-row gap-3 sm:items-center
               text-xs text-ink-faint"
      >
        <p>{{ t('landing.footerNote') }}</p>
        <NuxtLink :to="localePath('/risk')" class="sm:ms-auto hover:text-ink transition-colors">
          {{ t('landing.cta.risk') }} →
        </NuxtLink>
      </div>
    </footer>
  </div>
</template>
