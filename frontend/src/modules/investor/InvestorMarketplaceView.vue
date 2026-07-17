<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchCsrf, type MasterStrategy } from '../../api/client'
import { useCopytradingStore } from '../../stores/copytrading'
import { useCredentialsStore } from '../../stores/credentials'
import { useToast } from '../../composables/useToast'

const store = useCopytradingStore()
const creds = useCredentialsStore()
const toast = useToast()
const loading = ref(true)

const subForm = ref({
  master: null as MasterStrategy | null,
  credential: null as number | null,
  sizing_mode: 'risk_pct' as 'risk_pct' | 'fixed_notional',
  risk_pct: '1.0',
  fixed_notional: '100',
  leverage: 1,
})

onMounted(async () => {
  await fetchCsrf()
  try {
    await Promise.all([store.fetchMarketplace(), store.fetchSubscriptions(), creds.fetchAll()])
  } finally {
    loading.value = false
  }
})

function isSubscribed(id: number) {
  return store.subscriptions.some((s) => s.master_strategy === id)
}

function openSubscribe(m: MasterStrategy) {
  subForm.value.master = m
  subForm.value.credential = creds.credentials[0]?.id ?? null
}

async function confirmSubscribe() {
  const f = subForm.value
  if (!f.master || !f.credential) return
  try {
    await store.subscribe({
      master_strategy: f.master.id,
      credential: f.credential,
      sizing_mode: f.sizing_mode,
      risk_pct: f.risk_pct,
      fixed_notional: f.fixed_notional,
      leverage: f.leverage,
    })
    toast.show('Subscribed', 'success')
    subForm.value.master = null
  } catch {
    toast.show('Failed to subscribe', 'error')
  }
}

async function unsubscribe(masterId: number) {
  const sub = store.subscriptions.find((s) => s.master_strategy === masterId)
  if (sub) {
    await store.unsubscribe(sub.id)
    toast.show('Unsubscribed', 'success')
  }
}

const inputCls = 'mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200'
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-6">
    <h1 class="text-lg font-semibold text-zinc-200">Strategy Marketplace</h1>
    <div v-if="loading" class="text-sm text-zinc-500">Loading…</div>

    <template v-else>
      <p v-if="!creds.credentials.length" class="rounded-lg border border-amber-900 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
        Add an exchange credential in API Setup before subscribing.
      </p>

      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div v-for="m in store.masters" :key="m.id" class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-medium text-zinc-200">{{ m.name }}</h3>
            <span class="text-xs text-zinc-500">{{ m.symbol }}</span>
          </div>
          <p class="text-xs text-zinc-500">{{ m.market_type }} · {{ m.timeframe }}</p>
          <button
            v-if="!isSubscribed(m.id)"
            type="button"
            class="w-full rounded-lg bg-violet-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-600 disabled:opacity-50"
            :disabled="!creds.credentials.length"
            @click="openSubscribe(m)"
          >Subscribe</button>
          <button
            v-else
            type="button"
            class="w-full rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
            @click="unsubscribe(m.id)"
          >Unsubscribe</button>
        </div>
        <p v-if="!store.masters.length" class="text-sm text-zinc-500">No published strategies yet.</p>
      </div>
    </template>

    <!-- Subscribe modal -->
    <div v-if="subForm.master" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" @click.self="subForm.master = null">
      <div class="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-4">
        <h2 class="text-sm font-semibold text-zinc-200">Subscribe to {{ subForm.master.name }}</h2>
        <label class="block text-xs text-zinc-500">
          Credential
          <select v-model="subForm.credential" :class="inputCls">
            <option v-for="c in creds.credentials" :key="c.id" :value="c.id">{{ c.label }} ({{ c.exchange }})</option>
          </select>
        </label>
        <label class="block text-xs text-zinc-500">
          Sizing
          <select v-model="subForm.sizing_mode" :class="inputCls">
            <option value="risk_pct">Percent of balance</option>
            <option value="fixed_notional">Fixed notional</option>
          </select>
        </label>
        <label v-if="subForm.sizing_mode === 'risk_pct'" class="block text-xs text-zinc-500">
          Risk % per trade
          <input v-model="subForm.risk_pct" type="number" step="0.1" :class="inputCls" />
        </label>
        <label v-else class="block text-xs text-zinc-500">
          Notional per trade
          <input v-model="subForm.fixed_notional" type="number" step="1" :class="inputCls" />
        </label>
        <label class="block text-xs text-zinc-500">
          Leverage
          <input v-model.number="subForm.leverage" type="number" min="1" :class="inputCls" />
        </label>
        <div class="flex justify-end gap-2">
          <button type="button" class="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800" @click="subForm.master = null">Cancel</button>
          <button type="button" class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600" @click="confirmSubscribe">Confirm</button>
        </div>
      </div>
    </div>
  </div>
</template>
