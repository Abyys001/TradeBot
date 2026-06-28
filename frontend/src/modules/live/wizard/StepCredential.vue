<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCredentialsStore } from '../../../stores/credentials'
import { useToast } from '../../../composables/useToast'

const props = defineProps<{ credentialId: number | null }>()
const emit = defineEmits<{ 'update:credentialId': [id: number | null] }>()

const { t } = useI18n()
const store = useCredentialsStore()
const toast = useToast()

const showForm = ref(false)
const busy = ref(false)
const form = ref({ label: '', wallet_address: '', agent_private_key: '', network: 'testnet' })

const selected = computed(() => store.credentials.find((c) => c.id === props.credentialId) ?? null)

onMounted(async () => {
  await store.fetchAll()
  if (!props.credentialId && store.credentials.length) {
    const active = store.credentials.find((c) => c.is_active) ?? store.credentials[0]
    emit('update:credentialId', active.id)
  }
  if (!store.credentials.length) showForm.value = true
})

function pick(id: number) {
  emit('update:credentialId', id)
}

async function saveConnect() {
  busy.value = true
  try {
    const created = await store.create(form.value)
    emit('update:credentialId', created.id)
    const res = await store.verify(created.id)
    if (res.ok) toast.show(t('credentials.verified'), 'success')
    else toast.show(res.detail || t('credentials.verifyFailed'), 'error')
    showForm.value = false
    form.value = { label: '', wallet_address: '', agent_private_key: '', network: 'testnet' }
  } catch {
    toast.show(t('credentials.failed'), 'error')
  } finally {
    busy.value = false
  }
}

async function reverify(id: number) {
  busy.value = true
  try {
    const res = await store.verify(id)
    if (res.ok) toast.show(t('credentials.verified'), 'success')
    else toast.show(res.detail || t('credentials.verifyFailed'), 'error')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <h3 class="text-sm font-semibold text-zinc-200">{{ t('live.cred.title') }}</h3>
      <p class="mt-1 text-xs text-zinc-500">{{ t('live.cred.securityNote') }}</p>
    </div>

    <!-- existing credentials -->
    <div v-if="store.credentials.length" class="space-y-2">
      <label class="text-xs text-zinc-500">{{ t('live.cred.selectExisting') }}</label>
      <div
        v-for="c in store.credentials"
        :key="c.id"
        class="flex items-center justify-between rounded-lg border px-4 py-3 cursor-pointer transition-colors"
        :class="c.id === credentialId ? 'border-violet-600 bg-violet-950/20' : 'border-zinc-800 hover:border-zinc-700'"
        @click="pick(c.id)"
      >
        <div>
          <div class="text-sm text-zinc-200 font-medium">{{ c.label }}</div>
          <div class="mt-0.5 font-mono text-xs text-zinc-500">{{ c.wallet_address.slice(0, 6) }}…{{ c.wallet_address.slice(-4) }} · {{ c.network }}</div>
        </div>
        <div class="flex items-center gap-2">
          <span
            class="rounded px-2 py-0.5 text-[10px] font-medium"
            :class="c.is_active ? 'bg-emerald-900/50 text-emerald-400' : 'bg-zinc-800 text-zinc-500'"
          >
            {{ c.is_active ? t('live.cred.connected', { network: c.network }) : t('live.cred.notConnected') }}
          </span>
          <button
            type="button"
            class="text-[11px] text-zinc-400 hover:text-zinc-200"
            :disabled="busy"
            @click.stop="reverify(c.id)"
          >
            {{ t('credentials.verify') }}
          </button>
        </div>
      </div>
    </div>

    <button
      v-if="!showForm"
      type="button"
      class="text-xs text-violet-400 hover:underline"
      @click="showForm = true"
    >
      + {{ t('live.cred.addNew') }}
    </button>

    <!-- new credential form -->
    <form v-if="showForm" class="space-y-3 rounded-lg border border-zinc-800 p-4" @submit.prevent="saveConnect">
      <input
        v-model="form.label"
        :placeholder="t('credentials.label')"
        required
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
      />
      <input
        v-model="form.wallet_address"
        :placeholder="t('credentials.walletAddress')"
        required
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono"
      />
      <select v-model="form.network" class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm">
        <option value="testnet">Testnet</option>
        <option value="mainnet">Mainnet</option>
      </select>
      <input
        v-model="form.agent_private_key"
        type="password"
        :placeholder="t('credentials.agentKey')"
        required
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono"
      />
      <div class="flex justify-end gap-2">
        <button
          v-if="store.credentials.length"
          type="button"
          class="px-4 py-2 text-sm text-zinc-400"
          @click="showForm = false"
        >
          {{ t('health.cancel') }}
        </button>
        <button
          type="submit"
          class="rounded-lg bg-emerald-700 px-4 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
          :disabled="busy"
        >
          {{ busy ? t('live.cred.verifying') : t('live.cred.saveConnect') }}
        </button>
      </div>
    </form>

    <div
      v-if="selected"
      class="flex items-center gap-2 rounded-lg px-3 py-2 text-xs"
      :class="selected.is_active ? 'bg-emerald-950/30 text-emerald-400' : 'bg-amber-950/30 text-amber-400'"
    >
      <span class="h-2 w-2 rounded-full" :class="selected.is_active ? 'bg-emerald-500' : 'bg-amber-500'" />
      {{ selected.is_active ? t('live.cred.connected', { network: selected.network }) : t('live.cred.notConnected') }}
    </div>
  </div>
</template>
