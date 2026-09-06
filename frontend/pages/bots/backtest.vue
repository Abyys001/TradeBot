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
 * Three things the form does before it runs, and each one used to be discovered
 * afterwards:
 *
 *   **Properties first.** Initial capital, commission, slippage and the order
 *   size model are not decoration on a report — they change what the replay
 *   *is*. Editing them only after a run means every comparison starts from
 *   settings nobody chose, so they open in a dialog in front of the button.
 *
 *   **A visible download.** The first run on a pair the archive has never seen
 *   spends most of its wall clock paging a public endpoint. That is a job with
 *   a progress bar now, not a spinner that is indistinguishable from a hang.
 *
 *   **The archive is checked up front.** The form says how many bars are
 *   already stored before anything is pressed, so a cached window is visibly
 *   free rather than inferred from how fast it went.
 *
 * Every run is **kept**, and every run is **deletable**. A backtest is a working
 * note, not an audit record — the action log is the thing kept forever (Q26).
 * Deleting a report never touches the archived candles behind it, which belong
 * to the platform and would otherwise have to be downloaded again.
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

/** The job in flight, and the bar drawn from it. */
const job = ref<BacktestJobState | null>(null)
let poll: ReturnType<typeof setInterval> | null = null

/** What the archive already holds for the window on screen. */
const coverage = ref<BacktestCoverage | null>(null)
let coverageTimer: ReturnType<typeof setTimeout> | null = null

const showProperties = ref(false)
const propertyOverrides = ref<Record<string, unknown>>({})

const pendingDelete = ref<BacktestRun | null>(null)
const clearing = ref(false)
const deleting = ref(false)

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

const PCT_METRICS = new Set(['return_pct', 'max_drawdown_pct', 'win_rate_pct', 'time_in_market_pct'])
const MONEY_METRICS = new Set([
  'net_pnl',
  'final_equity',
  'gross_profit',
  'gross_loss',
  'average_win',
  'average_loss',
  'expectancy',
  'worst_trade',
  'best_trade',
  'total_fees',
])
const COUNT_METRICS = new Set([
  'trades',
  'max_consecutive_losses',
  'longest_flat_bars',
  'bars',
])

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

/**
 * Two decimal places, everywhere.
 *
 * The server stores eight — it is Decimal all the way down and a stored report
 * has to be re-readable at full precision — but `10.85000000%` is not a number
 * anyone reads. Rounding is done *here*, at the last moment before ink, so the
 * stored value never loses anything and nothing downstream inherits a rounded
 * figure it might do arithmetic on.
 */
function metric(key: string): string {
  const value = result.value?.metrics?.[key]
  if (value === null || value === undefined) return '—'
  if (MONEY_METRICS.has(key)) return money(Number(value))
  if (PCT_METRICS.has(key)) return `${Number(value).toFixed(2)}%`
  if (COUNT_METRICS.has(key)) return String(Math.round(Number(value)))
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(2) : String(value)
}

function toneFor(key: string): 'long' | 'short' | 'signal' | 'default' {
  if (key === 'net_pnl') {
    const n = rawMetric(key)
    return n === null ? 'default' : n > 0 ? 'long' : n < 0 ? 'short' : 'default'
  }
  if (key === 'max_drawdown_pct' || key === 'max_consecutive_losses') return 'signal'
  return 'default'
}

/** What the run started with and what it ended with — the question behind "return %". */
const capital = computed(() => {
  const started = Number(result.value?.assumptions?.initial_equity ?? 0)
  const ended = Number(result.value?.metrics?.final_equity ?? 0)
  if (!started) return null
  return { started, ended, delta: ended - started }
})

/** Where the bars came from. `downloaded: 0` is the cache hit worth naming. */
const dataSource = computed(() => result.value?.data_source ?? null)

/** Just the day, for the window a stored run covered — the clock is noise there. */
function day(seconds: number): string {
  return new Date(seconds * 1000).toISOString().slice(0, 10)
}

/** A stored row's headline PnL, for the history strip. Never recomputed here. */
function rowPnl(row: BacktestRun): number | null {
  const value = row.metrics?.net_pnl
  return value === null || value === undefined ? null : Number(value)
}

const fromSeconds = computed(() =>
  Math.floor(new Date(`${form.from}T00:00:00Z`).getTime() / 1000),
)
const toSeconds = computed(() => Math.floor(new Date(`${form.to}T23:59:59Z`).getTime() / 1000))

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

/**
 * Ask the archive what it holds, debounced. One indexed count, no network on
 * the server side — cheap enough to run on every keystroke of a date, and the
 * whole point is that it answers before the operator commits to a download.
 */
function refreshCoverage() {
  if (coverageTimer) clearTimeout(coverageTimer)
  coverageTimer = setTimeout(async () => {
    if (!form.symbol.trim() || !Number.isFinite(fromSeconds.value)) return
    try {
      coverage.value = await api.backtestCoverage({
        symbol: form.symbol.trim().toUpperCase(),
        interval: form.interval,
        market: form.market,
        from_time: fromSeconds.value,
        to_time: toSeconds.value,
      })
    } catch {
      // A window nothing is stored for is a normal answer, not an error worth
      // a banner over the form.
      coverage.value = null
    }
  }, 350)
}

/** The bar's caption: which phase, and whatever that phase can honestly count. */
const progressLabel = computed(() => {
  const status = job.value?.status ?? 'queued'
  return t(`bots.job.${status}`)
})

const progressDetail = computed(() => {
  const detail = job.value?.detail ?? {}
  const status = job.value?.status
  if (status === 'downloading') {
    if (detail.cached) return t('bots.job.fromArchive', { bars: detail.bars ?? 0 })
    return t('bots.job.downloaded', { bars: detail.bars ?? 0, pages: detail.pages ?? 0 })
  }
  if (status === 'replaying') {
    return t('bots.job.replayed', {
      bars: detail.bars ?? 0,
      total: detail.total ?? 0,
      trades: detail.trades ?? 0,
    })
  }
  return ''
})

function stopPolling() {
  if (poll) clearInterval(poll)
  poll = null
}

async function run() {
  if (!form.strategy_version) return
  running.value = true
  error.value = ''
  result.value = null
  viewing.value = null
  job.value = null
  try {
    const started = await api.startBacktest({
      strategy_version: form.strategy_version,
      symbol: form.symbol.trim().toUpperCase(),
      interval: form.interval,
      market: form.market,
      leverage: form.leverage,
      sl_pct: form.sl_pct || null,
      tp_pct: form.tp_pct || null,
      from_time: fromSeconds.value,
      to_time: toSeconds.value,
      property_overrides: propertyOverrides.value,
    })
    job.value = started
    await watchJob(started.job_id)
  } catch (e: any) {
    error.value = errorMessage(e)
    running.value = false
  }
}

/**
 * Poll until the job settles. Once a second: the phases move at human speed and
 * a tighter loop is a request per nothing.
 */
function watchJob(jobId: number) {
  return new Promise<void>((resolve) => {
    stopPolling()
    poll = setInterval(async () => {
      try {
        const state = await api.backtestJob(jobId)
        job.value = state
        if (!state.finished) return
        stopPolling()
        running.value = false
        if (state.status === 'failed') {
          error.value = state.error || t('bots.job.failed')
        } else if (state.backtest_id) {
          await Promise.all([openStored(state.backtest_id), loadHistory()])
        }
        resolve()
      } catch (e: any) {
        stopPolling()
        running.value = false
        error.value = errorMessage(e)
        resolve()
      }
    }, 1000)
  })
}

/**
 * Rebuild the report view from a stored run. The row and the report are two
 * shapes — `trades` is a count in one and the log in the other — so this builds
 * what the result view expects rather than casting one to the other.
 */
async function openStored(runId: number, row: BacktestRun | null = null) {
  const stored = await api.backtestRun(runId)
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
    data_source: (stored.assumptions as any)?.data_source,
  }
  viewing.value = row
  if (row) {
    form.symbol = stored.symbol
    form.interval = stored.interval
    form.market = stored.market
    form.from = new Date(stored.from_time * 1000).toISOString().slice(0, 10)
    form.to = new Date(stored.to_time * 1000).toISOString().slice(0, 10)
    form.strategy_version = stored.strategy_version
  }
}

async function reopen(row: BacktestRun) {
  openingRun.value = row.id
  error.value = ''
  try {
    await openStored(row.id, row)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    openingRun.value = null
  }
}

async function remove(row: BacktestRun) {
  deleting.value = true
  error.value = ''
  try {
    await api.deleteBacktest(row.id)
    history.value = history.value.filter((item) => item.id !== row.id)
    if (viewing.value?.id === row.id) {
      viewing.value = null
      result.value = null
    }
    pendingDelete.value = null
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    deleting.value = false
  }
}

async function clearAll() {
  deleting.value = true
  error.value = ''
  try {
    await api.clearBacktests()
    history.value = []
    viewing.value = null
    result.value = null
    clearing.value = false
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    deleting.value = false
  }
}

watch(
  () => [form.symbol, form.interval, form.market, form.from, form.to],
  refreshCoverage,
  { immediate: false },
)

/** Properties belong to a version. Switching version drops overrides for the old one. */
watch(
  () => form.strategy_version,
  () => {
    propertyOverrides.value = {}
  },
)

onBeforeUnmount(() => {
  stopPolling()
  if (coverageTimer) clearTimeout(coverageTimer)
})

onMounted(async () => {
  await Promise.all([store.load(), loadHistory()])
  // Arriving from a strategy's "Backtest" button: that version, preselected.
  const wanted = Number(route.query.version)
  if (wanted && versions.value.some((row) => row.id === wanted)) form.strategy_version = wanted
  else if (versions.value.length === 1) form.strategy_version = versions.value[0].id
  refreshCoverage()
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
                  <UiSymbolPicker v-model="form.symbol" />
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

              <!-- What is already stored, before anything is pressed. A cached
                   window is visibly free; a cold one warns about the download
                   instead of surprising the operator with it. -->
              <p v-if="coverage" class="text-tick leading-relaxed mt-2 num"
                 :class="coverage.cached ? 'text-ok' : 'text-ink-faint'">
                <template v-if="coverage.cached">
                  {{ t('bots.coverageCached', { bars: coverage.stored }) }}
                </template>
                <template v-else>
                  {{ t('bots.coveragePartial', {
                    stored: coverage.stored,
                    expected: coverage.expected,
                  }) }}
                </template>
              </p>
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

            <!-- The Properties tab, in front of the run rather than after it.
                 These numbers change what the replay is, not how it is
                 captioned. -->
            <div class="flex flex-wrap items-center gap-3">
              <button
                class="btn-ghost btn-sm"
                :disabled="!form.strategy_version"
                @click="showProperties = true"
              >
                <UiIcon name="settings" :size="14" />
                {{ t('bots.editProperties') }}
              </button>
              <span class="text-tick text-ink-faint">
                {{
                  Object.keys(propertyOverrides).length
                    ? t('bots.props.overriddenN', { n: Object.keys(propertyOverrides).length })
                    : t('bots.props.noOverrides')
                }}
              </span>
            </div>

            <p class="text-tick text-ink-faint leading-relaxed">{{ t('bots.sizingNote') }}</p>
          </div>
          <template #footer>
            <div class="w-full space-y-3">
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

              <UiProgress
                v-if="running || (job && !job.finished)"
                :value="job && job.status !== 'queued' ? job.progress : null"
                :label="progressLabel"
                :detail="progressDetail"
              />
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

          <!-- Capital first: "return %" is a ratio, and the two numbers it is a
               ratio *of* are what an operator actually reports to a partner. -->
          <UiCard v-if="capital" :title="t('bots.capital')" :hint="t('bots.capitalHint')">
            <div class="grid grid-cols-3 gap-3">
              <UiStat :label="t('bots.startingCapital')" :value="money(capital.started)" />
              <UiStat :label="t('bots.endingCapital')" :value="money(capital.ended)" />
              <UiStat
                :label="t('bots.metric.net_pnl')"
                :value="money(capital.delta)"
                :tone="capital.delta > 0 ? 'long' : capital.delta < 0 ? 'short' : 'default'"
              />
            </div>
            <p v-if="dataSource" class="text-tick text-ink-faint leading-relaxed mt-3 num">
              <template v-if="!dataSource.downloaded">
                {{ t('bots.barsFromArchive', { bars: dataSource.from_archive }) }}
              </template>
              <template v-else>
                {{ t('bots.barsDownloaded', {
                  downloaded: dataSource.downloaded,
                  stored: dataSource.from_archive,
                }) }}
              </template>
            </p>
          </UiCard>

          <!-- Assumptions. Not a footnote. -->
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
        <div v-if="history.length" class="px-4 py-2 border-b border-line flex justify-end">
          <button class="btn-quiet btn-sm text-ink-faint" @click="clearing = true">
            <UiIcon name="trash" :size="13" />
            {{ t('bots.clearHistory') }}
          </button>
        </div>
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
          <li v-for="row in history" :key="row.id" class="flex items-stretch">
            <button
              class="flex-1 min-w-0 text-start px-4 py-3 hover:bg-raised transition-colors disabled:opacity-60"
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
            <button
              class="btn-quiet btn-icon px-3 text-ink-faint hover:text-short shrink-0"
              :title="t('bots.deleteRun')"
              :aria-label="t('bots.deleteRun')"
              @click="pendingDelete = row"
            >
              <UiIcon name="trash" :size="13" />
            </button>
          </li>
        </ul>
      </UiCard>
    </div>

    <BotsPropertiesDialog
      v-model="showProperties"
      :version-id="form.strategy_version"
      :overrides="propertyOverrides"
      @apply="(next) => (propertyOverrides = next)"
    />

    <UiModal
      :model-value="pendingDelete !== null"
      :title="t('bots.deleteRun')"
      size="sm"
      @update:model-value="(v: boolean) => { if (!v) pendingDelete = null }"
    >
      <p class="text-sm leading-relaxed">{{ t('bots.deleteRunBody') }}</p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost btn-sm" @click="pendingDelete = null">
            {{ t('common.cancel') }}
          </button>
          <button class="btn-danger btn-sm" :disabled="deleting" @click="remove(pendingDelete!)">
            {{ t('common.delete') }}
          </button>
        </div>
      </template>
    </UiModal>

    <UiModal v-model="clearing" :title="t('bots.clearHistory')" size="sm">
      <p class="text-sm leading-relaxed">
        {{ t('bots.clearHistoryBody', { n: history.length }) }}
      </p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost btn-sm" @click="clearing = false">{{ t('common.cancel') }}</button>
          <button class="btn-danger btn-sm" :disabled="deleting" @click="clearAll">
            {{ t('common.delete') }}
          </button>
        </div>
      </template>
    </UiModal>
  </div>
</template>
