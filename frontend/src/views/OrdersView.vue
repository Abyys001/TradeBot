<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useOrdersStore } from '../stores/orders'
import { useStrategyStore } from '../stores/strategy'
import ResponsiveTable from '../components/ResponsiveTable.vue'

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
  <div class="scrollbar-styled scrollbar-thin scrollbar-idle-fade flex-1 overflow-y-auto p-3 space-y-4 max-w-5xl sm:p-4">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-fg">{{ t('orders.title') }}</h1>
      <button
        type="button"
        class="text-xs text-fg-muted hover:text-fg border border-border rounded px-2 py-1"
        @click="orders.fetchOrders(filterStrategy || undefined)"
      >
        {{ t('positions.refresh') }}
      </button>
    </div>
    <label class="text-xs text-fg-muted flex items-center gap-2">
      {{ t('orders.filterStrategy') }}
      <select
        v-model="filterStrategy"
        class="rounded border border-border bg-surface px-2 py-1 text-xs text-fg"
        @change="orders.fetchOrders(filterStrategy || undefined)"
      >
        <option value="">{{ t('terminal.all') }}</option>
        <option v-for="s in strategies.strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
    </label>
    <div class="rounded-xl border border-border overflow-hidden">
      <ResponsiveTable :loading="orders.loading" :empty="!filtered.length">
        <template #loading>{{ t('overview.loading') }}</template>
        <template #empty>{{ t('orders.empty') }}</template>
        <template #head>
          <th class="px-3 py-2 text-start">{{ t('strategies.name') }}</th>
          <th class="px-3 py-2 text-start">{{ t('data.coin') }}</th>
          <th class="px-3 py-2 text-start">{{ t('orders.side') }}</th>
          <th class="px-3 py-2 text-start">{{ t('orders.status') }}</th>
          <th class="px-3 py-2 text-end">{{ t('positions.size') }}</th>
          <th class="px-3 py-2 text-end">{{ t('orders.time') }}</th>
        </template>
        <template #row>
          <tr
            v-for="o in filtered"
            :key="o.id"
            class="border-t border-border/50 hover:bg-surface-raised cursor-pointer"
            @click="goStrategy(o.strategy)"
          >
            <td class="px-3 py-2 text-fg">{{ strategyName(o.strategy) }}</td>
            <td class="px-3 py-2 text-fg-muted">{{ o.symbol }}</td>
            <td class="px-3 py-2 text-fg-muted">{{ o.side }}</td>
            <td class="px-3 py-2 text-fg-muted">{{ o.status }}</td>
            <td class="px-3 py-2 text-end text-fg-muted">{{ o.size }}</td>
            <td class="px-3 py-2 text-end text-fg-muted text-xs">{{ formatTime(o.created_at) }}</td>
          </tr>
        </template>
        <template #card>
          <div
            v-for="o in filtered"
            :key="o.id"
            class="rounded-lg border border-border bg-surface-raised p-3 space-y-1.5 cursor-pointer"
            @click="goStrategy(o.strategy)"
          >
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium text-fg">{{ strategyName(o.strategy) }}</span>
              <span class="text-xs text-fg-muted">{{ o.symbol }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-fg-muted">{{ t('orders.side') }}</span>
              <span class="text-fg">{{ o.side }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-fg-muted">{{ t('orders.status') }}</span>
              <span class="text-fg">{{ o.status }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-fg-muted">{{ t('positions.size') }}</span>
              <span class="text-fg">{{ o.size }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-fg-muted">{{ t('orders.time') }}</span>
              <span class="text-fg-muted">{{ formatTime(o.created_at) }}</span>
            </div>
          </div>
        </template>
      </ResponsiveTable>
    </div>
  </div>
</template>
