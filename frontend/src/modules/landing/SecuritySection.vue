<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const points = ['point1', 'point2', 'point3', 'point4'] as const
</script>

<template>
  <section id="security" class="bg-surface-muted/50 py-16">
    <div class="mx-auto max-w-5xl px-4 sm:px-6">
      <div class="text-center">
        <h2 class="text-2xl font-bold text-fg sm:text-3xl">{{ t('landing.security.title') }}</h2>
        <p class="mt-2 text-fg-muted">{{ t('landing.security.subtitle') }}</p>
      </div>

      <div class="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div v-for="p in points" :key="p" class="flex gap-3 rounded-xl border border-border bg-surface p-5">
          <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-success-bg text-positive">
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </span>
          <div>
            <h3 class="font-semibold text-fg">{{ t(`landing.security.${p}.title`) }}</h3>
            <p class="mt-1 text-sm text-fg-muted">{{ t(`landing.security.${p}.desc`) }}</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
