<script setup lang="ts">
/**
 * What the bot decided, and what every account gave back.
 *
 * Every run's actions, not just the latest one's — the endpoint reads across
 * `run__bot`. A bot restarted this morning did not stop having traded last
 * night, and a log that began at the restart was why this panel read empty on a
 * bot that had been working for days.
 *
 * It lives in two places: its own tab, and beside the chart, where the mark on
 * the candle and the accounts it reached are one glance apart. So it fetches
 * its own rows rather than taking them as a prop — two copies of the list
 * behind one loading state is how the two surfaces start disagreeing about how
 * many trades there were.
 */
const props = defineProps<{
  botId: number
  /** The bar the socket last pushed an intent for, shown above the list. */
  intent?: Record<string, any> | null
  /** The run whose evaluated-bar count answers "is it working at all?". */
  run?: BotRun | null
  /** Beside the chart the list scrolls; in its own tab it runs the page. */
  compact?: boolean
}>()

const { t } = useI18n()
const api = useApi()
const { dateTime, money } = useFormat()

const actions = ref<BotAction[]>([])
const loading = ref(true)
const error = ref('')

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

async function load(quiet = false) {
  if (!quiet) loading.value = true
  try {
    actions.value = await api.botActions(props.botId)
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  void load()
  // Slow on purpose: an action is a routed order, not a bar, and they arrive at
  // human speed. The socket already pushes the live intent above the list.
  timer = setInterval(() => load(true), 30_000)
})
watch(() => props.botId, () => load())
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <UiCard :title="props.compact ? t('bots.tab.activity') : ''" flush>
    <div
      v-if="props.intent"
      class="px-3 py-2.5 border-b border-line text-xs flex items-center gap-2 flex-wrap"
    >
      <UiBadge tone="brand">{{ t('bots.liveIntent') }}</UiBadge>
      <span class="num">
        {{ props.intent.side ? t(`side.${props.intent.side}`) : t('bots.flat') }}
        <template v-if="props.intent.sl_pct"> · SL {{ props.intent.sl_pct }}%</template>
        <template v-if="props.intent.tp_pct"> · TP {{ props.intent.tp_pct }}%</template>
      </span>
      <span class="text-ink-faint">{{ props.intent.reason }}</span>
    </div>

    <p v-if="error" class="px-3 py-3 text-xs text-short">{{ error }}</p>
    <div v-else-if="loading" class="p-3 space-y-2">
      <div v-for="n in 4" :key="n" class="skeleton h-10" />
    </div>
    <!-- Nothing yet. The bars counter is here rather than in a tab of its own:
         "no actions" and "no bars either" are the same question asked twice,
         and a bot that has evaluated four hundred bars without trading is
         working, not broken. -->
    <UiEmpty
      v-else-if="!actions.length"
      icon="history"
      :title="t('bots.noActions')"
      :body="
        props.run ? t('bots.noActionsEvaluated', { n: props.run.bars_evaluated }) : t('bots.noActionsBody')
      "
    />
    <ul v-else class="divide-y divide-line" :class="props.compact ? 'max-h-[34rem] overflow-y-auto' : ''">
      <li v-for="action in actions" :key="action.id" class="px-3 py-2.5 space-y-1.5">
        <div class="flex items-center gap-2 flex-wrap text-xs">
          <!-- Shadow is neutral, never green: nothing was routed, and an "ok"
               tick beside a paper decision reads as a fill. -->
          <UiBadge :tone="action.action_type === 'shadow' ? 'neutral' : action.ok ? 'ok' : 'short'">
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
          <UiBadge v-for="leg in action.legs" :key="leg.account_id" :tone="leg.ok ? 'ok' : 'short'">
            {{ leg.account_label || `#${leg.account_id}` }}
            <span v-if="!leg.ok && leg.code"> · {{ leg.code }}</span>
          </UiBadge>
        </div>
      </li>
    </ul>
  </UiCard>
</template>
