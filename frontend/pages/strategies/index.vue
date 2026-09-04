<script setup lang="ts">
/**
 * Strategies: the scripts, and the editor that checks them.
 *
 * The whole page is one promise — **a script that will not load says why, by
 * name, line and column, before it is saved** (Q24). So validation runs as you
 * type, the errors are a list you can click, and saving a version that does not
 * validate is allowed but visibly marked: a draft you cannot save is a draft
 * you cannot come back to.
 *
 * Deleting cascades to every version — but a version a bot was built from is
 * `PROTECT`ed, so a strategy with bots refuses the delete and names them
 * (server-side, 409). The confirm dialog says the versions go; the banner says
 * which bots stopped it.
 */
const { t } = useI18n()
const api = useApi()
const localePath = useLocalePath()

useHead({ title: t('bots.strategies') })

const strategies = ref<Strategy[]>([])
const selected = ref<Strategy | null>(null)
const source = ref('')
const validation = ref<PineValidation | null>(null)
const checking = ref(false)
const saving = ref(false)
const loading = ref(true)
const error = ref('')
const creating = ref(false)
const newName = ref('')
const confirmingDelete = ref(false)
const deleting = ref(false)
const editor = ref<{ goTo: (line: number, col?: number) => void } | null>(null)

const TEMPLATE = `//@version=5
strategy("New strategy", overlay = true)

fastLen = input.int(9, "Fast", minval = 1)
slowLen = input.int(21, "Slow", minval = 2)

fast = ta.sma(close, fastLen)
slow = ta.sma(close, slowLen)

if ta.crossover(fast, slow)
    strategy.entry("Long", strategy.long)

if ta.crossunder(fast, slow)
    strategy.close("Long")

plot(fast, color = color.blue)
plot(slow, color = color.orange)
`

const diagnostics = computed<PineDiagnostic[]>(() => [
  ...(validation.value?.errors ?? []).map((row) => ({ ...row, kind: 'error' as const })),
  ...(validation.value?.warnings ?? []).map((row) => ({ ...row, kind: 'warning' as const })),
])

/**
 * The inputs, under the headings the script itself declared. A published
 * strategy has thirty of them across five `group=` sections; listing all thirty
 * in declaration order is technically the same settings and unusable.
 */
const inputGroups = computed(() => {
  const groups = new Map<string, PineInput[]>()
  for (const input of validation.value?.inputs ?? []) {
    const key = input.group || ''
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(input)
  }
  return [...groups.entries()].map(([group, inputs]) => ({ group, inputs }))
})

/**
 * The Properties tab, as rows. Only what the script actually declared, plus
 * anything that departs from live — a full dump of sixteen defaults would bury
 * the two lines that matter.
 */
const propertyRows = computed(() => {
  const props = validation.value?.properties
  if (!props) return []
  const declared = new Set(props.declared ?? [])
  const shown: Array<{ key: string; value: string }> = []
  for (const key of declared) {
    const value = (props as unknown as Record<string, unknown>)[key]
    if (value === undefined || value === null) continue
    shown.push({ key, value: String(value) })
  }
  return shown
})

const propertyNotes = computed(() => {
  const notes = validation.value?.property_notes
  return [
    ...(notes?.live_departures ?? []).map((text) => ({ tone: 'signal' as const, text })),
    ...(notes?.inert ?? []).map((text) => ({ tone: 'muted' as const, text })),
  ]
})

const dirty = computed(() => source.value !== (selected.value?.latest_version?.source ?? ''))

/** The dot next to a strategy in the list: green valid, red errors, grey no version. */
function health(strategy: Strategy): 'ok' | 'short' | 'neutral' {
  const version = strategy.latest_version
  if (!version) return 'neutral'
  if (!version.parsed_ok || version.validation_errors.length) return 'short'
  return 'ok'
}

const DOT: Record<string, string> = {
  ok: 'bg-ok',
  short: 'bg-short',
  neutral: 'bg-ink-faint',
}

async function load() {
  loading.value = true
  try {
    strategies.value = await api.strategies()
    if (!selected.value && strategies.value.length) choose(strategies.value[0])
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

function choose(strategy: Strategy) {
  selected.value = strategy
  source.value = strategy.latest_version?.source ?? TEMPLATE
  check()
}

/**
 * Debounced: this fires on every keystroke and the endpoint parses the whole
 * script. 350ms is below where the underlines feel like they lag the typing.
 */
let timer: ReturnType<typeof setTimeout> | null = null
function schedule() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(check, 350)
}

async function check() {
  if (!source.value.trim()) {
    validation.value = null
    return
  }
  checking.value = true
  try {
    validation.value = await api.validatePine(source.value)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    checking.value = false
  }
}

async function create() {
  if (!newName.value.trim()) return
  saving.value = true
  try {
    const strategy = await api.createStrategy({ name: newName.value.trim() })
    strategies.value.push(strategy)
    newName.value = ''
    creating.value = false
    choose(strategy)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function save() {
  if (!selected.value) return
  saving.value = true
  error.value = ''
  try {
    await api.saveVersion(selected.value.id, source.value)
    const fresh = await api.strategies()
    strategies.value = fresh
    const again = fresh.find((row) => row.id === selected.value?.id)
    if (again) selected.value = again
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!selected.value) return
  deleting.value = true
  error.value = ''
  try {
    const goneId = selected.value.id
    await api.deleteStrategy(goneId)
    strategies.value = strategies.value.filter((row) => row.id !== goneId)
    confirmingDelete.value = false
    selected.value = null
    source.value = ''
    validation.value = null
    if (strategies.value.length) choose(strategies.value[0])
  } catch (e: any) {
    // 409 = bots still point at a version of this strategy. The detail names them.
    confirmingDelete.value = false
    error.value = errorMessage(e)
  } finally {
    deleting.value = false
  }
}

function jump(item: PineDiagnostic) {
  if (item.span) editor.value?.goTo(item.span.line, item.span.col)
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-xl font-display">{{ t('bots.strategies') }}</h1>
        <p class="text-xs text-ink-muted mt-1 max-w-2xl leading-relaxed">
          {{ t('bots.strategiesLead') }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <NuxtLink :to="localePath('/bots/backtest')" class="btn-ghost btn-sm">
          <UiIcon name="trend" :size="14" />
          {{ t('bots.backtest') }}
        </NuxtLink>
        <NuxtLink :to="localePath('/bots')" class="btn-ghost btn-sm">
          <UiIcon name="bolt" :size="14" />
          {{ t('bots.title') }}
        </NuxtLink>
        <button class="btn-brand btn-sm" @click="creating = true">
          <UiIcon name="plus" :size="14" />
          {{ t('bots.newStrategy') }}
        </button>
      </div>
    </header>

    <p v-if="error" class="alert px-3 py-2 text-xs">{{ error }}</p>

    <div class="grid lg:grid-cols-[17rem_1fr] gap-4 items-start">
      <UiCard :title="t('bots.strategies')" flush>
        <div v-if="loading" class="p-4 space-y-2">
          <div v-for="n in 3" :key="n" class="skeleton h-9" />
        </div>
        <UiEmpty
          v-else-if="!strategies.length"
          icon="logs"
          :title="t('bots.noStrategies')"
          :body="t('bots.noStrategiesBody')"
        >
          <button class="btn-brand btn-sm" @click="creating = true">
            <UiIcon name="plus" :size="14" />
            {{ t('bots.newStrategy') }}
          </button>
        </UiEmpty>
        <ul v-else class="divide-y divide-line">
          <li v-for="strategy in strategies" :key="strategy.id">
            <button
              class="w-full text-start px-3 py-2.5 flex items-center gap-2.5 transition-colors"
              :class="selected?.id === strategy.id ? 'bg-raised' : 'hover:bg-raised/60'"
              @click="choose(strategy)"
            >
              <span
                class="w-1.5 h-1.5 rounded-full shrink-0"
                :class="DOT[health(strategy)]"
                :title="t(`bots.${health(strategy) === 'ok' ? 'valid' : health(strategy) === 'short' ? 'doesNotValidate' : 'noVersion'}`)"
              />
              <span class="min-w-0 flex-1">
                <span class="text-sm block truncate">{{ strategy.name }}</span>
                <span class="text-tick text-ink-faint">
                  {{
                    strategy.latest_version
                      ? t('bots.versionN', { n: strategy.latest_version.version })
                      : t('bots.noVersion')
                  }}
                </span>
              </span>
              <UiIcon
                v-if="selected?.id === strategy.id"
                name="chevronRight"
                :size="14"
                class="text-ink-faint flip-rtl shrink-0"
              />
            </button>
          </li>
        </ul>
      </UiCard>

      <div v-if="selected" class="space-y-3 min-w-0">
        <UiCard flush>
          <template #header>
            <div class="flex flex-wrap items-center gap-2 w-full">
              <span class="text-sm font-medium truncate">{{ selected.name }}</span>
              <UiBadge v-if="validation?.ok === false" tone="short">
                {{ t('bots.errorsN', { n: validation.errors.length }) }}
              </UiBadge>
              <UiBadge v-else-if="validation?.warnings.length" tone="signal">
                {{ t('bots.warningsN', { n: validation.warnings.length }) }}
              </UiBadge>
              <UiBadge v-else-if="validation" tone="ok">{{ t('bots.valid') }}</UiBadge>
              <span v-if="checking" class="text-tick text-ink-faint">{{ t('bots.checking') }}</span>
              <span v-else-if="dirty" class="text-tick text-signal">{{ t('bots.unsaved') }}</span>
            </div>
          </template>
          <template #actions>
            <button
              class="btn-quiet btn-sm btn-icon text-ink-muted hover:text-short"
              :disabled="deleting"
              :aria-label="t('bots.deleteStrategy')"
              :title="t('bots.deleteStrategy')"
              @click="confirmingDelete = true"
            >
              <UiIcon name="trash" :size="15" />
            </button>
            <button class="btn-primary btn-sm" :disabled="saving || !dirty" @click="save">
              {{ t('bots.saveVersion') }}
            </button>
          </template>

          <BotsPineEditor
            ref="editor"
            v-model="source"
            :diagnostics="diagnostics"
            :min-rows="26"
            @update:model-value="schedule"
            @save="save"
          />
        </UiCard>

        <UiCard v-if="diagnostics.length" :title="t('bots.diagnostics')" flush>
          <ul class="divide-y divide-line">
            <li v-for="(item, index) in diagnostics" :key="index">
              <button
                class="w-full text-start px-3 py-2 flex items-start gap-3 hover:bg-raised transition-colors"
                @click="jump(item)"
              >
                <UiBadge :tone="item.kind === 'error' ? 'short' : 'signal'">
                  {{ item.span ? `${item.span.line}:${item.span.col}` : '—' }}
                </UiBadge>
                <span class="text-xs leading-relaxed min-w-0">
                  {{ item.message }}
                  <span class="text-ink-faint num"> · {{ item.code }}</span>
                </span>
              </button>
            </li>
          </ul>
        </UiCard>

        <UiCard
          v-if="propertyRows.length || propertyNotes.length"
          :title="t('bots.properties')"
          flush
        >
          <p class="px-3 pt-3 text-tick text-ink-faint leading-relaxed">
            {{ t('bots.propertiesLead') }}
          </p>
          <dl v-if="propertyRows.length" class="px-3 py-2 grid sm:grid-cols-2 gap-x-4 gap-y-1">
            <div
              v-for="row in propertyRows"
              :key="row.key"
              class="flex justify-between gap-3 text-xs"
            >
              <dt class="text-ink-muted truncate">{{ row.key }}</dt>
              <dd class="num">{{ row.value }}</dd>
            </div>
          </dl>
          <ul v-if="propertyNotes.length" class="divide-y divide-line border-t border-line">
            <li
              v-for="(note, index) in propertyNotes"
              :key="index"
              class="px-3 py-2 flex items-start gap-3"
            >
              <UiBadge :tone="note.tone === 'signal' ? 'signal' : 'neutral'">
                {{ note.tone === 'signal' ? t('bots.backtestOnly') : t('bots.noEffect') }}
              </UiBadge>
              <span class="text-xs leading-relaxed min-w-0">{{ note.text }}</span>
            </li>
          </ul>
        </UiCard>

        <UiCard v-if="validation?.inputs.length" :title="t('bots.inputs')" flush>
          <div v-for="section in inputGroups" :key="section.group" class="overflow-x-auto">
            <p
              v-if="section.group"
              class="label px-3 pt-3 pb-1 border-t border-line first:border-t-0"
            >
              {{ section.group }}
            </p>
            <table class="w-full text-xs">
              <thead>
                <tr class="label">
                  <th class="text-start px-3 py-2">{{ t('bots.inputName') }}</th>
                  <th class="text-start px-3 py-2">{{ t('bots.inputType') }}</th>
                  <th class="text-end px-3 py-2">{{ t('bots.inputDefault') }}</th>
                  <th class="text-end px-3 py-2">{{ t('bots.inputRange') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line">
                <tr v-for="input in section.inputs" :key="input.name">
                  <td class="px-3 py-2 num">
                    {{ input.name }}
                    <span v-if="input.title" class="block text-tick text-ink-faint">
                      {{ input.title }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-ink-muted">
                    {{ input.kind }}
                    <span v-if="input.tooltip" class="block text-tick text-ink-faint">
                      {{ input.tooltip }}
                    </span>
                  </td>
                  <td class="px-3 py-2 num text-end">{{ input.default }}</td>
                  <td class="px-3 py-2 num text-end text-ink-muted">
                    {{ input.minval ?? '—' }} … {{ input.maxval ?? '—' }}
                    <span v-if="input.step" class="block text-tick">
                      {{ t('bots.inputStep', { n: String(input.step) }) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </UiCard>
      </div>

      <UiCard v-else flush>
        <UiEmpty
          icon="logs"
          :title="t('bots.selectStrategy')"
          :body="t('bots.selectStrategyBody')"
        />
      </UiCard>
    </div>

    <UiModal v-model="creating" :title="t('bots.newStrategy')" size="sm">
      <label class="block space-y-1.5">
        <span class="label">{{ t('bots.strategyName') }}</span>
        <input v-model="newName" class="field" @keyup.enter="create" />
      </label>
      <template #footer>
        <button class="btn-ghost btn-sm" @click="creating = false">{{ t('common.cancel') }}</button>
        <button class="btn-brand btn-sm" :disabled="saving || !newName.trim()" @click="create">
          {{ t('common.create') }}
        </button>
      </template>
    </UiModal>

    <UiModal v-model="confirmingDelete" :title="t('bots.deleteStrategyTitle')" size="sm">
      <p class="text-sm leading-relaxed">
        {{ t('bots.deleteStrategyConfirm', { name: selected?.name ?? '' }) }}
      </p>
      <template #footer>
        <button class="btn-ghost btn-sm" @click="confirmingDelete = false">
          {{ t('common.cancel') }}
        </button>
        <button class="btn-danger btn-sm" :disabled="deleting" @click="remove">
          {{ t('common.delete') }}
        </button>
      </template>
    </UiModal>
  </div>
</template>
