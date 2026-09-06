<script setup lang="ts">
/**
 * The Properties tab's fields, drawn once and used from two places.
 *
 * The bot page edits a saved set (`StrategyProperties.vue`); the backtest form
 * edits an unsaved one it will post with the run (`PropertiesDialog.vue`). The
 * *form* is identical in both, and the reason it is one component is the same
 * reason `properties.resolve` is one function: the moment there are two, one of
 * them starts disagreeing about which of platform → script → panel won a field,
 * and the report header is what ends up wrong.
 *
 * Owns no state beyond the draft it is given. The merge, the floors and the two
 * warning sentences all arrive resolved from the server.
 */
import type { PropertyFieldSpec } from '~/composables/useApi'

const props = defineProps<{
  resolved: Record<string, any>
  schema: { fields: PropertyFieldSpec[]; categories: { key: string; label: string }[] }
  /** Server-side complaints, per field, from a rejected save. */
  fieldErrors?: Record<string, string>
}>()

/** Only the keys actually overridden. An absent key means "whatever resolved". */
const draft = defineModel<Record<string, unknown>>({ required: true })

const { t, te } = useI18n()

const fields = computed<PropertyFieldSpec[]>(() => props.schema?.fields ?? [])

const categories = computed(() =>
  (props.schema?.categories ?? []).map((category) => ({
    ...category,
    // The server's label is the fallback: a new category ships working in
    // English before anybody writes the translations.
    label: te(`bots.props.group.${category.key}`)
      ? t(`bots.props.group.${category.key}`)
      : category.label,
    fields: fields.value.filter((row) => row.category === category.key),
  })),
)

function current(field: PropertyFieldSpec): unknown {
  if (field.key in draft.value) return draft.value[field.key]
  return props.resolved?.[field.key] ?? ''
}

function set(field: PropertyFieldSpec, value: unknown) {
  const next = { ...draft.value }
  if (value === '' || value === null) delete next[field.key]
  else next[field.key] = value
  draft.value = next
}

function clear(field: PropertyFieldSpec) {
  const next = { ...draft.value }
  delete next[field.key]
  draft.value = next
}

/**
 * Where this field's value came from. Three states, and the distinction is why
 * the form is worth drawing: "the author chose 25,000" and "nobody chose
 * anything so it is 10,000" look identical in a bare input.
 */
function source(field: PropertyFieldSpec): 'panel' | 'script' | 'default' {
  if (field.key in draft.value) return 'panel'
  if ((props.resolved?.declared ?? []).includes(field.key)) return 'script'
  return 'default'
}

const SOURCE_TONE = { panel: 'brand', script: 'ok', default: 'neutral' } as const

/** A field switched off by another — order size value under platform sizing. */
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
</script>

<template>
  <div class="space-y-4">
    <UiCard v-for="category in categories" :key="category.key" :title="category.label" flush>
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
              <p v-if="fieldErrors?.[field.key]" class="text-xs text-short mt-1">
                {{ fieldErrors[field.key] }}
              </p>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <input
                v-if="field.kind === 'bool'"
                type="checkbox"
                class="w-4 h-4 accent-brand"
                :checked="Boolean(current(field))"
                :disabled="!enabled(field)"
                @change="set(field, ($event.target as HTMLInputElement).checked)"
              />

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
  </div>
</template>
