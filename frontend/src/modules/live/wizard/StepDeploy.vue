<script setup lang="ts">
import { computed, ref } from 'vue'
import axios from 'axios'
import { useI18n } from 'vue-i18n'
import { useCredentialsStore } from '../../../stores/credentials'
import { useAuthStore } from '../../../stores/auth'
import { useToast } from '../../../composables/useToast'
import type { StrategyForm } from '../../../composables/useStrategyForm'

const props = defineProps<{ strategyForm: StrategyForm; credentialId: number | null }>()
const emit = defineEmits<{ deployed: [] }>()

const { t } = useI18n()
const creds = useCredentialsStore()
const auth = useAuthStore()
const toast = useToast()

const sf = props.strategyForm
const deploying = ref(false)
const errors = ref<string[]>([])

const credential = computed(() => creds.credentials.find((c) => c.id === props.credentialId) ?? null)
const risk = computed(() => sf.form.live_config.risk ?? {})
const tradingEnabled = computed(() => !!auth.user?.is_trading_enabled)

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

    <p v-if="!tradingEnabled" class="rounded-lg bg-amber-950/30 px-3 py-2 text-xs text-amber-400">
      {{ t('live.deploy.tradingDisabled') }}
    </p>

    <ul v-if="errors.length" class="rounded-lg bg-red-950/30 px-3 py-2 text-xs text-red-400">
      <li v-for="(e, i) in errors" :key="i">• {{ e }}</li>
    </ul>

    <button
      type="button"
      class="w-full rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 px-4 py-3 text-sm font-bold text-white shadow-lg shadow-violet-900/40 transition-all hover:from-violet-500 hover:to-fuchsia-500 disabled:opacity-50"
      :disabled="deploying"
      @click="deploy"
    >
      {{ deploying ? t('live.deploy.deploying') : t('live.deploy.initialize') }}
    </button>
  </div>
</template>
