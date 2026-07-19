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
  <header class="fixed inset-x-0 top-0 z-40 border-b border-border/40 bg-surface-overlay backdrop-blur-xl">
    <nav class="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
      <RouterLink :to="{ name: 'landing' }" class="flex shrink-0 items-center gap-2.5 font-semibold text-fg transition-opacity hover:opacity-80">
        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-accent shadow-sm shadow-accent/20">
          <svg viewBox="0 0 24 24" class="h-4 w-4 text-accent-fg" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" d="M3 17l6-6 4 4 8-8" />
            <path stroke-linecap="round" d="M15 7h6v6" />
          </svg>
        </span>
        <span>{{ t('app.title') }}</span>
      </RouterLink>

      <div class="hidden items-center gap-1 text-sm text-fg-muted md:flex">
        <a
          v-for="link in links"
          :key="link.href"
          :href="link.href"
          class="rounded-lg px-3 py-1.5 transition-colors hover:bg-surface-muted hover:text-fg"
        >
          {{ link.label() }}
        </a>
      </div>

      <div class="ms-auto hidden items-center gap-2 md:flex">
        <ThemeToggle />
        <LanguageToggle />
        <div class="ms-1 h-5 w-px bg-border" />
        <RouterLink
          :to="{ name: 'login' }"
          class="rounded-lg px-3 py-1.5 text-sm text-fg-muted transition-colors hover:bg-surface-muted hover:text-fg"
        >
          {{ t('landing.nav.login') }}
        </RouterLink>
        <RouterLink
          :to="{ name: 'login' }"
          class="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg shadow-sm shadow-accent/20 transition-all duration-200 hover:bg-accent-hover hover:shadow-md hover:shadow-accent/25"
        >
          {{ t('landing.nav.requestAccess') }}
        </RouterLink>
      </div>

      <button
        type="button"
        class="ms-auto flex h-9 w-9 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-surface-muted hover:text-fg md:hidden"
        :aria-label="t('nav.openMenu')"
        @click="menuOpen = !menuOpen"
      >
        <svg v-if="!menuOpen" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
        <svg v-else class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </nav>

    <!-- Mobile menu -->
    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0 -translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-2"
    >
      <div v-if="menuOpen" class="border-t border-border/40 bg-surface-overlay backdrop-blur-xl px-4 py-4 md:hidden">
        <div class="flex flex-col gap-1 text-sm">
          <a
            v-for="link in links"
            :key="link.href"
            :href="link.href"
            class="rounded-lg px-3 py-2.5 text-fg-muted transition-colors hover:bg-surface-muted hover:text-fg"
            @click="menuOpen = false"
          >
            {{ link.label() }}
          </a>
          <div class="my-2 h-px bg-border/50" />
          <div class="flex items-center gap-2 px-3 py-2">
            <ThemeToggle />
            <LanguageToggle />
          </div>
          <RouterLink
            :to="{ name: 'login' }"
            class="rounded-lg border border-border px-3 py-2.5 text-center text-fg transition-colors hover:bg-surface-muted"
          >
            {{ t('landing.nav.login') }}
          </RouterLink>
          <a
            href="#request-access"
            class="rounded-lg bg-accent px-3 py-2.5 text-center font-medium text-accent-fg shadow-sm shadow-accent/20"
            @click="menuOpen = false"
          >
            {{ t('landing.nav.requestAccess') }}
          </a>
        </div>
      </div>
    </Transition>
  </header>
</template>
