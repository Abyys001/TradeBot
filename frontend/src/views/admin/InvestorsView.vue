<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAdminStore } from '../../stores/admin'
import ResponsiveTable from '../../components/ResponsiveTable.vue'
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

const isEmpty = computed(() => !admin.loading && admin.investors.length === 0)

onMounted(() => admin.fetchAll())
</script>

<template>
  <div class="mx-auto max-w-5xl p-3 sm:p-6">
    <h1 class="mb-1 text-xl font-semibold text-fg">{{ t('investors.title') }}</h1>
    <p class="mb-6 text-sm text-fg-muted">{{ t('investors.subtitle') }}</p>

    <!-- Create form -->
    <div class="mb-8 rounded-xl border border-border bg-surface-raised p-5">
      <h2 class="mb-4 text-sm font-medium text-fg">{{ t('investors.createTitle') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-fg-muted">{{ t('investors.username') }}</span>
          <input v-model="form.username" type="text" autocomplete="off"
            class="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent" />
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-fg-muted">{{ t('investors.email') }}</span>
          <input v-model="form.email" type="email" autocomplete="off"
            class="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent" />
        </label>
        <label class="flex flex-col gap-1 sm:col-span-2">
          <span class="text-xs text-fg-muted">{{ t('investors.tempPassword') }}</span>
          <div class="flex gap-2">
            <input v-model="form.password" type="text" autocomplete="off"
              class="flex-1 rounded-lg border border-border bg-surface px-3 py-2 font-mono text-sm text-fg outline-none focus:border-accent" />
            <button type="button" @click="genPassword"
              class="rounded-lg border border-border px-3 py-2 text-sm text-fg hover:bg-surface-raised">
              {{ t('investors.generate') }}
            </button>
          </div>
          <span class="text-xs text-fg-muted">{{ t('investors.mustChangeHint') }}</span>
        </label>
        <label class="flex items-center gap-2 sm:col-span-2">
          <input v-model="form.is_trading_enabled" type="checkbox" class="accent-[var(--tb-accent)]" />
          <span class="text-sm text-fg-muted">{{ t('investors.enableTrading') }}</span>
        </label>
      </div>
      <div class="mt-4 flex items-center gap-3">
        <button type="button" :disabled="creating" @click="submit"
          class="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg hover:opacity-90 disabled:opacity-50">
          {{ creating ? t('investors.creating') : t('investors.createBtn') }}
        </button>
        <span v-if="error" class="text-sm text-negative">{{ error }}</span>
        <span v-else-if="notice" class="text-sm text-positive">{{ notice }}</span>
      </div>
    </div>

    <!-- Investor list -->
    <div class="rounded-xl border border-border overflow-hidden">
      <ResponsiveTable :empty="isEmpty">
        <template #empty>
          <span class="block px-4 py-8 text-center">{{ t('investors.empty') }}</span>
        </template>
        <template #head>
          <th class="px-4 py-3 text-start">{{ t('investors.username') }}</th>
          <th class="px-4 py-3 text-start">{{ t('investors.email') }}</th>
          <th class="px-4 py-3 text-start">{{ t('investors.status') }}</th>
          <th class="px-4 py-3 text-start">{{ t('investors.trading') }}</th>
          <th class="px-4 py-3 text-start">{{ t('investors.actions') }}</th>
        </template>
        <template #row>
          <tr v-for="inv in admin.investors" :key="inv.id" class="text-fg divide-y divide-border border-t border-border">
            <td class="px-4 py-3">
              <span class="font-medium text-fg">{{ inv.username }}</span>
              <span v-if="inv.must_change_password"
                class="ms-2 rounded bg-warning-bg px-1.5 py-0.5 text-[10px] text-warning">
                {{ t('investors.pendingChange') }}
              </span>
            </td>
            <td class="px-4 py-3 text-fg-muted">{{ inv.email || '—' }}</td>
            <td class="px-4 py-3">
              <span :class="inv.is_active ? 'text-positive' : 'text-fg-muted'">
                {{ inv.is_active ? t('investors.active') : t('investors.disabled') }}
              </span>
            </td>
            <td class="px-4 py-3">
              <button type="button" @click="toggleTrading(inv)"
                :class="inv.is_trading_enabled
                  ? 'bg-success-bg text-positive'
                  : 'bg-surface-raised text-fg-muted'"
                class="rounded-full px-2.5 py-1 text-xs">
                {{ inv.is_trading_enabled ? t('investors.on') : t('investors.off') }}
              </button>
            </td>
            <td class="px-4 py-3">
              <div class="flex gap-2">
                <button type="button" @click="resetPassword(inv)"
                  class="rounded-md border border-border px-2 py-1 text-xs text-fg hover:bg-surface-raised">
                  {{ t('investors.resetPassword') }}
                </button>
                <button type="button" @click="toggleActive(inv)"
                  class="rounded-md border border-border px-2 py-1 text-xs hover:bg-surface-raised"
                  :class="inv.is_active ? 'text-negative' : 'text-positive'">
                  {{ inv.is_active ? t('investors.disable') : t('investors.enable') }}
                </button>
              </div>
            </td>
          </tr>
        </template>
        <template #card>
          <div v-for="inv in admin.investors" :key="inv.id" class="rounded-lg border border-border bg-surface-raised p-3">
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0">
                <span class="font-medium text-fg">{{ inv.username }}</span>
                <span v-if="inv.must_change_password"
                  class="ms-1 rounded bg-warning-bg px-1.5 py-0.5 text-[10px] text-warning">
                  {{ t('investors.pendingChange') }}
                </span>
                <div class="text-xs text-fg-muted">{{ inv.email || '—' }}</div>
              </div>
              <span class="shrink-0 text-xs" :class="inv.is_active ? 'text-positive' : 'text-fg-muted'">
                {{ inv.is_active ? t('investors.active') : t('investors.disabled') }}
              </span>
            </div>
            <div class="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-2">
              <button type="button" @click="toggleTrading(inv)"
                :class="inv.is_trading_enabled
                  ? 'bg-success-bg text-positive'
                  : 'bg-surface-raised text-fg-muted'"
                class="rounded-full px-2.5 py-1 text-xs">
                {{ inv.is_trading_enabled ? t('investors.on') : t('investors.off') }}
              </button>
              <div class="flex gap-2">
                <button type="button" @click="resetPassword(inv)"
                  class="rounded-md border border-border px-2 py-1 text-xs text-fg hover:bg-surface-raised">
                  {{ t('investors.resetPassword') }}
                </button>
                <button type="button" @click="toggleActive(inv)"
                  class="rounded-md border border-border px-2 py-1 text-xs hover:bg-surface-raised"
                  :class="inv.is_active ? 'text-negative' : 'text-positive'">
                  {{ inv.is_active ? t('investors.disable') : t('investors.enable') }}
                </button>
              </div>
            </div>
          </div>
        </template>
      </ResponsiveTable>
    </div>
  </div>
</template>
