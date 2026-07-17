<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ThemeToggle from '../../components/ThemeToggle.vue'
import LanguageToggle from '../../components/LanguageToggle.vue'

const { t } = useI18n()
const year = computed(() => new Date().getFullYear())
</script>

<template>
  <footer class="border-t border-border">
    <div class="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div class="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        <div class="max-w-sm">
          <div class="font-semibold text-fg">{{ t('app.title') }}</div>
          <p class="mt-2 text-sm text-fg-muted">{{ t('landing.footer.tagline') }}</p>
        </div>

        <div class="flex gap-8 text-sm">
          <div class="flex flex-col gap-2 text-fg-muted">
            <a href="#features" class="hover:text-fg">{{ t('landing.nav.features') }}</a>
            <a href="#performance" class="hover:text-fg">{{ t('landing.nav.performance') }}</a>
            <a href="#how-it-works" class="hover:text-fg">{{ t('landing.nav.howItWorks') }}</a>
            <a href="#security" class="hover:text-fg">{{ t('landing.nav.security') }}</a>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <ThemeToggle />
          <LanguageToggle />
        </div>
      </div>

      <div class="mt-8 flex flex-col gap-2 border-t border-border pt-6 text-xs text-fg-muted sm:flex-row sm:items-center sm:justify-between">
        <p>{{ t('landing.footer.rights', { year }) }}</p>
        <p>{{ t('landing.footer.disclaimer') }}</p>
      </div>
    </div>
  </footer>
</template>
