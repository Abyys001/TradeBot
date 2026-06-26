<script setup lang="ts">
<<<<<<< HEAD
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { createChart, LineSeries, ColorType } from 'lightweight-charts'
import BaseModal from '../../components/BaseModal.vue'
import type { Backtest } from '../../api/client'

const props = defineProps<{
  backtest: Backtest
}>()

const emit = defineEmits<{ close: []; viewChart: [] }>()

const { t } = useI18n()
const equityEl = ref<HTMLElement | null>(null)
const chart = shallowRef<ReturnType<typeof createChart> | null>(null)

const metrics = computed(() => props.backtest.metrics ?? {})
const netPnl = computed(() => Number(metrics.value.net_pnl ?? 0))
const winRate = computed(() => Number(metrics.value.win_rate ?? 0))
const maxDd = computed(() => Number(metrics.value.max_drawdown ?? 0))
const numTrades = computed(() => Number(metrics.value.num_trades ?? 0))

const equityPoints = computed(() => {
  let cumulative = 0
  return props.backtest.trades.map((tr, i) => {
    cumulative += Number(tr.pnl)
    return { time: (tr.exit_bar ?? tr.entry_bar ?? i + 1) as import('lightweight-charts').Time, value: cumulative }
  })
})

onMounted(() => {
  if (!equityEl.value || !equityPoints.value.length) return
  chart.value = createChart(equityEl.value, {
    layout: { background: { type: ColorType.Solid, color: '#18181b' }, textColor: '#a1a1aa' },
    grid: { vertLines: { color: '#27272a' }, horzLines: { color: '#27272a' } },
    height: 200,
  })
  const line = chart.value.addSeries(LineSeries, { color: '#8b5cf6', lineWidth: 2 })
  line.setData(equityPoints.value)
  chart.value.timeScale().fitContent()
})

onUnmounted(() => {
  chart.value?.remove()
})
</script>

<template>
  <BaseModal size="lg" :title="t('backtest.results')" @close="emit('close')">
    <div v-if="backtest.status === 'failed'" class="rounded-lg border border-red-800 bg-red-950/40 p-4 text-sm text-red-300">
      {{ backtest.error || t('backtest.failed') }}
    </div>
    <template v-else>
      <div class="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div
          class="rounded-xl border p-3"
          :class="netPnl >= 0 ? 'border-emerald-800/50 bg-emerald-950/30' : 'border-red-800/50 bg-red-950/30'"
        >
          <p class="text-[10px] uppercase text-zinc-500">{{ t('backtest.netPnl') }}</p>
          <p class="text-lg font-semibold" :class="netPnl >= 0 ? 'text-emerald-400' : 'text-red-400'">
            {{ netPnl.toFixed(2) }}
          </p>
        </div>
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3">
          <p class="text-[10px] uppercase text-zinc-500">{{ t('backtest.winRate') }}</p>
          <p class="text-lg font-semibold text-zinc-100">{{ (winRate * 100).toFixed(1) }}%</p>
        </div>
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3">
          <p class="text-[10px] uppercase text-zinc-500">{{ t('backtest.maxDrawdown') }}</p>
          <p class="text-lg font-semibold text-amber-400">{{ maxDd.toFixed(2) }}</p>
        </div>
        <div class="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3">
          <p class="text-[10px] uppercase text-zinc-500">{{ t('backtest.numTrades') }}</p>
          <p class="text-lg font-semibold text-zinc-100">{{ numTrades }}</p>
        </div>
      </div>

      <div v-if="equityPoints.length" class="mb-5">
        <p class="mb-2 text-xs text-zinc-500">{{ t('backtest.equityCurve') }}</p>
        <div ref="equityEl" class="rounded-lg border border-zinc-800" />
      </div>

      <div v-if="backtest.trades.length" class="overflow-hidden rounded-lg border border-zinc-800">
        <table class="w-full text-xs">
          <thead class="bg-zinc-900/80 text-zinc-500">
            <tr>
              <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
              <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
              <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
              <th class="px-3 py-2 text-end">PnL</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(tr, i) in backtest.trades"
              :key="i"
              class="border-t border-zinc-800/50 hover:bg-zinc-900/40"
            >
              <td class="px-3 py-2 text-zinc-300">{{ tr.side }}</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ tr.entry_price }}</td>
              <td class="px-3 py-2 text-end text-zinc-400">{{ tr.exit_price }}</td>
              <td
                class="px-3 py-2 text-end font-medium"
                :class="Number(tr.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'"
              >
                {{ Number(tr.pnl).toFixed(4) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-lg px-4 py-2 text-sm text-zinc-400"
          @click="emit('close')"
        >
          {{ t('health.cancel') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-violet-700 px-4 py-2 text-sm text-white hover:bg-violet-600"
          @click="emit('viewChart'); emit('close')"
        >
          {{ t('backtest.viewOnChart') }}
        </button>
      </div>
    </template>
  </BaseModal>
=======
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Backtest } from '../../api/client'
import AppModal from '../../components/AppModal.vue'
import MetricsCards from './MetricsCards.vue'
import EquityCurve from './EquityCurve.vue'
import BacktestResultsSkeleton from '../../components/BacktestResultsSkeleton.vue'

const props = defineProps<{ backtest: Backtest }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()

const metrics = computed(() => props.backtest.metrics)
const trades = computed(() => props.backtest.trades ?? [])
const isLoading = computed(
  () => props.backtest.status === 'pending' || props.backtest.status === 'running',
)
</script>

<template>
  <AppModal :title="t('backtest.resultsTitle')" size="lg" @close="emit('close')">
    <div class="space-y-4 p-4">
      <div class="flex items-center gap-2 text-sm text-zinc-400">
        <span>{{ backtest.symbol }} / {{ backtest.timeframe }}</span>
        <span
          class="rounded px-1.5 py-0.5 text-xs font-medium"
          :class="{
            'bg-emerald-900 text-emerald-300': backtest.status === 'done',
            'bg-red-900 text-red-300': backtest.status === 'failed',
            'bg-amber-900 text-amber-300': backtest.status === 'running',
            'bg-zinc-800 text-zinc-400': backtest.status === 'pending',
          }"
        >
          {{ backtest.status }}
        </span>
      </div>

      <template v-if="isLoading">
        <p class="text-xs text-zinc-500">{{ t('backtest.progress') }}</p>
        <BacktestResultsSkeleton />
      </template>

      <template v-else>
        <div v-if="metrics" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.netPnl') }}</div>
            <div
              class="text-2xl font-bold"
              :class="(metrics.net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'"
            >
              {{ metrics.net_pnl?.toFixed(2) ?? '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.winRate') }}</div>
            <div class="text-2xl font-bold text-zinc-100">
              {{ metrics.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.maxDrawdown') }}</div>
            <div class="text-2xl font-bold text-red-400">
              {{ metrics.max_drawdown?.toFixed(2) ?? '—' }}
            </div>
          </div>
          <div class="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
            <div class="text-xs text-zinc-500">{{ t('backtest.numTrades') }}</div>
            <div class="text-2xl font-bold text-zinc-100">{{ metrics.num_trades ?? '—' }}</div>
          </div>
        </div>

        <div v-if="metrics?.equity_series?.length">
          <h3 class="mb-2 text-xs font-medium text-zinc-500">{{ t('backtest.equityCurve') }}</h3>
          <EquityCurve :series="metrics.equity_series" :height="200" />
        </div>

        <div v-if="trades.length" class="overflow-hidden rounded-lg border border-zinc-800">
          <div class="border-b border-zinc-800 bg-zinc-900/50 px-3 py-2 text-xs font-medium text-zinc-400">
            {{ t('backtest.tradesTitle', { count: trades.length }) }}
          </div>
          <div class="max-h-48 overflow-y-auto">
            <table class="w-full text-xs">
              <thead class="sticky top-0 bg-zinc-900/95 text-zinc-500 uppercase">
                <tr>
                  <th class="px-3 py-2 text-start">{{ t('backtest.side') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.entry') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.exit') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.pnl') }}</th>
                  <th class="px-3 py-2 text-end">{{ t('backtest.exitReason') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(tr, i) in trades" :key="i" class="border-t border-zinc-800/50">
                  <td class="px-3 py-1.5 text-zinc-300">{{ tr.side }}</td>
                  <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.entry_price }}</td>
                  <td class="px-3 py-1.5 text-end text-zinc-400">{{ tr.exit_price ?? '—' }}</td>
                  <td
                    class="px-3 py-1.5 text-end"
                    :class="Number(tr.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'"
                  >
                    {{ tr.pnl }}
                  </td>
                  <td class="px-3 py-1.5 text-end text-zinc-500">{{ tr.exit_reason || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="metrics">
          <h3 class="mb-2 text-xs font-medium text-zinc-500">{{ t('backtest.moreMetrics') }}</h3>
          <MetricsCards :metrics="metrics" />
        </div>

        <p v-if="backtest.error" class="text-sm text-red-400">{{ backtest.error }}</p>
      </template>
    </div>

    <template #footer>
      <div class="flex justify-end">
        <button
          type="button"
          class="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
          @click="emit('close')"
        >
          {{ t('modal.close') }}
        </button>
      </div>
    </template>
  </AppModal>
>>>>>>> 1af07065fe5a87dc8ca34e162c3bf176e3907b0c
</template>
