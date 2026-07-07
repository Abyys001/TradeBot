<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import BaseModal from '../../components/BaseModal.vue'
import RangeField from '../../components/RangeField.vue'
import { useStrategyStore } from '../../stores/strategy'
import type { LiveConfig } from '../../api/client'

const props = defineProps<{
  strategyId: number
  liveConfig: LiveConfig
  warmupBars: number
}>()

const emit = defineEmits<{
  close: []
  save: [payload: { live_config: LiveConfig; warmup_bars: number }]
  loadSource: [source: string]
}>()

const { t } = useI18n()
const store = useStrategyStore()

const risk = ref({
  leverage: 1,
  position_size_pct: 5,
  global_stop_loss_pct: 10,
})
const warmup = ref(20)
const loadFromId = ref<number | ''>('')

watch(
  () => props.liveConfig,
  (cfg) => {
    risk.value = {
      leverage: cfg.risk?.leverage ?? 1,
      position_size_pct: cfg.risk?.position_size_pct ?? 5,
      global_stop_loss_pct: cfg.risk?.global_stop_loss_pct ?? 10,
    }
  },
  { immediate: true },
)

watch(
  () => props.warmupBars,
  (v) => {
    warmup.value = v
  },
  { immediate: true },
)

function onLoadSource() {
  if (!loadFromId.value) return
  const s = store.strategies.find((x) => x.id === Number(loadFromId.value))
  if (s?.source) emit('loadSource', s.source)
}

function apply() {
  emit('save', {
    live_config: {
      ...props.liveConfig,
      risk: { ...risk.value },
    },
    warmup_bars: warmup.value,
  })
  emit('close')
}
</script>

<template>
  <BaseModal size="lg" :title="t('backtest.advanced')" @close="emit('close')">
    <div class="space-y-5">
      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.source') }}</label>
        <div class="mt-1 flex gap-2">
          <select
            v-model="loadFromId"
            class="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
          >
            <option value="">— {{ t('backtest.loadValidated') }} —</option>
            <option v-for="s in store.validatedStrategies" :key="s.id" :value="s.id">
              {{ s.name }}
            </option>
          </select>
          <button
            type="button"
            class="rounded-lg bg-zinc-800 px-3 text-xs text-zinc-300 hover:bg-zinc-700"
            :disabled="!loadFromId"
            @click="onLoadSource"
          >
            Load
          </button>
        </div>
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('backtest.warmupBars') }}</label>
        <input
          v-model.number="warmup"
          type="number"
          min="0"
          class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
        />
      </div>

      <div class="space-y-4 rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
        <h3 class="text-xs font-medium uppercase tracking-wide text-zinc-500">
          {{ t('backtest.riskLimits') }}
        </h3>
        <RangeField v-model="risk.leverage" :label="t('strategy.leverage')" :min="1" :max="50" />
        <RangeField
          v-model="risk.position_size_pct"
          :label="t('strategy.positionSize')"
          :min="0.1"
          :max="100"
          :step="0.1"
          unit="%"
        />
        <RangeField
          v-model="risk.global_stop_loss_pct"
          :label="t('strategy.globalSl')"
          :min="0.1"
          :max="50"
          :step="0.1"
          unit="%"
        />
      </div>
    </div>
    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-lg px-4 py-2 text-sm text-zinc-400"
          @click="emit('close')"
        >
          {{ t('health.cancel') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-zinc-700 px-4 py-2 text-sm text-white hover:bg-zinc-600"
          @click="apply"
        >
          {{ t('strategy.save') }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>
