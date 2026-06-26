<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import { useCredentialsStore } from '../stores/credentials'
import { useToast } from '../composables/useToast'
import CreateStrategyModal from '../modules/strategy/CreateStrategyModal.vue'
import ActionIconButton from '../components/ActionIconButton.vue'
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

function validationBadgeClass(v: string) {
  if (v === 'ok') return 'bg-emerald-900/50 text-emerald-400'
  if (v === 'error') return 'bg-red-900/50 text-red-400'
  return 'bg-zinc-800 text-zinc-400'
}

function validationLabel(v: string) {
  if (v === 'ok') return t('status.ok')
  if (v === 'error') return t('status.error')
  return 'draft'
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

    <div
      v-if="!list.length"
      class="flex flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700 p-16 text-center"
    >
      <svg class="mb-4 h-16 w-16 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
      <p class="mb-2 text-zinc-400">{{ t('strategies.emptyTitle') }}</p>
      <p class="mb-6 max-w-sm text-sm text-zinc-600">{{ t('strategies.empty') }}</p>
      <button
        type="button"
        class="rounded-lg bg-emerald-700 px-6 py-2.5 text-sm font-medium text-white hover:bg-emerald-600"
        @click="showCreate = true"
      >
        {{ t('strategies.emptyCta') }}
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
            class="border-t border-zinc-800/50 transition-colors hover:bg-zinc-800/60"
          >
            <td class="px-4 py-3">
              <button type="button" class="text-zinc-200 hover:text-emerald-400 font-medium" @click="openDetail(s.id)">
                {{ s.name }}
              </button>
            </td>
            <td class="px-4 py-3 text-zinc-400">{{ s.symbol }}</td>
            <td class="px-4 py-3">
              <span class="rounded-full px-2.5 py-0.5 text-xs font-medium" :class="statusClass(s.status)">
                {{ s.status }}
              </span>
            </td>
            <td class="px-4 py-3">
              <span
                class="rounded-full px-2.5 py-0.5 text-xs font-medium"
                :class="validationBadgeClass(s.validation_status)"
              >
                {{ validationLabel(s.validation_status) }}
              </span>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center justify-end gap-0.5">
                <ActionIconButton :title="t('strategies.edit')" @click="openDetail(s.id)">
                  <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                  </svg>
                </ActionIconButton>
                <ActionIconButton :title="t('strategy.validate')" @click="onValidate(s)">
                  <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </ActionIconButton>
                <ActionIconButton
                  v-if="s.status === 'active'"
                  :title="t('strategy.stop')"
                  variant="warning"
                  @click="onStop(s)"
                >
                  <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z" />
                  </svg>
                </ActionIconButton>
                <ActionIconButton
                  v-else
                  :title="t('strategy.start')"
                  variant="success"
                  @click="onStart(s)"
                >
                  <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                  </svg>
                </ActionIconButton>
                <ActionIconButton :title="t('strategies.delete')" variant="danger" @click="deleteTarget = s">
                  <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                  </svg>
                </ActionIconButton>
              </div>
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
