<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, fetchCsrf } from '../api/client'
import type { TelegramConfig, AlertWhitelistEntry } from '../api/client'
import { useToast } from '../composables/useToast'

const { t } = useI18n()
const toast = useToast()

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const checking = ref(false)
const hasToken = ref(false)
const botStatus = ref<{
  valid: boolean
  configured: boolean
  username?: string
  first_name?: string
  error?: string
} | null>(null)

const config = ref<TelegramConfig>({
  bot_token: '',
  enabled: false,
  created_at: '',
  updated_at: '',
})
const whitelist = ref<AlertWhitelistEntry[]>([])
const newChatId = ref('')
const newLabel = ref('')

const statusClass = computed(() => {
  if (!botStatus.value) return 'text-zinc-600'
  if (!botStatus.value.valid) return 'text-red-400'
  if (!botStatus.value.configured) return 'text-amber-400'
  return 'text-green-400'
})

const statusText = computed(() => {
  if (!botStatus.value) return t('telegram.statusChecking')
  if (!botStatus.value.valid) return t('telegram.statusInvalid')
  if (!botStatus.value.configured) return t('telegram.statusDisabled')
  return t('telegram.statusOk')
})

onMounted(async () => {
  await fetchCsrf()
  await Promise.all([loadConfig(), loadWhitelist()])
  await checkStatus()
})

async function loadConfig() {
  try {
    const { data } = await api.get<TelegramConfig & { has_bot_token?: boolean }>(
      '/telegram/config/',
    )
    hasToken.value = data.has_bot_token ?? false
    config.value = {
      bot_token: '',
      enabled: data.enabled,
      created_at: data.created_at,
      updated_at: data.updated_at,
    }
  } finally {
    loading.value = false
  }
}

async function loadWhitelist() {
  try {
    const { data } = await api.get<AlertWhitelistEntry[]>('/telegram/whitelist/')
    whitelist.value = data
  } catch {
    // ignore
  }
}

async function checkStatus() {
  checking.value = true
  try {
    const { data } = await api.get('/telegram/config/status/')
    botStatus.value = data as typeof botStatus.value
  } catch {
    botStatus.value = { valid: false, configured: false, error: 'Request failed' }
  } finally {
    checking.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const { data } = await api.post('/telegram/config/', {
      bot_token: config.value.bot_token || '',
      enabled: config.value.enabled,
    })
    hasToken.value = (data as any).has_bot_token ?? !!config.value.bot_token
    toast.show(t('telegram.saved'), 'success')
    await checkStatus()
  } catch {
    toast.show(t('telegram.saveFailed'), 'error')
  } finally {
    saving.value = false
  }
}

async function addChat() {
  const chatId = Number(newChatId.value)
  if (!chatId) return
  try {
    const { data } = await api.post<AlertWhitelistEntry>('/telegram/whitelist/', {
      chat_id: chatId,
      label: newLabel.value || '',
    })
    whitelist.value.push(data)
    newChatId.value = ''
    newLabel.value = ''
  } catch {
    toast.show(t('telegram.saveFailed'), 'error')
  }
}

async function removeChat(id: number) {
  try {
    await api.delete(`/telegram/whitelist/${id}/`)
    whitelist.value = whitelist.value.filter((e) => e.id !== id)
  } catch {
    toast.show(t('telegram.saveFailed'), 'error')
  }
}

async function test() {
  testing.value = true
  try {
    const { data } = await api.post<{ sent: number; total: number }>(
      '/telegram/config/test/',
    )
    toast.show(`${t('telegram.testSent')} (${data.sent}/${data.total})`, 'success')
  } catch {
    toast.show(t('telegram.testFailed'), 'error')
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-6 space-y-6 max-w-2xl">
    <h1 class="text-lg font-semibold text-zinc-200">{{ t('telegram.title') }}</h1>

    <section class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-4">
      <p class="text-xs text-zinc-500">{{ t('telegram.subtitle') }}</p>

      <div v-if="loading" class="text-sm text-zinc-500">…</div>

      <template v-else>
        <!-- Status Badge -->
        <div class="flex items-center gap-2 text-sm" :class="statusClass">
          <span
            class="inline-block h-2 w-2 rounded-full"
            :class="{
              'bg-green-400': botStatus?.valid && botStatus?.configured,
              'bg-amber-400': botStatus?.valid && !botStatus?.configured,
              'bg-red-400': botStatus && !botStatus?.valid,
              'bg-zinc-600': !botStatus,
            }"
          />
          <span class="font-medium">{{ statusText }}</span>
          <span v-if="botStatus?.username" class="text-zinc-500">@{{ botStatus.username }}</span>
          <span v-if="botStatus?.error" class="text-xs text-zinc-500">— {{ botStatus.error }}</span>
        </div>

        <!-- Enabled Toggle -->
        <label class="flex items-center gap-2 text-sm text-zinc-300">
          <input v-model="config.enabled" type="checkbox" class="rounded border-zinc-600" />
          {{ t('telegram.enabled') }}
        </label>

        <!-- Bot Token -->
        <label class="block text-xs text-zinc-500">
          {{ t('telegram.botToken') }}
          <span v-if="hasToken" class="text-emerald-400 ms-1">✓ {{ t('telegram.configured') }}</span>
          <input
            v-model="config.bot_token"
            type="password"
            autocomplete="off"
            :placeholder="t('telegram.botTokenHint')"
            class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 font-mono"
          />
        </label>

        <!-- Actions -->
        <div class="flex gap-2">
          <button
            type="button"
            class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
            :disabled="saving"
            @click="saveConfig"
          >
            {{ t('modal.save') }}
          </button>

          <button
            type="button"
            class="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            :disabled="testing || !config.enabled"
            @click="test"
          >
            {{ t('telegram.test') }}
          </button>

          <button
            type="button"
            class="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            :disabled="checking"
            @click="checkStatus"
          >
            {{ t('telegram.refreshStatus') }}
          </button>
        </div>

        <!-- Whitelist -->
        <div class="border-t border-zinc-800 pt-4">
          <h3 class="text-xs font-medium text-zinc-400 mb-2">{{ t('telegram.whitelistTitle') }}</h3>

          <div v-if="!whitelist.length" class="text-xs text-zinc-600 mb-3">
            {{ t('telegram.whitelistEmpty') }}
          </div>

          <div v-for="entry in whitelist" :key="entry.id" class="flex items-center gap-2 mb-2">
            <span class="text-xs text-zinc-300 flex-1">
              <template v-if="entry.label">{{ entry.label }} — </template>
              <code class="text-zinc-500">{{ entry.chat_id }}</code>
            </span>
            <button
              type="button"
              class="text-xs text-red-400 hover:text-red-300"
              @click="removeChat(entry.id)"
            >
              {{ t('telegram.removeChat') }}
            </button>
          </div>

          <div class="flex flex-wrap items-end gap-2 mt-3">
            <label class="block text-xs text-zinc-500 flex-1 min-w-[120px]">
              Chat ID
              <input
                v-model="newChatId"
                type="text"
                :placeholder="t('telegram.chatIdHint')"
                class="mt-0.5 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-200"
              />
            </label>
            <label class="block text-xs text-zinc-500 flex-1 min-w-[100px]">
              {{ t('telegram.chatIdLabel') }}
              <input
                v-model="newLabel"
                type="text"
                class="mt-0.5 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-200"
              />
            </label>
            <button
              type="button"
              class="rounded bg-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-600"
              :disabled="!newChatId"
              @click="addChat"
            >
              {{ t('telegram.addChat') }}
            </button>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>
