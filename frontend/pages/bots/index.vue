<script setup lang="ts">
/**
 * The bots: what is running, what it is doing, and what stopped.
 *
 * A stopped bot is not a quiet row. Q25's premise is that nobody is watching at
 * 03:00, so the list leads with anything that stopped itself and says why,
 * rather than sorting it under the running ones where it reads as idle.
 */
const { t } = useI18n()
const api = useApi()
const store = useBotsStore()
const live = useLiveStore()
const localePath = useLocalePath()
const { dateTime } = useFormat()

useHead({ title: t('bots.title') })

const creating = ref(false)
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

const versions = computed(() =>
  store.strategies
    .filter((strategy) => strategy.latest_version)
    .map((strategy) => ({
      id: strategy.latest_version!.id,
      label: `${strategy.name} · v${strategy.latest_version!.version}`,
      ok: strategy.latest_version!.parsed_ok,
    })),
)

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
    error.value = e?.data?.code === 'gate_unmet' ? t('bots.gateUnmet', { name: bot.name }) : errorMessage(e)
  } finally {
    busy.value = null
  }
}

async function create() {
  if (!form.strategy_version || !form.name.trim()) return
  busy.value = -1
  try {
    store.upsert(
      await api.createBot({
        ...form,
        name: form.name.trim(),
        sl_pct: form.sl_pct || null,
        tp_pct: form.tp_pct || null,
      }),
    )
    creating.value = false
    form.name = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

onMounted(() => store.load())
</script>

<template>
  <div class="space-y-4">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-xl font-display">{{ t('bots.title') }}</h1>
        <p class="text-xs text-ink-muted mt-1 max-w-2xl leading-relaxed">{{ t('bots.lead') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <NuxtLink :to="localePath('/bots/backtest')" class="btn-ghost btn-sm">
          <UiIcon name="trend" :size="14" />
          {{ t('bots.backtest') }}
        </NuxtLink>
        <NuxtLink :to="localePath('/strategies')" class="btn-ghost btn-sm">
          <UiIcon name="logs" :size="14" />
          {{ t('bots.strategies') }}
        </NuxtLink>
        <button class="btn-brand btn-sm" :disabled="!versions.length" @click="creating = true">
          <UiIcon name="plus" :size="14" />
          {{ t('bots.newBot') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="alert px-3 py-2 text-xs">{{ error }}</p>

    <div v-if="store.loading" class="space-y-2">
      <div v-for="n in 3" :key="n" class="skeleton h-20" />
    </div>

    <UiEmpty
      v-else-if="!store.bots.length"
      icon="bolt"
      :title="t('bots.none')"
      :body="t('bots.noneBody')"
    >
      <NuxtLink :to="localePath('/strategies')" class="btn-brand btn-sm">
        {{ t('bots.newStrategy') }}
      </NuxtLink>
    </UiEmpty>

    <ul v-else class="space-y-2">
      <li v-for="bot in ordered" :key="bot.id">
        <UiCard :tone="bot.state === 'stopped' ? 'signal' : 'default'">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 space-y-1">
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
              <p class="text-xs text-ink-muted num">
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
                <UiIcon name="chevronRight" :size="14" />
              </NuxtLink>
            </div>
          </div>
        </UiCard>
      </li>
    </ul>

    <UiModal v-model="creating" :title="t('bots.newBot')">
      <div class="space-y-3">
        <label class="block space-y-1.5">
          <span class="label">{{ t('bots.strategyVersion') }}</span>
          <select v-model.number="form.strategy_version" class="field">
            <option :value="null">—</option>
            <option v-for="row in versions" :key="row.id" :value="row.id" :disabled="!row.ok">
              {{ row.label }}{{ row.ok ? '' : ` (${t('bots.doesNotValidate')})` }}
            </option>
          </select>
        </label>
        <label class="block space-y-1.5">
          <span class="label">{{ t('bots.botName') }}</span>
          <input v-model="form.name" class="field" />
        </label>
        <div class="grid sm:grid-cols-2 gap-3">
          <label class="block space-y-1.5">
            <span class="label">{{ t('terminal.symbol') }}</span>
            <input v-model="form.symbol" class="field" />
          </label>
          <label class="block space-y-1.5">
            <span class="label">{{ t('bots.interval') }}</span>
            <select v-model="form.interval" class="field">
              <option v-for="value in ['1m', '5m', '15m', '30m', '1h', '4h', '1d']" :key="value">
                {{ value }}
              </option>
            </select>
          </label>
          <label class="block space-y-1.5">
            <span class="label">{{ t('ticket.leverage') }}</span>
            <input v-model.number="form.leverage" type="number" min="1" max="10" class="field" />
          </label>
          <label class="block space-y-1.5">
            <span class="label">{{ t('bots.market') }}</span>
            <select v-model="form.market" class="field">
              <option value="futures">{{ t('market.futures') }}</option>
              <option value="spot">{{ t('market.spot') }}</option>
            </select>
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
        <p class="text-tick text-ink-faint leading-relaxed">{{ t('bots.sizingNote') }}</p>
      </div>
      <template #footer>
        <button class="btn-ghost btn-sm" @click="creating = false">{{ t('common.cancel') }}</button>
        <button
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
