<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../stores/strategy'
import { useCredentialsStore } from '../../stores/credentials'
import { useToast } from '../../composables/useToast'
import type { LiveConfig } from '../../api/client'
import VersionHistory from '../pro/VersionHistory.vue'

const props = defineProps<{ strategyId: number }>()

const { t } = useI18n()
const store = useStrategyStore()
const credentials = useCredentialsStore()
const toast = useToast()

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1H', '4H', '1D']

const form = ref({
  name: '',
  credential: null as number | null,
  source: '',
  live_config: {
    symbols: [] as string[],
    timeframes: [] as string[],
    risk: { leverage: 1, position_size_pct: 5, global_stop_loss_pct: 10 },
  } as LiveConfig,
})

const newSymbol = ref('')
const saving = ref(false)
const dragOver = ref(false)
const validationMsg = ref('')
const showAdvancedRisk = ref(false)
const engineType = ref('pine')

const selected = computed(() => store.strategies.find((s) => s.id === props.strategyId) ?? null)

const hasCredential = computed(() => !!selected.value?.credential)

onMounted(async () => {
  if (!credentials.credentials.length) await credentials.fetchAll()
  if (!store.engines.length) await store.fetchEngines()
})

watch(
  [selected, () => props.strategyId],
  ([s]) => {
    if (!s) return
    engineType.value = s.type || 'pine'
    form.value = {
      name: s.name,
      credential: s.credential,
      source: s.source,
      live_config: {
        symbols: s.live_config?.symbols?.length ? [...s.live_config.symbols] : [s.symbol],
        timeframes: s.live_config?.timeframes?.length ? [...s.live_config.timeframes] : [s.timeframe],
        risk: {
          leverage: s.live_config?.risk?.leverage ?? 1,
          position_size_pct: s.live_config?.risk?.position_size_pct ?? 5,
          global_stop_loss_pct: s.live_config?.risk?.global_stop_loss_pct ?? 10,
          risk_per_trade_pct: s.live_config?.risk?.risk_per_trade_pct ?? 1,
          max_daily_loss_pct: s.live_config?.risk?.max_daily_loss_pct ?? 5,
          max_drawdown_pct: s.live_config?.risk?.max_drawdown_pct ?? 15,
          max_open_trades: s.live_config?.risk?.max_open_trades ?? 3,
          max_exposure_pct: s.live_config?.risk?.max_exposure_pct ?? 50,
          max_leverage: s.live_config?.risk?.max_leverage ?? 10,
        },
      },
    }
    validationMsg.value = ''
  },
  { immediate: true },
)

function addSymbol() {
  const v = newSymbol.value.trim().toUpperCase()
  if (v && !form.value.live_config.symbols?.includes(v)) {
    form.value.live_config.symbols = [...(form.value.live_config.symbols || []), v]
  }
  newSymbol.value = ''
}

function removeSymbol(s: string) {
  form.value.live_config.symbols = form.value.live_config.symbols?.filter((x) => x !== s)
}

function addTf(tf: string) {
  if (!form.value.live_config.timeframes?.includes(tf)) {
    form.value.live_config.timeframes = [...(form.value.live_config.timeframes || []), tf]
  }
}

function removeTf(tf: string) {
  form.value.live_config.timeframes = form.value.live_config.timeframes?.filter((x) => x !== tf)
}

function onFile(file: File) {
  const reader = new FileReader()
  reader.onload = () => {
    form.value.source = String(reader.result || '')
  }
  reader.readAsText(file)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) onFile(file)
}

async function save() {
  if (!selected.value) return
  saving.value = true
  try {
    await store.updateStrategy(selected.value.id, {
      name: form.value.name,
      credential: form.value.credential,
      source: form.value.source,
      type: engineType.value,
      live_config: form.value.live_config,
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
    validationMsg.value = t('strategy.validatedOk')
    toast.show(t('strategy.validatedOk'), 'success')
  } else {
    const loc =
      result.line != null ? ` (line ${result.line}, col ${result.column ?? '?'})` : ''
    validationMsg.value = `${result.error || t('strategy.validatedFail')}${loc}`
    toast.show(validationMsg.value, 'error')
  }
}

async function start() {
  if (!selected.value) return
  await store.start(selected.value.id)
  toast.show(t('strategy.starting'), 'info')
}

async function stop() {
  if (!selected.value) return
  await store.stop(selected.value.id)
  toast.show(t('strategy.stopping'), 'info')
}

function loadSourceFrom(id: number) {
  const s = store.strategies.find((x) => x.id === id)
  if (s?.source) form.value.source = s.source
}
</script>

<template>
  <div v-if="selected" class="p-4 space-y-4">
    <h2 class="text-sm font-semibold text-zinc-300">{{ t('strategy.title') }}</h2>

    <div>
      <label class="text-xs text-zinc-500">{{ t('strategy.name') }}</label>
      <input
        v-model="form.name"
        class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
      />
    </div>

    <div>
      <label class="text-xs text-zinc-500">{{ t('strategy.engine') }}</label>
      <select
        v-model="engineType"
        class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
      >
        <option v-for="e in store.engines" :key="e" :value="e">{{ e }}</option>
      </select>
      <p v-if="engineType === 'ai'" class="text-xs text-zinc-500 mt-1">{{ t('strategy.aiHint') }}</p>
    </div>

    <div>
      <label class="text-xs text-zinc-500">
        {{ t('credentials.label') }}
        <span class="text-zinc-600">({{ t('strategy.credentialOptional') }})</span>
      </label>
      <select
        v-model="form.credential"
        class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm"
      >
        <option :value="null">{{ t('strategy.noCredentialBacktestOnly') }}</option>
        <option v-for="c in credentials.credentials" :key="c.id" :value="c.id">
          {{ c.label }}
        </option>
      </select>
      <p v-if="!hasCredential" class="text-xs text-zinc-500 mt-1">{{ t('strategy.liveRequiresCredential') }}</p>
    </div>

    <div>
      <label class="text-xs text-zinc-500">{{ t('strategy.source') }}</label>
      <select
        class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm mb-1"
        @change="loadSourceFrom(Number(($event.target as HTMLSelectElement).value))"
      >
        <option value="">— load from validated —</option>
        <option v-for="s in store.validatedStrategies" :key="s.id" :value="s.id">
          {{ s.name }}
        </option>
      </select>
      <div
        class="rounded-lg border border-dashed px-2 py-2 text-center text-[10px] text-zinc-600 mb-1"
        :class="dragOver ? 'border-emerald-500' : 'border-zinc-700'"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
      >
        {{ t('strategies.dropPine') }}
      </div>
      <textarea
        v-model="form.source"
        rows="8"
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs font-mono"
      />
      <div class="mt-1 flex items-center gap-2">
        <span
          v-if="selected.validation_status === 'ok'"
          class="text-xs text-emerald-400"
        >✓ {{ t('strategy.validatedOk') }}</span>
        <span
          v-else-if="selected.validation_status === 'error'"
          class="text-xs text-red-400"
        >✗ {{ selected.validation_error || t('strategy.validatedFail') }}</span>
      </div>
      <p v-if="validationMsg" class="text-xs text-zinc-500 mt-1 font-mono">{{ validationMsg }}</p>
    </div>

    <div>
      <label class="text-xs text-zinc-500">{{ t('strategy.symbols') }}</label>
      <div class="flex flex-wrap gap-1 mt-1 mb-1">
        <span
          v-for="sym in form.live_config.symbols"
          :key="sym"
          class="inline-flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 text-xs"
        >
          {{ sym }}
          <button type="button" class="text-zinc-500 hover:text-red-400" @click="removeSymbol(sym)">×</button>
        </span>
      </div>
      <div class="flex gap-1">
        <input
          v-model="newSymbol"
          :placeholder="t('strategy.addSymbol')"
          class="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs"
          @keydown.enter.prevent="addSymbol"
        />
        <button type="button" class="rounded bg-zinc-800 px-2 text-xs" @click="addSymbol">+</button>
      </div>
    </div>

    <div>
      <label class="text-xs text-zinc-500">{{ t('strategy.timeframes') }}</label>
      <div class="flex flex-wrap gap-1 mt-1 mb-1">
        <span
          v-for="tf in form.live_config.timeframes"
          :key="tf"
          class="inline-flex items-center gap-1 rounded bg-zinc-800 px-2 py-0.5 text-xs"
        >
          {{ tf }}
          <button type="button" class="text-zinc-500 hover:text-red-400" @click="removeTf(tf)">×</button>
        </span>
      </div>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="tf in TIMEFRAMES"
          :key="tf"
          type="button"
          class="rounded border border-zinc-700 px-2 py-0.5 text-xs hover:bg-zinc-800"
          @click="addTf(tf)"
        >
          {{ tf }}
        </button>
      </div>
    </div>

    <div class="grid grid-cols-3 gap-2">
      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.leverage') }}</label>
        <input
          v-model.number="form.live_config.risk!.leverage"
          type="number"
          min="1"
          class="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs"
        />
      </div>
      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.positionSize') }}</label>
        <input
          v-model.number="form.live_config.risk!.position_size_pct"
          type="number"
          min="0"
          step="0.1"
          class="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs"
        />
      </div>
      <div>
        <label class="text-xs text-zinc-500">{{ t('strategy.globalSl') }}</label>
        <input
          v-model.number="form.live_config.risk!.global_stop_loss_pct"
          type="number"
          min="0"
          step="0.1"
          class="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs"
        />
      </div>
    </div>

    <div>
      <button
        type="button"
        class="text-xs text-zinc-500 hover:text-zinc-300"
        @click="showAdvancedRisk = !showAdvancedRisk"
      >
        {{ showAdvancedRisk ? '▼' : '▶' }} {{ t('strategy.advancedRisk') }}
      </button>
      <div v-if="showAdvancedRisk" class="grid grid-cols-2 gap-2 mt-2">
        <div v-for="field in ['risk_per_trade_pct', 'max_daily_loss_pct', 'max_drawdown_pct', 'max_open_trades', 'max_exposure_pct', 'max_leverage']" :key="field">
          <label class="text-[10px] text-zinc-600">{{ field }}</label>
          <input
            v-model.number="(form.live_config.risk as Record<string, number>)[field]"
            type="number"
            class="mt-0.5 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs"
          />
        </div>
      </div>
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        type="button"
        class="rounded-lg bg-zinc-800 px-3 py-1.5 text-xs hover:bg-zinc-700"
        :disabled="saving"
        @click="save"
      >
        {{ t('strategy.save') }}
      </button>
      <button type="button" class="rounded-lg bg-zinc-800 px-3 py-1.5 text-xs hover:bg-zinc-700" @click="validate">
        {{ t('strategy.validate') }}
      </button>
      <template v-if="hasCredential">
        <button type="button" class="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs hover:bg-emerald-600" @click="start">
          {{ t('strategy.start') }}
        </button>
        <button type="button" class="rounded-lg bg-amber-800 px-3 py-1.5 text-xs hover:bg-amber-700" @click="stop">
          {{ t('strategy.stop') }}
        </button>
      </template>
    </div>

    <VersionHistory :strategy-id="strategyId" />
  </div>
</template>
