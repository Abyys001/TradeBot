<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { fetchCsrf, type CredentialCreatePayload } from '../api/client'
import { useCredentialsStore } from '../stores/credentials'
import { useToast } from '../composables/useToast'

const store = useCredentialsStore()
const toast = useToast()

type Tab = 'add' | 'test' | 'manage' | 'docs'
const tab = ref<Tab>('add')
const tabs: { id: Tab; label: string }[] = [
  { id: 'add', label: 'Add credentials' },
  { id: 'test', label: 'Test connection' },
  { id: 'manage', label: 'Manage keys' },
  { id: 'docs', label: 'API docs' },
]

const form = ref({
  exchange: 'tabdeal',
  label: '',
  network: 'testnet',
  // Hyperliquid
  wallet_address: '',
  agent_private_key: '',
  // Tabdeal
  api_key: '',
  api_secret: '',
})
const saving = ref(false)
const isTabdeal = computed(() => form.value.exchange === 'tabdeal')

onMounted(async () => {
  await fetchCsrf()
  await store.fetchAll()
})

async function submit() {
  saving.value = true
  try {
    const payload: CredentialCreatePayload = {
      label: form.value.label,
      exchange: form.value.exchange,
      network: form.value.network,
    }
    if (isTabdeal.value) {
      payload.api_key = form.value.api_key
      payload.api_secret = form.value.api_secret
    } else {
      payload.wallet_address = form.value.wallet_address
      payload.agent_private_key = form.value.agent_private_key
    }
    await store.create(payload)
    toast.show('Credential saved', 'success')
    form.value.api_key = ''
    form.value.api_secret = ''
    form.value.agent_private_key = ''
    tab.value = 'test'
  } catch {
    toast.show('Failed to save credential', 'error')
  } finally {
    saving.value = false
  }
}

const verifying = ref<number | null>(null)
async function verify(id: number) {
  verifying.value = id
  try {
    const res = await store.verify(id)
    toast.show(res.ok ? 'Verified ✓' : res.detail || 'Verification failed', res.ok ? 'success' : 'error')
  } finally {
    verifying.value = null
  }
}

async function remove(id: number) {
  await store.remove(id)
  toast.show('Credential removed', 'success')
}

const inputCls =
  'mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200'
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6 space-y-6">
    <h1 class="text-lg font-semibold text-zinc-200">API Setup</h1>

    <div class="flex gap-1 border-b border-zinc-800">
      <button
        v-for="tItem in tabs"
        :key="tItem.id"
        type="button"
        class="px-4 py-2 text-sm -mb-px border-b-2 transition-colors"
        :class="tab === tItem.id
          ? 'border-violet-500 text-zinc-100'
          : 'border-transparent text-zinc-500 hover:text-zinc-300'"
        @click="tab = tItem.id"
      >
        {{ tItem.label }}
      </button>
    </div>

    <!-- Add -->
    <section v-if="tab === 'add'" class="max-w-lg space-y-4 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
      <label class="block text-xs text-zinc-500">
        Exchange
        <select v-model="form.exchange" :class="inputCls">
          <option value="tabdeal">Tabdeal (futures)</option>
          <option value="hyperliquid">Hyperliquid</option>
        </select>
      </label>
      <label class="block text-xs text-zinc-500">
        Label
        <input v-model="form.label" type="text" :class="inputCls" placeholder="e.g. Main account" />
      </label>
      <label class="block text-xs text-zinc-500">
        Network
        <select v-model="form.network" :class="inputCls">
          <option value="testnet">Testnet</option>
          <option value="mainnet">Mainnet</option>
        </select>
      </label>

      <template v-if="isTabdeal">
        <label class="block text-xs text-zinc-500">
          API key
          <input v-model="form.api_key" type="text" autocomplete="off" :class="inputCls" />
        </label>
        <label class="block text-xs text-zinc-500">
          API secret
          <input v-model="form.api_secret" type="password" autocomplete="off" :class="inputCls" />
        </label>
      </template>
      <template v-else>
        <label class="block text-xs text-zinc-500">
          Master wallet address
          <input v-model="form.wallet_address" type="text" autocomplete="off" :class="inputCls" />
        </label>
        <label class="block text-xs text-zinc-500">
          Agent private key
          <input v-model="form.agent_private_key" type="password" autocomplete="off" :class="inputCls" />
        </label>
      </template>

      <button
        type="button"
        class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
        :disabled="saving || !form.label"
        @click="submit"
      >
        Save credential
      </button>
    </section>

    <!-- Test -->
    <section v-else-if="tab === 'test'" class="space-y-3">
      <p class="text-sm text-zinc-500">Verify each credential connects and can trade.</p>
      <div
        v-for="c in store.credentials"
        :key="c.id"
        class="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-3"
      >
        <div>
          <p class="text-sm text-zinc-200">{{ c.label }} <span class="text-zinc-500">· {{ c.exchange }} · {{ c.network }}</span></p>
          <p class="text-xs" :class="c.is_active ? 'text-emerald-400' : 'text-zinc-500'">
            {{ c.is_active ? 'Active' : 'Not verified' }}
          </p>
        </div>
        <button
          type="button"
          class="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
          :disabled="verifying === c.id"
          @click="verify(c.id)"
        >
          {{ verifying === c.id ? 'Testing…' : 'Test connection' }}
        </button>
      </div>
    </section>

    <!-- Manage -->
    <section v-else-if="tab === 'manage'" class="space-y-3">
      <div
        v-for="c in store.credentials"
        :key="c.id"
        class="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-3"
      >
        <div>
          <p class="text-sm text-zinc-200">{{ c.label }}</p>
          <p class="text-xs text-zinc-500">{{ c.exchange }} · {{ c.network }} · added {{ c.created_at?.slice(0, 10) }}</p>
        </div>
        <button
          type="button"
          class="rounded-lg border border-red-900 px-3 py-1.5 text-xs text-red-400 hover:bg-red-950"
          @click="remove(c.id)"
        >
          Remove
        </button>
      </div>
      <p v-if="!store.credentials.length" class="text-sm text-zinc-500">No credentials yet.</p>
    </section>

    <!-- Docs -->
    <section v-else class="max-w-2xl space-y-5 text-sm text-zinc-400">
      <div>
        <h3 class="font-medium text-zinc-200">Tabdeal (futures)</h3>
        <ol class="mt-2 list-decimal space-y-1 ps-5">
          <li>Open Tabdeal → Account → API Management.</li>
          <li>Create a key with <b>Futures trading</b> permission enabled.</li>
          <li>Copy the API key and secret into the Add tab. The secret is encrypted at rest.</li>
        </ol>
      </div>
      <div>
        <h3 class="font-medium text-zinc-200">Hyperliquid</h3>
        <ol class="mt-2 list-decimal space-y-1 ps-5">
          <li>In the Hyperliquid app, approve an <b>API agent wallet</b>.</li>
          <li>Paste the agent private key and your master wallet address in the Add tab.</li>
          <li>We never store your master wallet key — only the agent key, encrypted.</li>
        </ol>
      </div>
    </section>
  </div>
</template>
