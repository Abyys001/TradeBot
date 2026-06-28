<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePaperStore } from '../../stores/paper'

const props = defineProps<{ strategyId: number }>()
const { t } = useI18n()
const paper = usePaperStore()
const loading = ref(false)

const balance = computed(() => paper.balance)
const equity = computed(() => paper.equity)
const active = computed(() => paper.active)
const trades = computed(() => paper.trades)

async function refresh() {
  await Promise.all([paper.fetchAccount(props.strategyId), paper.fetchTrades(props.strategyId)])
}

async function start() {
  loading.value = true
  try {
    await paper.start(props.strategyId)
    await refresh()
  } finally {
    loading.value = false
  }
}

async function stop() {
  loading.value = true
  try {
    await paper.stop(props.strategyId)
    await refresh()
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 space-y-3">
    <div class="text-xs font-medium text-zinc-400">{{ t('paper.title') }}</div>
    <div class="grid grid-cols-2 gap-2 text-sm">
      <div>
        <div class="text-zinc-500 text-xs">{{ t('paper.balance') }}</div>
        <div class="text-zinc-200">{{ balance }}</div>
      </div>
      <div>
        <div class="text-zinc-500 text-xs">{{ t('paper.equity') }}</div>
        <div class="text-zinc-200">{{ equity }}</div>
      </div>
    </div>
    <div class="flex gap-2">
      <button
        v-if="!active"
        type="button"
        class="flex-1 rounded-lg bg-violet-700 hover:bg-violet-600 text-xs py-1.5 disabled:opacity-50"
        :disabled="loading"
        @click="start"
      >
        {{ t('paper.start') }}
      </button>
      <button
        v-else
        type="button"
        class="flex-1 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-xs py-1.5 disabled:opacity-50"
        :disabled="loading"
        @click="stop"
      >
        {{ t('paper.stop') }}
      </button>
      <button
        type="button"
        class="rounded-lg border border-zinc-700 px-2 text-xs text-zinc-400 hover:text-zinc-200"
        :disabled="loading"
        @click="refresh"
      >
        ↻
      </button>
    </div>
    <div v-if="trades.length" class="border-t border-zinc-800 pt-2">
      <div class="text-xs text-zinc-500 mb-1">{{ t('paper.trades') }}</div>
      <div class="overflow-x-auto"><table class="w-full text-[10px]">
        <thead class="text-zinc-600">
          <tr>
            <th class="text-start py-0.5">{{ t('paper.side') }}</th>
            <th class="text-end py-0.5">PnL</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tr in trades.slice(0, 10)" :key="tr.id" class="border-t border-zinc-800/50">
            <td class="py-0.5 text-zinc-400">{{ tr.side }}</td>
            <td class="py-0.5 text-end" :class="Number(tr.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ tr.pnl }}
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>
