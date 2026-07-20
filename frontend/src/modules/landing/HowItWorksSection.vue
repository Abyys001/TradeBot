<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const steps = ['step1', 'step2', 'step3', 'step4', 'step5'] as const
</script>

<template>
  <section id="how-it-works" class="mx-auto max-w-4xl px-4 py-20 sm:px-6">
    <div class="text-center">
      <span class="inline-block rounded-full bg-accent-muted px-3 py-1 text-xs font-medium text-accent">{{ t('landing.nav.howItWorks') }}</span>
      <h2 class="mt-4 text-3xl font-bold tracking-tight text-fg sm:text-4xl">{{ t('landing.howItWorks.title') }}</h2>
      <p class="mx-auto mt-3 max-w-2xl text-lg text-fg-muted">{{ t('landing.howItWorks.subtitle') }}</p>
    </div>

    <div class="relative mt-12">
      <!-- Connecting line -->
      <div class="absolute start-5 top-0 bottom-0 w-px bg-gradient-to-b from-accent/40 via-accent/20 to-transparent sm:start-1/2 sm:-translate-x-px" />

      <div class="space-y-8">
        <div
          v-for="(step, i) in steps"
          :key="step"
          class="step-card group relative flex gap-5 sm:gap-8"
          :class="i % 2 === 0 ? 'sm:flex-row' : 'sm:flex-row-reverse'"
        >
          <!-- Content -->
          <div class="flex-1 sm:w-1/2" :class="i % 2 === 0 ? 'sm:text-end' : 'sm:text-start'">
            <div class="rounded-xl border border-border bg-surface-raised p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-accent/20 hover:shadow-md hover:shadow-accent/5 sm:p-6">
              <h3 class="font-semibold text-fg">{{ t(`landing.howItWorks.${step}.title`) }}</h3>
              <p class="mt-2 text-sm leading-relaxed text-fg-muted">{{ t(`landing.howItWorks.${step}.desc`) }}</p>
            </div>
          </div>

          <!-- Step number circle -->
          <div class="relative z-10 flex shrink-0 items-start">
            <span class="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-accent to-purple-500 text-sm font-bold text-white shadow-lg shadow-accent/25 ring-4 ring-surface">
              {{ i + 1 }}
            </span>
          </div>

          <!-- Spacer for alternating layout -->
          <div class="hidden flex-1 sm:block sm:w-1/2" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
@media (max-width: 639px) {
  .step-card {
    padding-inline-start: 3.5rem;
  }
}
</style>
