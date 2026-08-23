<script setup lang="ts">
/**
 * "Download the statement" — but not before asking which period.
 *
 * The period is a question rather than a default because the file leaves the
 * platform: it goes to whoever put the capital in, and a PDF that silently
 * covers "everything, ever" when they asked about last month is a document
 * nobody can check. So the dialog always shows the two dates it is about to
 * send, presets fill them in rather than replacing them, and the summary line
 * under them restates the window in words before anything is generated.
 *
 * The dates are calendar days in the operator's own timezone and inclusive at
 * both ends, which is how a person reads "1st to 31st". The server turns the
 * end into the exclusive midnight after it — see `statement_window`.
 *
 * The language is asked the same way and for the same reason: the file is read
 * by whoever put the capital in, who does not necessarily read the language the
 * panel happens to be in. It opens on the panel's language because that is the
 * likelier answer, not because it is the only one.
 */
const props = defineProps<{ accountId: number; label: string; connectedAt: string }>()
const open = defineModel<boolean>({ required: true })

const { t, locale } = useI18n()
const api = useApi()
const { dateTime } = useFormat()

const from = ref('')
const to = ref('')
const busy = ref(false)
const error = ref('')

/** The document's own language. `en` and `fa` are what the server issues. */
const LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'fa', name: 'فارسی' },
] as const

const lang = ref<'en' | 'fa'>(locale.value === 'fa' ? 'fa' : 'en')

/** Named in its own language on the button that generates it, so the footer
 * note says which of the two files is about to be produced. */
const languageName = computed(
  () => LANGUAGES.find((option) => option.code === lang.value)?.name ?? '',
)

/** `YYYY-MM-DD` in local time. `toISOString` would shift the day in half the world. */
function iso(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function daysAgo(n: number): Date {
  const date = new Date()
  date.setDate(date.getDate() - n)
  return date
}

type Preset = { key: string; range: () => [string, string] }

const PRESETS: Preset[] = [
  { key: 'd7', range: () => [iso(daysAgo(6)), iso(new Date())] },
  { key: 'd30', range: () => [iso(daysAgo(29)), iso(new Date())] },
  {
    key: 'month',
    range: () => {
      const now = new Date()
      return [iso(new Date(now.getFullYear(), now.getMonth(), 1)), iso(now)]
    },
  },
  {
    key: 'lastMonth',
    range: () => {
      const now = new Date()
      return [
        iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
        iso(new Date(now.getFullYear(), now.getMonth(), 0)),
      ]
    },
  },
  {
    key: 'quarter',
    range: () => {
      const now = new Date()
      return [iso(new Date(now.getFullYear(), now.getMonth() - 3, now.getDate())), iso(now)]
    },
  },
  {
    key: 'ytd',
    range: () => [iso(new Date(new Date().getFullYear(), 0, 1)), iso(new Date())],
  },
  // Deliberately last and deliberately explicit: "everything" is a real answer,
  // but it should be one the operator picked, not one they fell into.
  { key: 'all', range: () => [iso(new Date(props.connectedAt)), iso(new Date())] },
]

/** Which preset the two dates currently match, if any — so the chip stays lit. */
const active = computed(
  () => PRESETS.find((preset) => preset.range().join() === `${from.value},${to.value}`)?.key ?? '',
)

function apply(preset: Preset) {
  ;[from.value, to.value] = preset.range()
}

const today = iso(new Date())
const connectedDay = computed(() => iso(new Date(props.connectedAt)))

/** The one thing that must not reach the server: a period that ends first. */
const backwards = computed(() => Boolean(from.value && to.value && from.value > to.value))

/** Named rather than assumed: the operator reads this before pressing Download. */
const summary = computed(() => {
  if (backwards.value) return ''
  if (!from.value && !to.value) return t('accounts.statement.summaryAll')
  if (!from.value) return t('accounts.statement.summaryUntil', { to: to.value })
  if (!to.value) return t('accounts.statement.summaryFrom', { from: from.value })
  return t('accounts.statement.summaryRange', { from: from.value, to: to.value })
})

/**
 * The window can legitimately start before the account existed — a whole
 * calendar month covers an account connected halfway through it — so this is a
 * note, not a block.
 */
const beforeConnection = computed(
  () => Boolean(from.value) && from.value < connectedDay.value,
)

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = ''
  if (!from.value && !to.value) apply(PRESETS[1])
})

async function download() {
  if (backwards.value) return
  busy.value = true
  error.value = ''
  try {
    const { blob, filename } = await api.accountStatement(
      props.accountId,
      from.value,
      to.value,
      lang.value,
    )
    // Handing the file over is a link click; the object URL is revoked on the
    // next frame, because a PDF held alive here is held for the whole session.
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
    open.value = false
  } catch (e: any) {
    // The response is a blob, so a DRF error arrives as one and `errorMessage`
    // would report "[object Blob]". Read it back out before giving up on it.
    error.value = (await blobError(e)) || errorMessage(e)
  } finally {
    busy.value = false
  }
}

async function blobError(e: any): Promise<string> {
  const data = e?.data
  if (!(data instanceof Blob)) return ''
  try {
    const parsed = JSON.parse(await data.text())
    return parsed?.detail ? String(parsed.detail) : ''
  } catch {
    return ''
  }
}
</script>

<template>
  <UiModal v-model="open" :title="t('accounts.statement.title')">
    <form id="statement-period" class="space-y-4" @submit.prevent="download">
      <p class="text-xs text-ink-muted leading-relaxed">
        {{ t('accounts.statement.intro', { label }) }}
      </p>

      <div>
        <span class="label">{{ t('accounts.statement.presets') }}</span>
        <div class="mt-1.5 flex flex-wrap gap-1.5">
          <button
            v-for="preset in PRESETS"
            :key="preset.key"
            type="button"
            class="btn-sm border transition-colors"
            :class="
              active === preset.key
                ? 'bg-brand-dim text-brand border-brand/60'
                : 'bg-sunken text-ink-muted border-line hover:text-ink'
            "
            @click="apply(preset)"
          >
            {{ t(`accounts.statement.preset.${preset.key}`) }}
          </button>
        </div>
      </div>

      <div>
        <span class="label">{{ t('accounts.statement.language') }}</span>
        <div class="mt-1.5 flex flex-wrap gap-1.5">
          <button
            v-for="option in LANGUAGES"
            :key="option.code"
            type="button"
            :aria-pressed="lang === option.code"
            class="btn-sm border transition-colors"
            :class="
              lang === option.code
                ? 'bg-brand-dim text-brand border-brand/60'
                : 'bg-sunken text-ink-muted border-line hover:text-ink'
            "
            :lang="option.code"
            :dir="option.code === 'fa' ? 'rtl' : 'ltr'"
            @click="lang = option.code"
          >
            {{ option.name }}
          </button>
        </div>
        <p class="mt-1.5 text-xs text-ink-faint leading-relaxed">
          {{ t('accounts.statement.languageHint') }}
        </p>
      </div>

      <div class="grid sm:grid-cols-2 gap-4">
        <UiField
          v-slot="{ id }"
          :label="t('accounts.statement.from')"
          :hint="t('accounts.statement.fromHint')"
        >
          <input :id="id" v-model="from" type="date" class="field" :max="today" />
        </UiField>
        <UiField
          v-slot="{ id }"
          :label="t('accounts.statement.to')"
          :hint="t('accounts.statement.toHint')"
          :error="backwards ? t('accounts.statement.backwards') : ''"
        >
          <input :id="id" v-model="to" type="date" class="field" :max="today" />
        </UiField>
      </div>

      <p v-if="summary" class="rounded-lg bg-sunken border border-line p-3 text-xs leading-relaxed">
        <UiIcon name="ledger" :size="13" class="inline-block me-1.5 -mt-0.5 text-brand" />
        {{ summary }}
      </p>

      <p v-if="beforeConnection" class="text-xs text-ink-faint leading-relaxed">
        {{ t('accounts.statement.beforeConnection', { when: dateTime(connectedAt) }) }}
      </p>

      <p v-if="error" class="alert p-3 text-xs">{{ error }}</p>
    </form>

    <template #footer>
      <div class="flex flex-wrap gap-2 items-center justify-end">
        <p class="text-[0.68rem] text-ink-faint me-auto">
          {{ t('accounts.statement.pdfNote', { language: languageName }) }}
        </p>
        <button class="btn-ghost" type="button" @click="open = false">
          {{ t('common.cancel') }}
        </button>
        <button
          class="btn-brand"
          type="submit"
          form="statement-period"
          :disabled="busy || backwards"
        >
          <UiIcon :name="busy ? 'refresh' : 'download'" :size="14" :class="busy ? 'animate-spin' : ''" />
          {{ busy ? t('accounts.statement.building') : t('accounts.statement.download') }}
        </button>
      </div>
    </template>
  </UiModal>
</template>
