<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n()
</script>

<template>
  <section class="relative overflow-hidden px-4 pb-20 pt-16 sm:px-6 sm:pt-24">
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="hero-orb hero-orb-1" />
      <div class="hero-orb hero-orb-2" />
    </div>
    <div
      class="pointer-events-none absolute inset-0 opacity-[0.03]"
      style="background-image: linear-gradient(color-mix(in srgb, var(--tb-fg) 60%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--tb-fg) 60%, transparent) 1px, transparent 1px); background-size: 60px 60px;"
    />

    <div class="relative mx-auto max-w-3xl text-center">
      <span class="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-raised px-3 py-1 text-xs font-medium text-fg-muted">
        <span class="h-1.5 w-1.5 rounded-full bg-positive" />
        {{ t('landing.hero.badge') }}
      </span>

      <h1 class="mt-6 text-4xl font-bold tracking-tight text-fg sm:text-5xl">
        {{ t('landing.hero.title') }}
      </h1>

      <p class="mx-auto mt-5 max-w-2xl text-lg text-fg-muted">
        {{ t('landing.hero.subtitle') }}
      </p>

      <div class="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <RouterLink
          :to="{ name: 'login' }"
          class="w-full rounded-lg bg-accent px-6 py-3 text-sm font-medium text-accent-fg shadow-lg shadow-accent/20 hover:opacity-90 transition-opacity sm:w-auto"
        >
          {{ t('landing.hero.ctaLogin') }}
        </RouterLink>
        <a
          href="#request-access"
          class="w-full rounded-lg border border-border bg-surface-raised px-6 py-3 text-sm font-medium text-fg hover:bg-surface-muted transition-colors sm:w-auto"
        >
          {{ t('landing.hero.ctaRequestAccess') }}
        </a>
      </div>
    </div>
  </section>
</template>

<style scoped>
@keyframes heroOrbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -30px) scale(1.05); }
  66% { transform: translate(-20px, 20px) scale(0.95); }
}

.hero-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.18;
  animation: heroOrbFloat 22s ease-in-out infinite;
}

.hero-orb-1 {
  width: 480px;
  height: 480px;
  background: radial-gradient(circle, #8b5cf6, transparent 70%);
  top: -140px;
  inset-inline-end: -160px;
}

.hero-orb-2 {
  width: 380px;
  height: 380px;
  background: radial-gradient(circle, #6366f1, transparent 70%);
  bottom: -120px;
  inset-inline-start: -140px;
  animation-delay: -11s;
}
</style>
