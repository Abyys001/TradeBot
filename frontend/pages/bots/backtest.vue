<script setup lang="ts">
/**
 * The backtest: replay a version over stored history, and say what it assumed.
 *
 * The assumptions sit **above** the metrics, always, because a backtest whose
 * fill model is optimistic is worse than no backtest — it produces a number
 * people act on. The intent digest is printed beside them: it is the whole
 * claim that this predicts anything, and the live loop computes it the same way
 * from the same function.
 *
 * Every run is **kept**. A replay costs seconds and, the first time a pair is
 * asked for, a download; the number an operator acted on last week has to still
 * be the number they saw, so the history strip reads stored runs back rather
 * than recomputing them.
 *
 * Missing history is **not an error here**. The server downloads what the
 * window needs and writes it to the archive, and a venue that cannot go back as
 * far as asked comes back as a warning above the metrics saying where the data
 * really started — never a refusal telling the operator to go run a command.
 */
const { t } = useI18n()
const api = useApi()
const store = useBotsStore()
const route = useRoute()
const localePath = useLocalePath()
const { money, dateTime } = useFormat()

useHead({ title: t('bots.backtest') })

const result = ref<BacktestResult | null>(null)
const running = ref(false)
const error = ref('')
const history = ref<BacktestRun[]>([])
const loadingHistory = ref(true)
const openingRun = ref<number | null>(null)
/** Set when the result on screen came out of the archive rather than this session. */
const viewing = ref<BacktestRun | null>(null)

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
      label: `${strategy.name} · ${t('bots.versionN', { n: strategy.latest_version!.version })}`,
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

const PCT_METRICS = new Set(['return_pct', 'max_drawdown_pct', 'win_rate_pct'])
const MONEY_METRICS = new Set(['net_pnl'])

const curve = computed(() =>
  (result.value?.equity_curve ?? []).map(([at, equity]) => ({
    label: dateTime(new Date(at * 1000).toISOString()),
    value: Number(equity),
  })),
)

/** Raw numeric value, for tone decisions — never parse it back off a $-string. */
function rawMetric(key: string): number | null {
  const value = result.value?.metrics?.[key]
  return value === null || value === undefined ? null : Number(value)
}

function metric(key: string): string {
  const value = result.value?.metrics?.[key]
  if (value === null || value === undefined) return '—'
  if (MONEY_METRICS.has(key)) return money(Number(value))
  if (PCT_METRICS.has(key)) return `${value}%`
  return String(value)
}

function toneFor(key: string): 'long' | 'short' | 'signal' | 'default' {
  if (key === 'net_pnl') {
    const n = rawMetric(key)
    return n === null ? 'default' : n > 0 ? 'long' : n < 0 ? 'short' : 'default'
  }
  if (key === 'max_drawdown_pct' || key === 'max_consecutive_losses') return 'signal'
  return 'default'
}

/** Just the day, for the window a stored run covered — the clock is noise there. */
function day(seconds: number): string {
  return new Date(seconds * 1000).toISOString().slice(0, 10)
}

/** A stored row's headline PnL, for the history strip. Never recomputed here. */
function rowPnl(row: BacktestRun): number | null {
  const value = row.metrics?.net_pnl
  return value === null || value === undefined ? null : Number(value)
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    history.value = await api.backtests()
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loadingHistory.value = false
  }
}

async function run() {
  if (!form.strategy_version) return
  running.value = true
  error.value = ''
  result.value = null
  viewing.value = null
  try {
    result.value = await api.runBacktest({
      strategy_version: form.strategy_version,
      symbol: form.symbol.trim().toUpperCase(),
      interval: form.interval,
      market: form.market,
      leverage: form.leverage,
      sl_pct: form.sl_pct || null,
      tp_pct: form.tp_pct || null,
      from_time: Math.floor(new Date(`${form.from}T00:00:00Z`).getTime() / 1000),
      to_time: Math.floor(new Date(`${form.to}T23:59:59Z`).getTime() / 1000),
    })
    await loadHistory()
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    running.value = false
  }
}

/**
 * Reopen a stored run. The row and the report are two shapes — `trades` is a
 * count in one and the log in the other — so this rebuilds the report the
 * result view expects rather than casting one to the other.
 */
async function reopen(row: BacktestRun) {
  openingRun.value = row.id
  error.value = ''
  try {
    const stored = await api.backtestRun(row.id)
    result.value = {
      symbol: stored.symbol,
      interval: stored.interval,
      from_time: stored.from_time,
      to_time: stored.to_time,
      bars: stored.bars,
      metrics: stored.metrics,
      assumptions: stored.assumptions,
      assumption_lines: stored.assumptions?.lines ?? [],
      equity_curve: stored.equity_curve,
      intent_digest: stored.intent_digest,
      trades: stored.trade_log,
      warnings: [],
    }
    viewing.value = row
    form.symbol = stored.symbol
    form.interval = stored.interval
    form.market = stored.market
    form.from = new Date(stored.from_time * 1000).toISOString().slice(0, 10)
    form.to = new Date(stored.to_time * 1000).toISOString().slice(0, 10)
    form.strategy_version = stored.strategy_version
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    openingRun.value = null
  }
}

onMounted(async () => {
  await Promise.all([store.load(), loadHistory()])
  // Arriving from a strategy's "Backtest" button: that version, preselected.
  const wanted = Number(route.query.version)
  if (wanted && versions.value.some((row) => row.id === wanted)) form.strategy_version = wanted
  else if (versions.value.length === 1) form.strategy_version = versions.value[0].id
})
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-4 sm:space-y-5">
    <header class="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div class="min-w-0">
        <h1 class="text-xl font-display">{{ t('bots.backtest') }}</h1>
        <p class="text-xs text-ink-muted mt-1.5 max-w-2xl leading-relaxed">
          {{ t('bots.backtestLead') }}
        </p>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <NuxtLink :to="localePath('/strategies')" class="btn-ghost btn-sm">
          <UiIcon name="logs" :size="14" />
          {{ t('bots.strategies') }}
        </NuxtLink>
        <NuxtLink :to="localePath('/bots')" class="btn-ghost btn-sm">
          <UiIcon name="bot" :size="14" />
          {{ t('bots.title') }}
        </NuxtLink>
      </div>
    </header>

    <div class="grid xl:grid-cols-[1fr_20rem] gap-5 items-start">
      <div class="space-y-5 min-w-0">
        <UiCard :title="t('bots.runBacktest')">
          <div class="space-y-5">
            <label class="block space-y-1.5">
              <span class="label">{{ t('bots.strategyVersion') }}</span>
              <select v-model.number="form.strategy_version" class="field">
                <option :value="null">—</option>
                <option v-for="row in versions" :key="row.id" :value="row.id">
                  {{ row.label }}
                </option>
              </select>
              <NuxtLink
                v-if="!versions.length"
                :to="localePath('/strategies')"
                class="text-tick text-brand hover:underline inline-block"
              >
                {{ t('bots.noStrategiesForBot') }}
              </NuxtLink>
            </label>

            <div>
              <p class="label mb-2">{{ t('bots.window') }}</p>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <label class="block space-y-1.5">
                  <span class="label">{{ t('terminal.symbol') }}</span>
                  <input v-model="form.symbol" class="field num" />
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
              </div>
              <p class="text-tick text-ink-faint leading-relaxed mt-2">
                {{ t('bots.historyNote') }}
              </p>
            </div>

            <div>
              <p class="label mb-2">{{ t('bots.execution') }}</p>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <label class="block space-y-1.5">
                  <span class="label">{{ t('bots.market') }}</span>
                  <select v-model="form.market" class="field">
                    <option value="futures">{{ t('market.futures') }}</option>
                    <option value="spot">{{ t('market.spot') }}</option>
                  </select>
                </label>
                <label class="block space-y-1.5">
                  <span class="label">{{ t('ticket.leverage') }}</span>
                  <input
                    v-model.number="form.leverage"
                    type="number"
                    min="1"
                    max="10"
                    class="field"
                  />
                </label>
                <label class="block space-y-1.5">
                  <span class="label">{{ t('ticket.stopLoss') }} %</span>
                  <input v-model="form.sl_pct" class="field" placeholder="—" />
                </label>
                <label class="block space-y-1.5">
                  <span class="label">{{ t('ticket.takeProfit') }} %</span>
                  <input v-model="form.tp_pct" class="field" placeholder="—" />
                </label>
              </div>
            </div>

            <p class="text-tick text-ink-faint leading-relaxed">{{ t('bots.sizingNote') }}</p>
          </div>
          <template #footer>
            <div class="flex items-center gap-3">
              <button
                class="btn-brand btn-sm"
                :disabled="running || !form.strategy_version"
                @click="run"
              >
                <UiIcon v-if="running" name="spinner" :size="14" class="animate-spin" />
                {{ running ? t('bots.replaying') : t('bots.runBacktest') }}
              </button>
              <span v-if="running" class="text-tick text-ink-faint leading-relaxed">
                {{ t('bots.replayingNote') }}
              </span>
            </div>
          </template>
        </UiCard>

        <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">{{ error }}</p>

        <template v-if="result">
          <div
            v-if="viewing"
            class="rounded-lg border border-line bg-raised/50 px-3.5 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
          >
            <UiIcon name="history" :size="14" class="text-ink-faint shrink-0" />
            <span class="text-ink-muted">
              {{ t('bots.viewingStored', { name: viewing.strategy_name }) }}
            </span>
            <span class="num text-ink-faint">{{ dateTime(viewing.created_at) }}</span>
          </div>

          <!-- Assumptions first. Not a footnote. -->
          <UiCard :title="t('bots.assumptions')" :hint="t('bots.assumptionsHint')">
            <ul class="space-y-2 text-xs text-ink-muted leading-relaxed">
              <li v-for="(line, index) in result.assumption_lines" :key="index" class="flex gap-2">
                <span class="text-ink-faint select-none">·</span><span>{{ line }}</span>
              </li>
            </ul>
            <p class="text-tick text-ink-faint num mt-4 pt-3 border-t border-line break-all">
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

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <UiStat
              v-for="key in HEADLINE"
              :key="key"
              :label="t(`bots.metric.${key}`)"
              :value="metric(key)"
              :tone="toneFor(key)"
            />
          </div>

          <UiCard v-if="curve.length > 1" :title="t('bots.equityCurve')">
            <UiTrendChart :points="curve" :format="(n: number) => money(n)" />
          </UiCard>

          <UiCard
            :title="t('bots.trades')"
            :hint="t('bots.tradesN', { n: result.trades.length })"
            flush
          >
            <UiEmpty v-if="!result.trades.length" icon="history" :title="t('bots.noTrades')" />
            <div v-else class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="label">
                    <th class="text-start px-4 py-2.5 font-normal">{{ t('bots.side') }}</th>
                    <th class="text-start px-4 py-2.5 font-normal">{{ t('bots.entry') }}</th>
                    <th class="text-start px-4 py-2.5 font-normal">{{ t('bots.exit') }}</th>
                    <th class="text-end px-4 py-2.5 font-normal">{{ t('bots.pnl') }}</th>
                    <th class="text-end px-4 py-2.5 font-normal">{{ t('bots.barsHeld') }}</th>
                    <th class="text-start px-4 py-2.5 font-normal">{{ t('bots.reason') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line">
                  <tr
                    v-for="(trade, index) in result.trades"
                    :key="index"
                    class="hover:bg-raised/50 transition-colors"
                  >
                    <td class="px-4 py-2">
                      <UiBadge :tone="trade.side === 'long' ? 'long' : 'short'">
                        {{ t(`side.${trade.side}`) }}
                      </UiBadge>
                    </td>
                    <td class="px-4 py-2 num text-ink-muted whitespace-nowrap">
                      {{ dateTime(new Date(trade.entry_time * 1000).toISOString()) }}
                      <span class="text-ink-faint"> @ {{ money(trade.entry_price) }}</span>
                    </td>
                    <td class="px-4 py-2 num text-ink-muted whitespace-nowrap">
                      {{ dateTime(new Date(trade.exit_time * 1000).toISOString()) }}
                      <span class="text-ink-faint"> @ {{ money(trade.exit_price) }}</span>
                    </td>
                    <td
                      class="px-4 py-2 num text-end whitespace-nowrap"
                      :class="Number(trade.pnl) >= 0 ? 'text-long' : 'text-short'"
                    >
                      {{ money(trade.pnl) }}
                    </td>
                    <td class="px-4 py-2 num text-end text-ink-muted">{{ trade.bars_held }}</td>
                    <td class="px-4 py-2 text-ink-muted">
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

      <UiCard :title="t('bots.history')" :hint="t('bots.historyLead')" flush>
        <div v-if="loadingHistory" class="p-4 space-y-2">
          <div v-for="n in 3" :key="n" class="skeleton h-14" />
        </div>
        <UiEmpty
          v-else-if="!history.length"
          icon="history"
          :title="t('bots.noHistory')"
          :body="t('bots.noHistoryBody')"
        />
        <ul v-else class="divide-y divide-line max-h-[40rem] overflow-y-auto">
          <li v-for="row in history" :key="row.id">
            <button
              class="w-full text-start px-4 py-3 hover:bg-raised transition-colors disabled:opacity-60"
              :class="viewing?.id === row.id ? 'bg-raised' : ''"
              :disabled="openingRun === row.id"
              @click="reopen(row)"
            >
              <span class="flex items-baseline justify-between gap-3">
                <span class="text-xs truncate min-w-0">{{ row.strategy_name }}</span>
                <span
                  v-if="rowPnl(row) !== null"
                  class="text-xs num shrink-0"
                  :class="rowPnl(row)! >= 0 ? 'text-long' : 'text-short'"
                >
                  {{ money(rowPnl(row)!) }}
                </span>
              </span>
              <span class="block text-tick text-ink-faint num mt-1 truncate">
                {{ row.symbol }} {{ row.interval }} ·
                {{ t('bots.versionN', { n: row.version }) }} ·
                {{ t('bots.tradesN', { n: row.trades }) }}
              </span>
              <span class="block text-tick text-ink-faint num mt-0.5">
                {{ day(row.from_time) }} → {{ day(row.to_time) }}
              </span>
            </button>
          </li>
        </ul>
      </UiCard>
    </div>
  </div>
</template>
