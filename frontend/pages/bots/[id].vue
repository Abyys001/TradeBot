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
const actions = ref<BotAction[]>([])
const gate = ref<PromotionGate | null>(null)
/** Which accounts a fan-out from this bot would actually reach. */
const reach = ref<BotAccountRow[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const tab = ref<
  'journal' | 'chart' | 'logic' | 'activity' | 'inputs' | 'properties' | 'promotion' | 'source'
>('journal')
const editing = ref(false)

useHead({ title: () => bot.value?.name ?? t('bots.title') })

const run = computed(() => store.runs[id.value] ?? runs.value[0] ?? null)

/**
 * How much of the entry a scale-out left running, as a percentage. Read off the
 * action's own intent rather than the bot's current position: the log is a
 * history, and by the time it is read the position has usually moved on.
 */
function remainingPct(action: BotAction): string {
  const fraction = action.intent?.fraction
  if (typeof fraction !== 'string') return ''
  const pct = Number(fraction) * 100
  return Number.isFinite(pct) ? `${Number(pct.toFixed(2))}` : ''
}

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
    const [botRow, runRows, actionRows, gateRows, reachRows] = await Promise.all([
      api.bot(id.value),
      api.botRuns(id.value),
      api.botActions(id.value),
      api.botPromotion(id.value),
      api.botAccounts(id.value),
    ])
    bot.value = botRow
    runs.value = runRows
    actions.value = actionRows
    gate.value = gateRows
    reach.value = reachRows.accounts
    store.upsert(botRow)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function act(action: 'paper' | 'live' | 'stop') {
  busy.value = true
  error.value = ''
  try {
    if (action === 'stop') await store.stop(id.value, t('bots.stoppedByHand'))
    else await store.start(id.value, action)
    await load()
  } catch (e: any) {
    if (e?.data?.gate) {
      gate.value = e.data.gate
      tab.value = 'promotion'
      error.value = t('bots.gateUnmetHere')
    } else {
      error.value = errorMessage(e)
    }
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
        </div>
      </header>

      <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">{{ error }}</p>

      <div
        v-if="bot.state === 'stopped' && run?.stop_reason"
        class="alert px-3 py-2.5 text-xs leading-relaxed"
      >
        <strong>{{ t(`bots.stop.${run.stop_reason}`, run.stop_reason) }}</strong>
        <span v-if="run.stop_detail"> — {{ run.stop_detail }}</span>
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
        <UiStat :label="t('bots.feed')" :value="run.feed_transport || run.feed_source || '—'" />
      </div>

      <!-- Seven tabs is a lot, so they scroll rather than wrap into three rows
           that push the content off a phone screen. Order is by how often they
           are opened: the log first, because "what is it doing" is the question
           that brings anyone here. The labels are never clipped — a tab reading
           "Prope…" is a tab nobody can choose between. -->
      <div class="overflow-x-auto -mx-1 px-1">
        <UiSegmented
          v-model="tab"
          class="min-w-max"
          :block="false"
          :options="[
            { value: 'journal', label: t('bots.tab.journal') },
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

      <!-- The chart, with the script's own indicators and its triggers drawn on
           it. Changing the timeframe here replays for display and never touches
           the running bot. -->
      <BotsBotChart v-else-if="tab === 'chart'" :bot-id="id" :interval="bot.interval" />

      <!-- What makes it trade, in the script's own words. -->
      <BotsBotLogic v-else-if="tab === 'logic'" :bot-id="id" />

      <!-- Activity: what the bot decided, and what every account gave back. -->
      <UiCard v-else-if="tab === 'activity'" flush>
        <div
          v-if="latestIntent"
          class="px-3 py-2.5 border-b border-line text-xs flex items-center gap-2 flex-wrap"
        >
          <UiBadge tone="brand">{{ t('bots.liveIntent') }}</UiBadge>
          <span class="num">
            {{ latestIntent.side ? t(`side.${latestIntent.side}`) : t('bots.flat') }}
            <template v-if="latestIntent.sl_pct"> · SL {{ latestIntent.sl_pct }}%</template>
            <template v-if="latestIntent.tp_pct"> · TP {{ latestIntent.tp_pct }}%</template>
          </span>
          <span class="text-ink-faint">{{ latestIntent.reason }}</span>
        </div>

        <!-- Nothing yet. The bars counter is here rather than in a tab of its
             own: "no actions" and "no bars either" are the same question asked
             twice, and a bot that has evaluated four hundred bars without
             trading is working, not broken. -->
        <UiEmpty
          v-if="!actions.length"
          icon="history"
          :title="t('bots.noActions')"
          :body="
            run
              ? t('bots.noActionsEvaluated', { n: run.bars_evaluated })
              : t('bots.noActionsBody')
          "
        />
        <ul v-else class="divide-y divide-line">
          <li v-for="action in actions" :key="action.id" class="px-3 py-2.5 space-y-1.5">
            <div class="flex items-center gap-2 flex-wrap text-xs">
              <!-- Shadow is neutral, never green: nothing was routed, and an
                   "ok" tick beside a paper decision reads as a fill. -->
              <UiBadge
                :tone="action.action_type === 'shadow' ? 'neutral' : action.ok ? 'ok' : 'short'"
              >
                {{ t(`bots.action.${action.action_type}`) }}
              </UiBadge>
              <!-- What, where and at what. A dry run has no fills behind it, so
                   without these the paper log could say only that something
                   happened at a time — which is most of what a paper run is. -->
              <UiBadge v-if="action.side" :tone="action.side === 'long' ? 'long' : 'short'">
                {{ t(`side.${action.side}`) }}
              </UiBadge>
              <span class="num text-ink-muted">{{ action.symbol }} {{ action.interval }}</span>
              <span v-if="action.price" class="num">@ {{ money(action.price) }}</span>
              <span class="num text-ink-muted">
                {{ dateTime(new Date(action.bar_time * 1000).toISOString()) }}
              </span>
              <span v-if="action.error" class="text-short">{{ action.error }}</span>
              <span v-if="action.action_type === 'shadow'" class="text-ink-faint">
                {{ t('bots.shadowNote') }}
              </span>
              <span v-else-if="remainingPct(action)" class="num text-ink-faint">
                {{ t('bots.stillOpen', { pct: remainingPct(action) }) }}
              </span>
            </div>
            <p v-if="action.reason" class="text-tick text-ink-faint leading-relaxed">
              {{ action.reason }}
            </p>
            <div v-if="action.legs.length" class="flex flex-wrap gap-1.5">
              <UiBadge
                v-for="leg in action.legs"
                :key="leg.account_id"
                :tone="leg.ok ? 'ok' : 'short'"
              >
                {{ leg.account_label || `#${leg.account_id}` }}
                <span v-if="!leg.ok && leg.code"> · {{ leg.code }}</span>
              </UiBadge>
            </div>
          </li>
        </ul>
      </UiCard>

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

          <p v-if="!editable" class="alert px-3 py-2 text-xs leading-relaxed">
            {{ t('bots.editLockedRunning') }}
          </p>

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

    </template>
  </div>
</template>
