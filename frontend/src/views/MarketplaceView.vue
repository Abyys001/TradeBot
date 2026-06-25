<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useProStore } from '../stores/pro'
import { useStrategyStore } from '../stores/strategy'
import MarketplaceCard from '../modules/pro/MarketplaceCard.vue'

const { t } = useI18n()
const router = useRouter()
const pro = useProStore()
const strategies = useStrategyStore()

const publishName = ref('')
const publishDesc = ref('')
const publishSource = ref('')
const publishing = ref(false)

onMounted(async () => {
  await Promise.all([pro.fetchMarketplace(), strategies.fetchAll()])
})

async function publish() {
  if (!publishSource.value.trim()) return
  publishing.value = true
  try {
    await pro.publishPackage({
      name: publishName.value || 'Strategy',
      description: publishDesc.value,
      source: publishSource.value,
      is_public: true,
    })
    publishName.value = ''
    publishDesc.value = ''
    publishSource.value = ''
  } finally {
    publishing.value = false
  }
}

async function onImport(id: number) {
  const strategyId = await pro.importPackage(id)
  router.push({ name: 'strategy-detail', params: { id: strategyId } })
}
</script>

<template>
  <div class="p-4 space-y-6 max-w-4xl">
    <h1 class="text-lg font-semibold text-zinc-100">{{ t('marketplace.title') }}</h1>
    <div class="rounded-xl border border-zinc-800 p-4 space-y-2">
      <h2 class="text-sm text-zinc-300">{{ t('marketplace.publish') }}</h2>
      <input v-model="publishName" :placeholder="t('strategies.name')" class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm" />
      <textarea v-model="publishDesc" rows="2" :placeholder="t('marketplace.description')" class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm" />
      <textarea v-model="publishSource" rows="4" :placeholder="t('strategy.source')" class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs font-mono" />
      <button
        type="button"
        class="rounded-lg bg-violet-700 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        :disabled="publishing"
        @click="publish"
      >
        {{ t('marketplace.publishBtn') }}
      </button>
    </div>
    <div v-if="!pro.packages.length" class="text-sm text-zinc-500">{{ t('marketplace.empty') }}</div>
    <div v-else class="grid gap-3 md:grid-cols-2">
      <MarketplaceCard
        v-for="pkg in pro.packages"
        :key="pkg.id"
        :pkg="pkg"
        @import="onImport(pkg.id)"
      />
    </div>
  </div>
</template>
