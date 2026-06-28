<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useOrdersStore } from '../stores/orders'
import { useStrategyStore } from '../stores/strategy'

const { t } = useI18n()
const router = useRouter()
const orders = useOrdersStore()
const strategies = useStrategyStore()

const filterStrategy = ref<number | ''>('')

onMounted(async () => {
  await Promise.all([orders.fetchOrders(), strategies.fetchAll()])
})

const filtered = computed(() => {
  if (!filterStrategy.value) return orders.orders
  return orders.orders.filter((o) => o.strategy === filterStrategy.value)
})

function strategyName(id: number) {
  return strategies.strategies.find((s) => s.id === id)?.name ?? `#${id}`
}

function goStrategy(id: number) {
  router.push({ name: 'strategy-detail', params: { id } })
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
</script>

<template>
  <div class="p-3 space-y-4 max-w-5xl sm:p-4">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-zinc-100">{{ t('orders.title') }}</h1>
      <button
        type="button"
        class="text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 rounded px-2 py-1"
        @click="orders.fetchOrders(filterStrategy || undefined)"
      >
        {{ t('positions.refresh') }}
      </button>
    </div>
    <label class="text-xs text-zinc-500 flex items-center gap-2">
      {{ t('orders.filterStrategy') }}
      <select
        v-model="filterStrategy"
        class="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
        @change="orders.fetchOrders(filterStrategy || undefined)"
      >
        <option value="">{{ t('terminal.all') }}</option>
        <option v-for="s in strategies.strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
    </label>
    <div v-if="orders.loading" class="text-sm text-zinc-500">{{ t('overview.loading') }}</div>
    <div v-else-if="!filtered.length" class="text-sm text-zinc-500">{{ t('orders.empty') }}</div>
    <div v-else class="rounded-xl border border-zinc-800 overflow-hidden">
      <div class="overflow-x-auto"><table class="w-full text-sm">
        <thead class="text-xs text-zinc-500 uppercase bg-zinc-900/50">
          <tr>
            <th class="px-3 py-2 text-start">{{ t('strategies.name') }}</th>
            <th class="px-3 py-2 text-start">{{ t('data.coin') }}</th>
            <th class="px-3 py-2 text-start">{{ t('orders.side') }}</th>
            <th class="px-3 py-2 text-start">{{ t('orders.status') }}</th>
            <th class="px-3 py-2 text-end">{{ t('positions.size') }}</th>
            <th class="px-3 py-2 text-end">{{ t('orders.time') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="o in filtered"
            :key="o.id"
            class="border-t border-zinc-800/50 hover:bg-zinc-900/40 cursor-pointer"
            @click="goStrategy(o.strategy)"
          >
            <td class="px-3 py-2 text-zinc-300">{{ strategyName(o.strategy) }}</td>
            <td class="px-3 py-2 text-zinc-500">{{ o.symbol }}</td>
            <td class="px-3 py-2 text-zinc-400">{{ o.side }}</td>
            <td class="px-3 py-2 text-zinc-400">{{ o.status }}</td>
            <td class="px-3 py-2 text-end text-zinc-400">{{ o.size }}</td>
            <td class="px-3 py-2 text-end text-zinc-500 text-xs">{{ formatTime(o.created_at) }}</td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </div>
</template>
