<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import ThemeToggle from '../../components/ThemeToggle.vue'
import LanguageToggle from '../../components/LanguageToggle.vue'

const { t } = useI18n()
const menuOpen = ref(false)

const links = [
  { href: '#features', label: () => t('landing.nav.features') },
  { href: '#performance', label: () => t('landing.nav.performance') },
  { href: '#how-it-works', label: () => t('landing.nav.howItWorks') },
  { href: '#security', label: () => t('landing.nav.security') },
]
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-border bg-surface/80 backdrop-blur-md">
    <nav class="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
      <RouterLink :to="{ name: 'landing' }" class="flex shrink-0 items-center gap-2 font-semibold text-fg">
        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-fg">
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" d="M3 17l6-6 4 4 8-8" />
            <path stroke-linecap="round" d="M15 7h6v6" />
          </svg>
        </span>
        <span>{{ t('app.title') }}</span>
      </RouterLink>

      <div class="hidden items-center gap-6 text-sm text-fg-muted md:flex">
        <a v-for="link in links" :key="link.href" :href="link.href" class="hover:text-fg transition-colors">
          {{ link.label() }}
        </a>
      </div>

      <div class="ms-auto hidden items-center gap-2 md:flex">
        <ThemeToggle />
        <LanguageToggle />
        <RouterLink
          :to="{ name: 'login' }"
          class="rounded-lg border border-border px-3 py-1.5 text-sm text-fg hover:bg-surface-raised transition-colors"
        >
          {{ t('landing.nav.login') }}
        </RouterLink>
        <a
          href="#request-access"
          class="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:opacity-90 transition-opacity"
        >
          {{ t('landing.nav.requestAccess') }}
        </a>
      </div>

      <button
        type="button"
        class="ms-auto flex h-9 w-9 items-center justify-center rounded-lg text-fg-muted hover:bg-surface-raised md:hidden"
        :aria-label="t('nav.openMenu')"
        @click="menuOpen = !menuOpen"
      >
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
    </nav>

    <div v-if="menuOpen" class="border-t border-border bg-surface px-4 py-3 md:hidden">
      <div class="flex flex-col gap-3 text-sm">
        <a v-for="link in links" :key="link.href" :href="link.href" class="text-fg-muted hover:text-fg" @click="menuOpen = false">
          {{ link.label() }}
        </a>
        <div class="flex items-center gap-2 pt-2">
          <ThemeToggle />
          <LanguageToggle />
        </div>
        <RouterLink :to="{ name: 'login' }" class="rounded-lg border border-border px-3 py-2 text-center text-fg">
          {{ t('landing.nav.login') }}
        </RouterLink>
        <a href="#request-access" class="rounded-lg bg-accent px-3 py-2 text-center font-medium text-accent-fg" @click="menuOpen = false">
          {{ t('landing.nav.requestAccess') }}
        </a>
      </div>
    </div>
  </header>
</template>
