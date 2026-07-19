<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n()
</script>

<template>
  <section class="relative overflow-hidden px-4 pb-24 pt-20 sm:px-6 sm:pt-32 lg:pt-40">
    <!-- Background orbs -->
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="hero-orb hero-orb-1" />
      <div class="hero-orb hero-orb-2" />
      <div class="hero-orb hero-orb-3" />
    </div>

    <!-- Grid overlay -->
    <div
      class="pointer-events-none absolute inset-0 opacity-[0.025]"
      style="background-image: linear-gradient(color-mix(in srgb, var(--tb-fg) 60%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--tb-fg) 60%, transparent) 1px, transparent 1px); background-size: 64px 64px;"
    />

    <!-- Radial fade at bottom -->
    <div class="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-surface to-transparent" />

    <div class="relative mx-auto max-w-4xl text-center">
      <!-- Badge -->
      <div class="hero-animate inline-flex items-center gap-2 rounded-full border border-border/60 bg-surface-overlay px-4 py-1.5 text-xs font-medium text-fg-muted backdrop-blur-sm" style="animation-delay: 0ms">
        <span class="relative flex h-2 w-2">
          <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive opacity-75" />
          <span class="relative inline-flex h-2 w-2 rounded-full bg-positive" />
        </span>
        {{ t('landing.hero.badge') }}
      </div>

      <!-- Headline -->
      <h1 class="hero-animate mt-7 text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl" style="animation-delay: 80ms">
        <span class="text-fg">{{ t('landing.hero.title').split(',').slice(0, -1).join(',') }},</span>
        <br class="hidden sm:block" />
        <span class="mt-1 inline-block bg-gradient-to-r from-accent via-purple-400 to-indigo-500 bg-clip-text text-transparent sm:mt-2">
          {{ t('landing.hero.title').split(',').pop() }}
        </span>
      </h1>

      <!-- Subtitle -->
      <p class="hero-animate mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-fg-muted sm:text-xl" style="animation-delay: 160ms">
        {{ t('landing.hero.subtitle') }}
      </p>

      <!-- CTAs -->
      <div class="hero-animate mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-4" style="animation-delay: 240ms">
        <RouterLink
          :to="{ name: 'login' }"
          class="group relative w-full overflow-hidden rounded-xl bg-accent px-7 py-3 text-sm font-semibold text-accent-fg shadow-lg shadow-accent/25 transition-all duration-300 hover:shadow-glow hover:-translate-y-0.5 sm:w-auto"
        >
          <span class="relative z-10">{{ t('landing.hero.ctaLogin') }}</span>
          <span class="absolute inset-0 bg-gradient-to-r from-accent-hover to-accent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        </RouterLink>
        <a
          href="#request-access"
          class="group w-full rounded-xl border border-border bg-surface-raised/80 px-7 py-3 text-sm font-semibold text-fg backdrop-blur-sm transition-all duration-300 hover:border-border-hover hover:bg-surface-muted hover:shadow-sm hover:-translate-y-0.5 sm:w-auto"
        >
          {{ t('landing.hero.ctaRequestAccess') }}
        </a>
      </div>

      <!-- Trust indicators -->
      <div class="hero-animate mt-12 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-fg-muted" style="animation-delay: 320ms">
        <span class="flex items-center gap-1.5">
          <svg class="h-3.5 w-3.5 text-positive" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
          {{ t('landing.features.security.title') }}
        </span>
        <span class="flex items-center gap-1.5">
          <svg class="h-3.5 w-3.5 text-positive" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
          Hyperliquid
        </span>
        <span class="flex items-center gap-1.5">
          <svg class="h-3.5 w-3.5 text-positive" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
          Pine Script v5
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero-animate {
  animation: heroFadeUp 0.7s ease-out both;
}

@keyframes heroFadeUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes heroOrbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(40px, -40px) scale(1.08); }
  66% { transform: translate(-30px, 30px) scale(0.92); }
}

.hero-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.15;
  animation: heroOrbFloat 24s ease-in-out infinite;
}

[data-theme="dark"] .hero-orb {
  opacity: 0.18;
}

.hero-orb-1 {
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, var(--tb-accent), transparent 70%);
  top: -200px;
  inset-inline-end: -200px;
}

.hero-orb-2 {
  width: 450px;
  height: 450px;
  background: radial-gradient(circle, #6366f1, transparent 70%);
  bottom: -150px;
  inset-inline-start: -180px;
  animation-delay: -8s;
}

.hero-orb-3 {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, #a78bfa, transparent 70%);
  top: 40%;
  left: 50%;
  animation-delay: -16s;
  opacity: 0.08;
}
</style>
