<script setup lang="ts">
/**
 * TradingView's Properties tab, for one bot.
 *
 * The point of the tab is to make a backtest here comparable with the one the
 * author ran on TradingView: same starting capital, same commission, same
 * slippage, same fill model. Nothing is recomputed in the browser — the merge
 * (platform default → what `strategy()` declared → what this form overrides)
 * happens once, in `apps/pine/properties.py`, and this component draws the
 * result and posts a diff.
 *
 * What it refuses to do is imply more than it delivers. Several of these
 * settings move the *backtest* and can never move live: spec §5 sizes every
 * live order at 99% of that account's own balance, so "order size" and the
 * margin pair describe the simulated account and nothing else. Those rows carry
 * the sentence that says so, from the server, always — not only once the value
 * departs, because the question a reader has while typing is "will this reach
 * live", and an answer that appears afterwards arrives too late to be useful.
 */
import type { BotProperties, PropertyFieldSpec } from '~/composables/useApi'

const props = defineProps<{ botId: number }>()

const { t, te } = useI18n()
const api = useApi()

const data = ref<BotProperties | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
/** Server-side complaints, per field, from a rejected save. */
const fieldErrors = ref<Record<string, string>>({})

/**
 * The working set. Only keys the operator actually touched live here — an
 * absent key means "whatever the script or the platform says", which is what
 * lets a later version of the script start winning a field without this form
 * having to be re-saved.
 */
const draft = ref<Record<string, unknown>>({})

const dirty = computed(
  () => JSON.stringify(draft.value) !== JSON.stringify(data.value?.overrides ?? {}),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const payload = await api.botProperties(props.botId)
    data.value = payload
    draft.value = { ...payload.overrides }
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  saved.value = false
  fieldErrors.value = {}
  try {
    await api.updateBot(props.botId, { property_overrides: draft.value })
    await load()
    saved.value = true
    setTimeout(() => (saved.value = false), 2500)
  } catch (e: any) {
    // DRF hands back `{property_overrides: ["initial_capital cannot be …"]}`.
    // The message names the field, so it is shown against the form rather than
    // only in the banner — a validation error nobody can locate is a dead end.
    const detail = e?.data?.property_overrides
    if (Array.isArray(detail)) {
      for (const message of detail) {
        const hit = fields.value.find((row) => String(message).startsWith(row.key))
        if (hit) fieldErrors.value[hit.key] = String(message)
      }
    }
    error.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

function revert() {
  draft.value = { ...(data.value?.overrides ?? {}) }
  fieldErrors.value = {}
}

const fields = computed<PropertyFieldSpec[]>(() => data.value?.schema.fields ?? [])

const categories = computed(() =>
  (data.value?.schema.categories ?? []).map((category) => ({
    ...category,
    // The server's label is the fallback: a new category ships working in
    // English before anybody writes the two translations.
    label: te(`bots.props.group.${category.key}`)
      ? t(`bots.props.group.${category.key}`)
      : category.label,
    fields: fields.value.filter((row) => row.category === category.key),
  })),
)

/** The value on screen: the operator's edit if there is one, else what resolved. */
function current(field: PropertyFieldSpec): unknown {
  if (field.key in draft.value) return draft.value[field.key]
  const resolved = data.value?.resolved as Record<string, unknown> | undefined
  return resolved?.[field.key] ?? ''
}

function set(field: PropertyFieldSpec, value: unknown) {
  delete fieldErrors.value[field.key]
  if (value === '' || value === null) delete draft.value[field.key]
  else draft.value[field.key] = value
}

/** Hand one field back to the script (or the platform) without touching the rest. */
function clear(field: PropertyFieldSpec) {
  delete draft.value[field.key]
  delete fieldErrors.value[field.key]
}

/**
 * Where this field's value came from. Three states, and the distinction is the
 * reason the form is worth drawing at all: "the author chose 25,000" and
 * "nobody chose anything so it is 10,000" look identical in a bare input.
 */
function source(field: PropertyFieldSpec): 'panel' | 'script' | 'default' {
  if (field.key in draft.value) return 'panel'
  if ((data.value?.resolved.declared ?? []).includes(field.key)) return 'script'
  return 'default'
}

const SOURCE_TONE = { panel: 'brand', script: 'ok', default: 'neutral' } as const

/** A field switched off by another field — order size value under platform sizing. */
function enabled(field: PropertyFieldSpec): boolean {
  if (!field.enabled_when) return true
  const gate = fields.value.find((row) => row.key === field.enabled_when!.key)
  if (!gate) return true
  return field.enabled_when.values.includes(String(current(gate)))
}

function label(field: PropertyFieldSpec): string {
  const key = `bots.props.field.${field.key}`
  return te(key) ? t(key) : field.key.replace(/_/g, ' ')
}

function choiceLabel(field: PropertyFieldSpec, choice: string): string {
  const key = `bots.props.choice.${field.key}.${choice}`
  return te(key) ? t(key) : choice
}

onMounted(load)
watch(() => props.botId, load)
</script>

<template>
  <div class="space-y-4">
    <!-- The correction that has to arrive before the form, not after it: this
         tab configures the replay. Live sizing is spec §5 and no field here
         moves it. Saying so once, up front, is what stops the per-row notes
         from reading as fine print. -->
    <UiCard :title="t('bots.props.title')" :hint="t('bots.props.lead')">
      <p class="text-xs text-ink-muted leading-relaxed">{{ t('bots.props.liveNote') }}</p>
    </UiCard>

    <UiCard v-if="error" flush>
      <p class="px-4 py-3 text-xs text-short">{{ error }}</p>
    </UiCard>

    <div v-if="loading" class="text-xs text-ink-faint px-1">{{ t('common.loading') }}</div>

    <template v-else-if="data">
      <UiCard
        v-for="category in categories"
        :key="category.key"
        :title="category.label"
        flush
      >
        <div class="divide-y divide-line">
          <div
            v-for="field in category.fields"
            :key="field.key"
            class="px-4 py-3.5"
            :class="enabled(field) ? '' : 'opacity-45'"
          >
            <div class="flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm">{{ label(field) }}</span>
                  <UiBadge :tone="SOURCE_TONE[source(field)]">
                    {{ t(`bots.props.source.${source(field)}`) }}
                  </UiBadge>
                </div>

                <p v-if="field.backtest_only" class="text-xs text-signal mt-1 leading-relaxed">
                  {{ field.backtest_only }}
                </p>
                <p v-if="field.inert" class="text-xs text-ink-faint mt-1 leading-relaxed">
                  {{ field.inert }}
                </p>
                <p v-if="fieldErrors[field.key]" class="text-xs text-short mt-1">
                  {{ fieldErrors[field.key] }}
                </p>
              </div>

              <div class="flex items-center gap-2 shrink-0">
                <!-- bool -->
                <input
                  v-if="field.kind === 'bool'"
                  type="checkbox"
                  class="w-4 h-4 accent-brand"
                  :checked="Boolean(current(field))"
                  :disabled="!enabled(field)"
                  @change="set(field, ($event.target as HTMLInputElement).checked)"
                />

                <!-- choice / currency -->
                <select
                  v-else-if="field.kind === 'choice' || field.kind === 'currency'"
                  class="field w-auto min-w-[11rem]"
                  :value="String(current(field))"
                  :disabled="!enabled(field)"
                  @change="set(field, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="choice in field.choices" :key="choice" :value="choice">
                    {{ choiceLabel(field, choice) }}
                  </option>
                </select>

                <!-- decimal / int -->
                <div v-else class="flex items-center gap-1.5">
                  <input
                    class="field w-32 text-end"
                    inputmode="decimal"
                    :step="field.kind === 'int' ? '1' : 'any'"
                    :min="field.minimum ?? undefined"
                    :value="current(field) ?? ''"
                    :disabled="!enabled(field)"
                    @input="set(field, ($event.target as HTMLInputElement).value)"
                  />
                  <span v-if="field.unit" class="text-xs text-ink-faint w-14">{{ field.unit }}</span>
                </div>

                <button
                  class="btn-quiet btn-sm"
                  :disabled="!(field.key in draft)"
                  :title="t('bots.props.clearHint')"
                  @click="clear(field)"
                >
                  {{ t('bots.props.clear') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </UiCard>

      <!-- What this set would simulate that live will not do. Derived on the
           server from the *resolved* values, so it reflects the saved state
           rather than the draft — which is why it sits below the form. -->
      <UiCard
        v-if="data.live_departures.length || data.inert.length"
        :title="t('bots.props.notes')"
        flush
      >
        <ul class="divide-y divide-line">
          <li
            v-for="(line, index) in data.live_departures"
            :key="`d${index}`"
            class="px-4 py-2.5 flex items-start gap-3"
          >
            <UiBadge tone="signal" class="mt-px shrink-0">{{ t('bots.backtestOnly') }}</UiBadge>
            <span class="text-xs leading-relaxed">{{ line }}</span>
          </li>
          <li
            v-for="(line, index) in data.inert"
            :key="`i${index}`"
            class="px-4 py-2.5 flex items-start gap-3"
          >
            <UiBadge tone="neutral" class="mt-px shrink-0">{{ t('bots.noEffect') }}</UiBadge>
            <span class="text-xs leading-relaxed">{{ line }}</span>
          </li>
        </ul>
      </UiCard>

      <div class="flex items-center justify-end gap-2">
        <span v-if="saved" class="text-xs text-ok me-auto">{{ t('bots.props.saved') }}</span>
        <button class="btn-ghost btn-sm" :disabled="!dirty || saving" @click="revert">
          {{ t('common.cancel') }}
        </button>
        <button class="btn-brand btn-sm" :disabled="!dirty || saving" @click="save">
          {{ saving ? t('common.saving') : t('common.save') }}
        </button>
      </div>
    </template>
  </div>
</template>
