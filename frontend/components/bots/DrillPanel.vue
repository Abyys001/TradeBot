<script setup lang="ts">
/**
 * The drills, as buttons that actually fire.
 *
 * Two of the gate's rows ask for things nobody can prove by remembering them:
 * that the kill switch has been pulled on this bot, and that every Q25
 * auto-stop has been fired deliberately. Before this they could only be
 * satisfied by editing the database, which makes the gate a form rather than a
 * measurement.
 *
 * **The halt drill is the real thing.** It engages the §7 halt, force-closes
 * every open trade through the same call Stop-all makes — with no reference
 * whatsoever to what the strategy thinks should be open, which is the entire
 * point of the exercise — and then resumes the bot into the same run so the
 * soak clock is not reset by proving the brake works.
 *
 * The confirmation is not ceremony. This sends real close orders.
 */
const props = defineProps<{ botId: number; running: boolean; fired: string[]; haltDrills: number }>()
const emit = defineEmits<{ (event: 'done'): void }>()

const { t } = useI18n()
const api = useApi()

const Q25 = [
  'consecutive_losses',
  'drawdown',
  'feed_gap',
  'script_error',
  'state_disagreement',
  'trade_rate',
  'no_bars',
]

const busy = ref('')
const error = ref('')
const result = ref<DrillResult | null>(null)
const confirming = ref<string | null>(null)

function done(kind: string): boolean {
  return kind === 'halt' ? props.haltDrills > 0 : props.fired.includes(kind)
}

async function fire(kind: string) {
  confirming.value = null
  busy.value = kind
  error.value = ''
  result.value = null
  try {
    result.value = await api.runDrill(props.botId, kind)
    emit('done')
  } catch (e: any) {
    error.value = errorMessage(e)
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <UiCard :title="t('bots.drills')" :hint="t('bots.drillsHint')" flush>
    <p class="px-4 py-3 text-xs text-ink-muted leading-relaxed border-b border-line">
      {{ t('bots.drillsLead') }}
    </p>

    <p v-if="!running" class="px-4 py-3 text-xs text-signal leading-relaxed border-b border-line">
      {{ t('bots.drillsNeedRunning') }}
    </p>

    <div class="p-4 space-y-4">
      <!-- The halt drill, on its own, because it is not the same kind of thing
           as the six below it: it sends orders. -->
      <div class="rounded-lg border border-line bg-sunken/40 p-3.5 space-y-2">
        <div class="flex items-center gap-2 flex-wrap">
          <UiIcon name="alert" :size="14" class="text-signal" />
          <span class="text-sm font-medium">{{ t('bots.drill.halt') }}</span>
          <UiBadge v-if="done('halt')" tone="ok">
            {{ t('bots.drillPassedN', { n: haltDrills }) }}
          </UiBadge>
          <button
            class="btn-warn btn-sm ms-auto"
            :disabled="!running || busy === 'halt'"
            @click="confirming = 'halt'"
          >
            <UiIcon v-if="busy === 'halt'" name="spinner" :size="13" class="animate-spin" />
            {{ t('bots.runDrill') }}
          </button>
        </div>
        <p class="text-xs text-ink-muted leading-relaxed">{{ t('bots.drill.haltBody') }}</p>
      </div>

      <div>
        <p class="label mb-2">{{ t('bots.q25Drills') }}</p>
        <p class="text-xs text-ink-muted leading-relaxed mb-3">{{ t('bots.q25DrillsBody') }}</p>
        <div class="grid sm:grid-cols-2 gap-2">
          <div
            v-for="kind in Q25"
            :key="kind"
            class="flex items-center gap-2 rounded-lg border border-line px-3 py-2"
          >
            <UiIcon
              :name="done(kind) ? 'check' : 'alert'"
              :size="13"
              :class="done(kind) ? 'text-ok' : 'text-ink-faint'"
            />
            <span class="text-xs truncate">{{ t(`bots.stop.${kind}`) }}</span>
            <button
              class="btn-quiet btn-sm ms-auto shrink-0"
              :disabled="!running || busy === kind"
              @click="fire(kind)"
            >
              <UiIcon v-if="busy === kind" name="spinner" :size="12" class="animate-spin" />
              {{ done(kind) ? t('bots.rerunDrill') : t('bots.runDrill') }}
            </button>
          </div>
        </div>
      </div>

      <p v-if="error" class="alert px-3 py-2 text-xs leading-relaxed">{{ error }}</p>

      <div
        v-if="result"
        class="rounded-lg border border-ok/40 bg-ok-dim/30 px-3.5 py-3 text-xs leading-relaxed space-y-1"
      >
        <p class="font-medium">{{ t('bots.drillDone', { kind: t(`bots.drillKind.${result.kind}`, result.kind) }) }}</p>
        <p v-if="result.kind === 'halt'">
          {{ t('bots.drillClosed', { trades: result.trades_closed, ok: result.legs_ok, failed: result.legs_failed }) }}
        </p>
        <p>{{ result.resumed ? t('bots.drillResumed') : t('bots.drillNotResumed') }}</p>
      </div>
    </div>

    <UiModal
      :model-value="confirming !== null"
      :title="t('bots.drillConfirmTitle')"
      size="sm"
      @update:model-value="(v: boolean) => { if (!v) confirming = null }"
    >
      <p class="text-sm leading-relaxed">{{ t('bots.drillConfirmBody') }}</p>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost btn-sm" @click="confirming = null">{{ t('common.cancel') }}</button>
          <button class="btn-warn btn-sm" @click="fire(confirming!)">
            {{ t('bots.drillConfirmAction') }}
          </button>
        </div>
      </template>
    </UiModal>
  </UiCard>
</template>
