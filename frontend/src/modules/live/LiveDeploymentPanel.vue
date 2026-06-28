<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchCsrf } from '../../api/client'
import { useStrategyStore } from '../../stores/strategy'
import { useCredentialsStore } from '../../stores/credentials'
import { useToast } from '../../composables/useToast'

const props = defineProps<{ strategyId: number }>()
const { t } = useI18n()
const store = useStrategyStore()
const credentials = useCredentialsStore()
const toast = useToast()

const activeTab = ref<'config' | 'status'>('status')
const saving = ref(false)
const starting = ref(false)
const stopping = ref(false)

const strategy = computed(() => store.strategies.find((s) => s.id === props.strategyId) ?? null)
const state = computed(() => strategy.value?.state ?? null)
const isLive = computed(() => !!state.value?.live_started_at)

const form = ref({
  credential: strategy.value?.credential ?? null,
  symbol: '',
  timeframe: '1m',
  leverage: 5,
  position_size_pct: 20,
  max_drawdown_pct: 25,
  max_daily_loss_pct: 10,
  max_open_trades: 3,
})

onMounted(async () => {
  await fetchCsrf()
  await credentials.fetchAll()
  if (strategy.value) {
    const lc = strategy.value.live_config
    form.value = {
      credential: strategy.value.credential,
      symbol: strategy.value.symbol,
      timeframe: strategy.value.timeframe,
      leverage: lc.risk?.leverage ?? 5,
      position_size_pct: lc.risk?.position_size_pct ?? 20,
      max_drawdown_pct: lc.risk?.max_drawdown_pct ?? 25,
      max_daily_loss_pct: lc.risk?.max_daily_loss_pct ?? 10,
      max_open_trades: lc.risk?.max_open_trades ?? 3,
    }
  }
  if (isLive.value) activeTab.value = 'status'
})

async function saveConfig() {
  saving.value = true
  try {
    await store.updateStrategy(props.strategyId, {
      credential: form.value.credential,
      symbol: form.value.symbol || strategy.value?.symbol || 'BTC-USDT',
      timeframe: form.value.timeframe,
      live_config: {
        symbols: [form.value.symbol || strategy.value?.symbol || 'BTC-USDT'],
        timeframes: [form.value.timeframe],
        risk: {
          leverage: form.value.leverage,
          position_size_pct: form.value.position_size_pct,
          max_drawdown_pct: form.value.max_drawdown_pct,
          max_daily_loss_pct: form.value.max_daily_loss_pct,
          max_open_trades: form.value.max_open_trades,
        },
      },
    })
    toast.show(t('live.configSaved'), 'success')
  } catch {
    toast.show(t('live.failed'), 'error')
  } finally {
    saving.value = false
  }
}

async function start() {
  if (!strategy.value) return
  starting.value = true
  try {
    await saveConfig()
    await store.start(props.strategyId)
    toast.show(t('live.started'), 'success')
    activeTab.value = 'status'
  } catch {
    toast.show(t('live.failed'), 'error')
  } finally {
    starting.value = false
  }
}

async function stop() {
  stopping.value = true
  try {
    await store.stop(props.strategyId)
    toast.show(t('live.stopped'), 'success')
  } catch {
    toast.show(t('live.stopFailed'), 'error')
  } finally {
    stopping.value = false
  }
}

const canStart = computed(() => {
  if (!strategy.value) return false
  if (strategy.value.validation_status !== 'ok') return false
  return true
})
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <div v-if="!strategy" class="flex flex-1 items-center justify-center text-xs text-zinc-500">
      {{ t('live.noStrategy') }}
    </div>

    <template v-else>
      <div class="flex gap-2 border-b border-zinc-800 px-4 py-2">
        <button
          type="button"
          class="rounded px-3 py-1 text-xs font-medium transition-colors"
          :class="activeTab === 'status' ? 'bg-violet-700 text-white' : 'text-zinc-400 hover:text-zinc-200'"
          @click="activeTab = 'status'"
        >
          Status
        </button>
        <button
          type="button"
          class="rounded px-3 py-1 text-xs font-medium transition-colors"
          :class="activeTab === 'config' ? 'bg-violet-700 text-white' : 'text-zinc-400 hover:text-zinc-200'"
          @click="activeTab = 'config'"
        >
          Configuration
        </button>
      </div>

      <div v-if="activeTab === 'status'" class="flex-1 overflow-y-auto p-4 space-y-3">
        <div class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 text-xs space-y-2">
          <div class="flex justify-between">
            <span class="text-zinc-500">{{ t('live.statusNotRunning') }}</span>
            <span v-if="isLive" class="text-emerald-400 font-medium">{{ t('live.statusRunning') }}</span>
            <span v-else class="text-zinc-500">{{ t('live.statusNotRunning') }}</span>
          </div>
          <div v-if="strategy.validation_status !== 'ok'" class="text-amber-400">
            {{ t('live.noStrategy') }}: {{ strategy.validation_error }}
          </div>
          <div v-if="state?.last_bar_ts" class="flex justify-between">
            <span class="text-zinc-500">{{ t('live.lastBar') }}</span>
            <span class="text-zinc-300">{{ new Date(state.last_bar_ts * 1000).toLocaleString() }}</span>
          </div>
          <div v-if="state?.last_signal" class="flex justify-between">
            <span class="text-zinc-500">{{ t('live.lastSignal') }}</span>
            <span class="text-zinc-300">{{ state.last_signal }}</span>
          </div>
          <div v-if="state?.position" class="flex justify-between">
            <span class="text-zinc-500">{{ t('live.currentPosition') }}</span>
            <span class="text-zinc-300">{{ JSON.stringify(state.position) }}</span>
          </div>
          <div v-if="state?.pnl" class="flex justify-between">
            <span class="text-zinc-500">{{ t('live.currentPnl') }}</span>
            <span :class="Number(state.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ state.pnl }}
            </span>
          </div>
          <div v-if="state?.live_error" class="text-red-400 text-xs mt-2">
            {{ state.live_error }}
          </div>
        </div>

        <div class="flex gap-2">
          <button
            v-if="!isLive"
            type="button"
            class="flex-1 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
            :disabled="starting || !canStart"
            @click="start"
          >
            {{ starting ? t('live.starting') : t('live.start') }}
          </button>
          <button
            v-if="isLive"
            type="button"
            class="flex-1 rounded-lg bg-red-700 px-3 py-2 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
            :disabled="stopping"
            @click="stop"
          >
            {{ stopping ? t('live.stopping') : t('live.stop') }}
          </button>
        </div>
      </div>

      <div v-if="activeTab === 'config'" class="flex-1 overflow-y-auto p-4 space-y-3">
        <label class="block text-xs text-zinc-500">
          {{ t('live.selectCredential') }}
          <select
            v-model="form.credential"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          >
            <option :value="null">—</option>
            <option
              v-for="c in credentials.credentials"
              :key="c.id"
              :value="c.id"
            >
              {{ c.label }} ({{ c.wallet_address }})
            </option>
          </select>
        </label>

        <label class="block text-xs text-zinc-500">
          {{ t('live.symbol') }}
          <input
            v-model="form.symbol"
            type="text"
            placeholder="BTC-USDT"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          />
        </label>

        <label class="block text-xs text-zinc-500">
          {{ t('live.timeframe') }}
          <select
            v-model="form.timeframe"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          >
            <option value="1m">1m</option>
            <option value="5m">5m</option>
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
            <option value="1d">1d</option>
          </select>
        </label>

        <label class="block text-xs text-zinc-500">
          {{ t('live.leverage') }}
          <input
            v-model.number="form.leverage"
            type="number"
            min="1"
            max="50"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          />
        </label>

        <label class="block text-xs text-zinc-500">
          {{ t('live.positionSize') }}
          <span class="text-zinc-600 ms-1">{{ t('live.positionSizeHint') }}</span>
          <input
            v-model.number="form.position_size_pct"
            type="number"
            min="1"
            max="100"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          />
        </label>

        <label class="block text-xs text-zinc-500">
          {{ t('live.maxDrawdown') }}
          <input
            v-model.number="form.max_drawdown_pct"
            type="number"
            min="1"
            max="100"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          />
        </label>

        <label class="block text-xs text-zinc-500">
          {{ t('live.maxDailyLoss') }}
          <input
            v-model.number="form.max_daily_loss_pct"
            type="number"
            min="1"
            max="100"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          />
        </label>

        <label class="block text-xs text-zinc-500">
          {{ t('live.maxOpenTrades') }}
          <input
            v-model.number="form.max_open_trades"
            type="number"
            min="1"
            max="20"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
          />
        </label>

        <button
          type="button"
          class="w-full rounded-lg bg-violet-700 px-3 py-2 text-xs font-medium text-white hover:bg-violet-600 disabled:opacity-50"
          :disabled="saving"
          @click="saveConfig"
        >
          {{ t('modal.save') }}
        </button>
      </div>
    </template>
  </div>
</template>
