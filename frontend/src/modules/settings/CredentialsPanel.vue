<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCredentialsStore } from '../../stores/credentials'
import { useToast } from '../../composables/useToast'

const { t } = useI18n()
const store = useCredentialsStore()
const toast = useToast()

const showForm = ref(false)
const editingId = ref<number | null>(null)
const deleteId = ref<number | null>(null)
const verifying = ref<number | null>(null)

const form = ref({
  label: '',
  wallet_address: '',
  agent_private_key: '',
  network: 'testnet',
})

onMounted(() => store.fetchAll())

function resetForm() {
  form.value = { label: '', wallet_address: '', agent_private_key: '', network: 'testnet' }
  editingId.value = null
  showForm.value = false
}

function startCreate() {
  resetForm()
  showForm.value = true
}

function startEdit(id: number) {
  const c = store.credentials.find((x) => x.id === id)
  if (!c) return
  editingId.value = id
  form.value = {
    label: c.label,
    wallet_address: c.wallet_address,
    agent_private_key: '',
    network: c.network,
  }
  showForm.value = true
}

async function submit() {
  try {
    if (editingId.value) {
      const patch: Record<string, string> = {
        label: form.value.label,
        wallet_address: form.value.wallet_address,
        network: form.value.network,
      }
      if (form.value.agent_private_key) {
        patch.agent_private_key = form.value.agent_private_key
      }
      await store.update(editingId.value, patch)
      toast.show(t('credentials.updated'), 'success')
    } else {
      await store.create(form.value)
      toast.show(t('credentials.created'), 'success')
    }
    resetForm()
  } catch {
    toast.show(t('credentials.failed'), 'error')
  }
}

async function verify(id: number) {
  verifying.value = id
  try {
    const result = await store.verify(id)
    if (result.ok) toast.show(t('credentials.verified'), 'success')
    else toast.show(result.detail || t('credentials.verifyFailed'), 'error')
  } finally {
    verifying.value = null
  }
}

async function confirmDelete() {
  if (!deleteId.value) return
  await store.remove(deleteId.value)
  toast.show(t('credentials.deleted'), 'success')
  deleteId.value = null
}

function formatTime(iso: string | null) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function shortAddr(addr: string) {
  if (addr.length <= 12) return addr
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`
}
</script>

<template>
  <section class="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-sm font-semibold text-zinc-300">{{ t('credentials.title') }}</h2>
      <button
        type="button"
        class="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs text-white hover:bg-emerald-600"
        @click="startCreate"
      >
        {{ t('credentials.add') }}
      </button>
    </div>

    <div v-if="!store.credentials.length && !showForm" class="text-sm text-zinc-600 py-4">
      {{ t('credentials.empty') }}
    </div>

    <div v-else class="space-y-3 mb-6">
      <div
        v-for="c in store.credentials"
        :key="c.id"
        class="flex items-center justify-between rounded-lg border border-zinc-800 px-4 py-3"
      >
        <div>
          <div class="text-sm text-zinc-200 font-medium">{{ c.label }}</div>
          <div class="text-xs text-zinc-500 mt-0.5 font-mono">
            {{ shortAddr(c.wallet_address) }} · {{ c.network }} ·
            <span :class="c.is_active ? 'text-emerald-400' : 'text-zinc-600'">
              {{ c.is_active ? t('credentials.active') : t('credentials.inactive') }}
            </span>
          </div>
          <div class="text-[10px] text-zinc-600 mt-0.5">{{ formatTime(c.last_verified_at) }}</div>
        </div>
        <div class="flex gap-2 text-xs">
          <button
            type="button"
            class="text-zinc-400 hover:text-zinc-200"
            :disabled="verifying === c.id"
            @click="verify(c.id)"
          >
            {{ t('credentials.verify') }}
          </button>
          <button type="button" class="text-zinc-400 hover:text-zinc-200" @click="startEdit(c.id)">
            {{ t('credentials.edit') }}
          </button>
          <button type="button" class="text-red-400 hover:text-red-300" @click="deleteId = c.id">
            {{ t('credentials.delete') }}
          </button>
        </div>
      </div>
    </div>

    <form v-if="showForm" class="space-y-3 border-t border-zinc-800 pt-4" @submit.prevent="submit">
      <h3 class="text-xs text-zinc-500 uppercase">
        {{ editingId ? t('credentials.edit') : t('credentials.add') }}
      </h3>
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
      <select
        v-model="form.network"
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
      >
        <option value="testnet">Testnet</option>
        <option value="mainnet">Mainnet</option>
      </select>
      <input
        v-model="form.agent_private_key"
        type="password"
        :placeholder="t('credentials.agentKey')"
        :required="!editingId"
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono"
      />
      <p v-if="editingId" class="text-xs text-zinc-600">{{ t('credentials.secretsOptional') }}</p>
      <div class="flex gap-2">
        <button type="button" class="px-4 py-2 text-sm text-zinc-400" @click="resetForm">
          {{ t('health.cancel') }}
        </button>
        <button type="submit" class="px-4 py-2 text-sm bg-emerald-700 text-white rounded-lg">
          {{ t('credentials.save') }}
        </button>
      </div>
    </form>

    <div v-if="deleteId" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div class="w-full max-w-sm rounded-xl border border-zinc-700 bg-zinc-900 p-6">
        <p class="text-zinc-200 mb-4">{{ t('credentials.deleteConfirm') }}</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="px-4 py-2 text-sm text-zinc-400" @click="deleteId = null">
            {{ t('health.cancel') }}
          </button>
          <button type="button" class="px-4 py-2 text-sm bg-red-600 text-white rounded-lg" @click="confirmDelete">
            {{ t('credentials.delete') }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
