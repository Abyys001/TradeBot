<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getPublicPerformance, type PublicPerformance } from '../../api/public'
import StatCard from '../overview/StatCard.vue'
import PublicEquityChart from './PublicEquityChart.vue'

const { t, locale } = useI18n()

const data = ref<PublicPerformance | null>(null)
const loading = ref(true)
const error = ref(false)

const isEmpty = computed(() => data.value !== null && data.value.equity_curve.length === 0 && data.value.headline.total_closed_trades === 0)

const netPnlAccent = computed(() => {
  const v = Number(data.value?.headline.net_realized_pnl ?? 0)
  return v > 0 ? 'green' : v < 0 ? 'red' : 'neutral'
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
  <section id="performance" class="mx-auto max-w-5xl px-4 py-16 sm:px-6">
    <div class="text-center">
      <h2 class="text-2xl font-bold text-fg sm:text-3xl">{{ t('landing.performance.title') }}</h2>
      <p class="mt-2 text-fg-muted">{{ t('landing.performance.subtitle') }}</p>
    </div>

    <div v-if="loading" class="mt-10 flex items-center justify-center py-10 text-sm text-fg-muted">
      {{ t('landing.performance.loading') }}
    </div>

    <div v-else-if="error" class="mt-10 rounded-xl border border-border bg-surface-raised p-6 text-center text-sm text-fg-muted">
      {{ t('landing.performance.error') }}
    </div>

    <div v-else-if="isEmpty" class="mt-10 rounded-xl border border-border bg-surface-raised p-6 text-center text-sm text-fg-muted">
      {{ t('landing.performance.empty') }}
    </div>

    <template v-else-if="data">
      <div class="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard :label="t('landing.performance.netPnl')" :value="'$' + data.headline.net_realized_pnl" :accent="netPnlAccent" />
        <StatCard :label="t('landing.performance.winRate')" :value="(data.headline.win_rate * 100).toFixed(1) + '%'" />
        <StatCard :label="t('landing.performance.totalTrades')" :value="data.headline.total_closed_trades" />
        <StatCard :label="t('landing.performance.activeStrategies')" :value="data.headline.active_strategies" />
      </div>

      <div class="mt-6">
        <PublicEquityChart :points="data.equity_curve" />
      </div>

      <p class="mt-3 text-center text-xs text-fg-muted">{{ asOfLabel }}</p>
    </template>

    <p class="mt-6 text-center text-xs text-fg-muted">{{ t('landing.performance.disclaimer') }}</p>
  </section>
</template>
