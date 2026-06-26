<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../stores/strategy'
import { useToast } from '../composables/useToast'
import CreateStrategyModal from '../modules/strategy/CreateStrategyModal.vue'
import ResearchGuide from '../modules/strategy/ResearchGuide.vue'
import StrategiesEmptyState from '../components/StrategiesEmptyState.vue'
import type { Strategy } from '../api/client'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useStrategyStore()
const toast = useToast()

const showCreate = ref(false)
const deleteTarget = ref<Strategy | null>(null)
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadSource = ref('')

const badgeBase = 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium'
const iconBtnBase = 'rounded-md p-1.5 text-zinc-600 transition-colors hover:bg-zinc-800'

onMounted(() => {
  void store.fetchAll()
})

const list = computed(() => store.strategies)

const dataPrefill = computed(() => {
  const coin = route.query.dataCoin as string | undefined
  const interval = route.query.dataInterval as string | undefined
  const network = (route.query.dataNetwork as string | undefined) || 'mainnet'
  if (!coin || !interval) return null
  return { coin, interval, network }
})

function strategyQuery(): Record<string, string> {
  const query: Record<string, string> = {}
  if (route.query.dataCoin) query.dataCoin = String(route.query.dataCoin)
  if (route.query.dataInterval) query.dataInterval = String(route.query.dataInterval)
  if (route.query.dataNetwork) query.dataNetwork = String(route.query.dataNetwork)
  return query
}

function statusClass(status: string) {
  if (status === 'active') return 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40'
  if (status === 'paused') return 'bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30'
  if (status === 'stopped') return 'bg-red-500/15 text-red-300 ring-1 ring-red-500/30'
  return 'bg-zinc-700/50 text-zinc-400 ring-1 ring-zinc-600/40'
}

function statusLabel(status: string) {
  if (status === 'active') return t('strategies.statusActive')
  if (status === 'paused') return t('strategies.statusPaused')
  if (status === 'stopped') return t('strategies.statusStopped')
  return t('strategies.statusDraft')
}

function pineClass(v: string) {
  if (v === 'ok') return 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40'
  if (v === 'error') return 'bg-red-500/15 text-red-300 ring-1 ring-red-500/30'
  return 'bg-zinc-700/50 text-zinc-400 ring-1 ring-zinc-600/40'
}

function pineLabel(v: string) {
  if (v === 'ok') return t('strategies.pineOk')
  if (v === 'error') return t('strategies.pineError')
  return t('strategies.pineDraft')
}

function openDetail(id: number) {
  store.select(id)
  router.push({
    name: 'strategy-detail',
    params: { id },
    query: strategyQuery(),
  })
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
      v-if="dataPrefill"
      class="mb-4 rounded-lg border border-violet-900/50 bg-violet-950/30 px-3 py-2 text-sm text-violet-300"
    >
      {{ t('data.prefillHint', dataPrefill) }}
    </div>

    <div v-if="!list.length" class="flex min-h-[50vh] flex-col items-center justify-center">
      <StrategiesEmptyState @create="showCreate = true" @upload="onUploadClick" />
    </div>

    <ResearchGuide
      v-if="!list.length"
      class="mb-6"
      @upload="onUploadClick"
      @create="showCreate = true"
    />

    <div v-else class="rounded-xl border border-zinc-800 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-zinc-900/80 text-xs text-zinc-500 uppercase">
          <tr>
            <th class="text-start px-4 py-3">{{ t('strategy.name') }}</th>
            <th class="text-start px-4 py-3">{{ t('strategy.symbols') }}</th>
            <th class="text-start px-4 py-3">{{ t('strategies.statusColumn') }}</th>
            <th class="text-start px-4 py-3">{{ t('strategies.pineColumn') }}</th>
            <th class="text-end px-4 py-3">{{ t('strategies.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in list"
            :key="s.id"
            class="cursor-default border-t border-zinc-800/50 transition-colors duration-150 hover:bg-zinc-800/40"
          >
            <td class="px-4 py-3">
              <button type="button" class="text-zinc-200 hover:text-emerald-400 font-medium" @click="openDetail(s.id)">
                {{ s.name }}
              </button>
            </td>
            <td class="px-4 py-3 text-zinc-400">{{ s.symbol }}</td>
            <td class="px-4 py-3">
              <span :class="[badgeBase, statusClass(s.status)]">{{ statusLabel(s.status) }}</span>
            </td>
            <td class="px-4 py-3">
              <span :class="[badgeBase, pineClass(s.validation_status)]">{{ pineLabel(s.validation_status) }}</span>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center justify-end gap-0.5">
                <button
                  type="button"
                  :class="[iconBtnBase, 'hover:text-zinc-200']"
                  :title="t('strategies.edit')"
                  @click="openDetail(s.id)"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
                  </svg>
                </button>
                <button
                  type="button"
                  :class="[iconBtnBase, 'hover:text-violet-400']"
                  :title="t('strategy.validate')"
                  @click="onValidate(s)"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <path d="m9 11 3 3L22 4" />
                  </svg>
                </button>
                <button
                  v-if="s.status === 'active'"
                  type="button"
                  :class="[iconBtnBase, 'hover:text-amber-400']"
                  :title="t('strategy.stop')"
                  @click="onStop(s)"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="6" y="6" width="12" height="12" rx="1" />
                  </svg>
                </button>
                <button
                  v-else-if="s.credential"
                  type="button"
                  :class="[iconBtnBase, 'hover:text-emerald-400']"
                  :title="t('strategy.start')"
                  @click="onStart(s)"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="6 3 20 12 6 21 6 3" />
                  </svg>
                </button>
                <button
                  type="button"
                  :class="[iconBtnBase, 'hover:text-red-400']"
                  :title="t('strategies.delete')"
                  @click="deleteTarget = s"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
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
