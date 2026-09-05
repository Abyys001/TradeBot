<script setup lang="ts">
/**
 * The bots: what is running, what it is doing, and what stopped.
 *
 * A stopped bot is not a quiet row. Q25's premise is that nobody is watching at
 * 03:00, so the list leads with anything that stopped itself and says why,
 * rather than sorting it under the running ones where it reads as idle.
 *
 * Creating one asks for the **strategy first** and refuses to go on without it.
 * A bot is "this version of that script, on this pair" — with the script left
 * blank there is nothing to configure, so the form does not offer the rest of
 * itself until the question is answered.
 */
const { t } = useI18n()
const api = useApi()
const store = useBotsStore()
const live = useLiveStore()
const localePath = useLocalePath()
const { dateTime } = useFormat()

useHead({ title: t('bots.title') })

const creating = ref(false)
const step = ref<'strategy' | 'settings'>('strategy')
const busy = ref<number | null>(null)
const error = ref('')

const form = reactive({
  strategy_version: null as number | null,
  name: '',
  symbol: 'BTCUSDT',
  interval: '1h',
  market: 'futures',
  leverage: 1,
  sl_pct: '',
  tp_pct: '',
})

/** One row per strategy — its newest version, which is the only one a new bot may use. */
const choices = computed(() =>
  store.strategies
    .filter((strategy) => strategy.latest_version)
    .map((strategy) => ({
      id: strategy.latest_version!.id,
      name: strategy.name,
      version: strategy.latest_version!.version,
      ok: strategy.latest_version!.parsed_ok,
    })),
)

const chosen = computed(() => choices.value.find((row) => row.id === form.strategy_version) ?? null)

/** Stopped first, then live, then paper, then draft. See the page comment. */
const ORDER: Record<BotState, number> = { stopped: 0, live: 1, paper: 2, draft: 3 }
const ordered = computed(() =>
  [...store.bots].sort((a, b) => ORDER[a.state] - ORDER[b.state] || a.name.localeCompare(b.name)),
)

const TONE: Record<BotState, 'neutral' | 'ok' | 'signal' | 'brand'> = {
  draft: 'neutral',
  paper: 'brand',
  live: 'ok',
  stopped: 'signal',
}

function runOf(bot: BotSummary): BotRun | null {
  return store.runs[bot.id] ?? bot.latest_run ?? null
}

/** The freshest bar this bot has evaluated, socket first, then the run row. */
function lastBar(bot: BotSummary): number | null {
  const pushed = live.botBars[bot.id]?.bar_time
  return pushed ?? runOf(bot)?.last_bar_time ?? null
}

async function act(bot: BotSummary, action: 'paper' | 'live' | 'stop') {
  busy.value = bot.id
  error.value = ''
  try {
    if (action === 'stop') await store.stop(bot.id, t('bots.stoppedByHand'))
    else await store.start(bot.id, action)
  } catch (e: any) {
    // A 409 from the gate carries the whole gate; the detail page renders it,
    // so the list says which bot and sends the operator there rather than
    // trying to explain nine rows in a toast.
    error.value =
      e?.data?.code === 'gate_unmet' ? t('bots.gateUnmet', { name: bot.name }) : errorMessage(e)
  } finally {
    busy.value = null
  }
}

function open() {
  step.value = 'strategy'
  form.strategy_version = null
  form.name = ''
  creating.value = true
}

/** The name defaults to the script's, because that is what it is until told otherwise. */
function pick(id: number) {
  form.strategy_version = id
  const row = choices.value.find((choice) => choice.id === id)
  if (row && !form.name.trim()) form.name = row.name
  step.value = 'settings'
}

async function create() {
  if (!form.strategy_version || !form.name.trim()) return
  busy.value = -1
  error.value = ''
  try {
    const bot = await api.createBot({
      ...form,
      name: form.name.trim(),
      symbol: form.symbol.trim().toUpperCase(),
      sl_pct: form.sl_pct || null,
      tp_pct: form.tp_pct || null,
    })
    store.upsert(bot)
    creating.value = false
    navigateTo(localePath(`/bots/${bot.id}`))
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

onMounted(() => store.load())
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-4 sm:space-y-5">
    <header class="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div class="min-w-0">
        <h1 class="text-xl font-display">{{ t('bots.title') }}</h1>
        <p class="text-xs text-ink-muted mt-1.5 max-w-2xl leading-relaxed">{{ t('bots.lead') }}</p>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <NuxtLink :to="localePath('/bots/backtest')" class="btn-ghost btn-sm">
          <UiIcon name="trend" :size="14" />
          {{ t('bots.backtest') }}
        </NuxtLink>
        <button class="btn-brand btn-sm" @click="open">
          <UiIcon name="plus" :size="14" />
          {{ t('bots.newBot') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">{{ error }}</p>

    <div v-if="store.loading" class="space-y-3">
      <div v-for="n in 3" :key="n" class="skeleton h-24" />
    </div>

    <UiCard v-else-if="!store.bots.length" flush>
      <UiEmpty icon="bot" :title="t('bots.none')" :body="t('bots.noneBody')">
        <div class="flex flex-wrap items-center justify-center gap-2">
          <button class="btn-brand btn-sm" @click="open">
            <UiIcon name="plus" :size="14" />
            {{ t('bots.newBot') }}
          </button>
          <NuxtLink :to="localePath('/strategies')" class="btn-ghost btn-sm">
            {{ t('bots.strategies') }}
          </NuxtLink>
        </div>
      </UiEmpty>
    </UiCard>

    <ul v-else class="space-y-3">
      <li v-for="bot in ordered" :key="bot.id">
        <UiCard :tone="bot.state === 'stopped' ? 'signal' : 'default'">
          <div class="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
            <div class="min-w-0 space-y-2">
              <div class="flex items-center gap-2 flex-wrap">
                <NuxtLink
                  :to="localePath(`/bots/${bot.id}`)"
                  class="text-sm font-medium hover:text-brand transition-colors"
                >
                  {{ bot.name }}
                </NuxtLink>
                <UiBadge :tone="TONE[bot.state]" dot>{{ t(`bots.state.${bot.state}`) }}</UiBadge>
                <UiBadge v-if="bot.dry_run && bot.state !== 'draft'" tone="neutral">
                  {{ t('bots.dryRun') }}
                </UiBadge>
              </div>
              <p class="text-xs text-ink-muted num leading-relaxed">
                {{ bot.strategy_name }} · v{{ bot.version }} · {{ bot.symbol }}
                {{ bot.interval }} · {{ bot.leverage }}×
                <template v-if="bot.sl_pct"> · SL {{ bot.sl_pct }}%</template>
                <template v-if="bot.tp_pct"> · TP {{ bot.tp_pct }}%</template>
              </p>
              <p
                v-if="bot.state === 'stopped' && runOf(bot)?.stop_reason"
                class="text-xs text-signal leading-relaxed"
              >
                {{ t(`bots.stop.${runOf(bot)!.stop_reason}`, runOf(bot)!.stop_reason) }}
                <span v-if="runOf(bot)!.stop_detail" class="text-ink-muted">
                  — {{ runOf(bot)!.stop_detail }}
                </span>
              </p>
              <p v-else-if="lastBar(bot)" class="text-tick text-ink-faint num">
                {{ t('bots.lastBar') }} {{ dateTime(new Date(lastBar(bot)! * 1000).toISOString()) }}
                · {{ t('bots.barsN', { n: runOf(bot)?.bars_evaluated ?? 0 }) }}
              </p>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <button
                v-if="bot.state === 'draft' || bot.state === 'stopped'"
                class="btn-info btn-sm"
                :disabled="busy === bot.id"
                @click="act(bot, 'paper')"
              >
                <UiIcon name="play" :size="14" />
                {{ t('bots.startPaper') }}
              </button>
              <button
                v-if="bot.state === 'paper'"
                class="btn-ok btn-sm"
                :disabled="busy === bot.id"
                @click="act(bot, 'live')"
              >
                {{ t('bots.goLive') }}
              </button>
              <button
                v-if="bot.state === 'paper' || bot.state === 'live'"
                class="btn-warn btn-sm"
                :disabled="busy === bot.id"
                @click="act(bot, 'stop')"
              >
                <UiIcon name="pause" :size="14" />
                {{ t('bots.stop.action') }}
              </button>
              <NuxtLink :to="localePath(`/bots/${bot.id}`)" class="btn-ghost btn-sm btn-icon">
                <UiIcon name="chevronRight" :size="14" class="flip-rtl" />
              </NuxtLink>
            </div>
          </div>
        </UiCard>
      </li>
    </ul>

    <UiModal v-model="creating" :title="t('bots.newBot')">
      <!-- Step 1. Without a script there is nothing to configure, so nothing else is shown. -->
      <div v-if="step === 'strategy'" class="space-y-3">
        <p class="text-xs text-ink-muted leading-relaxed">{{ t('bots.pickStrategyLead') }}</p>

        <UiEmpty
          v-if="!choices.length"
          icon="logs"
          :title="t('bots.noStrategies')"
          :body="t('bots.noStrategiesForBot')"
        >
          <NuxtLink
            :to="localePath('/strategies')"
            class="btn-brand btn-sm"
            @click="creating = false"
          >
            <UiIcon name="plus" :size="14" />
            {{ t('bots.newStrategy') }}
          </NuxtLink>
        </UiEmpty>

        <ul v-else class="space-y-2 max-h-80 overflow-y-auto -mx-1 px-1">
          <li v-for="row in choices" :key="row.id">
            <button
              class="w-full text-start rounded-lg border px-3.5 py-3 flex items-center gap-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :class="
                form.strategy_version === row.id
                  ? 'border-brand bg-brand/5'
                  : 'border-line hover:border-ink-faint hover:bg-raised/60'
              "
              :disabled="!row.ok"
              @click="pick(row.id)"
            >
              <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="row.ok ? 'bg-ok' : 'bg-short'" />
              <span class="min-w-0 flex-1">
                <span class="text-sm block truncate">{{ row.name }}</span>
                <span class="text-tick text-ink-faint block mt-0.5">
                  {{ t('bots.versionN', { n: row.version }) }}
                  <template v-if="!row.ok"> · {{ t('bots.doesNotValidate') }}</template>
                </span>
              </span>
              <UiIcon name="chevronRight" :size="14" class="text-ink-faint flip-rtl shrink-0" />
            </button>
          </li>
        </ul>
      </div>

      <!-- Step 2. -->
      <div v-else class="space-y-4">
        <div class="rounded-lg border border-line bg-raised/50 px-3.5 py-2.5 flex items-center gap-3">
          <UiIcon name="logs" :size="15" class="text-ink-faint shrink-0" />
          <span class="min-w-0 flex-1">
            <span class="text-sm block truncate">{{ chosen?.name }}</span>
            <span class="text-tick text-ink-faint">
              {{ t('bots.versionN', { n: chosen?.version ?? 0 }) }}
            </span>
          </span>
          <button class="btn-quiet btn-sm shrink-0" @click="step = 'strategy'">
            {{ t('common.change') }}
          </button>
        </div>

        <label class="block space-y-1.5">
          <span class="label">{{ t('bots.botName') }}</span>
          <input v-model="form.name" class="field" />
        </label>

        <div>
          <p class="label mb-2">{{ t('bots.window') }}</p>
          <div class="grid sm:grid-cols-2 gap-3">
            <label class="block space-y-1.5">
              <span class="label">{{ t('terminal.symbol') }}</span>
              <input v-model="form.symbol" class="field num" />
            </label>
            <label class="block space-y-1.5">
              <span class="label">{{ t('bots.interval') }}</span>
              <select v-model="form.interval" class="field">
                <option v-for="value in ['1m', '5m', '15m', '30m', '1h', '4h', '1d']" :key="value">
                  {{ value }}
                </option>
              </select>
            </label>
          </div>
        </div>

        <div>
          <p class="label mb-2">{{ t('bots.execution') }}</p>
          <div class="grid sm:grid-cols-2 gap-3">
            <label class="block space-y-1.5">
              <span class="label">{{ t('bots.market') }}</span>
              <select v-model="form.market" class="field">
                <option value="futures">{{ t('market.futures') }}</option>
                <option value="spot">{{ t('market.spot') }}</option>
              </select>
            </label>
            <label class="block space-y-1.5">
              <span class="label">{{ t('ticket.leverage') }}</span>
              <input v-model.number="form.leverage" type="number" min="1" max="10" class="field" />
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
        <button v-if="step === 'settings'" class="btn-ghost btn-sm" @click="step = 'strategy'">
          {{ t('common.back') }}
        </button>
        <button v-else class="btn-ghost btn-sm" @click="creating = false">
          {{ t('common.cancel') }}
        </button>
        <button
          v-if="step === 'settings'"
          class="btn-brand btn-sm"
          :disabled="busy === -1 || !form.strategy_version || !form.name.trim()"
          @click="create"
        >
          {{ t('common.create') }}
        </button>
      </template>
    </UiModal>
  </div>
</template>
