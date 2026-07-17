<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, fetchCsrf } from '../../api/client'
import type { TelegramConfig, AlertWhitelistEntry } from '../../api/client'
import { useToast } from '../../composables/useToast'

const { t } = useI18n()
const toast = useToast()

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const config = ref<TelegramConfig>({ bot_token: '', enabled: false, created_at: '', updated_at: '' })
const whitelist = ref<AlertWhitelistEntry[]>([])
const newChatId = ref('')
const newLabel = ref('')

onMounted(async () => {
  await fetchCsrf()
  await Promise.all([loadConfig(), loadWhitelist()])
})

async function loadConfig() {
  try {
    const { data } = await api.get<TelegramConfig>('/telegram/config/')
    config.value = { ...config.value, ...data, bot_token: data.bot_token || '' }
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

async function saveConfig() {
  saving.value = true
  try {
    await api.post('/telegram/config/', {
      bot_token: config.value.bot_token || '',
      enabled: config.value.enabled,
    })
    toast.show(t('telegram.saved'), 'success')
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
    const { data } = await api.post<{ sent: number; total: number }>('/telegram/config/test/')
    toast.show(`${t('telegram.testSent')} (${data.sent}/${data.total})`, 'success')
  } catch {
    toast.show(t('telegram.testFailed'), 'error')
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <section class="rounded-lg border border-border bg-surface-muted/40 p-4 space-y-4">
    <h2 class="text-sm font-medium text-fg">{{ t('telegram.title') }}</h2>
    <p class="text-xs text-fg-muted">{{ t('telegram.subtitle') }}</p>

    <div v-if="loading" class="text-sm text-fg-muted">…</div>

    <template v-else>
      <label class="flex items-center gap-2 text-sm text-fg">
        <input v-model="config.enabled" type="checkbox" class="rounded border-border" />
        {{ t('telegram.enabled') }}
      </label>

      <label class="block text-xs text-fg-muted">
        {{ t('telegram.botToken') }}
        <input
          v-model="config.bot_token"
          type="password"
          autocomplete="off"
          :placeholder="t('telegram.botTokenHint')"
          class="mt-1 w-full rounded border border-border bg-surface-muted px-2 py-1.5 text-sm text-fg"
        />
      </label>

      <button
        type="button"
        class="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="saving"
        @click="saveConfig"
      >
        {{ t('modal.save') }}
      </button>

      <button
        type="button"
        class="rounded-lg border border-border px-4 py-2 text-sm text-fg hover:bg-surface-raised disabled:opacity-50 ms-2"
        :disabled="testing || !config.enabled"
        @click="test"
      >
        {{ t('telegram.test') }}
      </button>

      <div class="border-t border-border pt-4">
        <h3 class="text-xs font-medium text-fg-muted mb-2">{{ t('telegram.whitelistTitle') }}</h3>

        <div v-if="!whitelist.length" class="text-xs text-fg-muted mb-3">
          {{ t('telegram.whitelistEmpty') }}
        </div>

        <div v-for="entry in whitelist" :key="entry.id" class="flex items-center gap-2 mb-2">
          <span class="text-xs text-fg flex-1">
            <template v-if="entry.label">{{ entry.label }} — </template>
            <code class="text-fg-muted">{{ entry.chat_id }}</code>
          </span>
          <button
            type="button"
            class="text-xs text-negative hover:text-negative"
            @click="removeChat(entry.id)"
          >
            {{ t('telegram.removeChat') }}
          </button>
        </div>

        <div class="flex flex-wrap items-end gap-2 mt-3">
          <label class="block text-xs text-fg-muted flex-1 min-w-[120px]">
            Chat ID
            <input
              v-model="newChatId"
              type="text"
              :placeholder="t('telegram.chatIdHint')"
              class="mt-0.5 w-full rounded border border-border bg-surface-muted px-2 py-1 text-sm text-fg"
            />
          </label>
          <label class="block text-xs text-fg-muted flex-1 min-w-[100px]">
            {{ t('telegram.chatIdLabel') }}
            <input
              v-model="newLabel"
              type="text"
              class="mt-0.5 w-full rounded border border-border bg-surface-muted px-2 py-1 text-sm text-fg"
            />
          </label>
          <button
            type="button"
            class="rounded bg-border px-3 py-1.5 text-xs text-fg hover:opacity-80"
            :disabled="!newChatId"
            @click="addChat"
          >
            {{ t('telegram.addChat') }}
          </button>
        </div>
      </div>
    </template>
  </section>
</template>
