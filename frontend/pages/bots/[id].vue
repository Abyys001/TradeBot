<script setup lang="ts">
/**
 * One bot, whole: what it is, what it decided, what came back, and what stands
 * between it and real money.
 *
 * The promotion gate is the page's spine. `paper → live` is not a confirmation
 * dialog — it is nine measurements, and the page shows every one with the
 * number behind it, met or not. A row that cannot be measured from inside
 * (no adapter has been run against a live exchange) is shown as exactly that.
 */
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
const bars = ref<BotBar[]>([])
const gate = ref<PromotionGate | null>(null)
/** Which accounts a fan-out from this bot would actually reach. */
const reach = ref<BotAccountRow[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const tab = ref<
  'journal' | 'chart' | 'logic' | 'activity' | 'bars' | 'properties' | 'promotion' | 'source'
>('journal')
const renaming = ref(false)
const renameTo = ref('')

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

/** The exact source this bot runs — the version it points at, never the latest. */
const sourceOf = ref('')

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
    // The version's own source, not the strategy's newest: a bot points at an
    // immutable version precisely so it cannot change under a running run.
    const strategy = store.strategies.find((row) =>
      row.versions.some((version) => version.id === botRow.strategy_version),
    )
    sourceOf.value =
      strategy?.versions.find((version) => version.id === botRow.strategy_version)?.source ?? ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function loadBars() {
  bars.value = await api.botBars(id.value, 300)
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

function openRename() {
  renameTo.value = bot.value?.name ?? ''
  renaming.value = true
}

/** The name only. A bot's pair, version and levels are what it *is*; those are
 * set once at creation because changing them under a run would silently make it
 * a different bot with the same history. */
async function rename() {
  const name = renameTo.value.trim()
  if (!bot.value || !name || name === bot.value.name) {
    renaming.value = false
    return
  }
  busy.value = true
  error.value = ''
  try {
    const updated = await api.updateBot(bot.value.id, { name })
    bot.value = updated
    store.upsert(updated)
    renaming.value = false
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

watch(tab, (value) => {
  if (value === 'bars' && !bars.value.length) loadBars()
})

onMounted(async () => {
  if (!store.strategies.length) await store.load()
  await load()
})
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
              :aria-label="t('bots.renameBot')"
              :title="t('bots.renameBot')"
              @click="openRename"
            >
              <UiIcon name="edit" :size="13" />
            </button>
            <UiBadge :tone="TONE[bot.state]" dot>{{ t(`bots.state.${bot.state}`) }}</UiBadge>
            <UiBadge v-if="bot.dry_run && bot.state !== 'draft'" tone="neutral">
              {{ t('bots.dryRun') }}
            </UiBadge>
          </div>
          <p class="text-xs text-ink-muted num leading-relaxed">
            {{ bot.strategy_name }} · v{{ bot.version }} · {{ bot.symbol }} {{ bot.interval }} ·
            {{ bot.leverage }}×
            <template v-if="bot.sl_pct"> · SL {{ bot.sl_pct }}%</template>
            <template v-if="bot.tp_pct"> · TP {{ bot.tp_pct }}%</template>
          </p>
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

      <!-- Eight tabs is a lot, so they scroll rather than wrap into three rows
           that push the content off a phone screen. Order is by how often they
           are opened: the log first, because "what is it doing" is the question
           that brings anyone here. -->
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
            { value: 'bars', label: t('bots.tab.bars') },
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

        <UiEmpty
          v-if="!actions.length"
          icon="history"
          :title="t('bots.noActions')"
          :body="t('bots.noActionsBody')"
        />
        <ul v-else class="divide-y divide-line">
          <li v-for="action in actions" :key="action.id" class="px-3 py-2.5 space-y-1.5">
            <div class="flex items-center gap-2 flex-wrap text-xs">
              <UiBadge :tone="action.ok ? 'ok' : 'short'">
                {{ t(`bots.action.${action.action_type}`) }}
              </UiBadge>
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

      <!-- Bars: what the script saw and what it plotted. -->
      <UiCard v-else-if="tab === 'bars'" flush>
        <UiEmpty v-if="!bars.length" icon="chart" :title="t('bots.noBars')" />
        <div v-else class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="label">
                <th class="text-start px-3 py-2">{{ t('bots.barTime') }}</th>
                <th class="text-end px-3 py-2">{{ t('bots.close') }}</th>
                <th class="text-start px-3 py-2">{{ t('bots.intent') }}</th>
                <th class="text-start px-3 py-2">{{ t('bots.plots') }}</th>
                <th class="text-end px-3 py-2">{{ t('bots.evaluated') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="bar in bars" :key="bar.id" :class="{ 'bg-raised': bar.changed }">
                <td class="px-3 py-1.5 num text-ink-muted">
                  {{ dateTime(new Date(bar.bar_time * 1000).toISOString()) }}
                </td>
                <td class="px-3 py-1.5 num text-end">{{ money(bar.close) }}</td>
                <td class="px-3 py-1.5">
                  <UiBadge v-if="bar.intent?.side" :tone="bar.intent.side === 'long' ? 'long' : 'short'">
                    {{ t(`side.${bar.intent.side}`) }}
                  </UiBadge>
                  <span v-else class="text-ink-faint">{{ t('bots.flat') }}</span>
                </td>
                <td class="px-3 py-1.5 num text-ink-muted truncate max-w-xs">
                  {{ Object.entries(bar.plots ?? {}).map(([k, v]) => `${k}=${v}`).join('  ') || '—' }}
                </td>
                <td class="px-3 py-1.5 num text-end text-ink-faint">
                  {{ bar.evaluation_ms === null ? '—' : ms(bar.evaluation_ms) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>

      <!-- The gate. Nine measurements, not a dialog. -->
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
        <div v-if="gate" class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="label">
                <th class="text-start px-3 py-2 w-8" />
                <th class="text-start px-3 py-2">{{ t('bots.requirement') }}</th>
                <th class="text-start px-3 py-2">{{ t('bots.threshold') }}</th>
                <th class="text-start px-3 py-2">{{ t('bots.measured') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              <tr v-for="row in gate.rows" :key="row.key">
                <td class="px-3 py-2 align-top">
                  <UiIcon
                    :name="row.met ? 'check' : 'alert'"
                    :size="14"
                    :class="row.met ? 'text-ok' : 'text-signal'"
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
                <td class="px-3 py-2 num align-top" :class="row.met ? 'text-ok' : 'text-signal'">
                  {{ measured(row) }}
                  <span
                    v-if="row.key === 'soak' && !row.met && soakRunning"
                    class="block text-tick text-ink-faint mt-0.5"
                  >
                    {{ t('bots.gate.soakRemaining', { left: formatDuration(soakRemaining) }) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
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

      <!-- Outside the tab chain on purpose: it is a second card *under* the
           gate, not a ninth tab. The two rows it fires are the only ones on the
           gate that are exercises rather than measurements, and the halt one
           sends real close orders. -->
      <BotsDrillPanel
        v-if="tab === 'promotion'"
        :bot-id="id"
        :running="bot.state === 'paper' || bot.state === 'live'"
        :fired="bot.drills_fired ?? []"
        :halt-drills="run?.halt_drills ?? 0"
        @done="load"
      />

      <UiModal v-model="renaming" :title="t('bots.renameBot')" size="sm">
        <label class="block space-y-1.5">
          <span class="label">{{ t('bots.botName') }}</span>
          <input v-model="renameTo" class="field" autofocus @keyup.enter="rename" />
        </label>
        <template #footer>
          <button class="btn-ghost btn-sm" @click="renaming = false">
            {{ t('common.cancel') }}
          </button>
          <button class="btn-brand btn-sm" :disabled="busy || !renameTo.trim()" @click="rename">
            {{ t('common.save') }}
          </button>
        </template>
      </UiModal>
    </template>
  </div>
</template>
