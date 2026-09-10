<script setup lang="ts">
/**
 * The script's settings, in front of a backtest instead of behind it.
 *
 * The sibling of `PropertiesDialog.vue`, and the reason both exist in front of
 * the run is the same: a replay made under settings nobody chose is not a
 * comparison, it is a first draft. The difference is which half of the dialog
 * it edits — properties describe the simulated broker, inputs are what the
 * strategy computes with, and a length changed here changes the signals rather
 * than the caption.
 *
 * No bot in the picture: this is about to run a *version*, so it reads
 * `/bots/versions/<id>/inputs/` and the values are posted with the run rather
 * than saved anywhere. Presets are read-only here — saving one belongs where
 * there is something to save it *from*, which is the bot's own tab.
 */
import type { InputPreset, InputsPayload } from '~/composables/useApi'

const open = defineModel<boolean>({ required: true })
const props = defineProps<{ versionId: number | null; values: Record<string, unknown> }>()
const emit = defineEmits<{ (event: 'apply', values: Record<string, unknown>): void }>()

const { t } = useI18n()
const api = useApi()

const data = ref<InputsPayload | null>(null)
const loading = ref(false)
const error = ref('')
const draft = ref<Record<string, unknown>>({})

const count = computed(() => Object.keys(draft.value).length)

async function load() {
  if (!props.versionId) return
  loading.value = true
  error.value = ''
  try {
    data.value = await api.versionInputs(props.versionId)
    draft.value = { ...props.values }
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

function apply() {
  emit('apply', { ...draft.value })
  open.value = false
}

/** Hand every setting back to the script at once. */
function resetAll() {
  draft.value = {}
}

function usePreset(preset: InputPreset) {
  draft.value = { ...preset.values }
}

watch(
  () => [open.value, props.versionId] as const,
  ([isOpen]) => {
    if (isOpen) load()
  },
  { immediate: true },
)
</script>

<template>
  <UiModal v-model="open" :title="t('bots.inputs.title')" size="lg">
    <div class="space-y-4">
      <p class="text-xs text-ink-muted leading-relaxed">{{ t('bots.inputs.dialogLead') }}</p>

      <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">{{ error }}</p>
      <div v-if="loading" class="skeleton h-40" />

      <template v-else-if="data">
        <div v-if="data.presets.length" class="flex items-center gap-2 flex-wrap">
          <span class="text-xs text-ink-faint">{{ t('bots.inputs.presets') }}</span>
          <button
            v-for="preset in data.presets"
            :key="preset.id"
            class="btn-quiet btn-sm"
            @click="usePreset(preset)"
          >
            {{ preset.name }}
          </button>
        </div>

        <BotsInputsForm v-model="draft" :schema="data.schema" :resolved="data.resolved" />
      </template>
    </div>

    <template #footer>
      <div class="flex items-center gap-2">
        <span class="text-xs text-ink-faint me-auto">
          {{ count ? t('bots.inputs.changedN', { n: count }) : t('bots.inputs.noChanges') }}
        </span>
        <button class="btn-ghost btn-sm" :disabled="!count" @click="resetAll">
          {{ t('bots.props.resetAll') }}
        </button>
        <button class="btn-brand btn-sm" @click="apply">{{ t('common.apply') }}</button>
      </div>
    </template>
  </UiModal>
</template>
