<script setup lang="ts">
import { computed } from 'vue'
import type { AnalyticsRun } from '../../stores/analytics'

const props = defineProps<{ runs: AnalyticsRun[] }>()
const emit = defineEmits<{ select: [run: AnalyticsRun] }>()

function sparkPath(series?: number[]): { line: string; area: string } {
  if (!series?.length) return { line: '', area: '' }
  const w = 300
  const h = 52
  const min = Math.min(...series)
  const max = Math.max(...series)
  const range = Math.max(max - min, 1)
  const pts = series.map((v, i) => {
    const x = (i / Math.max(series.length - 1, 1)) * w
    const y = h - ((v - min) / range) * (h - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p}`).join(' ')
  const area = `${line} L${w},${h} L0,${h} Z`
  return { line, area }
}

function fmtPnl(v?: number) {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + v.toFixed(2)
}

function fmtPct(v?: number) {
  if (v == null) return null
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%'
}

function returnPct(run: AnalyticsRun) {
  if (run.initial_balance && run.net_pnl != null) {
    return fmtPct(run.net_pnl / run.initial_balance)
  }
  return null
}

function winPct(run: AnalyticsRun) {
  if (run.win_rate == null) return null
  return Math.round(run.win_rate * 100)
}

function fmtDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const cards = computed(() =>
  props.runs.map((r) => {
    const profitable = (r.net_pnl ?? 0) >= 0
    const spark = sparkPath(r.equity_series)
    return {
      run: r,
      profitable,
      spark,
      win: winPct(r),
      ret: returnPct(r),
    }
  }),
)
</script>

<template>
  <div>
    <h2 class="mb-4 text-sm font-medium text-fg">{{ $t('analytics.historyChart') }}</h2>
    <div
      v-if="!runs.length"
      class="flex items-center justify-center rounded-xl border border-dashed border-border py-16 text-xs text-fg-muted"
    >
      {{ $t('analytics.noHistoryData') }}
    </div>

    <div v-else class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <button
        v-for="c in cards"
        :key="c.run.backtest_id"
        type="button"
        class="group relative flex flex-col overflow-hidden rounded-2xl border text-start transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        :class="
          c.profitable
            ? 'border-border bg-surface hover:border-positive/40 hover:shadow-positive/20'
            : 'border-border bg-surface hover:border-negative/40 hover:shadow-negative/20'
        "
        @click="emit('select', c.run)"
      >
        <!-- ambient glow strip -->
        <div
          class="absolute inset-x-0 top-0 h-px"
          :class="c.profitable ? 'bg-gradient-to-r from-transparent via-positive/40 to-transparent' : 'bg-gradient-to-r from-transparent via-negative/30 to-transparent'"
        />

        <!-- card body -->
        <div class="flex flex-1 flex-col gap-3 p-4">

          <!-- row 1: name + status badge -->
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="truncate text-sm font-semibold text-fg group-hover:text-white">
                {{ c.run.strategy_name }}
              </p>
              <div class="mt-1 flex flex-wrap items-center gap-1">
                <span class="rounded bg-surface-raised/80 px-1.5 py-0.5 text-[10px] font-medium text-fg">
                  {{ c.run.symbol }}
                </span>
                <span class="rounded bg-surface-raised/80 px-1.5 py-0.5 text-[10px] text-fg-muted">
                  {{ c.run.timeframe ?? '—' }}
                </span>
                <span
                  v-if="c.run.network"
                  class="rounded px-1.5 py-0.5 text-[10px]"
                  :class="c.run.network === 'mainnet' ? 'bg-accent/15 text-accent' : 'bg-surface-raised text-fg-muted'"
                >
                  {{ c.run.network }}
                </span>
              </div>
            </div>
            <span
              class="mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              :class="c.profitable ? 'bg-success-bg text-positive' : 'bg-danger-bg text-negative'"
            >
              {{ c.profitable ? 'Profit' : 'Loss' }}
            </span>
          </div>

          <!-- row 2: PnL + return -->
          <div class="flex items-end justify-between gap-2">
            <div>
              <p class="text-[11px] text-fg-muted">Net PnL</p>
              <p
                class="text-2xl font-bold tabular-nums leading-tight"
                :class="c.profitable ? 'text-positive' : 'text-negative'"
              >
                {{ fmtPnl(c.run.net_pnl) }}
              </p>
            </div>
            <div v-if="c.ret" class="text-end">
              <p class="text-[11px] text-fg-muted">Return</p>
              <p
                class="text-sm font-semibold tabular-nums"
                :class="c.profitable ? 'text-positive' : 'text-negative'"
              >
                {{ c.ret }}
              </p>
            </div>
          </div>

          <!-- row 3: win rate bar -->
          <div v-if="c.win != null" class="space-y-1">
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-fg-muted">Win Rate</span>
              <span class="font-medium" :class="c.win >= 50 ? 'text-positive' : 'text-fg-muted'">
                {{ c.win }}%
              </span>
            </div>
            <div class="h-1 rounded-full bg-surface-raised">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="c.win >= 50 ? 'bg-positive' : 'bg-border'"
                :style="{ width: `${c.win}%` }"
              />
            </div>
          </div>

          <!-- row 4: mini metrics row -->
          <div class="grid grid-cols-3 gap-2 rounded-xl bg-surface-muted/60 px-3 py-2">
            <div class="text-center">
              <p class="text-[10px] text-fg-muted">Sharpe</p>
              <p class="text-xs font-medium text-fg">{{ c.run.sharpe_ratio?.toFixed(2) ?? '—' }}</p>
            </div>
            <div class="text-center">
              <p class="text-[10px] text-fg-muted">Max DD</p>
              <p class="text-xs font-medium text-negative/80">
                {{ c.run.max_drawdown != null ? c.run.max_drawdown.toFixed(1) + '%' : '—' }}
              </p>
            </div>
            <div class="text-center">
              <p class="text-[10px] text-fg-muted">Trades</p>
              <p class="text-xs font-medium text-fg">{{ c.run.num_trades ?? '—' }}</p>
            </div>
          </div>
        </div>

        <!-- sparkline footer -->
        <div class="relative h-14 w-full overflow-hidden">
          <svg
            v-if="c.spark.line"
            viewBox="0 0 300 52"
            class="absolute inset-0 h-full w-full"
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient :id="`grad-${c.run.backtest_id}`" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  :stop-color="c.profitable ? '#10b981' : '#ef4444'"
                  stop-opacity="0.25"
                />
                <stop offset="100%" :stop-color="c.profitable ? '#10b981' : '#ef4444'" stop-opacity="0" />
              </linearGradient>
            </defs>
            <path :d="c.spark.area" :fill="`url(#grad-${c.run.backtest_id})`" />
            <path
              :d="c.spark.line"
              fill="none"
              :stroke="c.profitable ? '#10b981' : '#ef4444'"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <div
            v-else
            class="flex h-full items-center justify-center text-[10px] text-fg-muted"
          >
            no equity data
          </div>
        </div>

        <!-- bottom strip: date + PF -->
        <div
          class="flex items-center justify-between border-t border-border/60 px-4 py-2 text-[11px]"
        >
          <span class="text-fg-muted">{{ fmtDate(c.run.created_at) }}</span>
          <span v-if="c.run.profit_factor != null" class="text-fg-muted">
            PF <span class="text-fg-muted">{{ c.run.profit_factor.toFixed(2) }}</span>
          </span>
        </div>
      </button>
    </div>
  </div>
</template>
