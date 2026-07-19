<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const points = ['point1', 'point2', 'point3', 'point4'] as const
</script>

<template>
  <section id="security" class="bg-surface-muted/50 py-20">
    <div class="mx-auto max-w-5xl px-4 sm:px-6">
      <div class="text-center">
        <span class="inline-block rounded-full bg-success-bg px-3 py-1 text-xs font-medium text-positive">{{ t('landing.nav.security') }}</span>
        <h2 class="mt-4 text-3xl font-bold tracking-tight text-fg sm:text-4xl">{{ t('landing.security.title') }}</h2>
        <p class="mx-auto mt-3 max-w-2xl text-lg text-fg-muted">{{ t('landing.security.subtitle') }}</p>
      </div>

      <div class="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div
          v-for="p in points"
          :key="p"
          class="security-card group flex gap-4 rounded-xl border border-border bg-surface-raised p-6 transition-all duration-300 hover:-translate-y-0.5 hover:border-positive/20 hover:shadow-md"
        >
          <span class="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-success-bg to-success-bg text-positive transition-transform duration-300 group-hover:scale-110">
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </span>
          <div>
            <h3 class="font-semibold text-fg">{{ t(`landing.security.${p}.title`) }}</h3>
            <p class="mt-1.5 text-sm leading-relaxed text-fg-muted">{{ t(`landing.security.${p}.desc`) }}</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
