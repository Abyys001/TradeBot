<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProStore } from '../../stores/pro'
import { useStrategyStore } from '../../stores/strategy'

const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const pro = useProStore()
const strategies = useStrategyStore()

const title = ref('')
const body = ref('')
const strategyId = ref<number | ''>('')
const saving = ref(false)

async function submit() {
  saving.value = true
  try {
    await pro.createJournalEntry({
      title: title.value || t('journal.untitled'),
      body: body.value,
      strategy_id: strategyId.value ? Number(strategyId.value) : undefined,
    })
    title.value = ''
    body.value = ''
    emit('saved')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="rounded-xl border border-zinc-800 p-4 space-y-2" @submit.prevent="submit">
    <input v-model="title" :placeholder="t('journal.entryTitle')" class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm" />
    <select v-model="strategyId" class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs">
      <option value="">{{ t('journal.noStrategy') }}</option>
      <option v-for="s in strategies.strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
    </select>
    <textarea v-model="body" rows="4" class="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm" />
    <button type="submit" class="rounded-lg bg-zinc-700 px-3 py-1.5 text-xs" :disabled="saving">{{ t('journal.save') }}</button>
  </form>
</template>
