<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import { useCredentialsStore } from '../stores/credentials'
import { useToast } from '../composables/useToast'
import CreateStrategyModal from '../modules/strategy/CreateStrategyModal.vue'
import type { Strategy } from '../api/client'

const { t } = useI18n()
const router = useRouter()
const store = useStrategyStore()
const credentials = useCredentialsStore()
const toast = useToast()

const showCreate = ref(false)
const deleteTarget = ref<Strategy | null>(null)
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadSource = ref('')

onMounted(async () => {
  await Promise.all([store.fetchAll(), credentials.fetchAll()])
})

const list = computed(() => store.strategies)

function statusClass(status: string) {
  if (status === 'active') return 'bg-emerald-900/50 text-emerald-400'
  if (status === 'paused') return 'bg-amber-900/50 text-amber-400'
  if (status === 'stopped') return 'bg-red-900/50 text-red-400'
  return 'bg-zinc-800 text-zinc-400'
}

function validationClass(v: string) {
  if (v === 'ok') return 'text-emerald-400'
  if (v === 'error') return 'text-red-400'
  return 'text-zinc-500'
}

function openDetail(id: number) {
  store.select(id)
  router.push({ name: 'strategy-detail', params: { id } })
}

async function onValidate(s: Strategy) {
  const result = await store.validate(s.id)
  if (result.ok) toast.show(t('strategy.validatedOk'), 'success')
  else toast.show(result.error || t('strategy.validatedFail'), 'error')
}

async function onStart(s: Strategy) {
  await store.start(s.id)
  toast.show(t('strategy.starting'), 'info')
}

async function onStop(s: Strategy) {
  await store.stop(s.id)
  toast.show(t('strategy.stopping'), 'info')
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  await store.deleteStrategy(deleteTarget.value.id)
  toast.show(t('strategy.deleted'), 'success')
  deleteTarget.value = null
}

function onUploadClick() {
  uploadInput.value?.click()
}

function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    uploadSource.value = String(reader.result || '')
    showCreate.value = true
  }
  reader.readAsText(file)
  ;(e.target as HTMLInputElement).value = ''
}

function onCreated(id: number) {
  showCreate.value = false
  uploadSource.value = ''
  toast.show(t('strategy.created'), 'success')
  openDetail(id)
}
</script>

<template>
  <div class="flex-1 overflow-y-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-lg font-semibold text-zinc-200">{{ t('strategies.title') }}</h1>
      <div class="flex gap-2">
        <input ref="uploadInput" type="file" accept=".pine,.txt,.pinescript" class="hidden" @change="onFileSelected" />
        <button
          type="button"
          class="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          @click="onUploadClick"
        >
          {{ t('strategies.uploadPine') }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs text-white hover:bg-emerald-600"
          @click="showCreate = true"
        >
          {{ t('strategies.new') }}
        </button>
      </div>
    </div>

    <div v-if="!list.length" class="rounded-xl border border-dashed border-zinc-700 p-12 text-center">
      <p class="text-zinc-500 mb-4">{{ t('strategies.empty') }}</p>
      <button
        type="button"
        class="rounded-lg bg-emerald-700 px-4 py-2 text-sm text-white hover:bg-emerald-600"
        @click="showCreate = true"
      >
        {{ t('strategies.new') }}
      </button>
    </div>

    <div v-else class="rounded-xl border border-zinc-800 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-zinc-900/80 text-xs text-zinc-500 uppercase">
          <tr>
            <th class="text-start px-4 py-3">{{ t('strategy.name') }}</th>
            <th class="text-start px-4 py-3">{{ t('strategy.symbols') }}</th>
            <th class="text-start px-4 py-3">Status</th>
            <th class="text-start px-4 py-3">Pine</th>
            <th class="text-end px-4 py-3">{{ t('strategies.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in list"
            :key="s.id"
            class="border-t border-zinc-800/50 hover:bg-zinc-900/40"
          >
            <td class="px-4 py-3">
              <button type="button" class="text-zinc-200 hover:text-emerald-400 font-medium" @click="openDetail(s.id)">
                {{ s.name }}
              </button>
            </td>
            <td class="px-4 py-3 text-zinc-400">{{ s.symbol }}</td>
            <td class="px-4 py-3">
              <span class="rounded px-2 py-0.5 text-xs" :class="statusClass(s.status)">{{ s.status }}</span>
            </td>
            <td class="px-4 py-3 text-xs" :class="validationClass(s.validation_status)">
              {{ s.validation_status || '—' }}
            </td>
            <td class="px-4 py-3 text-end space-x-1">
              <button type="button" class="text-xs text-zinc-400 hover:text-zinc-200" @click="openDetail(s.id)">
                {{ t('strategies.edit') }}
              </button>
              <button type="button" class="text-xs text-zinc-400 hover:text-zinc-200" @click="onValidate(s)">
                {{ t('strategy.validate') }}
              </button>
              <button
                v-if="s.status === 'active'"
                type="button"
                class="text-xs text-amber-400 hover:text-amber-300"
                @click="onStop(s)"
              >
                {{ t('strategy.stop') }}
              </button>
              <button
                v-else
                type="button"
                class="text-xs text-emerald-400 hover:text-emerald-300"
                @click="onStart(s)"
              >
                {{ t('strategy.start') }}
              </button>
              <button type="button" class="text-xs text-red-400 hover:text-red-300" @click="deleteTarget = s">
                {{ t('strategies.delete') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <CreateStrategyModal
      v-if="showCreate"
      :initial-source="uploadSource"
      @close="showCreate = false; uploadSource = ''"
      @created="onCreated"
    />

    <div v-if="deleteTarget" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div class="w-full max-w-sm rounded-xl border border-zinc-700 bg-zinc-900 p-6">
        <h3 class="text-zinc-200 font-medium mb-2">{{ t('strategies.deleteConfirm') }}</h3>
        <p class="text-sm text-zinc-500 mb-4">{{ deleteTarget.name }}</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="px-4 py-2 text-sm text-zinc-400" @click="deleteTarget = null">
            {{ t('health.cancel') }}
          </button>
          <button type="button" class="px-4 py-2 text-sm bg-red-600 text-white rounded-lg" @click="confirmDelete">
            {{ t('strategies.delete') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
