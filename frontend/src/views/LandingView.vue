<script setup lang="ts">
import LandingNav from '../modules/landing/LandingNav.vue'
import LandingHero from '../modules/landing/LandingHero.vue'
import LivePerformanceSection from '../modules/landing/LivePerformanceSection.vue'
import FeaturesGrid from '../modules/landing/FeaturesGrid.vue'
import HowItWorksSection from '../modules/landing/HowItWorksSection.vue'
import SecuritySection from '../modules/landing/SecuritySection.vue'
import RequestAccessForm from '../modules/landing/RequestAccessForm.vue'
import LandingFooter from '../modules/landing/LandingFooter.vue'
</script>

<template>
  <div class="min-h-dvh bg-surface text-fg">
    <LandingNav />
    <main>
      <LandingHero />
      <LivePerformanceSection />
      <FeaturesGrid />
      <HowItWorksSection />
      <SecuritySection />
      <RequestAccessForm />
    </main>
    <LandingFooter />
  </div>
</template>
