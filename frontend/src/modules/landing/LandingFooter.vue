<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import ThemeToggle from '../../components/ThemeToggle.vue'
import LanguageToggle from '../../components/LanguageToggle.vue'

const { t } = useI18n()
const year = computed(() => new Date().getFullYear())

const links = [
  { href: '#features', label: () => t('landing.nav.features') },
  { href: '#performance', label: () => t('landing.nav.performance') },
  { href: '#how-it-works', label: () => t('landing.nav.howItWorks') },
  { href: '#security', label: () => t('landing.nav.security') },
]
</script>

<template>
  <footer class="border-t border-border/60 bg-surface-muted/30">
    <div class="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <div class="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
        <div class="max-w-sm">
          <RouterLink :to="{ name: 'landing' }" class="flex items-center gap-2.5 font-semibold text-fg transition-opacity hover:opacity-80">
            <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-accent shadow-sm shadow-accent/20">
              <svg viewBox="0 0 24 24" class="h-4 w-4 text-accent-fg" fill="none" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" d="M3 17l6-6 4 4 8-8" />
                <path stroke-linecap="round" d="M15 7h6v6" />
              </svg>
            </span>
            <span>{{ t('app.title') }}</span>
          </RouterLink>
          <p class="mt-3 text-sm leading-relaxed text-fg-muted">{{ t('landing.footer.tagline') }}</p>
        </div>

        <div class="flex gap-10">
          <div class="flex flex-col gap-2.5 text-sm">
            <a
              v-for="link in links"
              :key="link.href"
              :href="link.href"
              class="text-fg-muted transition-colors hover:text-fg"
            >
              {{ link.label() }}
            </a>
          </div>

          <div class="flex items-start gap-2">
            <ThemeToggle />
            <LanguageToggle />
          </div>
        </div>
      </div>

      <div class="mt-10 flex flex-col gap-2 border-t border-border/60 pt-6 text-xs text-fg-muted sm:flex-row sm:items-center sm:justify-between">
        <p>{{ t('landing.footer.rights', { year }) }}</p>
        <p class="text-fg-muted/60">{{ t('landing.footer.disclaimer') }}</p>
      </div>
    </div>
  </footer>
</template>
