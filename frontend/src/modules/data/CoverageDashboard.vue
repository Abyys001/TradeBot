<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type MarketDataReadiness } from '../../api/client'

const { t } = useI18n()

const symbols = ref<string[]>(['BTC-USDT', 'ETH-USDT', 'SOL-USDT'])
const readiness = ref<Record<string, MarketDataReadiness>>({})
const loading = ref(false)
const lastRefresh = ref<Date | null>(null)

const sorted = computed(() =>
  symbols.value.map((s) => ({
    symbol: s,
    data: readiness.value[s] ?? null,
  })),
)

async function fetchReadiness() {
  loading.value = true
  try {
    for (const sym of symbols.value) {
      try {
        const { data } = await api.get<MarketDataReadiness>('/marketdata/readiness/', {
          params: { symbol: sym, tf: '1m' },
        })
        readiness.value[sym] = data
      } catch {
        readiness.value[sym] = {
          symbol: sym, timeframe: '1m', clean_bars: 0, required_bars: 200,
          ready: false, eta_seconds: null, recording_since: null,
          coverage_pct: 0, suspect_bars_24h: 0, error: 'fetch failed',
        }
      }
    }
    lastRefresh.value = new Date()
  } finally {
    loading.value = false
  }
}

function coverageColor(pct: number): string {
  if (pct >= 95) return 'text-positive'
  if (pct >= 70) return 'text-warning'
  return 'text-negative'
}

function formatSince(ts: string | null): string {
  if (!ts) return 'Not started'
  const d = new Date(ts)
  const diffMs = Date.now() - d.getTime()
  const hours = Math.floor(diffMs / 3600000)
  if (hours < 1) return '< 1 hour'
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d ${hours % 24}h`
}

onMounted(fetchReadiness)
</script>

<template>
  <div class="rounded-xl border border-border p-4 space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-fg">Recording Status</h3>
      <button
        type="button"
        class="rounded px-2 py-1 text-xs bg-surface-raised text-fg-muted hover:bg-border"
        :disabled="loading"
        @click="fetchReadiness"
      >
        {{ loading ? '...' : 'Refresh' }}
      </button>
    </div>

    <div v-if="lastRefresh" class="text-[10px] text-fg-muted">
      Updated {{ lastRefresh.toLocaleTimeString() }}
    </div>

    <div class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-border text-fg-muted">
            <th class="py-1.5 text-left font-medium">Symbol</th>
            <th class="py-1.5 text-left font-medium">Status</th>
            <th class="py-1.5 text-right font-medium">Clean Bars</th>
            <th class="py-1.5 text-right font-medium">Coverage</th>
            <th class="py-1.5 text-right font-medium">Recording Since</th>
            <th class="py-1.5 text-right font-medium">Suspect 24h</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in sorted"
            :key="row.symbol"
            class="border-b border-border/50"
          >
            <td class="py-2 font-medium text-fg">{{ row.symbol }}</td>
            <td class="py-2">
              <span
                v-if="row.data?.ready"
                class="inline-flex items-center gap-1 rounded bg-success-bg px-1.5 py-0.5 text-positive"
              >
                <span class="h-1.5 w-1.5 rounded-full bg-positive animate-pulse" />
                Live
              </span>
              <span
                v-else-if="row.data?.recording_since"
                class="inline-flex items-center gap-1 rounded bg-warning-bg px-1.5 py-0.5 text-warning"
              >
                Warming
              </span>
              <span
                v-else
                class="inline-flex items-center gap-1 rounded bg-surface-raised px-1.5 py-0.5 text-fg-muted"
              >
                Idle
              </span>
            </td>
            <td class="py-2 text-right tabular-nums">
              {{ row.data?.clean_bars ?? 0 }} / {{ row.data?.required_bars ?? 200 }}
            </td>
            <td class="py-2 text-right tabular-nums">
              <span :class="coverageColor(row.data?.coverage_pct ?? 0)">
                {{ (row.data?.coverage_pct ?? 0).toFixed(1) }}%
              </span>
            </td>
            <td class="py-2 text-right text-fg-muted">
              {{ formatSince(row.data?.recording_since ?? null) }}
            </td>
            <td class="py-2 text-right tabular-nums">
              <span :class="(row.data?.suspect_bars_24h ?? 0) > 0 ? 'text-warning' : 'text-fg-muted'">
                {{ row.data?.suspect_bars_24h ?? 0 }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="text-[10px] text-fg-muted">
      Live = ready for strategy deployment. Warming = recording but not enough clean bars yet.
    </p>
  </div>
</template>
