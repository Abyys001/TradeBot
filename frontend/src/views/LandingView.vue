<script setup lang="ts">
import { ref } from 'vue'
import { useScrollReveal } from '../composables/useScrollReveal'
import LandingNav from '../modules/landing/LandingNav.vue'
import LandingHero from '../modules/landing/LandingHero.vue'
import LivePerformanceSection from '../modules/landing/LivePerformanceSection.vue'
import FeaturesGrid from '../modules/landing/FeaturesGrid.vue'
import HowItWorksSection from '../modules/landing/HowItWorksSection.vue'
import SecuritySection from '../modules/landing/SecuritySection.vue'
import RequestAccessForm from '../modules/landing/RequestAccessForm.vue'
import LandingFooter from '../modules/landing/LandingFooter.vue'

const performanceEl = ref<HTMLElement | null>(null)
const featuresEl = ref<HTMLElement | null>(null)
const howItWorksEl = ref<HTMLElement | null>(null)
const securityEl = ref<HTMLElement | null>(null)
const accessEl = ref<HTMLElement | null>(null)

useScrollReveal(performanceEl)
useScrollReveal(featuresEl)
useScrollReveal(howItWorksEl)
useScrollReveal(securityEl)
useScrollReveal(accessEl)
</script>

<template>
  <div class="min-h-dvh bg-surface text-fg">
    <LandingNav />
    <main>
      <LandingHero />

      <div ref="performanceEl" class="scroll-reveal">
        <LivePerformanceSection />
      </div>

      <!-- Divider -->
      <div class="mx-auto max-w-5xl px-4 sm:px-6">
        <div class="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
      </div>

      <div ref="featuresEl" class="scroll-reveal">
        <FeaturesGrid />
      </div>

      <!-- Divider -->
      <div class="mx-auto max-w-5xl px-4 sm:px-6">
        <div class="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
      </div>

      <div ref="howItWorksEl" class="scroll-reveal">
        <HowItWorksSection />
      </div>

      <div ref="securityEl" class="scroll-reveal">
        <SecuritySection />
      </div>

      <!-- Divider -->
      <div class="mx-auto max-w-5xl px-4 sm:px-6">
        <div class="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
      </div>

      <div ref="accessEl" class="scroll-reveal">
        <RequestAccessForm />
      </div>
    </main>
    <LandingFooter />
  </div>
</template>
