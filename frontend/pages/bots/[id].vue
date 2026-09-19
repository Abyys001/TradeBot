<script setup lang="ts">
/**
 * One bot, whole: what it is, what it decided, what came back, and what stands
 * between it and real money.
 *
 * The promotion gate is the page's spine. `paper → live` is not a confirmation
 * dialog — it is a set of measurements, and the page shows every one with the
 * number behind it, met or not. A row that cannot be measured from inside
 * (no adapter has been run against a live exchange) is shown as exactly that.
 *
 * Two switches sit on top of it, and both belong to the admin: the gate can be
 * turned off entirely, and any single row can be waived. Either way the rows
 * keep being measured and keep being shown — "allowed" and "proven" are
 * different sentences and the page says both.
 */
import { INTERVALS } from '~/stores/market'

const { t, te } = useI18n()
const route = useRoute()
const api = useApi()
const store = useBotsStore()
const live = useLiveStore()
const localePath = useLocalePath()
const { dateTime, money, ms } = useFormat()

const id = computed(() => Number(route.params.id))

const bot = ref<BotSummary | null>(null)
const runs = ref<BotRun[]>([])
const gate = ref<PromotionGate | null>(null)
/** Which accounts a fan-out from this bot would actually reach. */
const reach = ref<BotAccountRow[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const tab = ref<
  | 'journal'
  | 'control'
  | 'chart'
  | 'logic'
  | 'activity'
  | 'inputs'
  | 'properties'
  | 'promotion'
  | 'source'
>('journal')
const editing = ref(false)

useHead({ title: () => bot.value?.name ?? t('bots.title') })

const run = computed(() => store.runs[id.value] ?? runs.value[0] ?? null)

const TONE: Record<BotState, 'neutral' | 'ok' | 'signal' | 'brand'> = {
  draft: 'neutral',
  paper: 'brand',
  live: 'ok',
  stopped: 'signal',
}

/**
 * The last bar the socket pushed, folded in front of the fetched list. A bot on
 * a 1m timeframe would otherwise look frozen between polls.
 */
const latestBar = computed(() => live.botBars[id.value] ?? null)
const latestIntent = computed(() => live.botIntents[id.value] ?? null)

/**
 * The exact source this bot runs — the version it points at, never the latest.
 * Fetched by id, and only when the Source tab is opened: it used to come out of
 * the whole strategy list, which meant every bot page downloaded every version
 * of every script on the platform to show one.
 */
const sourceOf = ref('')
const sourceLoading = ref(false)

async function loadSource() {
  if (!bot.value || sourceOf.value || sourceLoading.value) return
  sourceLoading.value = true
  try {
    sourceOf.value = (await api.strategyVersion(bot.value.strategy_version)).source
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    sourceLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [botRow, runRows, gateRows, reachRows] = await Promise.all([
      api.bot(id.value),
      api.botRuns(id.value),
      api.botPromotion(id.value),
      api.botAccounts(id.value),
    ])
    bot.value = botRow
    runs.value = runRows
    gate.value = gateRows
    reach.value = reachRows.accounts
    store.upsert(botRow)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

/**
 * The bot was refused for having nothing to protect an order with, *and* its
 * script has its own exits — so the fix is one field, offered right here.
 */
const canSwitchPolicy = ref(false)
/** What the operator asked for, so the retry after the switch is the same act. */
const lastAction = ref<'paper' | 'live' | null>(null)

/**
 * Switch to strategy-managed exits, then retry the start that was refused.
 *
 * The switch is a real edit to the bot, saved through the same endpoint the
 * settings dialog uses — not a flag on this request. A bot that went live under
 * a policy the stored row does not reflect is a bot whose trade log would
 * describe the wrong thing.
 */
async function switchToStrategyExits() {
  const row = bot.value
  if (!row) return
  // Where to put it back. What the operator asked for if they asked, otherwise
  // whatever it was doing when they pressed this — the button exists to leave
  // the bot running, not to trade a refusal for a stopped bot.
  const running = row.state === 'paper' || row.state === 'live'
  const resume = lastAction.value ?? (running ? (row.state as 'paper' | 'live') : null)
  busy.value = true
  error.value = ''
  try {
    // **The policy is frozen while a bot runs**, and for a real reason: an open
    // position would be left protected by one rule while the bot plans against
    // the other. So the switch stops it first rather than handing back the
    // server's "stop the bot before changing this" and leaving somebody to find
    // the stop button, come back, and repeat the whole click. That round trip
    // is what made a bot refused at the Live button unfixable from the banner
    // offering the fix — the bot was already running in paper.
    if (running) await store.stop(id.value, t('bots.stoppedToEdit'))
    const updated = await api.updateBot(row.id, { exit_policy: 'strategy_managed' })
    bot.value = updated
    store.upsert(updated)
    canSwitchPolicy.value = false
  } catch (e: any) {
    error.value = errorMessage(e)
    busy.value = false
    // It may have stopped before the edit failed. Show what is actually true.
    await load()
    return
  }
  busy.value = false
  if (resume) await act(resume)
  else await load()
}

/**
 * Stop the bot without leaving the settings dialog.
 *
 * What a bot trades is frozen while it runs and the fields grey out to say so,
 * but the operator still has to act on that, and closing the dialog to hunt for
 * the stop button and coming back is exactly where "I change it and nothing
 * happens" comes from. `editable` flips on the reload, so the form already open
 * becomes writable in place — and nothing is re-seeded, so a name typed before
 * pressing this survives.
 */
async function stopToEdit() {
  busy.value = true
  error.value = ''
  try {
    await store.stop(id.value, t('bots.stoppedToEdit'))
    await load()
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

async function act(action: 'paper' | 'live' | 'stop') {
  busy.value = true
  error.value = ''
  canSwitchPolicy.value = false
  if (action !== 'stop') lastAction.value = action
  try {
    if (action === 'stop') await store.stop(id.value, t('bots.stoppedByHand'))
    else await store.start(id.value, action)
    await load()
  } catch (e: any) {
    if (e?.data?.gate) {
      gate.value = e.data.gate
      tab.value = 'promotion'
      error.value = t('bots.gateUnmetHere')
    } else if (e?.data?.code === 'unprotected') {
      // **The server's own words, not a canned string.** It knows which half is
      // missing and which of Q37's two questions it was asking; this page
      // knows neither. A hardcoded sentence here is how the panel went on
      // telling operators to "set SL % and TP %" long after a second, better
      // answer existed — and never mentioned it.
      error.value = errorMessage(e)
      // When the script closes its own positions, the operator is one setting
      // away from a bot that works. Offer it here, where they hit the wall.
      canSwitchPolicy.value = Boolean(e.data.can_switch)
    } else {
      error.value = errorMessage(e)
    }
  } finally {
    busy.value = false
  }
}

/** Deleting this bot. The list has the same button; this is where you already are. */
const confirmingDelete = ref(false)

async function remove() {
  busy.value = true
  error.value = ''
  try {
    await store.remove(id.value)
    confirmingDelete.value = false
    navigateTo(localePath('/bots'))
  } catch (e: any) {
    confirmingDelete.value = false
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

/**
 * What this bot *is*, editable. Everything but the strategy version: a version
 * is immutable and is the bot's identity — pointing it at a different script
 * would be a different bot wearing this one's history — while the pair, the
 * timeframe and the levels are settings, and a desk that has to delete a bot to
 * move it from 1h to 4h ends up with a list of near-duplicates.
 *
 * Refused while it is running, and the modal says why. Changing the instrument
 * under a live strategy would leave its state machine describing a market it is
 * no longer trading.
 */
const settings = reactive({
  name: '',
  symbol: '',
  interval: '1h',
  market: 'futures',
  leverage: 1,
  sl_pct: '',
  tp_pct: '',
  exit_policy: 'protected' as ExitPolicy,
  safety_net_pct: '',
})

const editable = computed(() => bot.value?.state === 'draft' || bot.value?.state === 'stopped')

function openSettings() {
  const row = bot.value
  if (!row) return
  settings.name = row.name
  settings.symbol = row.symbol
  settings.interval = row.interval
  settings.market = row.market
  settings.leverage = row.leverage
  settings.sl_pct = row.sl_pct ?? ''
  settings.tp_pct = row.tp_pct ?? ''
  settings.exit_policy = row.exit_policy ?? 'protected'
  settings.safety_net_pct = row.safety_net_pct ?? ''
  editing.value = true
}

async function saveSettings() {
  const row = bot.value
  const name = settings.name.trim()
  const symbol = settings.symbol.trim().toUpperCase()
  if (!row || !name || !symbol) return
  busy.value = true
  error.value = ''
  try {
    const body: Record<string, unknown> = { name }
    // The rest only while it is safe to move them; a running bot may still be
    // renamed, which is the one edit that changes nothing about what it does.
    if (editable.value) {
      Object.assign(body, {
        symbol,
        interval: settings.interval,
        market: settings.market,
        leverage: settings.leverage,
        sl_pct: settings.sl_pct === '' ? null : settings.sl_pct,
        tp_pct: settings.tp_pct === '' ? null : settings.tp_pct,
        exit_policy: settings.exit_policy,
        // Cleared rather than left set when the policy cannot use it: the
        // server drops it anyway, and a net stored under a fixed stop reads on
        // this page as protection that exists.
        safety_net_pct:
          settings.exit_policy === 'strategy_managed' && settings.safety_net_pct !== ''
            ? settings.safety_net_pct
            : null,
      })
    }
    const updated = await api.updateBot(row.id, body)
    bot.value = updated
    store.upsert(updated)
    editing.value = false
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

/**
 * The soak row, ticking. The server sends seconds and the instant the run
 * started; counting from there is what turns "0.5 days" — a number that looks
 * frozen for hours — into minutes that visibly move.
 */
const soakRow = computed(() => gate.value?.rows.find((row) => row.key === 'soak') ?? null)
const soakSince = computed(() => (soakRow.value?.params?.since as string | null) ?? null)
const soakBase = computed(() => Number(soakRow.value?.params?.seconds ?? 0))
const soakRunning = computed(() => Boolean(soakRow.value?.params?.running))
const { seconds: soakSeconds } = useCountdown(soakSince, soakBase, soakRunning)
const soakRequired = computed(() => Number(soakRow.value?.params?.required_seconds ?? 0))
const soakRemaining = computed(() => Math.max(0, soakRequired.value - soakSeconds.value))

/**
 * What a row *measures*, in the reader's language.
 *
 * The server's English sentence is the fallback, never the first choice: a gate
 * nobody on this platform can read is a gate they click past. The soak row is
 * the one that is recomputed here rather than rendered, because it is counting.
 */
function measured(row: PromotionRow): string {
  if (row.key === 'soak') return formatDuration(soakSeconds.value)
  const key = `bots.gate.measured.${row.key}`
  return te(key) ? t(key, row.params as Record<string, unknown>) : row.measured
}

function requirement(row: PromotionRow): string {
  const key = `bots.gate.requirement.${row.key}`
  return te(key) ? t(key) : row.requirement
}

function threshold(row: PromotionRow): string {
  if (row.key === 'soak') return formatDuration(Number(row.params?.required_seconds ?? 0))
  const key = `bots.gate.threshold.${row.key}`
  return te(key) ? t(key, row.params as Record<string, unknown>) : row.threshold
}

async function acknowledgeAdapters(on: boolean) {
  busy.value = true
  error.value = ''
  try {
    const payload = await api.acknowledgeAdapters(id.value, on)
    gate.value = payload.gate
    await load()
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

/** Accounts that are active *and* opted in to bot orders — the real fan-out set. */
const eligible = computed(() => reach.value.filter((row) => row.eligible))

/**
 * The gate's two switches. Both post and take the gate straight back, so the
 * table redraws from the server's arithmetic rather than the browser's guess at
 * what waiving a row would do to `ready`.
 */
async function setGate(body: { enforced?: boolean; waive?: string; on?: boolean }) {
  busy.value = true
  error.value = ''
  try {
    gate.value = (await api.setBotGate(id.value, body)).gate
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

watch(tab, (value) => {
  if (value === 'source') loadSource()
})

onMounted(load)
</script>

<template>
  <div class="max-w-[100rem] mx-auto p-3 sm:p-4 lg:p-6 space-y-4 sm:space-y-5">
    <div v-if="loading" class="space-y-3">
      <div class="skeleton h-20" />
      <div class="skeleton h-64" />
    </div>

    <template v-else-if="bot">
      <header class="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div class="min-w-0 space-y-1.5">
          <NuxtLink
            :to="localePath('/bots')"
            class="text-tick text-ink-faint hover:text-ink transition-colors inline-flex items-center gap-1"
          >
            <UiIcon name="arrowRight" :size="12" class="rotate-180" />
            {{ t('bots.title') }}
          </NuxtLink>
          <div class="flex items-center gap-2 flex-wrap">
            <h1 class="text-xl font-display">{{ bot.name }}</h1>
            <button
              class="btn-quiet btn-icon text-ink-faint hover:text-ink shrink-0"
              :aria-label="t('bots.editBot')"
              :title="t('bots.editBot')"
              @click="openSettings"
            >
              <UiIcon name="edit" :size="13" />
            </button>
            <UiBadge :tone="TONE[bot.state]" dot>{{ t(`bots.state.${bot.state}`) }}</UiBadge>
            <UiBadge v-if="bot.dry_run && bot.state !== 'draft'" tone="neutral">
              {{ t('bots.dryRun') }}
            </UiBadge>
          </div>
          <!-- The same line the modal edits, so it is the thing you press to
               edit it. Everything but the version, which is the bot's identity. -->
          <button
            class="text-xs text-ink-muted num leading-relaxed text-start hover:text-ink transition-colors"
            :title="t('bots.editBot')"
            @click="openSettings"
          >
            {{ bot.strategy_name }} · v{{ bot.version }} · {{ bot.symbol }} {{ bot.interval }} ·
            {{ bot.leverage }}×
            <template v-if="bot.sl_pct"> · SL {{ bot.sl_pct }}%</template>
            <template v-if="bot.tp_pct"> · TP {{ bot.tp_pct }}%</template>
          </button>
        </div>

        <div class="flex items-center gap-2 shrink-0">
          <button
            v-if="bot.state === 'draft' || bot.state === 'stopped'"
            class="btn-info btn-sm"
            :disabled="busy"
            @click="act('paper')"
          >
            <UiIcon name="play" :size="14" />
            {{ t('bots.startPaper') }}
          </button>
          <button
            v-if="bot.state === 'paper'"
            class="btn-ok btn-sm"
            :disabled="busy || gate?.ready === false"
            :title="gate?.ready === false ? t('bots.gateBlocks') : ''"
            @click="act('live')"
          >
            {{ t('bots.goLive') }}
          </button>
          <button
            v-if="bot.state === 'paper' || bot.state === 'live'"
            class="btn-warn btn-sm"
            :disabled="busy"
            @click="act('stop')"
          >
            <UiIcon name="pause" :size="14" />
            {{ t('bots.stop.action') }}
          </button>
          <button
            class="btn-quiet btn-sm btn-icon text-ink-muted hover:text-short"
            :disabled="busy || bot.state === 'paper' || bot.state === 'live'"
            :aria-label="t('bots.deleteBot')"
            :title="
              bot.state === 'paper' || bot.state === 'live'
                ? t('bots.deleteBotRunning')
                : t('bots.deleteBot')
            "
            @click="confirmingDelete = true"
          >
            <UiIcon name="trash" :size="15" />
          </button>
        </div>
      </header>

      <div v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">
        <p>{{ error }}</p>
        <!-- The way out, where the wall is. Only when the script really does
             close its own positions — offering it otherwise would swap one
             refusal for a bot that opens a trade nothing ever closes. -->
        <button
          v-if="canSwitchPolicy"
          class="btn-brand btn-sm mt-2"
          :disabled="busy"
          @click="switchToStrategyExits"
        >
          {{ t('bots.exitPolicy.switchAndStart') }}
        </button>
      </div>

      <!-- Why this bot would place no order if it signalled one. Shown standing,
           not only at the Live button: the server's refusal guards `live` only,
           so a paper bot with this gap starts, warms up, evaluates every bar and
           routes nothing — which on this page is indistinguishable from a quiet
           market, and is what "nothing changes" looks like from the outside. -->
      <div
        v-if="bot.protection_gap && !error"
        class="alert px-3 py-2.5 text-xs leading-relaxed"
      >
        <p>{{ bot.protection_gap }}</p>
        <button
          v-if="bot.can_switch_policy"
          class="btn-brand btn-sm mt-2"
          :disabled="busy"
          @click="switchToStrategyExits"
        >
          {{ t('bots.exitPolicy.switchAndStart') }}
        </button>
      </div>

      <div
        v-if="bot.state === 'stopped' && run?.stop_reason"
        class="alert px-3 py-2.5 text-xs leading-relaxed"
      >
        <strong>{{ t(`bots.stop.${run.stop_reason}`, run.stop_reason) }}</strong>
        <span v-if="run.stop_detail"> — {{ run.stop_detail }}</span>
        <!-- Named when a person pressed it; silent when the platform did, which
             is the difference an operator reading this at 03:00 needs. -->
        <span v-if="run.stopped_by"> · {{ t('bots.stoppedBy', { name: run.stopped_by }) }}</span>
        <p class="text-ink-muted mt-1">{{ t('bots.noAutoResume') }}</p>
      </div>

      <!-- The run's own counters. Every one of these is a gate input. -->
      <div v-if="run" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <UiStat :label="t('bots.barsEvaluated')" :value="String(run.bars_evaluated)" />
        <UiStat
          :label="t('bots.lastBar')"
          :value="
            (latestBar?.bar_time ?? run.last_bar_time)
              ? dateTime(new Date(((latestBar?.bar_time ?? run.last_bar_time) as number) * 1000).toISOString())
              : '—'
          "
        />
        <UiStat :label="t('bots.divergences')" :value="String(run.divergences)" :tone="run.divergences ? 'short' : 'ok'" />
        <UiStat
          :label="t('bots.feedGaps')"
          :value="`${run.feed_gaps_repaired}/${run.feed_gaps}`"
          :tone="run.feed_gaps > run.feed_gaps_repaired ? 'signal' : undefined"
        />
        <UiStat :label="t('bots.restarts')" :value="String(run.recoveries)" />
        <UiStat :label="t('bots.startedByLabel')" :value="run.started_by || '—'" />
        <UiStat :label="t('bots.feed')" :value="run.feed_transport || run.feed_source || '—'" />
      </div>

      <!-- Nine tabs is a lot, so they scroll rather than wrap into three rows
           that push the content off a phone screen. Order is by how often they
           are opened: the log first, because "what is it doing" is the question
           that brings anyone here, and manual control second, because the
           question after it is "and is that what the chart says". The labels
           are never clipped — a tab reading "Prope…" is a tab nobody can
           choose between. -->
      <div class="overflow-x-auto -mx-1 px-1">
        <UiSegmented
          v-model="tab"
          class="min-w-max"
          :block="false"
          :options="[
            { value: 'journal', label: t('bots.tab.journal') },
            { value: 'control', label: t('bots.tab.control') },
            { value: 'chart', label: t('bots.tab.chart') },
            { value: 'logic', label: t('bots.tab.logic') },
            { value: 'activity', label: t('bots.tab.activity') },
            { value: 'inputs', label: t('bots.tab.inputs') },
            { value: 'properties', label: t('bots.tab.properties') },
            { value: 'promotion', label: t('bots.tab.promotion') },
            { value: 'source', label: t('bots.tab.source') },
          ]"
        />
      </div>

      <!-- The commonest reason a working bot does nothing: no account has
           opted in to bot orders. That switch defaults off, and a page that
           did not say so left the operator debugging the strategy. -->
      <div
        v-if="bot.state !== 'draft' && !eligible.length"
        class="alert px-3 py-2.5 text-xs leading-relaxed flex flex-wrap items-center gap-x-3 gap-y-1.5"
      >
        <UiIcon name="alert" :size="14" class="shrink-0" />
        <span>{{ t('bots.noBotAccounts') }}</span>
        <NuxtLink :to="localePath('/accounts')" class="text-brand hover:underline">
          {{ t('bots.openAccounts') }}
        </NuxtLink>
      </div>
      <p
        v-else-if="bot.state !== 'draft'"
        class="text-tick text-ink-faint leading-relaxed px-1"
      >
        {{ t('bots.reachesN', { n: eligible.length, total: reach.length }) }}
        <span class="num">{{ eligible.map((row) => row.label).join(', ') }}</span>
      </p>

      <!-- The log. What it was thinking, bar by bar — including the bars where
           the answer was "nothing", which is most of them. -->
      <BotsBotJournal v-if="tab === 'journal'" :bot-id="id" :interval="bot.interval" />

      <!-- Manual control (Q41): where the operator does by hand what the
           strategy and the chart disagree about, with everything the decision
           needs on the same screen as the buttons. -->
      <BotsBotDesk v-else-if="tab === 'control'" :bot-id="id" />

      <!-- The chart, and the activity log beside it. Two halves of one
           question: the marks say where the strategy would have traded, the
           list says which accounts a routed order actually reached, and on a
           wide screen they are one glance apart rather than one tab apart. -->
      <div v-else-if="tab === 'chart'" class="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <BotsBotChart :bot-id="id" :interval="bot.interval" />
        <BotsBotActivity :bot-id="id" :intent="latestIntent" :run="run" compact />
      </div>

      <!-- What makes it trade, in the script's own words. -->
      <BotsBotLogic v-else-if="tab === 'logic'" :bot-id="id" />

      <!-- Activity: what the bot decided, and what every account gave back. -->
      <BotsBotActivity
        v-else-if="tab === 'activity'"
        :bot-id="id"
        :intent="latestIntent"
        :run="run"
      />

      <!-- Inputs: the script's own settings, and the one editable tab whose
           values reach live untouched. Its own component for the same reasons
           the Properties tab is: it loads, saves and can be refused. -->
      <BotsStrategyInputs
        v-else-if="tab === 'inputs'"
        :bot-id="id"
        :running="bot.state === 'paper' || bot.state === 'live'"
      />

      <!-- Properties: the backtest's model of a broker, per bot. Its own
           component because it owns a draft, a save and a validation round
           trip, none of which the read-only tabs around it have. -->
      <BotsStrategyProperties v-else-if="tab === 'properties'" :bot-id="id" />

      <UiCard
        v-else-if="tab === 'promotion'"
        :title="t('bots.promotion')"
        :hint="t('bots.promotionHint')"
        flush
        :tone="gate?.ready ? 'ok' : 'default'"
      >
        <div v-if="gate">
          <!-- The master switch. On is the platform's answer; off is the
               admin's, and it is stored on the bot so a promotion that skipped
               the numbers is answerable afterwards. -->
          <div class="px-3 py-3 border-b border-line space-y-2">
            <UiSwitch
              :model-value="gate.enforced"
              :label="t('bots.gate.enforceLabel')"
              :hint="t('bots.gate.enforceHint')"
              :disabled="busy"
              @update:model-value="setGate({ enforced: $event })"
            />
            <p v-if="!gate.enforced" class="alert px-3 py-2 text-xs leading-relaxed">
              {{ t('bots.gate.offWarning') }}
              <span v-if="!gate.measured_ready"> {{ t('bots.gate.offUnmet') }}</span>
            </p>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="label">
                  <th class="text-start px-3 py-2 w-8" />
                  <th class="text-start px-3 py-2">{{ t('bots.requirement') }}</th>
                  <th class="text-start px-3 py-2">{{ t('bots.threshold') }}</th>
                  <th class="text-start px-3 py-2">{{ t('bots.measured') }}</th>
                  <th class="text-end px-3 py-2">{{ t('bots.gate.required') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line">
                <tr v-for="row in gate.rows" :key="row.key" :class="row.waived ? 'opacity-60' : ''">
                  <td class="px-3 py-2 align-top">
                    <UiIcon
                      :name="row.met ? 'check' : 'alert'"
                      :size="14"
                      :class="row.met ? 'text-ok' : row.waived ? 'text-ink-faint' : 'text-signal'"
                    />
                  </td>
                  <td class="px-3 py-2 leading-relaxed align-top">
                    {{ requirement(row) }}
                    <!-- The one row nothing can measure from inside, made
                         tickable here. A gate that can only be cleared from a
                         shell is a gate people route around. -->
                    <label
                      v-if="row.actionable === 'acknowledge_adapters'"
                      class="mt-1.5 flex items-start gap-2 text-xs text-ink-muted cursor-pointer select-none"
                    >
                      <input
                        type="checkbox"
                        class="accent-brand mt-0.5"
                        :checked="row.met"
                        :disabled="busy"
                        @change="acknowledgeAdapters(($event.target as HTMLInputElement).checked)"
                      />
                      <span>{{ t('bots.gate.adaptersConfirm') }}</span>
                    </label>
                    <p
                      v-if="row.actionable === 'acknowledge_adapters' && row.params?.by"
                      class="text-tick text-ink-faint mt-1 num"
                    >
                      {{ t('bots.gate.adaptersBy', { by: row.params.by, at: dateTime(String(row.params.at)) }) }}
                    </p>
                  </td>
                  <td class="px-3 py-2 num text-ink-muted align-top">{{ threshold(row) }}</td>
                  <td
                    class="px-3 py-2 num align-top"
                    :class="row.met ? 'text-ok' : row.waived ? 'text-ink-faint' : 'text-signal'"
                  >
                    {{ measured(row) }}
                    <span
                      v-if="row.key === 'soak' && !row.met && soakRunning"
                      class="block text-tick text-ink-faint mt-0.5"
                    >
                      {{ t('bots.gate.soakRemaining', { left: formatDuration(soakRemaining) }) }}
                    </span>
                  </td>
                  <!-- Per row, the same decision the master switch makes for
                       all of them. Every row is waivable: with the whole gate
                       switchable off, a shorter list of "the ones you may skip"
                       would be a rule the operator can already step around. -->
                  <td class="px-3 py-2 align-top text-end">
                    <label class="inline-flex items-center gap-1.5 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        class="accent-brand"
                        :checked="!row.waived"
                        :disabled="busy || !gate.enforced"
                        @change="setGate({ waive: row.key, on: !($event.target as HTMLInputElement).checked })"
                      />
                      <span class="sr-only">{{ t('bots.gate.requiredFor', { row: requirement(row) }) }}</span>
                    </label>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="px-3 py-2.5 text-tick text-ink-faint leading-relaxed border-t border-line">
            {{ t('bots.gateFootnote') }}
          </p>
        </div>
      </UiCard>

      <!-- The exact source this bot is running. Read-only on purpose: a version
           is immutable, so editing here would silently be editing a new one. -->
      <UiCard v-else-if="tab === 'source'" :hint="t('bots.sourceHint')" flush>
        <BotsPineEditor
          v-if="sourceOf"
          :model-value="sourceOf"
          readonly
          :min-rows="24"
          @update:model-value="() => {}"
        />
        <UiEmpty v-else icon="logs" :title="t('bots.noSource')" />
      </UiCard>

      <!-- Everything this bot is, except the version it pins. A version is
           immutable and is the bot's identity; the pair, the timeframe and the
           levels are settings, and a desk that has to delete a bot to move it
           from 1h to 4h ends up with a list of near-duplicates. -->
      <UiModal v-model="editing" :title="t('bots.editBot')">
        <div class="space-y-4">
          <label class="block space-y-1.5">
            <span class="label">{{ t('bots.botName') }}</span>
            <input v-model="settings.name" class="field" autofocus />
          </label>

          <div v-if="!editable" class="alert px-3 py-2 text-xs leading-relaxed">
            <p>{{ t('bots.editLockedRunning') }}</p>
            <!-- The way out, in the dialog that is refusing. -->
            <button class="btn-brand btn-sm mt-2" :disabled="busy" @click="stopToEdit">
              {{ t('bots.stopToEdit') }}
            </button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label class="block space-y-1.5">
              <span class="label">{{ t('terminal.symbol') }}</span>
              <UiSymbolPicker v-model="settings.symbol" :disabled="!editable" />
            </label>
            <label class="block space-y-1.5">
              <span class="label">{{ t('bots.interval') }}</span>
              <select v-model="settings.interval" class="field" :disabled="!editable">
                <option v-for="value in INTERVALS" :key="value">{{ value }}</option>
              </select>
            </label>
            <label class="block space-y-1.5">
              <span class="label">{{ t('bots.market') }}</span>
              <select v-model="settings.market" class="field" :disabled="!editable">
                <option value="futures">{{ t('market.futures') }}</option>
                <option value="spot">{{ t('market.spot') }}</option>
              </select>
            </label>
            <label class="block space-y-1.5">
              <span class="label">{{ t('ticket.leverage') }}</span>
              <input
                v-model.number="settings.leverage"
                type="number"
                min="1"
                max="125"
                class="field num"
                :disabled="!editable"
              />
            </label>
            <label class="col-span-2 block space-y-1.5">
              <span class="label">{{ t('ticket.exitPolicy.label') }}</span>
              <select v-model="settings.exit_policy" class="field" :disabled="!editable">
                <option value="protected">{{ t('ticket.exitPolicy.protected') }}</option>
                <option value="strategy_managed">{{ t('ticket.exitPolicy.managed') }}</option>
              </select>
              <p class="text-tick text-ink-faint leading-relaxed">
                {{
                  settings.exit_policy === 'strategy_managed'
                    ? t('bots.exitPolicy.managedHint')
                    : t('bots.exitPolicy.protectedHint')
                }}
              </p>
            </label>
            <label class="block space-y-1.5">
              <span class="label">{{ t('ticket.stopLoss') }} %</span>
              <input
                v-model="settings.sl_pct"
                type="number"
                step="0.01"
                min="0"
                class="field num"
                placeholder="—"
                :disabled="!editable"
              />
            </label>
            <label class="block space-y-1.5">
              <span class="label">{{ t('ticket.takeProfit') }} %</span>
              <input
                v-model="settings.tp_pct"
                type="number"
                step="0.01"
                min="0"
                class="field num"
                placeholder="—"
                :disabled="!editable"
              />
            </label>
            <label
              v-if="settings.exit_policy === 'strategy_managed'"
              class="col-span-2 block space-y-1.5"
            >
              <span class="label">{{ t('ticket.safetyNet.label') }}</span>
              <input
                v-model="settings.safety_net_pct"
                type="number"
                step="0.01"
                min="0"
                class="field num"
                :placeholder="t('ticket.safetyNet.placeholder')"
                :disabled="!editable"
              />
              <p class="text-tick text-ink-faint leading-relaxed">
                {{ t('ticket.safetyNet.hint') }}
              </p>
            </label>
          </div>

          <p class="text-tick text-ink-faint leading-relaxed">
            {{ t('bots.editVersionFixed', { name: bot.strategy_name, n: bot.version }) }}
          </p>
        </div>
        <template #footer>
          <button class="btn-ghost btn-sm" @click="editing = false">
            {{ t('common.cancel') }}
          </button>
          <button
            class="btn-brand btn-sm"
            :disabled="busy || !settings.name.trim() || !settings.symbol.trim()"
            @click="saveSettings"
          >
            {{ t('common.save') }}
          </button>
        </template>
      </UiModal>

      <UiModal v-model="confirmingDelete" :title="t('bots.deleteBotTitle')" size="sm">
        <p class="text-sm leading-relaxed">
          {{ t('bots.deleteBotConfirm', { name: bot.name }) }}
        </p>
        <template #footer>
          <button class="btn-ghost btn-sm" @click="confirmingDelete = false">
            {{ t('common.cancel') }}
          </button>
          <button class="btn-danger btn-sm" :disabled="busy" @click="remove">
            {{ t('common.delete') }}
          </button>
        </template>
      </UiModal>
    </template>
  </div>
</template>
