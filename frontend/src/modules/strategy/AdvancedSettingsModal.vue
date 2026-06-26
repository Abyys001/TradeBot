<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppModal from '../../components/AppModal.vue'
import SliderInput from '../../components/SliderInput.vue'
import { ADVANCED_RISK_FIELDS, TIMEFRAME_OPTIONS, type StrategyForm } from '../../composables/useStrategyForm'

const props = defineProps<{ strategyForm: StrategyForm }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const showAdvancedRisk = ref(false)

const sf = props.strategyForm
const isSaving = computed(() => sf.saving.value)

const leverageMax = computed(
  () => Math.max(1, sf.form.live_config.risk?.max_leverage ?? 50),
)

const leverage = computed({
  get: () => sf.form.live_config.risk?.leverage ?? 1,
  set: (v: number) => {
    if (sf.form.live_config.risk) sf.form.live_config.risk.leverage = v
  },
})

const positionSizePct = computed({
  get: () => sf.form.live_config.risk?.position_size_pct ?? 5,
  set: (v: number) => {
    if (sf.form.live_config.risk) sf.form.live_config.risk.position_size_pct = v
  },
})

const globalStopLossPct = computed({
  get: () => sf.form.live_config.risk?.global_stop_loss_pct ?? 10,
  set: (v: number) => {
    if (sf.form.live_config.risk) sf.form.live_config.risk.global_stop_loss_pct = v
  },
})

const inputClass =
  'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-violet-600 focus:outline-none focus:ring-1 focus:ring-violet-600/40'

async function onSave() {
  const ok = await sf.save()
  if (ok) emit('close')
}
</script>

<template>
  <AppModal :title="t('backtest.advancedSettings')" size="lg" @close="emit('close')">
    <div class="space-y-4 p-4">
      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.name') }}</label>
        <input v-model="sf.form.name" :class="inputClass" />
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.engine') }}</label>
        <select v-model="sf.engineType" :class="inputClass">
          <option v-for="e in sf.store.engines" :key="e" :value="e">{{ e }}</option>
        </select>
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.source') }}</label>
        <select
          :class="inputClass"
          @change="sf.loadSourceFrom(Number(($event.target as HTMLSelectElement).value))"
        >
          <option value="">{{ t('backtest.loadValidated') }}</option>
          <option v-for="s in sf.store.validatedStrategies" :key="s.id" :value="s.id">
            {{ s.name }}
          </option>
        </select>
        <p class="mt-1 text-xs text-zinc-600">{{ t('backtest.loadValidatedHint') }}</p>
      </div>

      <div class="space-y-4">
        <h3 class="text-xs font-medium text-zinc-400">{{ t('strategy.riskSection') }}</h3>
        <SliderInput
          v-model="leverage"
          :label="t('strategy.leverage')"
          :min="1"
          :max="leverageMax"
          suffix="x"
        />
        <SliderInput
          v-model="positionSizePct"
          :label="t('strategy.positionSize')"
          :min="0"
          :max="100"
          :step="0.1"
          suffix="%"
        />
        <SliderInput
          v-model="globalStopLossPct"
          :label="t('strategy.globalSl')"
          :min="0"
          :max="100"
          :step="0.1"
          suffix="%"
        />
      </div>

      <div>
        <button
          type="button"
          class="text-xs text-zinc-500 hover:text-zinc-300"
          @click="showAdvancedRisk = !showAdvancedRisk"
        >
          {{ showAdvancedRisk ? '▼' : '▶' }} {{ t('strategy.advancedRisk') }}
        </button>
        <div v-if="showAdvancedRisk" class="mt-2 grid grid-cols-2 gap-2">
          <div v-for="field in ADVANCED_RISK_FIELDS" :key="field">
            <label class="text-[10px] text-zinc-600">{{ field }}</label>
            <input
              v-model.number="(sf.form.live_config.risk as Record<string, number>)[field]"
              type="number"
              class="mt-0.5 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs"
            />
          </div>
        </div>
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.symbols') }}</label>
        <div class="mt-1 mb-2 flex flex-wrap gap-1">
          <span
            v-for="sym in sf.form.live_config.symbols"
            :key="sym"
            class="inline-flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 text-xs"
          >
            {{ sym }}
            <button type="button" class="text-zinc-500 hover:text-red-400" @click="sf.removeSymbol(sym)">×</button>
          </span>
        </div>
        <div class="flex gap-1">
          <input
            v-model="sf.newSymbol"
            :placeholder="t('strategy.addSymbol')"
            class="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
            @keydown.enter.prevent="sf.addSymbol"
          />
          <button type="button" class="rounded-lg bg-zinc-800 px-3 text-sm" @click="sf.addSymbol">+</button>
        </div>
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.timeframes') }}</label>
        <div class="mt-1 mb-2 flex flex-wrap gap-1">
          <span
            v-for="tf in sf.form.live_config.timeframes"
            :key="tf"
            class="inline-flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 text-xs"
          >
            {{ tf }}
            <button type="button" class="text-zinc-500 hover:text-red-400" @click="sf.removeTf(tf)">×</button>
          </span>
        </div>
        <select
          class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-200"
          @change="sf.addTf(($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
        >
          <option value="">{{ t('strategy.addTimeframe') }}</option>
          <option v-for="tf in TIMEFRAME_OPTIONS" :key="tf" :value="tf">{{ tf }}</option>
        </select>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          @click="emit('close')"
        >
          {{ t('modal.close') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
          :disabled="isSaving"
          @click="onSave"
        >
          {{ t('modal.save') }}
        </button>
      </div>
    </template>
  </AppModal>
</template>
