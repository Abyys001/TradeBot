<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, fetchCsrf } from '../../api/client'
import type { SignumConfig } from '../../api/client'
import { useToast } from '../../composables/useToast'

const { t } = useI18n()
const toast = useToast()

const loading = ref(true)
const saving = ref(false)
const form = ref({
  enabled: false,
  order_size_default: '80%',
  use_settings_bot_id: true,
  bot_id: '',
  webhook_url: '',
})
const hasBotId = ref(false)
const hasWebhookUrl = ref(false)

onMounted(async () => {
  await fetchCsrf()
  await load()
})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get<SignumConfig>('/signum/')
    form.value = {
      enabled: data.enabled ?? false,
      order_size_default: data.order_size_default ?? '80%',
      use_settings_bot_id: data.use_settings_bot_id ?? true,
      bot_id: '',
      webhook_url: '',
    }
    hasBotId.value = !!data.has_bot_id
    hasWebhookUrl.value = !!data.has_webhook_url
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      enabled: form.value.enabled,
      order_size_default: form.value.order_size_default,
      use_settings_bot_id: form.value.use_settings_bot_id,
    }
    if (form.value.bot_id) payload.bot_id = form.value.bot_id
    if (form.value.webhook_url) payload.webhook_url = form.value.webhook_url
    const { data } = await api.post<SignumConfig>('/signum/', payload)
    hasBotId.value = !!data.has_bot_id
    hasWebhookUrl.value = !!data.has_webhook_url
    form.value.bot_id = ''
    form.value.webhook_url = ''
    toast.show(t('signum.saved'), 'success')
  } catch {
    toast.show(t('signum.saveFailed'), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-4">
    <h2 class="text-sm font-medium text-zinc-200">{{ t('signum.title') }}</h2>
    <p class="text-xs text-zinc-500">{{ t('signum.subtitle') }}</p>

    <div v-if="loading" class="text-sm text-zinc-500">…</div>

    <template v-else>
      <label class="flex items-center gap-2 text-sm text-zinc-300">
        <input v-model="form.enabled" type="checkbox" class="rounded border-zinc-600" />
        {{ t('signum.enabled') }}
      </label>

      <label class="flex items-center gap-2 text-sm text-zinc-300">
        <input v-model="form.use_settings_bot_id" type="checkbox" class="rounded border-zinc-600" />
        {{ t('signum.useSettingsBotId') }}
      </label>

      <label class="block text-xs text-zinc-500">
        {{ t('signum.orderSize') }}
        <input
          v-model="form.order_size_default"
          type="text"
          class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
        />
      </label>

      <label class="block text-xs text-zinc-500">
        {{ t('signum.botId') }}
        <span v-if="hasBotId" class="text-emerald-400 ms-1">({{ t('signum.configured') }})</span>
        <input
          v-model="form.bot_id"
          type="password"
          autocomplete="off"
          :placeholder="t('signum.secretsOptional')"
          class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
        />
      </label>

      <label class="block text-xs text-zinc-500">
        {{ t('signum.webhookUrl') }}
        <span v-if="hasWebhookUrl" class="text-emerald-400 ms-1">({{ t('signum.configured') }})</span>
        <input
          v-model="form.webhook_url"
          type="password"
          autocomplete="off"
          :placeholder="t('signum.secretsOptional')"
          class="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200"
        />
      </label>

      <button
        type="button"
        class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50"
        :disabled="saving"
        @click="save"
      >
        {{ t('signum.save') }}
      </button>
    </template>
  </section>
</template>
