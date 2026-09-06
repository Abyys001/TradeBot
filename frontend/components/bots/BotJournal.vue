<script setup lang="ts">
/**
 * The bot's log: what it was thinking, bar by bar.
 *
 * The action list answers "what did it do". On most bars the answer is
 * "nothing", and *why* nothing is the question an operator actually has at
 * 03:00 — the condition was not met, the position was already right, the gate
 * was closed, the feed had just been repaired. This is that.
 *
 * Every line is rendered from a code and parameters the server derived from
 * stored rows (`apps/bots/narrate.py`). Nothing is invented here and nothing is
 * a server-side English sentence, which is what lets it read in six languages.
 *
 * Quiet bars are foldable rather than absent. Hiding them would make the log
 * look like the bot was idle for hours; folding them says "it was watching, and
 * here is the count", which is the true statement.
 */
const props = defineProps<{ botId: number; interval: string }>()

const { t, te } = useI18n()
const api = useApi()
const { dateTime, money } = useFormat()

const events = ref<JournalEvent[]>([])
const loading = ref(true)
const error = ref('')
const showQuiet = ref(true)
const auto = ref(true)

let timer: ReturnType<typeof setInterval> | null = null

/** A bar where nothing changed. The bulk of any log, and worth folding away. */
function isQuiet(event: JournalEvent): boolean {
  return event.kind === 'bar' && (event.code.startsWith('watching_') || event.code.startsWith('holding'))
}

const visible = computed(() =>
  showQuiet.value ? events.value : events.value.filter((event) => !isQuiet(event)),
)

const quietCount = computed(() => events.value.filter(isQuiet).length)

const LEVEL_CLASS: Record<string, string> = {
  info: 'text-ink-muted',
  signal: 'text-brand',
  ok: 'text-ok',
  warn: 'text-signal',
  danger: 'text-short',
}

const LEVEL_DOT: Record<string, string> = {
  info: 'bg-ink-faint',
  signal: 'bg-brand',
  ok: 'bg-ok',
  warn: 'bg-signal',
  danger: 'bg-short',
}

/**
 * The sentence. Falls back to the code itself rather than rendering an empty
 * line: a narration key nobody has written yet should look like a missing
 * translation, not like the bot having no thought.
 */
function line(event: JournalEvent): string {
  const key = `bots.journal.${event.code}`
  const params = {
    ...event.params,
    close: event.params.close ? money(event.params.close) : '',
    plots: plots(event),
    side: event.params.side ? t(`side.${event.params.side}`) : '',
    was: event.params.was ? t(`side.${event.params.was}`) : '',
    reason: event.params.reason || '',
  }
  return te(key) ? t(key, params) : event.code
}

/** `RSI 62.4 · EMA9 104,220` — the script's own values, at reading precision. */
function plots(event: JournalEvent): string {
  const rows = (event.params.plots ?? []) as { name: string; value: string }[]
  if (!rows.length) return ''
  return rows.map((row) => `${row.name} ${row.value}`).join(' · ')
}

/** The failed legs a `legsFailed` event names, as one readable list. */
function accountList(event: JournalEvent): string {
  const rows = (event.params.accounts ?? []) as { label: string; code: string }[]
  return rows.map((row) => (row.code ? `${row.label} (${row.code})` : row.label)).join(', ')
}

async function load(quiet = false) {
  if (!quiet) loading.value = true
  try {
    const payload = await api.botJournal(props.botId, 300)
    events.value = payload.events
    error.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

/**
 * Refresh on the bot's own cadence, roughly. A 1m bot gets a new line a minute;
 * polling faster than that is a request per nothing, and slower makes the log
 * look stalled while the chart beside it moves.
 */
const POLL_MS: Record<string, number> = {
  '1m': 20_000,
  '5m': 30_000,
  '15m': 60_000,
  '1h': 60_000,
  '4h': 120_000,
  '1d': 300_000,
}

function schedule() {
  if (timer) clearInterval(timer)
  if (!auto.value) return
  timer = setInterval(() => load(true), POLL_MS[props.interval] ?? 60_000)
}

onMounted(() => {
  load()
  schedule()
})
watch(auto, schedule)
watch(() => props.botId, () => load())
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <UiCard :title="t('bots.journalTitle')" :hint="t('bots.journalHint')" flush>
    <div class="px-3 py-2.5 border-b border-line flex flex-wrap items-center gap-x-4 gap-y-2">
      <label class="flex items-center gap-2 text-xs text-ink-muted cursor-pointer select-none">
        <input v-model="showQuiet" type="checkbox" class="accent-brand" />
        {{ t('bots.showQuietBars', { n: quietCount }) }}
      </label>
      <label class="flex items-center gap-2 text-xs text-ink-muted cursor-pointer select-none">
        <input v-model="auto" type="checkbox" class="accent-brand" />
        {{ t('bots.autoRefresh') }}
      </label>
      <button class="btn-quiet btn-sm ms-auto" :disabled="loading" @click="load()">
        <UiIcon name="refresh" :size="13" />
        {{ t('common.refresh') }}
      </button>
    </div>

    <p v-if="error" class="px-3 py-3 text-xs text-short">{{ error }}</p>
    <div v-else-if="loading" class="p-3 space-y-2">
      <div v-for="n in 6" :key="n" class="skeleton h-8" />
    </div>
    <UiEmpty
      v-else-if="!visible.length"
      icon="logs"
      :title="t('bots.noJournal')"
      :body="t('bots.noJournalBody')"
    />
    <ul v-else class="divide-y divide-line max-h-[38rem] overflow-y-auto">
      <li
        v-for="(event, index) in visible"
        :key="`${event.at}-${event.code}-${index}`"
        class="px-3 py-2 flex items-start gap-2.5"
      >
        <span
          class="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
          :class="LEVEL_DOT[event.level] ?? 'bg-ink-faint'"
        />
        <span class="num text-tick text-ink-faint w-24 shrink-0 mt-px">
          {{ dateTime(new Date(event.at * 1000).toISOString()) }}
        </span>
        <span class="text-xs leading-relaxed min-w-0" :class="LEVEL_CLASS[event.level] ?? ''">
          {{ line(event) }}
          <span v-if="event.code === 'legsFailed'" class="text-ink-faint num">
            — {{ accountList(event) }}
          </span>
        </span>
      </li>
    </ul>
  </UiCard>
</template>
