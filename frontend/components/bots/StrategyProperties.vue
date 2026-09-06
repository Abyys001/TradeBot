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

const { t } = useI18n()
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
        const hit = (data.value?.schema.fields ?? []).find((row: PropertyFieldSpec) =>
          String(message).startsWith(row.key),
        )
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
      <!-- The fields themselves live in `PropertiesForm`, shared with the
           backtest page's dialog: two copies of this form is how the report
           header and the form that produced it start disagreeing. -->
      <BotsPropertiesForm
        v-model="draft"
        :resolved="data.resolved as unknown as Record<string, any>"
        :schema="data.schema"
        :field-errors="fieldErrors"
      />

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
