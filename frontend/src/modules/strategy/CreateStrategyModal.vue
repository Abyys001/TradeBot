<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../stores/strategy'
import { useCredentialsStore } from '../../stores/credentials'
import { useToast } from '../../composables/useToast'
import TradingPairSelector from '../../components/TradingPairSelector.vue'

const props = defineProps<{ initialSource?: string; forceCopyTrading?: boolean }>()
const emit = defineEmits<{ close: []; created: [id: number] }>()

const { t } = useI18n()
const store = useStrategyStore()
const credentials = useCredentialsStore()
const toast = useToast()

const name = ref('New Strategy')
const credentialId = ref<number | null>(null)
const selectedSymbols = ref<string[]>(['BTC-USDT'])
const selectedTimeframes = ref<string[]>(['1h'])
const source = ref(props.initialSource || '')
const engineType = ref('pine')
const saving = ref(false)
const dragOver = ref(false)

// Bot-cards flow (forceCopyTrading): live orders only ever route through the
// copy-trading fan-out, which only ever pays out to Tabdeal credentials -- a
// Hyperliquid credential here would fail on the first live bar.
const availableCredentials = computed(() =>
  props.forceCopyTrading
    ? credentials.credentials.filter((c) => c.exchange === 'tabdeal')
    : credentials.credentials,
)

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1H', '4H', '1D']

function toggleTf(tf: string) {
  if (selectedTimeframes.value.includes(tf)) {
    selectedTimeframes.value = selectedTimeframes.value.filter((x) => x !== tf)
  } else {
    selectedTimeframes.value = [...selectedTimeframes.value, tf]
  }
}

onMounted(async () => {
  if (!credentials.credentials.length) await credentials.fetchAll()
  if (!store.engines.length) await store.fetchEngines()
  credentialId.value = availableCredentials.value[0]?.id ?? null
})

function onFile(file: File) {
  const reader = new FileReader()
  reader.onload = () => {
    source.value = String(reader.result || '')
  }
  reader.readAsText(file)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) onFile(file)
}

function onFileInput(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) onFile(file)
}

async function submit() {
  saving.value = true
  try {
    const s = await store.createStrategy({
      name: name.value,
      type: engineType.value,
      credential: credentialId.value,
      symbol: selectedSymbols.value[0] || 'BTC-USDT',
      source: source.value,
      live_config: {
        symbols: selectedSymbols.value.length ? selectedSymbols.value : ['BTC-USDT'],
        timeframes: selectedTimeframes.value.length ? selectedTimeframes.value : ['1h'],
        risk: { leverage: 1, position_size_pct: 5, global_stop_loss_pct: 10 },
        ...(props.forceCopyTrading ? { copy_trading: true } : {}),
      },
    })
    emit('created', s.id)
  } catch {
    toast.show(t('strategy.saveFailed'), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
    <div class="scrollbar-styled scrollbar-thin w-full max-w-lg rounded-xl border border-zinc-700 bg-zinc-900 p-6 max-h-[90vh] overflow-y-auto">
      <h2 class="text-lg font-semibold text-zinc-200 mb-4">{{ t('strategies.new') }}</h2>

      <div class="space-y-3">
        <div>
          <label class="text-xs text-zinc-500">{{ t('strategy.name') }}</label>
          <input v-model="name" class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="text-xs text-zinc-500">{{ t('strategy.engine') }}</label>
          <select v-model="engineType" class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm">
            <option v-for="e in store.engines" :key="e" :value="e">{{ e }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-zinc-500">
            {{ t('credentials.label') }}
            <span class="text-zinc-600">({{ t('strategy.credentialOptional') }})</span>
          </label>
          <select v-model="credentialId" class="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm">
            <option v-if="!forceCopyTrading" :value="null">{{ t('strategy.noCredentialBacktestOnly') }}</option>
            <option v-for="c in availableCredentials" :key="c.id" :value="c.id">
              {{ c.label }} ({{ c.network }})
            </option>
          </select>
          <p v-if="!availableCredentials.length" class="text-xs text-zinc-500 mt-1">
            {{ t('strategy.liveRequiresCredential') }}
          </p>
        </div>
        <div>
          <label class="text-xs text-zinc-500">{{ t('strategy.symbols') }}</label>
          <TradingPairSelector
            v-model="selectedSymbols"
            multiple
            class="mt-1"
          />
          <p class="mt-1 text-[10px] text-zinc-600">{{ t('strategy.pairsHint') }}</p>
        </div>
        <div>
          <label class="text-xs text-zinc-500">{{ t('strategy.timeframes') }}</label>
          <div class="mt-1 flex flex-wrap gap-1">
            <button
              v-for="tf in TIMEFRAMES"
              :key="tf"
              type="button"
              class="rounded px-2 py-0.5 text-xs transition-colors"
              :class="selectedTimeframes.includes(tf) ? 'bg-emerald-900 text-emerald-300' : 'bg-zinc-800 text-zinc-400'"
              @click="toggleTf(tf)"
            >
              {{ tf }}
            </button>
          </div>
        </div>
        <div>
          <label class="text-xs text-zinc-500">{{ t('strategy.source') }}</label>
          <div
            class="mt-1 rounded-lg border border-dashed px-3 py-4 text-center text-xs transition-colors"
            :class="dragOver ? 'border-emerald-500 bg-emerald-950/20' : 'border-zinc-700 text-zinc-500'"
            @dragover.prevent="dragOver = true"
            @dragleave="dragOver = false"
            @drop.prevent="onDrop"
          >
            {{ t('strategies.dropPine') }}
            <input type="file" accept=".pine,.txt" class="mt-2 text-xs" @change="onFileInput" />
          </div>
          <textarea
            v-model="source"
            rows="8"
            class="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs font-mono"
            :placeholder="t('strategies.pinePlaceholder')"
          />
        </div>
      </div>

      <div class="flex justify-end gap-2 mt-6">
        <button type="button" class="px-4 py-2 text-sm text-zinc-400" @click="emit('close')">
          {{ t('health.cancel') }}
        </button>
        <button
          type="button"
          class="px-4 py-2 text-sm bg-emerald-700 text-white rounded-lg disabled:opacity-40"
          :disabled="saving"
          @click="submit"
        >
          {{ t('strategies.create') }}
        </button>
      </div>
    </div>
  </div>
</template>
