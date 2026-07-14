<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAdminStore } from '../../stores/admin'
import type { Investor } from '../../api/client'

const { t } = useI18n()
const admin = useAdminStore()

const form = reactive({ username: '', password: '', email: '', is_trading_enabled: false })
const creating = ref(false)
const error = ref('')
const notice = ref('')

function genPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%'
  let out = ''
  const arr = new Uint32Array(16)
  crypto.getRandomValues(arr)
  for (const n of arr) out += chars[n % chars.length]
  form.password = out
}

async function submit() {
  error.value = ''
  notice.value = ''
  if (!form.username || !form.password) {
    error.value = t('investors.errRequired')
    return
  }
  creating.value = true
  try {
    await admin.create({ ...form })
    notice.value = t('investors.created', { u: form.username })
    form.username = ''
    form.password = ''
    form.email = ''
    form.is_trading_enabled = false
  } catch (e: any) {
    const d = e?.response?.data
    error.value = typeof d === 'object' ? JSON.stringify(d) : String(d ?? e)
  } finally {
    creating.value = false
  }
}

async function toggleTrading(inv: Investor) {
  await admin.setTrading(inv.id, !inv.is_trading_enabled)
}
async function toggleActive(inv: Investor) {
  await admin.setActive(inv.id, !inv.is_active)
}
async function resetPassword(inv: Investor) {
  const pw = window.prompt(t('investors.resetPrompt', { u: inv.username }))
  if (!pw) return
  try {
    await admin.resetPassword(inv.id, pw)
    notice.value = t('investors.resetDone', { u: inv.username })
  } catch (e: any) {
    error.value = JSON.stringify(e?.response?.data ?? e)
  }
}

onMounted(() => admin.fetchAll())
</script>

<template>
  <div class="mx-auto max-w-5xl p-6">
    <h1 class="mb-1 text-xl font-semibold text-zinc-100">{{ t('investors.title') }}</h1>
    <p class="mb-6 text-sm text-zinc-500">{{ t('investors.subtitle') }}</p>

    <!-- Create form -->
    <div class="mb-8 rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
      <h2 class="mb-4 text-sm font-medium text-zinc-300">{{ t('investors.createTitle') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500">{{ t('investors.username') }}</span>
          <input v-model="form.username" type="text" autocomplete="off"
            class="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-violet-500" />
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500">{{ t('investors.email') }}</span>
          <input v-model="form.email" type="email" autocomplete="off"
            class="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-violet-500" />
        </label>
        <label class="flex flex-col gap-1 sm:col-span-2">
          <span class="text-xs text-zinc-500">{{ t('investors.tempPassword') }}</span>
          <div class="flex gap-2">
            <input v-model="form.password" type="text" autocomplete="off"
              class="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-violet-500" />
            <button type="button" @click="genPassword"
              class="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800">
              {{ t('investors.generate') }}
            </button>
          </div>
          <span class="text-xs text-zinc-600">{{ t('investors.mustChangeHint') }}</span>
        </label>
        <label class="flex items-center gap-2 sm:col-span-2">
          <input v-model="form.is_trading_enabled" type="checkbox" class="accent-violet-500" />
          <span class="text-sm text-zinc-400">{{ t('investors.enableTrading') }}</span>
        </label>
      </div>
      <div class="mt-4 flex items-center gap-3">
        <button type="button" :disabled="creating" @click="submit"
          class="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">
          {{ creating ? t('investors.creating') : t('investors.createBtn') }}
        </button>
        <span v-if="error" class="text-sm text-red-400">{{ error }}</span>
        <span v-else-if="notice" class="text-sm text-emerald-400">{{ notice }}</span>
      </div>
    </div>

    <!-- Investor list -->
    <div class="overflow-x-auto rounded-xl border border-zinc-800">
      <table class="w-full text-left text-sm">
        <thead class="bg-zinc-900/70 text-xs uppercase text-zinc-500">
          <tr>
            <th class="px-4 py-3">{{ t('investors.username') }}</th>
            <th class="px-4 py-3">{{ t('investors.email') }}</th>
            <th class="px-4 py-3">{{ t('investors.status') }}</th>
            <th class="px-4 py-3">{{ t('investors.trading') }}</th>
            <th class="px-4 py-3">{{ t('investors.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          <tr v-for="inv in admin.investors" :key="inv.id" class="text-zinc-300">
            <td class="px-4 py-3">
              <span class="font-medium text-zinc-100">{{ inv.username }}</span>
              <span v-if="inv.must_change_password"
                class="ms-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">
                {{ t('investors.pendingChange') }}
              </span>
            </td>
            <td class="px-4 py-3 text-zinc-500">{{ inv.email || '—' }}</td>
            <td class="px-4 py-3">
              <span :class="inv.is_active ? 'text-emerald-400' : 'text-zinc-500'">
                {{ inv.is_active ? t('investors.active') : t('investors.disabled') }}
              </span>
            </td>
            <td class="px-4 py-3">
              <button type="button" @click="toggleTrading(inv)"
                :class="inv.is_trading_enabled
                  ? 'bg-emerald-500/15 text-emerald-400'
                  : 'bg-zinc-800 text-zinc-500'"
                class="rounded-full px-2.5 py-1 text-xs">
                {{ inv.is_trading_enabled ? t('investors.on') : t('investors.off') }}
              </button>
            </td>
            <td class="px-4 py-3">
              <div class="flex gap-2">
                <button type="button" @click="resetPassword(inv)"
                  class="rounded-md border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800">
                  {{ t('investors.resetPassword') }}
                </button>
                <button type="button" @click="toggleActive(inv)"
                  class="rounded-md border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-800"
                  :class="inv.is_active ? 'text-red-400' : 'text-emerald-400'">
                  {{ inv.is_active ? t('investors.disable') : t('investors.enable') }}
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!admin.loading && admin.investors.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-zinc-600">{{ t('investors.empty') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
