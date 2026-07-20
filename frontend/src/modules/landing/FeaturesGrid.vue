<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const features = [
  { key: 'pine', icon: 'code' },
  { key: 'backtest', icon: 'chart' },
  { key: 'paper', icon: 'flask' },
  { key: 'live', icon: 'bolt' },
  { key: 'risk', icon: 'shield' },
  { key: 'optimizer', icon: 'sliders' },
  { key: 'copyTrading', icon: 'copy' },
  { key: 'telegram', icon: 'bell' },
  { key: 'security', icon: 'lock' },
] as const
</script>

<template>
  <section id="features" class="mx-auto max-w-6xl px-4 py-20 sm:px-6">
    <div class="text-center">
      <span class="inline-block rounded-full bg-accent-muted px-3 py-1 text-xs font-medium text-accent">{{ t('landing.nav.features') }}</span>
      <h2 class="mt-4 text-3xl font-bold tracking-tight text-fg sm:text-4xl">{{ t('landing.features.title') }}</h2>
      <p class="mx-auto mt-3 max-w-2xl text-lg text-fg-muted">{{ t('landing.features.subtitle') }}</p>
    </div>

    <div class="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="f in features"
        :key="f.key"
        class="feature-card group relative rounded-xl border border-border bg-surface-raised p-6 transition-all duration-300 hover:-translate-y-1 hover:border-accent/30 hover:shadow-lg hover:shadow-accent/5"
      >
        <!-- Accent top border on hover -->
        <div class="absolute inset-x-0 top-0 h-0.5 rounded-t-xl bg-gradient-to-r from-accent to-purple-400 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />

        <span class="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-accent/15 to-purple-500/10 text-accent transition-colors duration-300 group-hover:from-accent/20 group-hover:to-purple-500/15">
          <svg v-if="f.icon === 'code'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 8l-4 4 4 4M15 8l4 4-4 4" /></svg>
          <svg v-else-if="f.icon === 'chart'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M3 3v18h18M7 16l4-8 4 4 5-9" /></svg>
          <svg v-else-if="f.icon === 'flask'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 3h6M10 3v6l-5.5 9.5A1.5 1.5 0 0 0 5.8 21h12.4a1.5 1.5 0 0 0 1.3-2.5L14 9V3" /></svg>
          <svg v-else-if="f.icon === 'bolt'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" /></svg>
          <svg v-else-if="f.icon === 'shield'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3l8 3v6c0 4.5-3 7.5-8 9-5-1.5-8-4.5-8-9V6z" /></svg>
          <svg v-else-if="f.icon === 'sliders'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" d="M4 6h10M4 18h6M18 18h2M4 12h4" /><circle cx="16" cy="6" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="8" cy="18" r="2" /></svg>
          <svg v-else-if="f.icon === 'copy'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="8" width="12" height="12" rx="2" /><path stroke-linecap="round" d="M4 16V5a1 1 0 0 1 1-1h11" /></svg>
          <svg v-else-if="f.icon === 'bell'" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path stroke-linecap="round" d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
          <svg v-else class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="11" width="14" height="10" rx="2" /><path stroke-linecap="round" d="M8 11V7a4 4 0 1 1 8 0v4" /></svg>
        </span>
        <h3 class="mt-4 font-semibold text-fg">{{ t(`landing.features.${f.key}.title`) }}</h3>
        <p class="mt-2 text-sm leading-relaxed text-fg-muted">{{ t(`landing.features.${f.key}.desc`) }}</p>
      </div>
    </div>
  </section>
</template>
