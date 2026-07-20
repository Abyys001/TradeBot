<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import { useI18n } from 'vue-i18n'
import { useCredentialsStore } from '../../../stores/credentials'
import { useAuthStore } from '../../../stores/auth'
import { useMarketDataStore } from '../../../stores/marketdata'
import { useToast } from '../../../composables/useToast'
import type { StrategyForm } from '../../../composables/useStrategyForm'

const props = defineProps<{ strategyForm: StrategyForm; credentialId: number | null }>()
const emit = defineEmits<{ deployed: [] }>()

const { t } = useI18n()
const creds = useCredentialsStore()
const auth = useAuthStore()
const md = useMarketDataStore()
const toast = useToast()

const sf = props.strategyForm
const deploying = ref(false)
const errors = ref<string[]>([])

const credential = computed(() => creds.credentials.find((c) => c.id === props.credentialId) ?? null)
const risk = computed(() => sf.form.live_config.risk ?? {})
const tradingEnabled = computed(() => !!auth.user?.is_trading_enabled)

// --- Market-data readiness gate (candle design §5) ---------------------------
const primarySymbol = computed(
  () => sf.form.live_config.symbols?.[0] ?? sf.selected.value?.symbol ?? '',
)
const primaryTf = computed(
  () => sf.form.live_config.timeframes?.[0] ?? sf.selected.value?.timeframe ?? '',
)
const readiness = computed(() => md.readiness)
const isReady = computed(() => readiness.value?.ready ?? false)

function fmtEta(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return h > 0 ? `~${h}h ${m}min` : `~${m}min`
}

const readinessLabel = computed(() => {
  const r = readiness.value
  if (!r) return ''
  if (r.error) return r.error
  const base = `${r.symbol} ${r.timeframe} — ${r.clean_bars}/${r.required_bars} bars`
  return r.ready ? `${base} · ready` : `${base} · live in ${fmtEta(r.eta_seconds)}`
})

let pollTimer: ReturnType<typeof setInterval> | null = null

async function refreshReadiness() {
  if (!primarySymbol.value || !primaryTf.value) return
  try {
    await md.fetchReadiness({
      symbol: primarySymbol.value,
      tf: primaryTf.value,
      strategyId: sf.selected.value?.id,
      requiredBars: sf.selected.value?.warmup_bars,
    })
  } catch {
    /* readiness is a soft gate; ignore transient errors */
  }
}

onMounted(() => {
  refreshReadiness()
  pollTimer = setInterval(refreshReadiness, 15000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

async function deploy() {
  const s = sf.selected.value
  if (!s) return
  errors.value = []
  deploying.value = true
  try {
    await sf.save()
    await sf.store.start(s.id)
    toast.show(t('live.deploy.deployed'), 'success')
    emit('deployed')
  } catch (err: unknown) {
    if (axios.isAxiosError(err) && err.response?.data?.errors) {
      errors.value = err.response.data.errors as string[]
    } else {
      errors.value = [t('strategy.saveFailed')]
    }
  } finally {
    deploying.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <h3 class="text-sm font-semibold text-zinc-200">{{ t('live.deploy.title') }}</h3>

    <dl class="divide-y divide-zinc-800 rounded-lg border border-zinc-800 text-sm">
      <div class="flex justify-between px-4 py-2.5">
        <dt class="text-zinc-500">{{ t('live.deploy.credential') }}</dt>
        <dd class="text-zinc-200">{{ credential?.label ?? '—' }} · {{ credential?.network ?? '' }}</dd>
      </div>
      <div class="flex justify-between px-4 py-2.5">
        <dt class="text-zinc-500">{{ t('live.deploy.strategy') }}</dt>
        <dd class="text-zinc-200">{{ sf.form.name }}</dd>
      </div>
      <div class="flex justify-between px-4 py-2.5">
        <dt class="text-zinc-500">{{ t('live.deploy.pairs') }}</dt>
        <dd class="text-zinc-200">{{ sf.form.live_config.symbols?.join(', ') }}</dd>
      </div>
      <div class="flex justify-between px-4 py-2.5">
        <dt class="text-zinc-500">{{ t('live.deploy.timeframe') }}</dt>
        <dd class="text-zinc-200">{{ sf.form.live_config.timeframes?.join(', ') }}</dd>
      </div>
      <div class="flex justify-between px-4 py-2.5">
        <dt class="text-zinc-500">{{ t('live.deploy.leverage') }}</dt>
        <dd class="text-zinc-200">{{ risk.leverage }}×</dd>
      </div>
      <div class="flex justify-between px-4 py-2.5">
        <dt class="text-zinc-500">{{ t('live.deploy.allocation') }}</dt>
        <dd class="text-zinc-200">{{ risk.position_size_pct }}%</dd>
      </div>
      <div class="flex justify-between px-4 py-2.5">
        <dt class="text-zinc-500">{{ t('live.deploy.stopLoss') }}</dt>
        <dd class="text-zinc-200">{{ risk.global_stop_loss_pct }}%</dd>
      </div>
    </dl>

    <div
      v-if="readinessLabel"
      class="rounded-lg px-3 py-2 text-xs"
      :class="isReady ? 'bg-emerald-950/30 text-emerald-400' : 'bg-sky-950/30 text-sky-300'"
    >
      <div class="flex items-center justify-between">
        <span>{{ isReady ? 'Data ready' : 'Recording history…' }}</span>
        <span class="tabular-nums">{{ readinessLabel }}</span>
      </div>
      <div v-if="!isReady && readiness" class="mt-1.5 h-1 overflow-hidden rounded bg-zinc-800">
        <div
          class="h-full bg-sky-500 transition-all"
          :style="{ width: Math.min(100, (readiness.clean_bars / Math.max(readiness.required_bars, 1)) * 100) + '%' }"
        />
      </div>
    </div>

    <p v-if="!tradingEnabled" class="rounded-lg bg-amber-950/30 px-3 py-2 text-xs text-amber-400">
      {{ t('live.deploy.tradingDisabled') }}
    </p>

    <ul v-if="errors.length" class="rounded-lg bg-red-950/30 px-3 py-2 text-xs text-red-400">
      <li v-for="(e, i) in errors" :key="i">• {{ e }}</li>
    </ul>

    <button
      type="button"
      class="w-full rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 px-4 py-3 text-sm font-bold text-white shadow-lg shadow-violet-900/40 transition-all hover:from-violet-500 hover:to-fuchsia-500 disabled:opacity-50"
      :disabled="deploying || !isReady"
      :title="!isReady ? 'Waiting for enough clean recorded bars to warm up' : ''"
      @click="deploy"
    >
      {{ deploying ? t('live.deploy.deploying') : !isReady ? 'Waiting for data…' : t('live.deploy.initialize') }}
    </button>
  </div>
</template>
