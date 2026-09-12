<script setup lang="ts">
/**
 * The script's own settings, drawn from the schema the server derived.
 *
 * The sibling of `PropertiesForm.vue`, and deliberately the same shape: a group
 * per heading, a row per setting, a badge saying whether the value came from
 * the script or from this panel, and a per-row reset that *deletes* the
 * override rather than writing the default back. What differs is that nothing
 * here is a fixed list — the groups, the controls, the bounds and the order all
 * arrive from `apps/pine/inputs.py`, which read them off the uploaded script.
 * A hard-coded row for any one strategy would be a row the next upload is wrong
 * about.
 *
 * Three rules this component holds to:
 *
 * **It recomputes nothing.** The effective value, the widget, the category and
 * the gate all arrive resolved. The browser deciding that a number is "really"
 * a risk setting is a second opinion, and the two would disagree on the day it
 * mattered.
 *
 * **A gated row is dimmed, never disabled.** `depends_on` is advisory: the
 * analysis is conservative and can still be wrong, and a setting the operator
 * cannot reach on a live book is worse than one that is bright while it does
 * nothing. So the row says what turns it off and stays editable.
 *
 * **Titles are the author's.** They come out of the script and are shown as
 * written, in any language the author used — `i18n` covers the chrome around
 * them, never the settings themselves.
 */
import type { PineInput, PineInputSchema } from '~/composables/useApi'

const props = defineProps<{
  schema: PineInputSchema
  /** Every input's effective value — default under override, resolved server-side. */
  resolved: Record<string, unknown>
  /** Server-side complaints, per input name, from a rejected save. */
  fieldErrors?: Record<string, string>
}>()

/** Only the inputs actually overridden. An absent key means "whatever the script chose". */
const draft = defineModel<Record<string, unknown>>({ required: true })

const { t, te } = useI18n()

const fields = computed<PineInput[]>(() => props.schema?.fields ?? [])
const byName = computed(() => new Map(fields.value.map((row) => [row.name, row])))

/** Which categories are actually present, so the filter never offers an empty one. */
const categories = computed(() => {
  const present = new Set(fields.value.map((row) => row.category))
  return (props.schema?.categories ?? []).filter((row) => present.has(row.key as never))
})

const filter = ref<string>('all')

const collapsed = ref<Record<string, boolean>>({})
function toggle(key: string) {
  collapsed.value = { ...collapsed.value, [key]: !collapsed.value[key] }
}

/**
 * The groups, each already laid out: `inline=` runs come back as one row and
 * everything else as a row of its own, in declaration order.
 */
const groups = computed(() =>
  (props.schema?.groups ?? [])
    .map((group) => {
      const shown = group.names
        .map((name) => byName.value.get(name))
        .filter((row): row is PineInput => !!row && (filter.value === 'all' || row.category === filter.value))
      const inRow = new Map<string, string[]>()
      for (const row of group.rows) for (const name of row) inRow.set(name, row)

      const rows: PineInput[][] = []
      const taken = new Set<string>()
      for (const field of shown) {
        if (taken.has(field.name)) continue
        const run = inRow.get(field.name)
        if (!run) {
          rows.push([field])
          taken.add(field.name)
          continue
        }
        const members = run
          .map((name) => shown.find((row) => row.name === name))
          .filter((row): row is PineInput => !!row)
        members.forEach((row) => taken.add(row.name))
        rows.push(members)
      }
      return { ...group, label: group.title || t('bots.inputs.ungrouped'), rows, count: shown.length }
    })
    .filter((group) => group.count > 0),
)

const overrideCount = computed(() => Object.keys(draft.value).length)

function current(field: PineInput): unknown {
  if (field.name in draft.value) return draft.value[field.name]
  return props.resolved?.[field.name] ?? field.default
}

function set(field: PineInput, value: unknown) {
  draft.value = { ...draft.value, [field.name]: value }
}

function setNumber(field: PineInput, raw: string) {
  if (raw === '') return clear(field)
  const value = Number(raw)
  set(field, Number.isNaN(value) ? raw : value)
}

function clear(field: PineInput) {
  const next = { ...draft.value }
  delete next[field.name]
  draft.value = next
}

function resetGroup(names: string[]) {
  const next = { ...draft.value }
  for (const name of names) delete next[name]
  draft.value = next
}

/** Where this value came from. The same three states the Properties tab shows. */
function source(field: PineInput): 'panel' | 'script' {
  return field.name in draft.value ? 'panel' : 'script'
}

/**
 * Whether the strategy currently reads this setting, following the chain: an
 * input gated by a toggle that is itself gated is inactive when either is.
 * Depth-capped because the schema is data and a cycle in it must not hang the
 * panel — an unresolvable chain reads as active, the safe answer.
 */
function active(field: PineInput, depth = 0): boolean {
  if (!field.depends_on.length || depth > 4) return true
  return field.depends_on.every((gate) => {
    const controller = byName.value.get(gate.controller)
    if (!controller) return true
    const held = current(controller)
    const matches = gate.values.some((value) => String(value) === String(held))
    return matches && active(controller, depth + 1)
  })
}

/** "Inactive while Enable take profit is off" — in the author's own words. */
function gateNote(field: PineInput): string {
  const parts = field.depends_on.map((gate) => {
    const controller = byName.value.get(gate.controller)
    const label = controller?.title || gate.controller
    const values = gate.values.map((value) => (typeof value === 'boolean' ? '' : String(value)))
    return values.every((row) => row === '')
      ? t('bots.inputs.gateBool', { name: label })
      : t('bots.inputs.gateValue', { name: label, values: values.join(', ') })
  })
  return parts.join(' · ')
}

const CATEGORY_TONE: Record<string, 'brand' | 'ok' | 'signal' | 'neutral'> = {
  risk: 'signal',
  execution: 'brand',
  backtest: 'neutral',
  logic: 'ok',
  visual: 'neutral',
}

/** The server's label is the fallback: a new category ships working in English
 *  before anybody writes the six translations. */
function categoryLabel(key: string): string {
  const path = `bots.inputs.category.${key}`
  return te(path) ? t(path) : (categories.value.find((row) => row.key === key)?.label ?? key)
}

/** A `datetime-local` value from the epoch milliseconds an `input.time` holds. */
function asLocalDateTime(value: unknown): string {
  let ms = Number(value)
  if (!Number.isFinite(ms)) return ''
  // A version validated before Pine time became milliseconds stored its
  // default in seconds, which read as a date in January 1970.
  if (ms > 0 && ms < 1e11) ms *= 1000
  const date = new Date(ms - new Date(ms).getTimezoneOffset() * 60000)
  return date.toISOString().slice(0, 16)
}

function fromLocalDateTime(field: PineInput, raw: string) {
  const ms = new Date(raw).getTime()
  if (Number.isFinite(ms)) set(field, ms)
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <UiSegmented
        v-if="categories.length > 1"
        v-model="filter"
        size="sm"
        :block="false"
        :options="[
          { value: 'all', label: t('bots.inputs.allCategories') },
          ...categories.map((row) => ({ value: row.key, label: categoryLabel(row.key) })),
        ]"
      />
      <button class="btn-quiet btn-sm" :disabled="!overrideCount" @click="draft = {}">
        {{ t('bots.inputs.resetAll', { n: overrideCount }) }}
      </button>
    </div>

    <UiCard v-for="group in groups" :key="group.key" flush>
      <template #header>
        <button
          class="flex items-center gap-2 text-start text-sm font-medium"
          @click="toggle(group.key)"
        >
          <UiIcon :name="collapsed[group.key] ? 'chevronRight' : 'chevronDown'" :size="14" />
          <span class="truncate">{{ group.label }}</span>
          <span class="text-xs text-ink-faint">{{ group.count }}</span>
        </button>
      </template>

      <div v-show="!collapsed[group.key]" class="divide-y divide-line">
        <div
          v-for="(row, index) in group.rows"
          :key="index"
          class="px-4 py-3.5"
          :class="row.every((field) => !active(field)) ? 'opacity-45' : ''"
        >
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div class="min-w-0 flex-1 space-y-1">
              <div class="flex items-center gap-2 flex-wrap">
                <span v-for="field in row" :key="field.name" class="text-sm">
                  {{ field.title }}
                </span>
                <UiBadge :tone="CATEGORY_TONE[row[0].category] ?? 'neutral'">
                  {{ categoryLabel(row[0].category) }}
                </UiBadge>
                <UiBadge v-if="row.some((field) => source(field) === 'panel')" tone="brand">
                  {{ t('bots.inputs.source.panel') }}
                </UiBadge>
              </div>

              <p v-if="row[0].tooltip" class="text-xs text-ink-muted leading-relaxed">
                {{ row[0].tooltip }}
              </p>
              <p
                v-if="row.some((field) => field.depends_on.length)"
                class="text-xs text-ink-faint leading-relaxed"
              >
                {{ gateNote(row.find((field) => field.depends_on.length)!) }}
              </p>
              <p v-if="row.every((field) => !field.used)" class="text-xs text-ink-faint">
                {{ t('bots.inputs.unused') }}
              </p>
              <p
                v-for="field in row.filter((one) => fieldErrors?.[one.name])"
                :key="field.name"
                class="text-xs text-short"
              >
                {{ field.title }}: {{ fieldErrors?.[field.name] }}
              </p>
            </div>

            <div class="flex items-center gap-2 shrink-0 flex-wrap justify-end">
              <template v-for="field in row" :key="field.name">
                <input
                  v-if="field.widget === 'toggle'"
                  type="checkbox"
                  class="w-4 h-4 accent-brand"
                  :checked="Boolean(current(field))"
                  @change="set(field, ($event.target as HTMLInputElement).checked)"
                />

                <select
                  v-else-if="field.widget === 'select' || field.widget === 'source'"
                  class="field w-auto min-w-[11rem]"
                  :value="String(current(field))"
                  @change="set(field, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="choice in field.choices" :key="String(choice)" :value="String(choice)">
                    {{ choice }}
                  </option>
                </select>

                <div v-else-if="field.widget === 'color'" class="flex items-center gap-1.5">
                  <input
                    type="color"
                    class="w-9 h-8 rounded border border-line bg-raised"
                    :value="String(current(field)).slice(0, 7)"
                    @input="set(field, ($event.target as HTMLInputElement).value.toUpperCase())"
                  />
                  <span class="text-xs text-ink-faint font-mono">{{ current(field) }}</span>
                </div>

                <input
                  v-else-if="field.widget === 'datetime'"
                  type="datetime-local"
                  class="field w-auto"
                  :value="asLocalDateTime(current(field))"
                  @change="fromLocalDateTime(field, ($event.target as HTMLInputElement).value)"
                />

                <textarea
                  v-else-if="field.widget === 'textarea'"
                  class="field w-64 h-16"
                  :value="String(current(field) ?? '')"
                  @input="set(field, ($event.target as HTMLTextAreaElement).value)"
                />

                <input
                  v-else-if="field.widget === 'number'"
                  class="field w-28 text-end"
                  inputmode="decimal"
                  :step="(field.step as number) ?? (field.kind === 'int' ? 1 : 'any')"
                  :min="(field.minval as number) ?? undefined"
                  :max="(field.maxval as number) ?? undefined"
                  :value="current(field) ?? ''"
                  @input="setNumber(field, ($event.target as HTMLInputElement).value)"
                />

                <input
                  v-else
                  class="field w-40"
                  :value="String(current(field) ?? '')"
                  @input="set(field, ($event.target as HTMLInputElement).value)"
                />
              </template>

              <button
                class="btn-quiet btn-sm"
                :disabled="!row.some((field) => field.name in draft)"
                :title="t('bots.inputs.resetHint')"
                @click="resetGroup(row.map((field) => field.name))"
              >
                {{ t('bots.props.clear') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </UiCard>

    <UiEmpty v-if="!groups.length" :title="t('bots.inputs.none')" />
  </div>
</template>
