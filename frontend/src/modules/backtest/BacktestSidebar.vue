<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../stores/strategy'
import { useChartStore } from '../../stores/chart'
import { useBacktestStore } from '../../stores/backtest'
import { useToast } from '../../composables/useToast'
import { useHotkeys } from '../../composables/useHotkeys'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import PineEditorModal from './PineEditorModal.vue'
import AdvancedSettingsModal from './AdvancedSettingsModal.vue'
import BacktestResultsModal from './BacktestResultsModal.vue'
import type { LiveConfig } from '../../api/client'

const props = defineProps<{ strategyId: number }>()

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1H', '4H', '1D']

const { t } = useI18n()
const store = useStrategyStore()
const chartStore = useChartStore()
const backtestStore = useBacktestStore()
const toast = useToast()

const form = ref({
  name: '',
  source: '',
  symbol: 'BTC-USDT',
  timeframe: '15m',
  live_config: {
    symbols: [] as string[],
    timeframes: [] as string[],
    risk: { leverage: 1, position_size_pct: 5, global_stop_loss_pct: 10 },
  } as LiveConfig,
  warmup_bars: 20,
})

const saving = ref(false)
const showPineModal = ref(false)
const showAdvancedModal = ref(false)

const selected = computed(() => store.strategies.find((s) => s.id === props.strategyId) ?? null)

watch(
  [selected, () => props.strategyId],
  ([s]) => {
    if (!s) return
    const sym = s.live_config?.symbols?.[0] || s.symbol
    const tf = s.live_config?.timeframes?.[0] || s.timeframe
    form.value = {
      name: s.name,
      source: s.source,
      symbol: sym,
      timeframe: tf,
      live_config: {
        symbols: [sym],
        timeframes: [tf],
        risk: {
          leverage: s.live_config?.risk?.leverage ?? 1,
          position_size_pct: s.live_config?.risk?.position_size_pct ?? 5,
          global_stop_loss_pct: s.live_config?.risk?.global_stop_loss_pct ?? 10,
        },
      },
      warmup_bars: s.warmup_bars ?? 20,
    }
  },
  { immediate: true },
)

async function save() {
  if (!selected.value) return
  saving.value = true
  try {
    await store.updateStrategy(selected.value.id, {
      name: form.value.name,
      source: form.value.source,
      warmup_bars: form.value.warmup_bars,
      live_config: {
        symbols: [form.value.symbol],
        timeframes: [form.value.timeframe],
        risk: form.value.live_config.risk,
      },
    })
    toast.show(t('strategy.saved'), 'success')
  } catch {
    toast.show(t('strategy.saveFailed'), 'error')
  } finally {
    saving.value = false
  }
}

async function validate() {
  if (!selected.value) return
  await save()
  const result = await store.validate(selected.value.id)
  if (result.ok) {
    toast.show(t('strategy.validatedOk'), 'success')
  } else {
    const loc =
      result.line != null ? ` (line ${result.line}, col ${result.column ?? '?'})` : ''
    toast.show(`${result.error || t('strategy.validatedFail')}${loc}`, 'error')
  }
}

async function runBacktest() {
  if (!selected.value || backtestStore.running) return
  if (selected.value.validation_status !== 'ok') {
    toast.show(t('backtest.validateFirst'), 'info')
    return
  }
  try {
    await save()
    const candles = await chartStore.fetchCandles(form.value.symbol, form.value.timeframe)
    if (!candles.length) {
      toast.show(t('backtest.noCandles'), 'error')
      return
    }
    const result = await backtestStore.runBacktest(selected.value.id, {
      symbol: form.value.symbol,
      timeframe: form.value.timeframe,
      candles,
    })
    if (result.status === 'failed') {
      toast.show(result.error || t('backtest.failed'), 'error')
    } else {
      toast.show(t('backtest.complete'), 'success')
      backtestStore.openResults()
    }
  } catch (e) {
    toast.show(e instanceof Error ? e.message : t('backtest.failed'), 'error')
  }
}

useHotkeys({ 'mod+enter': runBacktest })

async function onAdvancedSave(payload: { live_config: LiveConfig; warmup_bars: number }) {
  form.value.live_config = payload.live_config
  form.value.warmup_bars = payload.warmup_bars
  await save()
}

async function onPineSave() {
  await save()
  showPineModal.value = false
}

function validationBadgeClass(status: string) {
  if (status === 'ok') return 'bg-emerald-900/50 text-emerald-400'
  if (status === 'error') return 'bg-red-900/50 text-red-400'
  return 'bg-zinc-800 text-zinc-400'
}
</script>

<template>
  <aside class="flex h-full w-80 shrink-0 flex-col border-s border-zinc-800 bg-zinc-900/30">
  <div class="flex-1 overflow-y-auto p-4">
    <div v-if="!selected && store.loading" class="space-y-3">
      <SkeletonBlock class="h-6 w-32" />
      <SkeletonBlock class="h-10 w-full" />
      <SkeletonBlock class="h-10 w-full" />
      <SkeletonBlock class="h-24 w-full" />
    </div>

    <div v-else-if="selected" class="space-y-4">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-sm font-semibold text-zinc-200">{{ t('strategy.title') }}</h2>
        <span
          class="rounded-full px-2 py-0.5 text-[10px] font-medium uppercase"
          :class="validationBadgeClass(selected.validation_status)"
        >
          {{ selected.validation_status || 'draft' }}
        </span>
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.name') }}</label>
        <input
          v-model="form.name"
          class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
        />
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.symbols') }}</label>
        <select
          v-model="form.symbol"
          class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
        >
          <option :value="form.symbol">{{ form.symbol }}</option>
          <option
            v-for="sym in selected.live_config?.symbols?.filter((s) => s !== form.symbol) ?? []"
            :key="sym"
            :value="sym"
          >
            {{ sym }}
          </option>
        </select>
      </div>

      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.timeframes') }}</label>
        <select
          v-model="form.timeframe"
          class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
        >
          <option v-for="tf in TIMEFRAMES" :key="tf" :value="tf">{{ tf }}</option>
        </select>
      </div>

      <button
        type="button"
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-left text-sm text-zinc-300 hover:border-violet-600 hover:bg-zinc-900"
        @click="showPineModal = true"
      >
        <span class="text-violet-400">⟨/⟩</span>
        {{ t('backtest.editPine') }}
        <span class="mt-0.5 block truncate text-[10px] text-zinc-600">
          {{ form.source ? `${form.source.length} chars` : t('backtest.noSource') }}
        </span>
      </button>

      <button
        type="button"
        class="flex w-full items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        @click="showAdvancedModal = true"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        {{ t('backtest.advanced') }}
      </button>

      <button
        type="button"
        class="w-full rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
        :disabled="backtestStore.running || saving"
        @click="runBacktest"
      >
        {{ backtestStore.running ? t('backtest.running') : t('backtest.run') }}
      </button>
      <p class="text-center text-[10px] text-zinc-600">{{ t('backtest.hotkeyHint') }}</p>

      <div class="flex gap-2">
        <button
          type="button"
          class="flex-1 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs hover:bg-zinc-700"
          :disabled="saving"
          @click="save"
        >
          {{ t('strategy.save') }}
        </button>
        <button
          type="button"
          class="flex-1 rounded-lg bg-zinc-800 px-3 py-1.5 text-xs hover:bg-zinc-700"
          @click="validate"
        >
          {{ t('strategy.validate') }}
        </button>
      </div>
    </div>

    <div v-else class="p-4 text-sm text-zinc-500">{{ t('overview.loading') }}</div>
  </div>

  <PineEditorModal
    v-if="showPineModal"
    v-model="form.source"
    @close="showPineModal = false"
    @save="onPineSave"
  />

  <AdvancedSettingsModal
    v-if="showAdvancedModal"
    :strategy-id="strategyId"
    :live-config="form.live_config"
    :warmup-bars="form.warmup_bars"
    @close="showAdvancedModal = false"
    @save="onAdvancedSave"
    @load-source="(src) => { form.source = src; save() }"
  />

  <BacktestResultsModal
    v-if="backtestStore.showResults && backtestStore.lastResult"
    :backtest="backtestStore.lastResult"
    @close="backtestStore.closeResults()"
    @view-chart="backtestStore.closeResults()"
  />
  </aside>
</template>
