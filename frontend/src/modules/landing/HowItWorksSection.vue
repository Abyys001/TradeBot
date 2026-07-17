<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const steps = ['step1', 'step2', 'step3', 'step4', 'step5'] as const
</script>

<template>
  <section id="how-it-works" class="mx-auto max-w-4xl px-4 py-16 sm:px-6">
    <div class="text-center">
      <h2 class="text-2xl font-bold text-fg sm:text-3xl">{{ t('landing.howItWorks.title') }}</h2>
      <p class="mt-2 text-fg-muted">{{ t('landing.howItWorks.subtitle') }}</p>
    </div>

    <ol class="mt-10 space-y-4">
      <li
        v-for="(step, i) in steps"
        :key="step"
        class="flex gap-4 rounded-xl border border-border bg-surface-raised p-5"
      >
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-fg">
          {{ i + 1 }}
        </span>
        <div>
          <h3 class="font-semibold text-fg">{{ t(`landing.howItWorks.${step}.title`) }}</h3>
          <p class="mt-1 text-sm text-fg-muted">{{ t(`landing.howItWorks.${step}.desc`) }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>
