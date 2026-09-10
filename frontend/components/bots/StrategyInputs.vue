<script setup lang="ts">
/**
 * The script's own settings, for one bot — the other half of the dialog
 * `StrategyProperties.vue` draws.
 *
 * The split is the one TradingView makes and it is worth keeping: a property
 * describes the simulated broker and stops at the backtest, while an input is a
 * number the strategy computes with and reaches live untouched. So this tab
 * carries no "backtest only" caveat, and instead carries the warning the
 * Properties tab does not need: **saving here changes what the bot trades.**
 *
 * A running bot is not reloaded from the database mid-run, so a change lands on
 * the next start. That is said on the card rather than left to be discovered,
 * and it is the reason the save button is not quieter about it.
 *
 * Presets sit here rather than in the form because they are about *this
 * strategy*, not about this bot: a set of values saved from one bot is the
 * obvious starting point for the next one, and the API keys them to the
 * strategy for exactly that reason.
 */
import type { InputPreset, InputsPayload } from '~/composables/useApi'

const props = defineProps<{ botId: number; running?: boolean }>()

const { t } = useI18n()
const api = useApi()

const data = ref<InputsPayload | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
/** Server-side complaints, per input, from a rejected save. */
const fieldErrors = ref<Record<string, string>>({})

/** Only the inputs the operator actually touched. An absent key follows the script. */
const draft = ref<Record<string, unknown>>({})

const presets = ref<InputPreset[]>([])
const presetName = ref('')
const presetBusy = ref(false)

const dirty = computed(
  () => JSON.stringify(draft.value) !== JSON.stringify(data.value?.overrides ?? {}),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const payload = await api.botInputs(props.botId)
    data.value = payload
    draft.value = { ...payload.overrides }
    presets.value = payload.presets
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
    await api.updateBot(props.botId, { input_values: draft.value })
    await load()
    saved.value = true
    setTimeout(() => (saved.value = false), 2500)
  } catch (e: any) {
    // DRF hands back `{input_values: ["mcgLength: must be at least 1"]}`. The
    // message names the input, so it is shown against its own row as well as in
    // the banner — a validation error nobody can locate is a dead end, and on
    // a panel of thirty settings "somewhere below" is not a location.
    const detail = e?.data?.input_values
    if (Array.isArray(detail)) {
      for (const message of detail) {
        const [name, ...rest] = String(message).split(': ')
        if (name && rest.length) fieldErrors.value[name] = rest.join(': ')
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

/**
 * Load a preset **into the draft**, not into the bot: it lands as unsaved
 * changes the operator can read before committing them. A preset that applied
 * itself would be a single click between a working book and different settings.
 */
function apply(preset: InputPreset) {
  draft.value = { ...preset.values }
  fieldErrors.value = {}
}

async function savePreset() {
  const name = presetName.value.trim()
  const strategy = data.value?.strategy
  if (!name || !strategy) return
  presetBusy.value = true
  error.value = ''
  try {
    const existing = presets.value.find((row) => row.name === name)
    // Same name is an update rather than a refusal: the operator who types a
    // name they already used means "save over it", and the unique constraint
    // would otherwise answer with a database error.
    const row = existing
      ? await api.updatePreset(existing.id, { values: draft.value })
      : await api.createPreset({ strategy, name, values: draft.value })
    presets.value = [...presets.value.filter((one) => one.id !== row.id), row].sort((a, b) =>
      a.name.localeCompare(b.name),
    )
    presetName.value = ''
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    presetBusy.value = false
  }
}

async function removePreset(preset: InputPreset) {
  presetBusy.value = true
  try {
    await api.deletePreset(preset.id)
    presets.value = presets.value.filter((row) => row.id !== preset.id)
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    presetBusy.value = false
  }
}

onMounted(load)
watch(() => props.botId, load)
</script>

<template>
  <div class="space-y-4">
    <UiCard :title="t('bots.inputs.title')" :hint="t('bots.inputs.lead')">
      <p class="text-xs text-ink-muted leading-relaxed">{{ t('bots.inputs.liveNote') }}</p>
      <p v-if="running" class="text-xs text-signal leading-relaxed mt-2">
        {{ t('bots.inputs.runningNote') }}
      </p>
    </UiCard>

    <UiCard v-if="error" flush>
      <p class="px-4 py-3 text-xs text-short">{{ error }}</p>
    </UiCard>

    <div v-if="loading" class="text-xs text-ink-faint px-1">{{ t('common.loading') }}</div>

    <template v-else-if="data">
      <UiCard :title="t('bots.inputs.presets')" :hint="t('bots.inputs.presetsHint')" flush>
        <ul v-if="presets.length" class="divide-y divide-line">
          <li v-for="preset in presets" :key="preset.id" class="px-4 py-2.5 flex items-center gap-3">
            <span class="text-sm min-w-0 truncate">{{ preset.name }}</span>
            <span class="text-xs text-ink-faint">
              {{ t('bots.inputs.presetSize', { n: Object.keys(preset.values).length }) }}
            </span>
            <div class="ms-auto flex items-center gap-2 shrink-0">
              <button class="btn-quiet btn-sm" :disabled="presetBusy" @click="apply(preset)">
                {{ t('bots.inputs.presetLoad') }}
              </button>
              <button class="btn-quiet btn-sm" :disabled="presetBusy" @click="removePreset(preset)">
                {{ t('common.delete') }}
              </button>
            </div>
          </li>
        </ul>
        <div class="px-4 py-3 flex items-center gap-2 border-t border-line">
          <input
            v-model="presetName"
            class="field w-56"
            :placeholder="t('bots.inputs.presetName')"
            @keyup.enter="savePreset"
          />
          <button
            class="btn-quiet btn-sm"
            :disabled="!presetName.trim() || presetBusy"
            @click="savePreset"
          >
            {{ t('bots.inputs.presetSave') }}
          </button>
        </div>
      </UiCard>

      <!-- The rows themselves live in `InputsForm`, shared with the backtest
           page's dialog. Two copies of a form drawn from a schema is two places
           for the schema to be read differently. -->
      <BotsInputsForm
        v-model="draft"
        :schema="data.schema"
        :resolved="data.resolved"
        :field-errors="fieldErrors"
      />

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
