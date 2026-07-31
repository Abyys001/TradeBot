<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStrategyStore } from '../../stores/strategy'
import { useCopytradingStore } from '../../stores/copytrading'
import { useCredentialsStore } from '../../stores/credentials'
import { useToast } from '../../composables/useToast'
import CreateStrategyModal from '../../modules/strategy/CreateStrategyModal.vue'
import BotScriptCard from '../../modules/strategy/BotScriptCard.vue'

const { t } = useI18n()
const store = useStrategyStore()
const copyStore = useCopytradingStore()
const credentials = useCredentialsStore()
const toast = useToast()

const showCreate = ref(false)
const togglingId = ref<number | null>(null)

const botScripts = computed(() =>
  store.strategies.filter((s) => s.live_config?.copy_trading),
)

const hasTabdealCredential = computed(() =>
  credentials.credentials.some((c) => c.exchange === 'tabdeal'),
)

onMounted(async () => {
  await Promise.all([
    store.fetchAll(),
    credentials.credentials.length ? Promise.resolve() : credentials.fetchAll(),
    copyStore.fetchStrategyPnl(),
  ])
})

async function onCreated(id: number) {
  showCreate.value = false
  const result = await store.validate(id)
  if (result.ok) toast.show(t('strategy.validatedOk'), 'success')
  else toast.show(result.error || t('bots.validationFailed'), 'error')
  await store.fetchAll()
}

async function onToggle(id: number, isActive: boolean) {
  togglingId.value = id
  try {
    if (isActive) {
      await store.stop(id)
      toast.show(t('bots.stopping'), 'info')
    } else {
      await store.start(id)
      toast.show(t('bots.starting'), 'info')
    }
    await copyStore.fetchStrategyPnl()
  } finally {
    togglingId.value = null
  }
}
</script>

<template>
  <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-3 sm:p-6">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
      <h1 class="text-lg font-semibold text-fg">{{ t('bots.title') }}</h1>
      <button
        type="button"
        class="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-500 disabled:opacity-40"
        :disabled="!hasTabdealCredential"
        :title="!hasTabdealCredential ? t('bots.needsTabdealCredential') : ''"
        @click="showCreate = true"
      >
        {{ t('bots.upload') }}
      </button>
    </div>
    <p class="text-xs text-fg-muted mb-6">{{ t('bots.onlyOneActiveHint') }}</p>

    <div v-if="!hasTabdealCredential" class="mb-6 rounded-lg border border-warning/30 bg-warning-bg px-3 py-2 text-sm text-warning">
      {{ t('bots.needsTabdealCredential') }}
    </div>

    <div v-if="!botScripts.length" class="flex min-h-[40vh] flex-col items-center justify-center text-sm text-fg-muted">
      {{ t('bots.empty') }}
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <BotScriptCard
        v-for="s in botScripts"
        :key="s.id"
        :strategy="s"
        :pnl="copyStore.strategyPnl[String(s.id)]"
        :toggling="togglingId === s.id"
        @toggle="onToggle(s.id, s.status === 'active')"
      />
    </div>

    <CreateStrategyModal
      v-if="showCreate"
      force-copy-trading
      @close="showCreate = false"
      @created="onCreated"
    />
  </div>
</template>
