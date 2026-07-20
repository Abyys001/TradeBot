<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getPublicPerformance, type PublicPerformance } from '../../api/public'
import PublicEquityChart from './PublicEquityChart.vue'

const { t, locale } = useI18n()

const data = ref<PublicPerformance | null>(null)
const loading = ref(true)
const error = ref(false)

const isEmpty = computed(() => data.value !== null && data.value.equity_curve.length === 0 && data.value.headline.total_closed_trades === 0)

const netPnlAccent = computed(() => {
  const v = Number(data.value?.headline.net_realized_pnl ?? 0)
  return v > 0 ? 'text-positive' : v < 0 ? 'text-negative' : 'text-fg-muted'
})

const asOfLabel = computed(() => {
  if (!data.value) return ''
  const date = new Date(data.value.as_of).toLocaleDateString(locale.value === 'fa' ? 'fa-IR' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
  return t('landing.performance.asOf', { date })
})

const stats = computed(() => {
  if (!data.value) return []
  return [
    {
      label: t('landing.performance.netPnl'),
      value: '$' + data.value.headline.net_realized_pnl,
      color: netPnlAccent.value,
    },
    {
      label: t('landing.performance.winRate'),
      value: (data.value.headline.win_rate * 100).toFixed(1) + '%',
      color: 'text-fg',
    },
    {
      label: t('landing.performance.totalTrades'),
      value: data.value.headline.total_closed_trades,
      color: 'text-fg',
    },
    {
      label: t('landing.performance.activeStrategies'),
      value: data.value.headline.active_strategies,
      color: 'text-fg',
    },
  ]
})

onMounted(async () => {
  try {
    data.value = await getPublicPerformance()
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section id="performance" class="mx-auto max-w-5xl px-4 py-20 sm:px-6">
    <div class="text-center">
      <span class="inline-block rounded-full bg-accent-muted px-3 py-1 text-xs font-medium text-accent">{{ t('landing.nav.performance') }}</span>
      <h2 class="mt-4 text-3xl font-bold tracking-tight text-fg sm:text-4xl">{{ t('landing.performance.title') }}</h2>
      <p class="mx-auto mt-3 max-w-2xl text-lg text-fg-muted">{{ t('landing.performance.subtitle') }}</p>
    </div>

    <div v-if="loading" class="mt-12 flex items-center justify-center py-12">
      <div class="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
    </div>

    <div v-else-if="error" class="mt-12 rounded-2xl border border-border bg-surface-raised p-8 text-center text-sm text-fg-muted">
      {{ t('landing.performance.error') }}
    </div>

    <div v-else-if="isEmpty" class="mt-12 rounded-2xl border border-border bg-surface-raised p-8 text-center text-sm text-fg-muted">
      {{ t('landing.performance.empty') }}
    </div>

    <template v-else-if="data">
      <div class="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div
          v-for="stat in stats"
          :key="stat.label"
          class="rounded-xl border border-border bg-surface-raised p-5 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md"
        >
          <p class="text-xs font-medium text-fg-muted">{{ stat.label }}</p>
          <p class="mt-1.5 text-2xl font-bold tracking-tight" :class="stat.color">{{ stat.value }}</p>
        </div>
      </div>

      <div class="mt-6 overflow-hidden rounded-2xl border border-border bg-surface-raised p-4">
        <PublicEquityChart :points="data.equity_curve" />
      </div>

      <p class="mt-4 text-center text-xs text-fg-muted">{{ asOfLabel }}</p>
    </template>

    <p class="mt-8 text-center text-xs text-fg-muted/70">{{ t('landing.performance.disclaimer') }}</p>
  </section>
</template>
