<script setup lang="ts">
/**
 * The backtest: replay a version over stored history, and say what it assumed.
 *
 * The assumptions sit **above** the metrics, always, because a backtest whose
 * fill model is optimistic is worse than no backtest — it produces a number
 * people act on. The intent digest is printed beside them: it is the whole
 * claim that this predicts anything, and the live loop computes it the same way
 * from the same function.
 */
const { t } = useI18n()
const api = useApi()
const store = useBotsStore()
const localePath = useLocalePath()
const { money, pct, dateTime } = useFormat()

useHead({ title: t('bots.backtest') })

const result = ref<BacktestResult | null>(null)
const running = ref(false)
const error = ref('')

const today = new Date()
const monthsAgo = new Date(today.getTime() - 180 * 24 * 3600 * 1000)

const form = reactive({
  strategy_version: null as number | null,
  symbol: 'BTCUSDT',
  interval: '1h',
  market: 'futures',
  leverage: 1,
  sl_pct: '',
  tp_pct: '',
  from: monthsAgo.toISOString().slice(0, 10),
  to: today.toISOString().slice(0, 10),
})

const versions = computed(() =>
  store.strategies
    .filter((strategy) => strategy.latest_version?.parsed_ok)
    .map((strategy) => ({
      id: strategy.latest_version!.id,
      label: `${strategy.name} · v${strategy.latest_version!.version}`,
    })),
)

/** The metrics worth leading with, in the order a reader asks for them. */
const HEADLINE = [
  'net_pnl',
  'return_pct',
  'max_drawdown_pct',
  'sharpe',
  'trades',
  'win_rate_pct',
  'profit_factor',
  'max_consecutive_losses',
] as const

const curve = computed(() =>
  (result.value?.equity_curve ?? []).map(([at, equity]) => ({
    label: dateTime(new Date(at * 1000).toISOString()),
    value: Number(equity),
  })),
)

function metric(key: string): string {
  const value = result.value?.metrics?.[key]
  if (value === null || value === undefined) return '—'
  return String(value)
}

async function run() {
  if (!form.strategy_version) return
  running.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await api.runBacktest({
      strategy_version: form.strategy_version,
      symbol: form.symbol.toUpperCase(),
      interval: form.interval,
      market: form.market,
      leverage: form.leverage,
      sl_pct: form.sl_pct || null,
      tp_pct: form.tp_pct || null,
      from_time: Math.floor(new Date(`${form.from}T00:00:00Z`).getTime() / 1000),
      to_time: Math.floor(new Date(`${form.to}T23:59:59Z`).getTime() / 1000),
    })
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    running.value = false
  }
}

onMounted(() => store.load())
</script>

<template>
  <div class="space-y-4">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-xl font-display">{{ t('bots.backtest') }}</h1>
        <p class="text-xs text-ink-muted mt-1 max-w-2xl leading-relaxed">{{ t('bots.backtestLead') }}</p>
      </div>
      <NuxtLink :to="localePath('/bots')" class="btn-ghost btn-sm">
        <UiIcon name="bolt" :size="14" />
        {{ t('bots.title') }}
      </NuxtLink>
    </header>

    <UiCard :title="t('bots.runBacktest')">
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <label class="block space-y-1.5 sm:col-span-2">
          <span class="label">{{ t('bots.strategyVersion') }}</span>
          <select v-model.number="form.strategy_version" class="field">
            <option :value="null">—</option>
            <option v-for="row in versions" :key="row.id" :value="row.id">{{ row.label }}</option>
          </select>
        </label>
        <label class="block space-y-1.5">
          <span class="label">{{ t('terminal.symbol') }}</span>
          <input v-model="form.symbol" class="field" />
        </label>
        <label class="block space-y-1.5">
          <span class="label">{{ t('bots.interval') }}</span>
          <select v-model="form.interval" class="field">
            <option v-for="value in ['5m', '15m', '30m', '1h', '4h', '1d']" :key="value">
              {{ value }}
            </option>
          </select>
        </label>
        <label class="block space-y-1.5">
          <span class="label">{{ t('bots.from') }}</span>
          <input v-model="form.from" type="date" class="field" />
        </label>
        <label class="block space-y-1.5">
          <span class="label">{{ t('bots.to') }}</span>
          <input v-model="form.to" type="date" class="field" />
        </label>
        <label class="block space-y-1.5">
          <span class="label">{{ t('ticket.leverage') }}</span>
          <input v-model.number="form.leverage" type="number" min="1" max="10" class="field" />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block space-y-1.5">
            <span class="label">SL %</span>
            <input v-model="form.sl_pct" class="field" placeholder="—" />
          </label>
          <label class="block space-y-1.5">
            <span class="label">TP %</span>
            <input v-model="form.tp_pct" class="field" placeholder="—" />
          </label>
        </div>
      </div>
      <template #footer>
        <button class="btn-brand btn-sm" :disabled="running || !form.strategy_version" @click="run">
          <UiIcon v-if="running" name="spinner" :size="14" class="animate-spin" />
          {{ running ? t('bots.replaying') : t('bots.runBacktest') }}
        </button>
      </template>
    </UiCard>

    <p v-if="error" class="alert px-3 py-2 text-xs">{{ error }}</p>

    <template v-if="result">
      <!-- Assumptions first. Not a footnote. -->
      <UiCard :title="t('bots.assumptions')" :hint="t('bots.assumptionsHint')">
        <ul class="space-y-1 text-xs text-ink-muted leading-relaxed">
          <li v-for="(line, index) in result.assumption_lines" :key="index">· {{ line }}</li>
        </ul>
        <p class="text-tick text-ink-faint num mt-3 break-all">
          {{ t('bots.intentDigest') }}: {{ result.intent_digest }}
        </p>
      </UiCard>

      <p
        v-for="(warning, index) in result.warnings"
        :key="index"
        class="alert px-3 py-2 text-xs leading-relaxed"
      >
        {{ warning }}
      </p>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <UiStat
          v-for="key in HEADLINE"
          :key="key"
          :label="t(`bots.metric.${key}`)"
          :value="metric(key)"
          :tone="
            key === 'net_pnl'
              ? Number(metric(key)) > 0
                ? 'long'
                : Number(metric(key)) < 0
                  ? 'short'
                  : 'default'
              : key === 'max_drawdown_pct'
                ? 'signal'
                : 'default'
          "
        />
      </div>

      <UiCard v-if="curve.length > 1" :title="t('bots.equityCurve')">
        <UiTrendChart :points="curve" :format="(n: number) => money(n)" />
      </UiCard>

      <UiCard :title="t('bots.trades')" :hint="t('bots.tradesN', { n: result.trades.length })" flush>
        <UiEmpty v-if="!result.trades.length" icon="history" :title="t('bots.noTrades')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="label">
                <th class="text-start px-3 py-2">{{ t('bots.side') }}</th>
                <th class="text-start px-3 py-2">{{ t('bots.entry') }}</th>
                <th class="text-start px-3 py-2">{{ t('bots.exit') }}</th>
                <th class="text-end px-3 py-2">{{ t('bots.pnl') }}</th>
                <th class="text-end px-3 py-2">{{ t('bots.barsHeld') }}</th>
                <th class="text-start px-3 py-2">{{ t('bots.reason') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="(trade, index) in result.trades" :key="index">
                <td class="px-3 py-1.5">
                  <UiBadge :tone="trade.side === 'long' ? 'long' : 'short'">
                    {{ t(`side.${trade.side}`) }}
                  </UiBadge>
                </td>
                <td class="px-3 py-1.5 num text-ink-muted">
                  {{ dateTime(new Date(trade.entry_time * 1000).toISOString()) }}
                  <span class="text-ink-faint"> @ {{ money(trade.entry_price) }}</span>
                </td>
                <td class="px-3 py-1.5 num text-ink-muted">
                  {{ dateTime(new Date(trade.exit_time * 1000).toISOString()) }}
                  <span class="text-ink-faint"> @ {{ money(trade.exit_price) }}</span>
                </td>
                <td
                  class="px-3 py-1.5 num text-end"
                  :class="Number(trade.pnl) >= 0 ? 'text-long' : 'text-short'"
                >
                  {{ money(trade.pnl) }}
                </td>
                <td class="px-3 py-1.5 num text-end text-ink-muted">{{ trade.bars_held }}</td>
                <td class="px-3 py-1.5 text-ink-muted">
                  {{ trade.exit_reason }}
                  <span v-if="trade.entry_span" class="text-ink-faint num">
                    · {{ t('bots.line') }} {{ trade.entry_span.line }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>
    </template>
  </div>
</template>
