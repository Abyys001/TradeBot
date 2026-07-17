<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, fetchCsrf, type TelegramConfig } from '../../api/client'
import { useToast } from '../../composables/useToast'

const toast = useToast()
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const hasToken = ref(false)
const form = ref({ enabled: false, chat_id: '', bot_token: '', events: [] as string[] })

const eventOptions = [
  { id: 'trade', label: 'Trade signals' },
  { id: 'fill', label: 'Order fills' },
  { id: 'error', label: 'Errors' },
]

onMounted(async () => {
  await fetchCsrf()
  await load()
})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get<TelegramConfig>('/telegram/')
    form.value = {
      enabled: data.enabled ?? false,
      chat_id: data.chat_id ?? '',
      bot_token: '',
      events: data.events ?? [],
    }
    hasToken.value = !!data.has_bot_token
  } finally {
    loading.value = false
  }
}

function toggleEvent(id: string) {
  const i = form.value.events.indexOf(id)
  if (i >= 0) form.value.events.splice(i, 1)
  else form.value.events.push(id)
}

async function save() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      enabled: form.value.enabled,
      chat_id: form.value.chat_id,
      events: form.value.events,
    }
    if (form.value.bot_token) payload.bot_token = form.value.bot_token
    const { data } = await api.post<TelegramConfig>('/telegram/', payload)
    hasToken.value = !!data.has_bot_token
    form.value.bot_token = ''
    toast.show('Telegram settings saved', 'success')
  } catch {
    toast.show('Failed to save', 'error')
  } finally {
    saving.value = false
  }
}

async function sendTest() {
  testing.value = true
  try {
    const { data } = await api.post<{ ok: boolean; reason?: string; error?: string }>('/telegram/test/', {})
    toast.show(data.ok ? 'Test message sent' : data.reason || data.error || 'Test failed', data.ok ? 'success' : 'error')
  } catch {
    toast.show('Test failed', 'error')
  } finally {
    testing.value = false
  }
}

const inputCls = 'mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200'
</script>

<template>
  <section class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-4">
    <h2 class="text-sm font-medium text-zinc-200">Telegram notifications</h2>
    <p class="text-xs text-zinc-500">Send trade, fill and error alerts to a Telegram chat via your bot.</p>

    <div v-if="loading" class="text-sm text-zinc-500">…</div>
    <template v-else>
      <label class="flex items-center gap-2 text-sm text-zinc-300">
        <input v-model="form.enabled" type="checkbox" class="rounded border-zinc-600" />
        Enabled
      </label>

      <label class="block text-xs text-zinc-500">
        Bot token
        <span v-if="hasToken" class="text-emerald-400 ms-1">(configured)</span>
        <input v-model="form.bot_token" type="password" autocomplete="off" placeholder="Leave blank to keep current" :class="inputCls" />
      </label>

      <label class="block text-xs text-zinc-500">
        Chat ID
        <input v-model="form.chat_id" type="text" :class="inputCls" />
      </label>

      <div class="text-xs text-zinc-500">
        Events
        <div class="mt-1 flex flex-wrap gap-3">
          <label v-for="e in eventOptions" :key="e.id" class="flex items-center gap-1.5 text-zinc-300">
            <input type="checkbox" :checked="form.events.includes(e.id)" class="rounded border-zinc-600" @change="toggleEvent(e.id)" />
            {{ e.label }}
          </label>
        </div>
        <p class="mt-1 text-zinc-600">No events selected = all events.</p>
      </div>

      <div class="flex gap-2">
        <button type="button" class="rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-600 disabled:opacity-50" :disabled="saving" @click="save">Save</button>
        <button type="button" class="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-800 disabled:opacity-50" :disabled="testing" @click="sendTest">Send test message</button>
      </div>
    </template>
  </section>
</template>
