<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useProStore } from '../stores/pro'
import { useStrategyStore } from '../stores/strategy'
import JournalEditor from '../modules/pro/JournalEditor.vue'

const { t } = useI18n()
const router = useRouter()
const pro = useProStore()
const strategies = useStrategyStore()
const showEditor = ref(false)

onMounted(async () => {
  await Promise.all([pro.fetchJournal(), strategies.fetchAll()])
})

function strategyName(id: number | null) {
  if (!id) return '—'
  return strategies.strategies.find((s) => s.id === id)?.name ?? `#${id}`
}
</script>

<template>
  <div class="p-4 space-y-4 max-w-3xl">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-zinc-100">{{ t('journal.title') }}</h1>
      <button
        type="button"
        class="rounded-lg bg-violet-700 px-3 py-1.5 text-xs text-white hover:bg-violet-600"
        @click="showEditor = !showEditor"
      >
        {{ t('journal.new') }}
      </button>
    </div>
    <JournalEditor v-if="showEditor" @saved="showEditor = false" />
    <div v-if="!pro.journal.length" class="text-sm text-zinc-500">{{ t('journal.empty') }}</div>
    <div v-else class="space-y-2">
      <article
        v-for="e in pro.journal"
        :key="e.id"
        class="rounded-xl border border-zinc-800 p-4 hover:border-zinc-700 cursor-pointer"
        @click="e.strategy_id && router.push({ name: 'strategy-detail', params: { id: e.strategy_id } })"
      >
        <h3 class="text-sm font-medium text-zinc-200">{{ e.title }}</h3>
        <p class="text-xs text-zinc-500 mt-1">{{ strategyName(e.strategy_id) }} · {{ new Date(e.created_at).toLocaleString() }}</p>
        <p class="text-sm text-zinc-400 mt-2 whitespace-pre-wrap">{{ e.body }}</p>
      </article>
    </div>
  </div>
</template>
