<script setup lang="ts">
/**
 * The Properties tab, in front of a backtest instead of behind it.
 *
 * These numbers are not decoration on a report — initial capital, commission,
 * slippage and the order-size model change what the replay *is*. Editing them
 * only after a run has finished means every comparison starts with a run made
 * under settings nobody chose, so the backtest form opens this first.
 *
 * There is no bot here: the form is about to run a *version*. So it reads
 * `/bots/versions/<id>/properties/` — the same `properties.resolve`, the same
 * schema, with the third step of the merge left to this dialog and posted with
 * the run rather than saved anywhere.
 */
const open = defineModel<boolean>({ required: true })
const props = defineProps<{ versionId: number | null; overrides: Record<string, unknown> }>()
const emit = defineEmits<{ (event: 'apply', overrides: Record<string, unknown>): void }>()

const { t } = useI18n()
const api = useApi()

const data = ref<VersionProperties | null>(null)
const loading = ref(false)
const error = ref('')
const draft = ref<Record<string, unknown>>({})

const count = computed(() => Object.keys(draft.value).length)

async function load() {
  if (!props.versionId) return
  loading.value = true
  error.value = ''
  try {
    data.value = await api.versionProperties(props.versionId)
    draft.value = { ...props.overrides }
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

/** Hand every field back to the script and the platform at once. */
function resetAll() {
  draft.value = {}
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
  <UiModal v-model="open" :title="t('bots.props.title')" size="lg">
    <div class="space-y-4">
      <p class="text-xs text-ink-muted leading-relaxed">{{ t('bots.props.dialogLead') }}</p>
      <p class="text-xs text-ink-muted leading-relaxed">{{ t('bots.props.liveNote') }}</p>

      <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">{{ error }}</p>
      <div v-if="loading" class="skeleton h-40" />

      <template v-else-if="data">
        <BotsPropertiesForm
          v-model="draft"
          :resolved="data.resolved as unknown as Record<string, any>"
          :schema="data.schema"
        />

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
      </template>
    </div>

    <template #footer>
      <div class="flex items-center gap-2">
        <span class="text-xs text-ink-faint me-auto">
          {{ count ? t('bots.props.overriddenN', { n: count }) : t('bots.props.noOverrides') }}
        </span>
        <button class="btn-ghost btn-sm" :disabled="!count" @click="resetAll">
          {{ t('bots.props.resetAll') }}
        </button>
        <button class="btn-brand btn-sm" @click="apply">{{ t('common.apply') }}</button>
      </div>
    </template>
  </UiModal>
</template>
